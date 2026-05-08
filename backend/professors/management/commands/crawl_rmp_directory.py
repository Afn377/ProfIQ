"""Crawl RMP directory metadata into the local DB."""
from __future__ import annotations

import json
import logging
import signal
import sys
from dataclasses import asdict
from pathlib import Path
from time import monotonic

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from professors.models import Department, Professor
from scrapers.rmp import RMPClient, RMPSchool, US_STATE_CODES

logger = logging.getLogger(__name__)

CHECKPOINT_PATH = Path(settings.BASE_DIR) / "data" / "rmp_crawl_checkpoint.json"


class Command(BaseCommand):
    help = "Bulk-crawl the RateMyProfessors US directory into the local DB."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--schools-limit", type=int, default=5,
            help="Max number of US schools to process (default 5).",
        )
        parser.add_argument(
            "--per-school-limit", type=int, default=None,
            help=(
                "Max number of teachers to pull per school "
                "(default: all teachers)."
            ),
        )
        parser.add_argument(
            "--min-ratings", type=int, default=0,
            help=(
                "Skip teachers with fewer than this many RMP ratings "
                "(default 0 — keep everyone)."
            ),
        )
        parser.add_argument(
            "--throttle", type=float, default=1.0,
            help="Seconds between GraphQL requests (default 1.0).",
        )
        parser.add_argument(
            "--resume", action="store_true",
            help=(
                "Resume from the last checkpoint instead of starting fresh."
            ),
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch but do not write to the DB.",
        )
        parser.add_argument(
            "--state", action="append", default=None,
            help=(
                "Optional 2-letter state code filter (can be passed "
                "multiple times). Defaults to all US states."
            ),
        )

    # ------------------------------------------------------------------ main

    def handle(self, *args, **opts) -> None:
        schools_limit: int = opts["schools_limit"]
        per_school_limit = opts["per_school_limit"]
        min_ratings: int = opts["min_ratings"]
        throttle: float = opts["throttle"]
        resume: bool = opts["resume"]
        dry_run: bool = opts["dry_run"]
        state_filter = (
            {s.upper() for s in opts["state"]} if opts["state"] else US_STATE_CODES
        )
        if not state_filter.issubset(US_STATE_CODES):
            unknown = state_filter - US_STATE_CODES
            raise CommandError(f"Unknown state codes: {sorted(unknown)}")

        ckpt = _load_checkpoint() if resume else _fresh_checkpoint()
        seen_school_ids: set[str] = set(ckpt.get("done_schools", []))

        client = RMPClient(throttle_seconds=throttle)

        self._install_signal_handlers(ckpt)

        self.stdout.write(
            f"Crawling RMP directory — schools_limit={schools_limit} "
            f"min_ratings={min_ratings} throttle={throttle}s "
            f"{'(resuming)' if resume else '(fresh)'}"
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: no DB writes"))

        total_profs = ckpt.get("total_profs", 0)
        schools_processed = 0
        start = monotonic()

        try:
            for school in client.iter_schools(us_only=True):
                if school.gid in seen_school_ids:
                    continue
                if school.state.upper() not in state_filter:
                    continue
                if schools_processed >= schools_limit:
                    break

                schools_processed += 1
                new_profs = self._crawl_school(
                    client, school,
                    per_school_limit=per_school_limit,
                    min_ratings=min_ratings,
                    dry_run=dry_run,
                )
                total_profs += new_profs
                seen_school_ids.add(school.gid)
                ckpt["done_schools"] = sorted(seen_school_ids)
                ckpt["total_profs"] = total_profs
                _save_checkpoint(ckpt)

                elapsed = monotonic() - start
                self.stdout.write(
                    f"  [{schools_processed}/{schools_limit}] "
                    f"{school.name} ({school.state}) → "
                    f"{new_profs} new profs · total={total_profs} · "
                    f"elapsed={elapsed:.0f}s"
                )
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nInterrupted — checkpoint saved."))
            sys.exit(130)

        self.stdout.write(self.style.SUCCESS(
            f"Done. Processed {schools_processed} schools, "
            f"{total_profs} professors total."
        ))

    # ---------------------------------------------------------------- helpers

    def _crawl_school(
        self,
        client: RMPClient,
        school: RMPSchool,
        per_school_limit: int | None,
        min_ratings: int,
        dry_run: bool,
    ) -> int:
        """Page through all teachers at ``school`` and upsert them."""
        new_profs = 0
        dept_cache: dict[str, Department] = {}

        for t in client.iter_teachers_all(
            school.gid, page_size=1000, max_teachers=per_school_limit,
        ):
            full_name = t.full_name
            if not full_name:
                continue
            if t.num_ratings < min_ratings:
                continue
            if dry_run:
                new_profs += 1
                continue

            dept = None
            dept_name = t.department.strip()
            if dept_name:
                dept = dept_cache.get(dept_name.casefold())
                if dept is None:
                    dept, _ = Department.objects.get_or_create(name=dept_name)
                    dept_cache[dept_name.casefold()] = dept

            external_ref = f"rmp:{t.legacy_id}" if t.legacy_id else ""
            defaults = {
                "department": dept,
                "institution": school.name,
                "external_ref": external_ref,
                "source_avg_rating": t.avg_rating,
                "source_num_ratings": t.num_ratings,
            }

            # Prefer dedup-by-external_ref when available (most reliable)
            # then fall back to (name, institution) uniqueness.
            try:
                with transaction.atomic():
                    if external_ref:
                        obj, created = Professor.objects.update_or_create(
                            external_ref=external_ref, defaults={
                                "name": full_name, **defaults,
                            },
                        )
                    else:
                        obj, created = Professor.objects.update_or_create(
                            name=full_name, institution=school.name,
                            defaults=defaults,
                        )
                if created:
                    new_profs += 1
            except Exception as exc:
                # Name+institution collision between two different RMP IDs —
                # log and skip. This is rare but possible (two "John Smith"s
                # at the same school).
                logger.warning(
                    "Skipped %s @ %s: %s", full_name, school.name, exc,
                )

        return new_profs

    def _install_signal_handlers(self, ckpt: dict) -> None:
        """Save checkpoint on SIGTERM so we can resume cleanly."""
        def _on_term(signum, frame):  # noqa: ARG001
            _save_checkpoint(ckpt)
            self.stdout.write(self.style.WARNING(
                "\nReceived SIGTERM — checkpoint saved."
            ))
            sys.exit(143)
        signal.signal(signal.SIGTERM, _on_term)


# ---------------------------------------------------------------------------
# Checkpoint helpers


def _fresh_checkpoint() -> dict:
    return {"done_schools": [], "total_profs": 0}


def _load_checkpoint() -> dict:
    if not CHECKPOINT_PATH.exists():
        return _fresh_checkpoint()
    try:
        return json.loads(CHECKPOINT_PATH.read_text())
    except json.JSONDecodeError:
        return _fresh_checkpoint()


def _save_checkpoint(ckpt: dict) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(ckpt, indent=2))
