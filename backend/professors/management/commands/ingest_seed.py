"""Load seed reviews and rebuild local stats."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from professors.models import (
    Source, Department, Professor, Course, Review, SentimentResult, ProfessorStats,
)
from sentiment.analyzer import analyze_text, aggregate_stats


class Command(BaseCommand):
    help = "Ingest seed reviews, run sentiment analysis, and compute aggregate stats."

    def add_arguments(self, parser):
        parser.add_argument("--path", type=str, default=None,
                            help="Path to JSON seed file.")
        parser.add_argument("--reset", action="store_true",
                            help="Delete existing data before ingest.")

    def handle(self, *args, **opts):
        path = opts["path"]
        if path is None:
            path = Path(__file__).resolve().parents[3] / "data" / "seed_reviews.json"
        path = Path(path)
        if not path.exists():
            self.stderr.write(self.style.ERROR(f"Seed file not found: {path}"))
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        with transaction.atomic():
            if opts["reset"]:
                self.stdout.write("Resetting existing data…")
                SentimentResult.objects.all().delete()
                ProfessorStats.objects.all().delete()
                Review.objects.all().delete()
                Course.objects.all().delete()
                Professor.objects.all().delete()
                Department.objects.all().delete()
                Source.objects.all().delete()

            self._load(data)

        self.stdout.write(self.style.SUCCESS("Ingestion complete."))

    def _load(self, data: dict) -> None:
        # Sources
        sources = {}
        for s in data.get("sources", []):
            obj, _ = Source.objects.get_or_create(
                name=s["name"], defaults={"base_url": s.get("base_url", "")}
            )
            sources[s["name"]] = obj

        # Departments
        depts = {}
        for d in data.get("departments", []):
            obj, _ = Department.objects.get_or_create(
                name=d["name"], defaults={"code": d.get("code", "")}
            )
            depts[d["name"]] = obj

        # Courses
        courses = {}
        for c in data.get("courses", []):
            obj, _ = Course.objects.get_or_create(
                code=c["code"],
                defaults={
                    "title": c.get("title", ""),
                    "department": depts.get(c.get("department")),
                },
            )
            courses[c["code"]] = obj

        # Professors, reviews, and sentiment
        created_profs = 0
        created_reviews = 0
        for p in data.get("professors", []):
            prof, is_new = Professor.objects.get_or_create(
                name=p["name"],
                institution=p.get("institution", ""),
                defaults={
                    "department": depts.get(p.get("department")),
                    "bio": p.get("bio", ""),
                },
            )
            if is_new:
                created_profs += 1

            for code in p.get("courses", []):
                if code in courses:
                    prof.courses.add(courses[code])

            for r in p.get("reviews", []):
                src = sources.get(r["source"])
                if not src:
                    continue
                review, created = Review.objects.get_or_create(
                    professor=prof,
                    source=src,
                    text=r["text"],
                    defaults={
                        "rating": r.get("rating"),
                        "course": courses.get(r.get("course")) if r.get("course") else None,
                        "source_url": r.get("source_url", ""),
                    },
                )
                if created:
                    created_reviews += 1
                # Run (or refresh) sentiment analysis. Pass through the
                # seeded star rating so it blends with the text compound.
                scores = analyze_text(review.text, rating=review.rating)
                SentimentResult.objects.update_or_create(
                    review=review,
                    defaults={
                        "compound": scores["compound"],
                        "positive": scores["positive"],
                        "neutral": scores["neutral"],
                        "negative": scores["negative"],
                        "label": scores["label"],
                        "themes": scores["themes"],
                    },
                )

        self.stdout.write(f"  professors created: {created_profs}")
        self.stdout.write(f"  reviews created: {created_reviews}")

        self._recompute_stats()

    def _recompute_stats(self) -> None:
        """Aggregate per-professor analytics into ProfessorStats rows."""
        self.stdout.write("Recomputing aggregate stats…")
        for prof in Professor.objects.all().prefetch_related("reviews__sentiment"):
            sentiments = []
            for review in prof.reviews.all():
                sent = getattr(review, "sentiment", None)
                if sent is None:
                    continue
                sentiments.append({
                    "compound": sent.compound,
                    "label": sent.label,
                    "themes": sent.themes or [],
                })
            agg = aggregate_stats(sentiments)
            ProfessorStats.objects.update_or_create(
                professor=prof, defaults=agg,
            )
        self.stdout.write(self.style.SUCCESS(f"Stats updated for {Professor.objects.count()} professors."))
