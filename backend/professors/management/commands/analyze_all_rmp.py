"""Build ProfessorStats rows from RMP review pages."""
from __future__ import annotations

import json
import logging
import signal
import sys
from pathlib import Path
from time import monotonic

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from professors.models import Professor, ProfessorStats
from scrapers.rmp import RMPClient, teacher_gid_from_legacy, _quality_rating
from sentiment.analyzer import aggregate_stats, analyze_text

logger = logging.getLogger(__name__)

CHECKPOINT_PATH = Path(settings.BASE_DIR) / "data" / "rmp_analyze_checkpoint.json"


class Command(BaseCommand):
    help = (
        "Compute sentiment/themes/score per professor from RMP reviews "
        "and store ONLY ProfessorStats. No review text is persisted."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--min-ratings", type=int, default=3,
            help=(
                "Skip professors with fewer than this many RMP ratings "
                "(default 3)."
            ),
        )
        parser.add_argument(
            "--max-reviews-per-prof", type=int, default=150,
            help=(
                "Maximum reviews to fetch per professor (default 150). "
                "Caps runtime for RMP celebrities with 1000+ ratings."
            ),
        )
        parser.add_argument(
            "--throttle", type=float, default=1.0,
            help="Seconds between GraphQL requests (default 1.0).",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Max number of professors to analyze in this run.",
        )
        parser.add_argument(
            "--reset", action="store_true",
            help=(
                "Re-analyze professors even if they already have a "
                "ProfessorStats row. Ignored checkpoints."
            ),
        )
        parser.add_argument(
            "--resume", action="store_true",
            help="Resume from the checkpoint file.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Fetch + analyze but do not write ProfessorStats.",
        )

    # ------------------------------------------------------------------ main

    def handle(self, *args, **opts) -> None:
        min_ratings: int = opts["min_ratings"]
        max_reviews: int = opts["max_reviews_per_prof"]
        throttle: float = opts["throttle"]
        limit = opts["limit"]
        reset: bool = opts["reset"]
        resume: bool = opts["resume"]
        dry_run: bool = opts["dry_run"]

        ckpt = _load_checkpoint() if resume else _fresh_checkpoint()
        done_ids: set[int] = set(ckpt.get("done_prof_ids", []))

        qs = (
            Professor.objects
            .filter(external_ref__startswith="rmp:",
                    source_num_ratings__gte=min_ratings)
            .order_by("-source_num_ratings")
        )
        if not reset:
            qs = qs.filter(stats__isnull=True)
        if done_ids:
            qs = qs.exclude(id__in=done_ids)

        total_to_process = qs.count()
        if limit:
            total_to_process = min(total_to_process, limit)

        self.stdout.write(
            f"Analyzing {total_to_process} professors "
            f"(min_ratings={min_ratings}, max_reviews={max_reviews}, "
            f"throttle={throttle}s) "
            f"{'[RESET]' if reset else ''}"
            f"{'[RESUME]' if resume else ''}"
            f"{'[DRY-RUN]' if dry_run else ''}"
        )

        if total_to_process == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        client = RMPClient(throttle_seconds=throttle)
        self._install_signal_handlers(ckpt)

        processed = 0
        written = 0
        start = monotonic()

        try:
            for prof in qs.iterator(chunk_size=200):
                if limit and processed >= limit:
                    break
                processed += 1

                ratings_analyzed, stats_dict = self._analyze_one(
                    client, prof, max_reviews=max_reviews,
                )
                if stats_dict is None:
                    # Nothing usable (no comments) — still mark as done so
                    # we don't retry endlessly.
                    done_ids.add(prof.id)
                    ckpt["done_prof_ids"] = sorted(done_ids)
                    _save_checkpoint(ckpt)
                    continue

                if not dry_run:
                    with transaction.atomic():
                        ProfessorStats.objects.update_or_create(
                            professor=prof,
                            defaults=stats_dict,
                        )
                    written += 1

                done_ids.add(prof.id)
                ckpt["done_prof_ids"] = sorted(done_ids)
                ckpt["written"] = written
                _save_checkpoint(ckpt)

                if processed % 25 == 0 or processed <= 5:
                    elapsed = monotonic() - start
                    rate = processed / max(elapsed, 0.01)
                    eta = (total_to_process - processed) / max(rate, 0.001)
                    self.stdout.write(
                        f"  [{processed}/{total_to_process}] "
                        f"{prof.name[:30]:30s} · "
                        f"{ratings_analyzed} reviews · "
                        f"score={stats_dict['recommendation_score']:.1f} · "
                        f"rate={rate:.2f}/s · eta={eta/60:.1f}m"
                    )
        except KeyboardInterrupt:
            _save_checkpoint(ckpt)
            self.stdout.write(self.style.WARNING(
                f"\nInterrupted after {processed} profs — checkpoint saved."
            ))
            sys.exit(130)

        elapsed = monotonic() - start
        self.stdout.write(self.style.SUCCESS(
            f"Done. Processed {processed} profs "
            f"({written} ProfessorStats rows written) in {elapsed/60:.1f}m."
        ))

    # ---------------------------------------------------------------- helpers

    def _analyze_one(
        self,
        client: RMPClient,
        prof: Professor,
        max_reviews: int,
    ) -> tuple[int, dict | None]:
        """Fetch and analyze one professor's reviews."""
        legacy_id = _legacy_id_from_ref(prof.external_ref)
        if legacy_id is None:
            return 0, None

        gid = teacher_gid_from_legacy(legacy_id)
        sentiments: list[dict] = []
        ratings_seen = 0
        try:
            for rating in client.iter_ratings(gid, page_size=20, max_reviews=max_reviews):
                ratings_seen += 1
                comment = (rating.get("comment") or "").strip()
                if not comment:
                    continue
                sentiments.append(analyze_text(comment, rating=_quality_rating(rating)))
        except Exception as exc:
            logger.warning(
                "RMP fetch failed for %s (rmp:%s): %s",
                prof.name, legacy_id, exc,
            )
            if not sentiments:
                return 0, None
            # Keep partial results when available.

        if not sentiments:
            return ratings_seen, None
        return len(sentiments), aggregate_stats(sentiments)

    def _install_signal_handlers(self, ckpt: dict) -> None:
        def _on_term(signum, frame):  # noqa: ARG001
            _save_checkpoint(ckpt)
            self.stdout.write(self.style.WARNING(
                "\nReceived SIGTERM — checkpoint saved."
            ))
            sys.exit(143)
        signal.signal(signal.SIGTERM, _on_term)


def _legacy_id_from_ref(external_ref: str) -> int | None:
    """Extract the legacy ID from ``"rmp:<legacy_id>"`` refs."""
    if not external_ref.startswith("rmp:"):
        return None
    try:
        # Use the first numeric chunk.
        parts = external_ref.split(":")
        return int(parts[1])
    except (IndexError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Checkpoint helpers


def _fresh_checkpoint() -> dict:
    return {"done_prof_ids": [], "written": 0}


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
