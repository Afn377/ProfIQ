"""Compute sentiment stats for every crawled professor. Stores only ProfessorStats."""
import json
import sys
from pathlib import Path
from time import monotonic

from django.conf import settings
from django.core.management.base import BaseCommand

from professors.models import Professor, ProfessorStats
from scrapers.rmp import RMPClient, teacher_gid_from_legacy
from sentiment.analyzer import aggregate_stats, analyze_text

CHECKPOINT = Path(settings.BASE_DIR) / "data" / "rmp_analyze_checkpoint.json"


def _quality_rating(rating: dict) -> float | None:
    """RMP has no single 1-5 rating; average helpful and clarity."""
    vals = [v for v in (rating.get("helpfulRating"), rating.get("clarityRating")) if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else None


class Command(BaseCommand):
    help = "Fetch each professor's reviews, run sentiment, store ProfessorStats. No review text is kept."

    def add_arguments(self, parser):
        parser.add_argument("--min-ratings", type=int, default=3)
        parser.add_argument("--max-reviews", type=int, default=150, help="Cap per professor")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--throttle", type=float, default=1.0)
        parser.add_argument("--resume", action="store_true")

    def handle(self, *args, **opts):
        ckpt = self._load() if opts["resume"] else {"done": []}
        done_ids = set(ckpt["done"])

        qs = (
            Professor.objects
            .filter(external_ref__startswith="rmp:", source_num_ratings__gte=opts["min_ratings"], stats__isnull=True)
            .exclude(id__in=done_ids)          # naive resume
            .order_by("-source_num_ratings")
        )
        if opts["limit"]:
            qs = qs[: opts["limit"]]
        total = qs.count()
        self.stdout.write(f"Analyzing {total} professors (max {opts['max_reviews']} reviews each)")

        client = RMPClient(throttle_seconds=opts["throttle"])
        start = monotonic()
        written = 0
        for i, prof in enumerate(qs.iterator(chunk_size=100), 1):
            legacy_id = int(prof.external_ref.split(":")[1])
            sentiments = []
            try:
                for r in client.iter_ratings(teacher_gid_from_legacy(legacy_id), max_reviews=opts["max_reviews"]):
                    comment = (r.get("comment") or "").strip()
                    if comment:
                        sentiments.append(analyze_text(comment, rating=_quality_rating(r)))
            except Exception as exc:
                self.stderr.write(f"  {prof.name}: fetch failed ({exc}); skipping")
            if sentiments:
                ProfessorStats.objects.update_or_create(professor=prof, defaults=aggregate_stats(sentiments))
                written += 1
            done_ids.add(prof.id)
            ckpt["done"] = sorted(done_ids)
            self._save(ckpt)
            if i % 10 == 0 or i <= 3:
                rate = i / max(monotonic() - start, 0.01)
                self.stdout.write(f"  [{i}/{total}] {prof.name[:28]:28s} {len(sentiments):3d} reviews  "
                                  f"score={aggregate_stats(sentiments)['recommendation_score']:5.1f}  "
                                  f"eta={(total - i) / max(rate, 0.001) / 60:.1f}m")
                self.stdout.flush()

        self.stdout.write(self.style.SUCCESS(f"Done: {written} stats rows written"))

    @staticmethod
    def _load():
        try:
            return json.loads(CHECKPOINT.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {"done": []}

    @staticmethod
    def _save(ckpt):
        CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        CHECKPOINT.write_text(json.dumps(ckpt))
