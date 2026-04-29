"""Embed every professor in the local DB who has stats, into the live index file."""
from django.core.management.base import BaseCommand

from professors.models import Professor
from scrapers.rmp import teacher_gid_from_legacy
from professors.views import _rmp_client


class Command(BaseCommand):
    help = "Fetch reviews for analyzed professors and add them to the embedding index."

    def add_arguments(self, parser):
        parser.add_argument("--max-reviews", type=int, default=40)
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **opts):
        import numpy as np
        from sentiment.ml import recommender as r
        qs = Professor.objects.filter(external_ref__startswith="rmp:", stats__isnull=False).order_by("-source_num_ratings")
        if opts["limit"]:
            qs = qs[: opts["limit"]]
        added = 0
        for prof in qs:
            if r.is_indexed(prof.external_ref):
                continue
            legacy = int(prof.external_ref.split(":")[1])
            texts = [(x.get("comment") or "").strip() for x in _rmp_client.iter_ratings(teacher_gid_from_legacy(legacy), max_reviews=opts["max_reviews"])]
            texts = [t for t in texts if t]
            if r.add_professor(prof.external_ref, f"{prof.name} @ {prof.institution}", texts):
                added += 1
                self.stdout.write(f"  + {prof.name} ({len(texts)} reviews)")
        ids, names, vecs, _ = r._load()
        np.savez_compressed(r.EMB_PATH, ids=ids, names=names, vecs=vecs)
        self.stdout.write(self.style.SUCCESS(f"added {added}, index now {len(ids)} professors, saved"))
