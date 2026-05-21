"""Build the saved similar-professor embedding index."""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Build per-professor MiniLM embeddings used by the similar-prof recommender."

    def add_arguments(self, parser):
        parser.add_argument("--corpus", default="data/ml/corpus.parquet")
        parser.add_argument("--out", default="data/ml/prof_embeddings.npz")
        parser.add_argument("--meta-out", default="data/ml/prof_embeddings_meta.parquet")
        parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
        parser.add_argument("--batch", type=int, default=64)
        parser.add_argument("--max-chars", type=int, default=4000)
        parser.add_argument("--min-reviews", type=int, default=3)

    def handle(self, *args, **opts):
        from sentiment.ml.build_embeddings import main as build_main

        argv = [
            "--corpus", opts["corpus"],
            "--out", opts["out"],
            "--meta-out", opts["meta_out"],
            "--model", opts["model"],
            "--batch", str(opts["batch"]),
            "--max-chars", str(opts["max_chars"]),
            "--min-reviews", str(opts["min_reviews"]),
        ]
        rc = build_main(argv)
        if rc != 0:
            self.stderr.write(self.style.ERROR(f"build_embeddings exited with {rc}"))
            raise SystemExit(rc)
        # Reload the recommender index after rebuilding it.
        try:
            from sentiment.ml import recommender
            recommender.reset()
        except Exception:
            pass
        self.stdout.write(self.style.SUCCESS(f"Embeddings written to {opts['out']}"))
