"""Run configured RMP and Reddit scrapes."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from scrapers.base import ScrapedProfessor, to_seed_format
from scrapers.reddit import scrape_reddit
from scrapers.rmp import scrape_rmp

from ._scrape_helpers import dump_and_maybe_ingest, timestamped_output


class Command(BaseCommand):
    help = "Run RMP + Reddit scrapers from a JSON config."

    def add_arguments(self, parser):
        parser.add_argument("--config", required=True,
                            help="Path to scrape targets JSON.")
        parser.add_argument("--skip-rmp", action="store_true")
        parser.add_argument("--skip-reddit", action="store_true")
        parser.add_argument("--out", default=None)
        parser.add_argument("--ingest", action="store_true")

    def handle(self, *args, **opts):
        cfg_path = Path(opts["config"])
        if not cfg_path.exists():
            raise CommandError(f"Config not found: {cfg_path}")
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

        profs: list[ScrapedProfessor] = []
        reviews = []

        if not opts["skip_rmp"]:
            rmp_cfg = cfg.get("rmp") or {}
            if "school" not in rmp_cfg:
                self.stderr.write(self.style.WARNING(
                    "rmp.school missing — skipping RMP scrape."
                ))
            else:
                self.stdout.write(f"[RMP] scraping {rmp_cfg['school']}…")
                r_profs, r_reviews = scrape_rmp(
                    school_name=rmp_cfg["school"],
                    teacher_names=rmp_cfg.get("teacher_names"),
                    max_teachers=rmp_cfg.get("max_teachers", 10),
                    max_reviews_per_teacher=rmp_cfg.get("reviews_per_teacher", 30),
                )
                self.stdout.write(
                    f"[RMP] got {len(r_profs)} professors · {len(r_reviews)} reviews"
                )
                profs.extend(r_profs)
                reviews.extend(r_reviews)

        if not opts["skip_reddit"]:
            rd_cfg = cfg.get("reddit") or {}
            if not profs:
                self.stderr.write(self.style.WARNING(
                    "No professors known yet — Reddit scrape needs names."
                    " Populate rmp.teacher_names or run scrape_rmp first."
                ))
            elif not rd_cfg.get("subreddits"):
                self.stderr.write(self.style.WARNING(
                    "reddit.subreddits missing — skipping Reddit scrape."
                ))
            else:
                self.stdout.write(
                    f"[Reddit] searching {rd_cfg['subreddits']} for "
                    f"{len(profs)} professors…"
                )
                rd_reviews = scrape_reddit(
                    professors=profs,
                    subreddits=rd_cfg["subreddits"],
                    per_query_limit=rd_cfg.get("per_query_limit", 25),
                    include_comments=rd_cfg.get("include_comments", True),
                    max_comments_per_post=rd_cfg.get("max_comments_per_post", 60),
                )
                self.stdout.write(f"[Reddit] got {len(rd_reviews)} mentions")
                reviews.extend(rd_reviews)

        if not profs:
            self.stderr.write(self.style.WARNING("Nothing scraped — aborting."))
            return

        payload = to_seed_format(profs, reviews)
        out_path = opts["out"] or timestamped_output("scrape_all")
        dump_and_maybe_ingest(self, payload, out_path, ingest=opts["ingest"])
