"""Crawl one school's professor directory from RateMyProfessors into the DB."""
import json
import signal
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from professors.models import Department, Professor
from scrapers.rmp import RMPClient

CHECKPOINT = Path(settings.BASE_DIR) / "data" / "rmp_crawl_checkpoint.json"


class Command(BaseCommand):
    help = "Crawl a school's professors from RateMyProfessors into the local DB."

    def add_arguments(self, parser):
        parser.add_argument("school", help="School name as RMP knows it, e.g. 'Rutgers'")
        parser.add_argument("--limit", type=int, default=None, help="Max teachers to pull")
        parser.add_argument("--min-ratings", type=int, default=0)
        parser.add_argument("--throttle", type=float, default=1.0)
        parser.add_argument("--resume", action="store_true", help="Continue from the last checkpoint")

    def handle(self, *args, **opts):
        client = RMPClient(throttle_seconds=opts["throttle"])
        school_id = client.find_school_id(opts["school"])
        if not school_id:
            raise CommandError(f"No RMP school matches {opts['school']!r}")

        ckpt = self._load_checkpoint() if opts["resume"] else {}
        start_cursor = ckpt.get("cursor") if ckpt.get("school_id") == school_id else None
        seen = ckpt.get("seen", 0) if start_cursor else 0
        if start_cursor:
            self.stdout.write(f"Resuming after {seen} teachers")

        state = {"school_id": school_id, "cursor": start_cursor, "seen": seen}

        # Save on SIGTERM (what `kill` and Cloud Run send) so nothing is lost.
        def on_term(signum, frame):
            self._save_checkpoint(state)
            self.stdout.write(self.style.WARNING("\nSIGTERM: checkpoint saved"))
            sys.exit(143)
        signal.signal(signal.SIGTERM, on_term)

        def on_page(next_cursor):
            state["cursor"] = next_cursor
            state["seen"] = seen_box[0]
            self._save_checkpoint(state)

        seen_box = [seen]
        created = 0
        try:
            for t in client.iter_teachers(
                school_id, max_teachers=opts["limit"], start_cursor=start_cursor, on_page=on_page,
            ):
                seen_box[0] += 1
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
                if seen_box[0] % 100 == 0:
                    self.stdout.write(f"  {seen_box[0]} seen, {created} new", ending="\n")
                    self.stdout.flush()
        except KeyboardInterrupt:
            self._save_checkpoint(state)
            self.stdout.write(self.style.WARNING("\nInterrupted: checkpoint saved"))
            sys.exit(130)

        self.stdout.write(self.style.SUCCESS(f"Done: {seen_box[0]} teachers seen, {created} new professors"))

    @staticmethod
    def _load_checkpoint() -> dict:
        if not CHECKPOINT.exists():
            return {}
        try:
            return json.loads(CHECKPOINT.read_text())
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _save_checkpoint(state: dict) -> None:
        CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
        CHECKPOINT.write_text(json.dumps(state, indent=2))
