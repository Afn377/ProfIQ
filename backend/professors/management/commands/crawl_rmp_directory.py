"""Crawl one school's professor directory from RateMyProfessors into the DB."""
from django.core.management.base import BaseCommand, CommandError

from professors.models import Department, Professor
from scrapers.rmp import RMPClient


class Command(BaseCommand):
    help = "Crawl a school's professors from RateMyProfessors into the local DB."

    def add_arguments(self, parser):
        parser.add_argument("school", help="School name as RMP knows it, e.g. 'Rutgers'")
        parser.add_argument("--limit", type=int, default=None, help="Max teachers to pull")
        parser.add_argument("--min-ratings", type=int, default=0)
        parser.add_argument("--throttle", type=float, default=1.0)

    def handle(self, *args, **opts):
        client = RMPClient(throttle_seconds=opts["throttle"])
        school_id = client.find_school_id(opts["school"])
        if not school_id:
            raise CommandError(f"No RMP school matches {opts['school']!r}")

        # Naive: no checkpoint, no per-row transaction. Just loop and upsert.
        created = 0
        seen = 0
        for t in client.iter_teachers(school_id, max_teachers=opts["limit"]):
            seen += 1
            if not t["name"] or t["num_ratings"] < opts["min_ratings"]:
                continue
            dept = None
            if t["department"]:
                dept, _ = Department.objects.get_or_create(name=t["department"])
            _, was_created = Professor.objects.update_or_create(
                external_ref=f"rmp:{t['legacy_id']}",
                defaults={
                    "name": t["name"],
                    "institution": t["school"],
                    "department": dept,
                    "source_avg_rating": t["avg_rating"],
                    "source_num_ratings": t["num_ratings"],
                },
            )
            created += was_created
            if seen % 25 == 0:
                self.stdout.write(f"  {seen} seen, {created} new")

        self.stdout.write(self.style.SUCCESS(f"Done: {seen} teachers seen, {created} new professors"))
