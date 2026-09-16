"""Verify + backfill ``external_ref`` for unlinked ``Professor`` rows via RMP.

The DB contains many ``Professor`` rows whose ``external_ref`` is empty — they
were created from seed/other sources and never linked to a RateMyProfessors
profile. This command walks every such row, grouped by ``institution`` (so the
school lookup is done once per institution rather than once per professor),
searches RMP for the professor by name at that school, and — on a single
confident fuzzy name match — updates the existing row with the RMP legacy id
and profile stats.

Nothing is ever created or deleted: only existing rows are updated in place.
"""
from __future__ import annotations

import json
import logging
import signal
import sys
from pathlib import Path
from time import monotonic

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from professors.models import Department, Professor
from scrapers.rmp import RMPClient, RMPTeacher

logger = logging.getLogger(__name__)

CHECKPOINT_PATH = (
    Path(settings.BASE_DIR) / "data" / "verify_unlinked_checkpoint.json"
)

# How often to emit a running-tally progress line (in professors processed).
PROGRESS_EVERY = 25


class Command(BaseCommand):
    help = (
        "Verify and backfill Professor rows with an empty external_ref by "
        "searching RateMyProfessors for each one by name at its institution."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--throttle", type=float, default=1.0,
            help="Seconds between GraphQL requests (default 1.0).",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help=(
                "Max number of professors to process in this run "
                "(default: all unlinked professors)."
            ),
        )
        parser.add_argument(
            "--resume", action="store_true",
            help="Resume from the checkpoint file.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help=(
                "Search RMP and report the matches that would be written, "
                "but do not touch the DB."
            ),
        )

    # ------------------------------------------------------------------ main

    def handle(self, *args, **opts) -> None:
        throttle: float = opts["throttle"]
        limit = opts["limit"]
        resume: bool = opts["resume"]
        dry_run: bool = opts["dry_run"]

        ckpt = _load_checkpoint() if resume else _fresh_checkpoint()
        done_ids: set[int] = set(ckpt.get("done_ids", []))
        done_order: list[int] = list(ckpt.get("done_ids", []))
        school_id_cache: dict[str, str | None] = {
            str(k): v for k, v in (ckpt.get("school_id_cache") or {}).items()
        }

        matched = ckpt.get("matched_count", 0)
        unmatched = ckpt.get("unmatched_count", 0)
        no_school = ckpt.get("no_school_count", 0)
        skipped = ckpt.get("skipped_conflict_count", 0)

        # Remaining work for this run. We deliberately filter ``done_ids`` in
        # Python instead of an ``id__in=...`` clause: a resumed run can carry
        # tens of thousands of processed IDs and a single huge IN list would
        # bump into SQLite's bound-parameter limit.
        target_ids = list(
            Professor.objects
            .filter(external_ref="")
            .values_list("id", flat=True)
        )
        remaining = sum(1 for pid in target_ids if pid not in done_ids)
        if limit is None:
            total_to_process = remaining
        else:
            total_to_process = min(remaining, max(limit, 0))

        self.stdout.write(
            f"Verifying unlinked professors — to_process={total_to_process} "
            f"(remaining={remaining}) throttle={throttle}s "
            f"[{'RESUME' if resume else 'FRESH'}]"
            f"{'[DRY-RUN]' if dry_run else ''}"
        )
        if total_to_process <= 0:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        institutions = list(
            Professor.objects
            .filter(external_ref="")
            .values_list("institution", flat=True)
            .distinct()
            .order_by("institution")
        )

        client = RMPClient(throttle_seconds=throttle)
        self._install_signal_handlers(ckpt)

        processed = 0
        dept_cache: dict[str, Department] = {}
        start = monotonic()

        try:
            for institution in institutions:
                if limit is not None and processed >= limit:
                    break

                profs = [
                    p for p in Professor.objects
                    .filter(external_ref="", institution=institution)
                    .order_by("id")
                    if p.id not in done_ids
                ]
                if not profs:
                    continue

                # Resolve the RMP school once per institution and cache it so
                # a resumed run never re-resolves (even an institution whose
                # lookups already came back empty).
                if institution in school_id_cache:
                    school_id = school_id_cache[institution]
                else:
                    school_id = (
                        client.find_school_id(institution)
                        if institution.strip() else None
                    )
                    school_id_cache[institution] = school_id
                    ckpt["school_id_cache"] = school_id_cache
                    _save_checkpoint(ckpt)

                if not school_id:
                    # RMP has no school for this institution at all. That's a
                    # useful signal in itself — record it and never retry.
                    for prof in profs:
                        if limit is not None and processed >= limit:
                            break
                        done_ids.add(prof.id)
                        done_order.append(prof.id)
                        no_school += 1
                        processed += 1
                    ckpt["done_ids"] = done_order
                    ckpt["no_school_count"] = no_school
                    _save_checkpoint(ckpt)
                    self.stdout.write(
                        f"  -- {institution or '(blank institution)'} → "
                        f"NO RMP SCHOOL · {no_school} no_school_match"
                    )
                    self._report(
                        institution, processed, total_to_process, matched,
                        unmatched, no_school, skipped, start,
                    )
                    continue

                self.stdout.write(
                    f"  -- {institution} → school_id={school_id} "
                    f"({len(profs)} unlinked profs)"
                )

                for prof in profs:
                    if limit is not None and processed >= limit:
                        break
                    processed += 1

                    name = (prof.name or "").strip()
                    if not name:
                        # Nothing to search for — record and move on.
                        unmatched += 1
                        done_ids.add(prof.id)
                        done_order.append(prof.id)
                        self._save_progress(
                            ckpt, done_order, matched, unmatched, no_school,
                            skipped,
                        )
                        continue

                    try:
                        candidates = client.search_teachers(
                            school_id, text=prof.name, limit=5,
                        )
                    except Exception as exc:
                        # Transient RMP failure — do NOT mark done so a later
                        # resume retries this professor.
                        logger.warning(
                            "RMP search failed for %s @ %s: %s",
                            prof.name, institution, exc,
                        )
                        continue

                    matches = [
                        t for t in candidates if _name_matches(prof.name, t)
                    ]
                    if len(matches) != 1 or not matches[0].legacy_id:
                        # Zero matches, ambiguous (multiple) matches, or a
                        # match without a usable legacy id — never guess.
                        unmatched += 1
                        done_ids.add(prof.id)
                        done_order.append(prof.id)
                        self._save_progress(
                            ckpt, done_order, matched, unmatched, no_school,
                            skipped,
                        )
                    else:
                        linked = self._link(
                            prof, matches[0], dept_cache, dry_run,
                        )
                        if linked:
                            matched += 1
                        else:
                            skipped += 1
                        done_ids.add(prof.id)
                        done_order.append(prof.id)
                        self._save_progress(
                            ckpt, done_order, matched, unmatched, no_school,
                            skipped,
                        )

                    if processed % PROGRESS_EVERY == 0:
                        self._report(
                            institution, processed, total_to_process, matched,
                            unmatched, no_school, skipped, start,
                        )
        except KeyboardInterrupt:
            _save_checkpoint(ckpt)
            self.stdout.write(self.style.WARNING(
                f"\nInterrupted after {processed} profs — checkpoint saved."
            ))
            sys.exit(130)

        elapsed = monotonic() - start
        self.stdout.write(self.style.SUCCESS(
            f"Done. processed={processed} this run · matched={matched} · "
            f"unmatched={unmatched} · no_school_match={no_school} · "
            f"skipped_conflict={skipped} · elapsed={elapsed/60:.1f}m"
        ))

    # --------------------------------------------------------------- helpers

    def _link(
        self,
        prof: Professor,
        teacher: RMPTeacher,
        dept_cache: dict[str, Department],
        dry_run: bool,
    ) -> bool:
        """Link ``prof`` to ``teacher`` in place.

        Returns True when the row was (or, in dry-run mode, would be) updated,
        and False when the write collided with another row's ``external_ref``.
        """
        external_ref = f"rmp:{teacher.legacy_id}"
        dept_name = (teacher.department or "").strip()

        dept = None
        if dept_name and prof.department_id is None and not dry_run:
            dept = dept_cache.get(dept_name.casefold())
            if dept is None:
                dept, _ = Department.objects.get_or_create(name=dept_name)
                dept_cache[dept_name.casefold()] = dept

        if dry_run:
            self.stdout.write(
                f"     WOULD link {prof.name} @ {prof.institution} → "
                f"{external_ref} ({teacher.full_name}, "
                f"dept={dept_name or '-'}, avg={teacher.avg_rating}, "
                f"n={teacher.num_ratings})"
            )
            return True

        try:
            with transaction.atomic():
                prof.external_ref = external_ref
                prof.source_avg_rating = teacher.avg_rating
                prof.source_num_ratings = teacher.num_ratings
                fields = [
                    "external_ref", "source_avg_rating",
                    "source_num_ratings",
                ]
                if dept is not None:
                    prof.department = dept
                    fields.append("department")
                prof.save(update_fields=fields)
        except IntegrityError as exc:
            # The matched legacy id already belongs to a different professor
            # row — a duplicate-profile edge case. Log and move on.
            logger.warning(
                "Skipped %s @ %s → %s: %s",
                prof.name, prof.institution, external_ref, exc,
            )
            return False
        return True

    def _save_progress(
        self,
        ckpt: dict,
        done_order: list[int],
        matched: int,
        unmatched: int,
        no_school: int,
        skipped: int,
    ) -> None:
        ckpt["done_ids"] = done_order
        ckpt["matched_count"] = matched
        ckpt["unmatched_count"] = unmatched
        ckpt["no_school_count"] = no_school
        ckpt["skipped_conflict_count"] = skipped
        _save_checkpoint(ckpt)

    def _report(
        self,
        label: str,
        processed: int,
        total_to_process: int,
        matched: int,
        unmatched: int,
        no_school: int,
        skipped: int,
        start: float,
    ) -> None:
        elapsed = monotonic() - start
        rate = processed / max(elapsed, 0.01)
        eta = max(0, total_to_process - processed) / max(rate, 0.001)
        self.stdout.write(
            f"  [{processed}/{total_to_process}] {label[:34]:34s} · "
            f"matched={matched} unmatched={unmatched} "
            f"no_school_match={no_school} skipped_conflict={skipped} · "
            f"rate={rate:.2f}/s · eta={eta/60:.1f}m"
        )

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
# Matching


def _name_matches(name: str, teacher: RMPTeacher) -> bool:
    """Mirror ``scrapers.rmp.scrape_rmp``'s fuzzy name-match check.

    A candidate counts as a match only when one casefolded name contains the
    other. Empty names never match (an empty string is a substring of
    everything).
    """
    hay = (teacher.full_name or "").casefold()
    needle = (name or "").casefold()
    if not hay or not needle:
        return False
    return needle in hay or hay in needle


# ---------------------------------------------------------------------------
# Checkpoint helpers


def _fresh_checkpoint() -> dict:
    return {
        "done_ids": [],
        "matched_count": 0,
        "unmatched_count": 0,
        "no_school_count": 0,
        "skipped_conflict_count": 0,
        "school_id_cache": {},
    }


def _load_checkpoint() -> dict:
    if not CHECKPOINT_PATH.exists():
        return _fresh_checkpoint()
    try:
        return json.loads(CHECKPOINT_PATH.read_text())
    except json.JSONDecodeError:
        return _fresh_checkpoint()


def _save_checkpoint(ckpt: dict) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(ckpt))
