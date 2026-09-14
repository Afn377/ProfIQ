"""Detect already-crawled RMP schools whose professors are missing locally."""
from __future__ import annotations

import json
import logging
import signal
import sys
from pathlib import Path
from time import monotonic

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count

from professors.models import Professor
from scrapers.rmp import RMPClient, RMPSchool, US_STATE_CODES

logger = logging.getLogger(__name__)

CRAWL_CHECKPOINT_PATH = Path(settings.BASE_DIR) / "data" / "rmp_crawl_checkpoint.json"
CHECKPOINT_PATH = Path(settings.BASE_DIR) / "data" / "rmp_gap_scan_checkpoint.json"


class Command(BaseCommand):
    help = (
        "Scan RMP schools already marked done in the crawl checkpoint and "
        "flag those missing professors locally (post-incident gap detection)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--resume", action="store_true",
            help=(
                "Resume from the gap-scan checkpoint instead of starting "
                "fresh."
            ),
        )
        parser.add_argument(
            "--throttle", type=float, default=1.0,
            help="Seconds between GraphQL requests (default 1.0).",
        )
        parser.add_argument(
            "--apply", action="store_true",
            help=(
                "After the scan, remove gap gids from the crawl checkpoint's "
                "done_schools list so they get re-crawled."
            ),
        )

    # ------------------------------------------------------------------ main

    def handle(self, *args, **opts) -> None:
        resume: bool = opts["resume"]
        throttle: float = opts["throttle"]
        apply_gaps: bool = opts["apply"]

        target_gids = _load_target_gids()
        ckpt = _load_checkpoint() if resume else _fresh_checkpoint()
        done_gids: set[str] = set(ckpt.get("done_gids", []))
        gap_gids: set[str] = set(ckpt.get("gap_gids", []))

        local_counts = _local_institution_counts()

        client = RMPClient(throttle_seconds=throttle)

        self._install_signal_handlers(ckpt)

        self.stdout.write(
            f"Scanning RMP directory for gaps — "
            f"target={len(target_gids)} already-done schools, "
            f"throttle={throttle}s "
            f"{'(resuming)' if resume else '(fresh)'}"
        )

        # Cumulative scan count; on resume it continues where we left off.
        scanned = ckpt.get("scanned", 0)
        target_total = len(target_gids)
        missing_by_gid: dict[str, int] = {}
        start = monotonic()

        try:
            for school in client.iter_schools(us_only=True):
                if school.gid not in target_gids:
                    continue
                if school.gid in done_gids:
                    continue

                live_count = client.get_teacher_count(school.gid)
                local_count = local_counts.get(school.name, 0)
                scanned += 1

                if local_count < live_count - max(2, round(0.05 * live_count)):
                    if local_count == 0 and live_count > 0:
                        self.stdout.write(self.style.WARNING(
                            "  school %s (%s) has 0 local professors despite "
                            "being marked done — possible institution-name "
                            "mismatch, will still be re-crawled"
                            % (school.name, school.gid)
                        ))
                    gap_gids.add(school.gid)
                    missing_by_gid[school.gid] = live_count - local_count

                done_gids.add(school.gid)
                ckpt["done_gids"] = sorted(done_gids)
                ckpt["gap_gids"] = sorted(gap_gids)
                ckpt["scanned"] = scanned
                ckpt["flagged"] = len(gap_gids)
                _save_checkpoint(ckpt)

                elapsed = monotonic() - start
                self.stdout.write(
                    f"  [{scanned}/{target_total}] "
                    f"{school.name} ({school.state}) → "
                    f"live={live_count} local={local_count} · "
                    f"gaps={len(gap_gids)} · elapsed={elapsed:.0f}s"
                )
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nInterrupted — checkpoint saved."))
            self._print_summary(scanned, gap_gids, missing_by_gid)
            sys.exit(130)

        self._print_summary(scanned, gap_gids, missing_by_gid)

        if apply_gaps:
            self._apply_gaps(gap_gids, target_total, scanned)

    # ---------------------------------------------------------------- helpers

    def _print_summary(
        self,
        scanned: int,
        gap_gids: set[str],
        missing_by_gid: dict[str, int],
    ) -> None:
        estimated_missing = sum(missing_by_gid.values())
        self.stdout.write(self.style.SUCCESS(
            f"Scan summary: scanned={scanned} schools · "
            f"gaps={len(gap_gids)} · "
            f"professors estimated missing={estimated_missing}."
        ))

    def _apply_gaps(
        self,
        gap_gids: set[str],
        target_total: int,
        scanned: int,
    ) -> None:
        """Remove flagged gids from the crawl checkpoint's done_schools."""
        crawl = _load_crawl_checkpoint()
        before = list(crawl.get("done_schools", []))
        remaining = [gid for gid in before if gid not in gap_gids]
        removed = len(before) - len(remaining)
        crawl["done_schools"] = remaining
        _save_crawl_checkpoint(crawl)

        unscanned = max(0, target_total - scanned)
        self.stdout.write(self.style.SUCCESS(
            f"--apply: removed {removed} gid(s) from "
            f"{CRAWL_CHECKPOINT_PATH.name} (done_schools "
            f"{len(before)} → {len(remaining)}); "
            f"{unscanned} target school(s) still unscanned."
        ))

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
    return {"done_gids": [], "gap_gids": [], "scanned": 0, "flagged": 0}


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


def _load_crawl_checkpoint() -> dict:
    if not CRAWL_CHECKPOINT_PATH.exists():
        return {"done_schools": [], "total_profs": 0}
    try:
        return json.loads(CRAWL_CHECKPOINT_PATH.read_text())
    except json.JSONDecodeError:
        return {"done_schools": [], "total_profs": 0}


def _save_crawl_checkpoint(ckpt: dict) -> None:
    CRAWL_CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CRAWL_CHECKPOINT_PATH.write_text(json.dumps(ckpt, indent=2))


def _load_target_gids() -> set[str]:
    """School gids already marked done in the crawl checkpoint."""
    return set(_load_crawl_checkpoint().get("done_schools", []))


def _local_institution_counts() -> dict[str, int]:
    """Local professor count per institution name in one query."""
    return dict(
        Professor.objects.values_list("institution")
        .annotate(n=Count("id"))
        .values_list("institution", "n")
    )
