"""Read-only checks for likely placeholder professor records."""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db.models import QuerySet

from professors.canary_data import (
    KNOWN_FICTIONAL,
    KNOWN_JOKES,
    normalise_name,
)
from professors.models import Professor

logger = logging.getLogger(__name__)

OPENALEX_AUTHORS_URL = "https://api.openalex.org/authors"
OPENALEX_INSTITUTIONS_URL = "https://api.openalex.org/institutions"
OPENALEX_TIMEOUT = 10.0
OPENALEX_PER_PAGE = 5

# Fuzzy threshold for institution name matching.
INSTITUTION_NAME_FUZZY_THRESHOLD = 0.55

# Strip noisy prefixes before OpenAlex search.
_INSTITUTION_PREFIX_NOISE = re.compile(r"^(the)\s+", re.IGNORECASE)

# Parenthetical text added to some RMP institution names.
# ("(all campuses)", "(all)", "(main campus)") and that OpenAlex chokes on.
_INSTITUTION_PAREN_NOISE = re.compile(r"\s*\([^)]*\)\s*$")

# Curly quotes / em-dashes confuse the search tokenizer; flatten them.
_TRANSLITERATION_TABLE = str.maketrans({
    "\u2019": "'",
    "\u2018": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "&": "and",
})


def _normalise_institution_query(name: str) -> str:
    """Clean an institution name for OpenAlex search."""
    cleaned = name.translate(_TRANSLITERATION_TABLE)
    cleaned = _INSTITUTION_PAREN_NOISE.sub("", cleaned)
    cleaned = _INSTITUTION_PREFIX_NOISE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

# Fuzzy institution-match threshold.
INSTITUTION_FUZZY_THRESHOLD = 0.65

# Cheap RMP-brand anagram detector.
_RMP_ANAGRAM_KEY = "".join(sorted("ratemyprofessors"))


def _is_rmp_anagram(normalised: str) -> bool:
    if not normalised:
        return False
    letters_only = "".join(c for c in normalised if c.isalpha())
    if len(letters_only) != len(_RMP_ANAGRAM_KEY):
        return False
    return "".join(sorted(letters_only)) == _RMP_ANAGRAM_KEY


def _looks_palindromic(normalised: str) -> bool:
    """Return True for long palindromic names."""
    letters_only = "".join(c for c in normalised if c.isalpha())
    if len(letters_only) < 6:
        return False
    return letters_only == letters_only[::-1]


def _fuzzy(a: str, b: str) -> float:
    return SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


class Command(BaseCommand):
    help = "Scan the Professor table for likely RMP canary records (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--layers", default="l1,l2,l3",
            help="Comma-separated list of layers to run. Choices: l1, l2, l3.",
        )
        parser.add_argument(
            "--sample-size", type=int, default=500,
            help="Random professors to query OpenAlex for in Layer 2.",
        )
        parser.add_argument(
            "--l3-min-prof-count", type=int, default=1,
            help="Layer 3: only check institutions with at least this many "
                 "professors. Set higher to skip long-tail single-prof entries.",
        )
        parser.add_argument(
            "--l3-max-institutions", type=int, default=None,
            help="Layer 3: cap how many distinct institutions to check (for "
                 "dev runs). Default: all of them.",
        )
        parser.add_argument(
            "--openalex-mailto", default=None,
            help="Email for the OpenAlex polite-pool User-Agent header. "
                 "Recommended; OpenAlex throttles less aggressively when set.",
        )
        parser.add_argument(
            "--output-dir", default=".",
            help="Directory for canary_report.{json,md}. Created if missing.",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Cap rows scanned in Layer 1 (for dev runs). Layer 2 still "
                 "samples from the full table unless this is also smaller.",
        )
        parser.add_argument(
            "--rate", type=float, default=8.0,
            help="Max OpenAlex requests per second. Polite pool allows 10/s.",
        )

    def handle(self, *args, **opts):
        layers = {x.strip().casefold() for x in opts["layers"].split(",") if x.strip()}
        unknown = layers - {"l1", "l2", "l3"}
        if unknown:
            raise CommandError(f"Unknown layer(s): {sorted(unknown)}")
        if not layers:
            raise CommandError("No layers requested.")

        out_dir = Path(opts["output_dir"]).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        report = {
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "layers_requested": sorted(layers),
            "config": {
                "limit": opts["limit"],
                "sample_size": opts["sample_size"],
                "rate": opts["rate"],
                "openalex_mailto_set": bool(opts["openalex_mailto"]),
                "fuzzy_threshold": INSTITUTION_FUZZY_THRESHOLD,
            },
            "findings": {},
        }

        if "l1" in layers:
            self.stdout.write(self.style.MIGRATE_HEADING("Layer 1: pattern blacklist"))
            t0 = time.monotonic()
            report["findings"]["l1"] = self._run_layer1(opts["limit"])
            report["findings"]["l1"]["duration_seconds"] = round(time.monotonic() - t0, 2)
            self.stdout.write(self.style.SUCCESS(
                f"  scanned={report['findings']['l1']['scanned']:,} "
                f"flagged={len(report['findings']['l1']['flagged'])} "
                f"in {report['findings']['l1']['duration_seconds']}s"
            ))

        if "l2" in layers:
            self.stdout.write(self.style.MIGRATE_HEADING("Layer 2: OpenAlex orphan sample"))
            t0 = time.monotonic()
            report["findings"]["l2"] = self._run_layer2(
                opts["sample_size"],
                opts["openalex_mailto"],
                opts["rate"],
            )
            report["findings"]["l2"]["duration_seconds"] = round(time.monotonic() - t0, 2)
            self.stdout.write(self.style.SUCCESS(
                f"  sampled={report['findings']['l2']['sampled']} "
                f"flagged={len(report['findings']['l2']['flagged'])} "
                f"in {report['findings']['l2']['duration_seconds']}s"
            ))

        if "l3" in layers:
            self.stdout.write(self.style.MIGRATE_HEADING("Layer 3: fake-institution check"))
            t0 = time.monotonic()
            report["findings"]["l3"] = self._run_layer3(
                opts["openalex_mailto"],
                opts["rate"],
                opts["l3_min_prof_count"],
                opts["l3_max_institutions"],
            )
            report["findings"]["l3"]["duration_seconds"] = round(time.monotonic() - t0, 2)
            self.stdout.write(self.style.SUCCESS(
                f"  checked={report['findings']['l3']['checked']} "
                f"flagged_institutions={len(report['findings']['l3']['flagged'])} "
                f"affected_professors={report['findings']['l3']['affected_professors']} "
                f"in {report['findings']['l3']['duration_seconds']}s"
            ))

        json_path = out_dir / "canary_report.json"
        md_path = out_dir / "canary_report.md"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        md_path.write_text(self._render_markdown(report))

        self.stdout.write(self.style.SUCCESS(
            f"\nWrote {json_path}\nWrote {md_path}"
        ))

    # ------------------------------------------------------------------ L1

