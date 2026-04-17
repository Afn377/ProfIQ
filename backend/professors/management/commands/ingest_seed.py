"""Load the demo seed file: professors, reviews, sentiment, and stats."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from professors.models import Course, Department, Professor, ProfessorStats, Review, SentimentResult, Source
from sentiment.analyzer import aggregate_stats, analyze_text

SEED = Path(settings.BASE_DIR) / "data" / "seed_reviews.json"


class Command(BaseCommand):
    help = "Load data/seed_reviews.json into the DB and compute stats."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing seed rows first")

    @transaction.atomic
    def handle(self, *args, **opts):
        data = json.loads(SEED.read_text())
        source, _ = Source.objects.get_or_create(name=data["source"]["name"], defaults={"base_url": data["source"]["base_url"]})

        if opts["reset"]:
            Professor.objects.filter(external_ref="", reviews__source=source).distinct().delete()

        for p in data["professors"]:
            dept, _ = Department.objects.get_or_create(name=p["department"])
            prof, _ = Professor.objects.get_or_create(
                name=p["name"], institution=p["institution"], defaults={"department": dept},
            )
            sentiments = []
            for r in p["reviews"]:
                course, _ = Course.objects.get_or_create(code=r["course"])
                course.professors.add(prof)
                review, created = Review.objects.get_or_create(
                    professor=prof, source=source, text=r["text"],
                    defaults={"rating": r["rating"], "course": course},
                )
                s = analyze_text(r["text"], rating=r["rating"])
                sentiments.append(s)
                if created:
                    SentimentResult.objects.create(
                        review=review, compound=s["compound"], positive=s["positive"],
                        neutral=s["neutral"], negative=s["negative"], label=s["label"], themes=s["themes"],
                    )
            ProfessorStats.objects.update_or_create(professor=prof, defaults=aggregate_stats(sentiments))
            self.stdout.write(f"  {prof.name}: {len(sentiments)} reviews")

        self.stdout.write(self.style.SUCCESS("Seed loaded"))
