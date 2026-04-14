"""Scrape Reddit mentions into seed-format JSON."""
from django.core.management.base import BaseCommand, CommandError

from scrapers.base import ScrapedProfessor, to_seed_format
from scrapers.reddit import scrape_reddit

from ._scrape_helpers import dump_and_maybe_ingest, timestamped_output


class Command(BaseCommand):
    help = "Scrape Reddit submissions and comments that mention professors."

    def add_arguments(self, parser):
        parser.add_argument("--names", nargs="+", required=True,
                            help="Professor names to search for.")
        parser.add_argument("--institution", default="",
                            help="Institution to attach to the scraped professors.")
        parser.add_argument("--department", default="",
                            help="Department name to attach.")
        parser.add_argument("--subreddits", nargs="+", required=True,
                            help="Subreddits (without the r/ prefix).")
        parser.add_argument("--limit", type=int, default=25,
                            help="Results per (subreddit, professor) query.")
        parser.add_argument("--no-comments", action="store_true",
                            help="Skip comment scraping (only titles + selftext).")
        parser.add_argument("--max-comments", type=int, default=60,
                            help="Maximum comments to keep per post.")
        parser.add_argument("--throttle", type=float, default=1.5,
                            help="Seconds between HTTP requests in fallback mode.")
        parser.add_argument("--out", default=None)
        parser.add_argument("--ingest", action="store_true")

    def handle(self, *args, **opts):
        profs = [
            ScrapedProfessor(
                name=n,
                institution=opts["institution"],
                department=opts["department"],
            )
            for n in opts["names"]
        ]
        try:
            reviews = scrape_reddit(
                professors=profs,
                subreddits=opts["subreddits"],
                per_query_limit=opts["limit"],
                include_comments=not opts["no_comments"],
                max_comments_per_post=opts["max_comments"],
                throttle_seconds=opts["throttle"],
            )
        except Exception as exc:
            raise CommandError(f"Reddit scrape failed: {exc}") from exc

        self.stdout.write(f"Collected {len(reviews)} Reddit reviews.")

        payload = to_seed_format(profs, reviews)
        out_path = opts["out"] or timestamped_output("reddit")
        dump_and_maybe_ingest(self, payload, out_path, ingest=opts["ingest"])
