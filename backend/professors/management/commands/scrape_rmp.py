"""Scrape RateMyProfessors reviews into seed-format JSON."""
from django.core.management.base import BaseCommand, CommandError

from scrapers.base import to_seed_format
from scrapers.rmp import scrape_rmp

from ._scrape_helpers import dump_and_maybe_ingest, timestamped_output


class Command(BaseCommand):
    help = "Scrape RateMyProfessors for a school / set of professors."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True,
                            help="School name to search (e.g. 'Stanford University').")
        parser.add_argument("--names", nargs="*", default=None,
                            help="Optional list of professor names to target.")
        parser.add_argument("--max-teachers", type=int, default=10,
                            help="If --names is omitted, take up to this many.")
        parser.add_argument("--reviews-per", type=int, default=30,
                            help="Maximum reviews to fetch per professor.")
        parser.add_argument("--throttle", type=float, default=1.0,
                            help="Seconds between GraphQL requests.")
        parser.add_argument("--out", default=None,
                            help="Optional explicit output JSON path.")
        parser.add_argument("--ingest", action="store_true",
                            help="After scraping, load the JSON via ingest_seed.")

    def handle(self, *args, **opts):
        try:
            profs, reviews = scrape_rmp(
                school_name=opts["school"],
                teacher_names=opts["names"],
                max_teachers=opts["max_teachers"],
                max_reviews_per_teacher=opts["reviews_per"],
                throttle_seconds=opts["throttle"],
            )
        except Exception as exc:
            raise CommandError(f"RMP scrape failed: {exc}") from exc

        if not profs:
            self.stderr.write(self.style.WARNING(
                "No professors matched — nothing to write."
            ))
            return

        payload = to_seed_format(profs, reviews)
        out_path = opts["out"] or timestamped_output("rmp")
        dump_and_maybe_ingest(self, payload, out_path, ingest=opts["ingest"])
