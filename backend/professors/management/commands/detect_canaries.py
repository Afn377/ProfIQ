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

    def _run_layer1(self, limit: int | None) -> dict:
        qs: QuerySet = Professor.objects.values(
            "id", "name", "institution", "external_ref",
        )
        if limit:
            qs = qs[:limit]
            scanned_total = limit
        else:
            scanned_total = Professor.objects.count()

        flagged: list[dict] = []
        scanned = 0
        for p in qs.iterator(chunk_size=5000):
            scanned += 1
            norm = normalise_name(p["name"])
            if not norm:
                continue
            reasons: list[str] = []
            if norm in KNOWN_FICTIONAL:
                reasons.append("fictional_character")
            if norm in KNOWN_JOKES:
                reasons.append("joke_name")
            if _is_rmp_anagram(norm):
                reasons.append("rmp_anagram")
            if _looks_palindromic(norm):
                reasons.append("palindrome")
            if reasons:
                flagged.append({
                    "id": p["id"],
                    "name": p["name"],
                    "institution": p["institution"],
                    "external_ref": p["external_ref"],
                    "reasons": reasons,
                })
            if scanned % 250_000 == 0:
                self.stdout.write(f"  ... {scanned:,} scanned, {len(flagged)} flagged so far")

        return {"scanned": scanned, "flagged": flagged}

    # ------------------------------------------------------------------ L2

    def _run_layer2(
        self,
        n: int,
        mailto: str | None,
        rate_per_sec: float,
    ) -> dict:
        if n <= 0:
            return {"sampled": 0, "flagged": [], "queried": 0, "errors": 0}

        # Sample size is small enough for SQLite random ordering.
        pool = list(
            Professor.objects.exclude(name="").order_by("?")
            [:n]
            .values("id", "name", "institution")
        )

        ua = "profiq-canary-audit/0.1"
        if mailto:
            ua = f"{ua} (mailto:{mailto})"
        session = requests.Session()
        session.headers["User-Agent"] = ua

        sleep_between = 1.0 / max(rate_per_sec, 0.5)
        flagged: list[dict] = []
        errors = 0
        queried = 0

        for idx, p in enumerate(pool, 1):
            try:
                hits = self._openalex_lookup(session, p["name"])
                queried += 1
            except Exception as exc:  # noqa: BLE001  - audit must continue
                errors += 1
                logger.warning("OpenAlex lookup failed for %s: %s", p["name"], exc)
                hits = None  # unknown, not a flag

            if hits is None:
                pass  # skip on error to avoid false flags
            elif not hits:
                flagged.append({
                    "id": p["id"],
                    "name": p["name"],
                    "institution": p["institution"],
                    "reason": "no_openalex_match",
                })
            else:
                if not self._institution_matches_any(p["institution"], hits):
                    flagged.append({
                        "id": p["id"],
                        "name": p["name"],
                        "institution": p["institution"],
                        "reason": "openalex_institution_mismatch",
                        "openalex_top_affiliations": [
                            h.get("affiliation", "") for h in hits[:3]
                        ],
                    })

            if idx % 50 == 0:
                self.stdout.write(
                    f"  ... {idx}/{len(pool)} queried, {len(flagged)} flagged, "
                    f"{errors} errors"
                )
            time.sleep(sleep_between)

        return {
            "sampled": len(pool),
            "queried": queried,
            "errors": errors,
            "flagged": flagged,
        }

    # ---------------------------------------------------------- layer 3

    def _run_layer3(
        self,
        mailto: str | None,
        rate_per_sec: float,
        min_prof_count: int,
        max_institutions: int | None,
    ) -> dict:
        from django.db.models import Count

        qs = (
            Professor.objects
            .exclude(institution="")
            .values("institution")
            .annotate(prof_count=Count("id"))
            .order_by("-prof_count")
        )
        if min_prof_count > 1:
            qs = qs.filter(prof_count__gte=min_prof_count)
        institutions = list(qs)
        if max_institutions:
            institutions = institutions[:max_institutions]

        if not institutions:
            return {
                "checked": 0,
                "queried": 0,
                "errors": 0,
                "affected_professors": 0,
                "flagged": [],
            }

        ua = "profiq-canary-audit/0.1"
        if mailto:
            ua = f"{ua} (mailto:{mailto})"
        session = requests.Session()
        session.headers["User-Agent"] = ua

        sleep_between = 1.0 / max(rate_per_sec, 0.5)
        cache: dict[str, list[dict]] = {}
        flagged: list[dict] = []
        errors = 0
        queried = 0

        for idx, row in enumerate(institutions, 1):
            name = row["institution"]
            count = row["prof_count"]
            cleaned = _normalise_institution_query(name) or name
            key = cleaned.casefold().strip()
            if key in cache:
                hits = cache[key]
            else:
                try:
                    hits = self._openalex_institution_lookup(session, cleaned)
                    cache[key] = hits
                    queried += 1
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    logger.warning(
                        "OpenAlex /institutions failed for %s: %s", cleaned, exc,
                    )
                    hits = None
                time.sleep(sleep_between)

            if hits is None:
                continue  # error → don't false-flag

            # Score the cleaned form against OpenAlex returns; using the raw
            # name would unfairly penalise legitimate schools whose RMP entry
            # has a "(all campuses)" tail.
            best_score, best_match = self._best_institution_match(cleaned, hits)
            if best_score < INSTITUTION_NAME_FUZZY_THRESHOLD:
                flagged.append({
                    "institution": name,
                    "cleaned_query": cleaned,
                    "professor_count": count,
                    "best_match_name": best_match,
                    "best_match_score": round(best_score, 3),
                    "openalex_top_names": [h.get("display_name", "") for h in hits[:3]],
                })

            if idx % 100 == 0:
                self.stdout.write(
                    f"  ... {idx}/{len(institutions)} institutions checked, "
                    f"{len(flagged)} flagged, {errors} errors"
                )

        affected = sum(f["professor_count"] for f in flagged)
        flagged.sort(key=lambda r: r["professor_count"], reverse=True)
        return {
            "checked": len(institutions),
            "queried": queried,
            "errors": errors,
            "affected_professors": affected,
            "flagged": flagged,
        }

    def _openalex_institution_lookup(
        self, session: requests.Session, name: str,
    ) -> list[dict]:
        """Return top OpenAlex institution matches."""
        params = {"search": name, "per-page": OPENALEX_PER_PAGE}
        url = (
            f"{OPENALEX_INSTITUTIONS_URL}?"
            + "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
        )
        resp = session.get(url, timeout=OPENALEX_TIMEOUT)
        if resp.status_code == 429:
            time.sleep(2.0)
            resp = session.get(url, timeout=OPENALEX_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        results = payload.get("results", []) or []
        out: list[dict] = []
        for r in results:
            out.append({
                "id": r.get("id", ""),
                "display_name": r.get("display_name", "") or "",
                "display_name_alternatives": r.get("display_name_alternatives") or [],
                "display_name_acronyms": r.get("display_name_acronyms") or [],
                "country_code": r.get("country_code") or "",
                "type": r.get("type") or "",
            })
        return out

    def _best_institution_match(
        self, query: str, hits: Iterable[dict],
    ) -> tuple[float, str]:
        """Return the best fuzzy institution match."""
        q_norm = query.casefold().strip()
        best = 0.0
        best_name = ""
        for h in hits:
            candidates: list[str] = []
            if h.get("display_name"):
                candidates.append(h["display_name"])
            candidates.extend(h.get("display_name_alternatives") or [])
            for ac in h.get("display_name_acronyms") or []:
                if ac and ac.casefold() == q_norm:
                    return 1.0, h.get("display_name", ac)
                candidates.append(ac)
            for cand in candidates:
                if not cand:
                    continue
                score = SequenceMatcher(None, q_norm, cand.casefold()).ratio()
                if score > best:
                    best = score
                    best_name = h.get("display_name", cand)
        return best, best_name

    def _openalex_lookup(self, session: requests.Session, name: str) -> list[dict]:
        """Return top OpenAlex author matches."""
        params = {
            "search": name,
            "per-page": OPENALEX_PER_PAGE,
        }
        url = f"{OPENALEX_AUTHORS_URL}?{'&'.join(f'{k}={quote_plus(str(v))}' for k, v in params.items())}"
        resp = session.get(url, timeout=OPENALEX_TIMEOUT)
        if resp.status_code == 429:
            time.sleep(2.0)
            resp = session.get(url, timeout=OPENALEX_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
        results = payload.get("results", []) or []
        out: list[dict] = []
        for r in results:
            affiliation = ""
            lkis = r.get("last_known_institutions") or []
            if lkis and isinstance(lkis, list):
                affiliation = (lkis[0] or {}).get("display_name", "") or ""
            elif r.get("last_known_institution"):
                affiliation = (r["last_known_institution"] or {}).get("display_name", "") or ""
            out.append({
                "id": r.get("id", ""),
                "display_name": r.get("display_name", ""),
                "affiliation": affiliation,
            })
        return out

    def _institution_matches_any(
        self, institution: str, hits: Iterable[dict],
    ) -> bool:
        if not institution:
            # No institution on file → can't say there's a mismatch.
            return True
        for h in hits:
            affil = h.get("affiliation") or ""
            if not affil:
                continue
            if _fuzzy(institution, affil) >= INSTITUTION_FUZZY_THRESHOLD:
                return True
            # Also try acronym/last-token comparisons for "BYU" vs
            # "Brigham Young University - Provo" style mismatches.
            inst_tokens = institution.split()
            affil_tokens = affil.split()
            if inst_tokens and affil_tokens:
                last_inst = inst_tokens[-1].casefold()
                if any(last_inst == t.casefold() for t in affil_tokens):
                    return True
        return False

    # ----------------------------------------------------------- markdown

    def _render_markdown(self, report: dict) -> str:
        lines = ["# Canary detection report", ""]
        lines.append(f"_scan_time:_ `{report['scan_time']}`")
        lines.append(f"_layers:_ `{', '.join(report['layers_requested'])}`")
        lines.append("")

        f = report["findings"]
        if "l1" in f:
            l1 = f["l1"]
            lines.append("## Layer 1 — pattern blacklist")
            lines.append("")
            lines.append(
                f"- scanned: **{l1['scanned']:,}** professors "
                f"in {l1['duration_seconds']}s"
            )
            lines.append(f"- flagged: **{len(l1['flagged'])}**")
            lines.append("")
            if l1["flagged"]:
                lines.append("| ID | Name | Institution | Reasons | external_ref |")
                lines.append("|---:|------|-------------|---------|--------------|")
                for row in l1["flagged"]:
                    lines.append(
                        f"| {row['id']} | {row['name']} | "
                        f"{row['institution'] or '-'} | "
                        f"{', '.join(row['reasons'])} | "
                        f"`{row['external_ref'] or '-'}` |"
                    )
            else:
                lines.append("_No pattern matches — none of the curated "
                             "fictional/joke/anagram/palindrome heuristics fired._")
            lines.append("")

        if "l2" in f:
            l2 = f["l2"]
            lines.append("## Layer 2 — OpenAlex orphan sample")
            lines.append("")
            lines.append(
                f"- sampled: **{l2['sampled']}**, queried: **{l2['queried']}**, "
                f"errors: **{l2['errors']}**, in {l2['duration_seconds']}s"
            )
            lines.append(f"- flagged: **{len(l2['flagged'])}**")
            lines.append("")
            if l2["flagged"]:
                lines.append("| ID | Name | Institution | Reason | OpenAlex top affiliations |")
                lines.append("|---:|------|-------------|--------|---------------------------|")
                for row in l2["flagged"]:
                    affs = row.get("openalex_top_affiliations") or []
                    aff_str = "; ".join(a for a in affs if a) or "-"
                    lines.append(
                        f"| {row['id']} | {row['name']} | "
                        f"{row['institution'] or '-'} | "
                        f"{row['reason']} | {aff_str} |"
                    )
            else:
                lines.append("_All sampled professors had at least one "
                             "plausible OpenAlex affiliation match._")
            lines.append("")

        if "l3" in f:
            l3 = f["l3"]
            lines.append("## Layer 3 — fake-institution check")
            lines.append("")
            lines.append(
                f"- checked: **{l3['checked']:,}** distinct institutions, "
                f"queried: **{l3['queried']:,}**, errors: **{l3['errors']}**, "
                f"in {l3['duration_seconds']}s"
            )
            lines.append(
                f"- flagged institutions: **{len(l3['flagged'])}**, "
                f"affected professors (collateral cleanup candidates): "
                f"**{l3['affected_professors']:,}**"
            )
            lines.append("")
            if l3["flagged"]:
                lines.append("Sorted by professor count — biggest fake institutions first.")
                lines.append("")
                lines.append("| Institution | Profs | Best OpenAlex match | Score | Top OpenAlex hits |")
                lines.append("|-------------|------:|---------------------|------:|-------------------|")
                for row in l3["flagged"]:
                    tops = row.get("openalex_top_names") or []
                    tops_str = "; ".join(t for t in tops if t) or "-"
                    lines.append(
                        f"| {row['institution']} | "
                        f"{row['professor_count']:,} | "
                        f"{row['best_match_name'] or '_(no hits)_'} | "
                        f"{row['best_match_score']:.2f} | "
                        f"{tops_str} |"
                    )
            else:
                lines.append("_Every checked institution had a plausible "
                             "OpenAlex match above the fuzzy threshold._")
            lines.append("")

        lines.append("---")
        lines.append(
            "Layer 1 catches obvious / legacy canaries only. Layer 2's flagged "
            "rows are *suspicious*, not confirmed — adjuncts, retired faculty, "
            "and lecturers who never published often look like orphans too. "
            "Layer 3 is much higher-confidence: a school with a real catalog "
            "of programs will be in OpenAlex's institutions index, so anything "
            "missing is either a fake-school canary, a typo, or an org so "
            "obscure (private training school, unlisted clinic) that pruning "
            "it costs little even if it's real."
        )
        lines.append("")
        return "\n".join(lines)
