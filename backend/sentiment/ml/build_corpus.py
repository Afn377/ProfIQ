"""Build the review corpus used by ML training scripts."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Allow running as a plain script from the backend/ dir
_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "recommender.settings")
django.setup()

import pandas as pd
from django.db.models import Count

from professors.models import Professor
from scrapers.rmp import RMPClient, teacher_gid_from_legacy

logger = logging.getLogger("build_corpus")


@dataclass(frozen=True)
class TargetProf:
    legacy_id: int
    name: str
    institution: str
    department: str
    source_num_ratings: int

    @property
    def gid(self) -> str:
        return teacher_gid_from_legacy(self.legacy_id)


def select_targets(
    schools: int,
    profs_per_school: int,
) -> list[TargetProf]:
    """Pick high-review professors from the largest schools.

    Only includes profs with ``external_ref`` matching ``rmp:<id>`` (so we
    can derive the GraphQL teacher gid) and ``source_num_ratings >= 5``
    (otherwise the rating page returns very little).
    """
    top_schools = (
        Professor.objects
        .filter(external_ref__startswith="rmp:", source_num_ratings__gte=5)
        .values("institution")
        .annotate(n=Count("id"))
        .order_by("-n")[:schools]
    )

    targets: list[TargetProf] = []
    for row in top_schools:
        inst = row["institution"]
        qs = (
            Professor.objects
            .filter(
                institution=inst,
                external_ref__startswith="rmp:",
                source_num_ratings__gte=5,
            )
            .order_by("-source_num_ratings")[:profs_per_school]
            .values(
                "external_ref", "name", "institution",
                "department__name", "source_num_ratings",
            )
        )
        for p in qs:
            ref = p["external_ref"]
            try:
                legacy = int(ref.split(":", 1)[1])
            except (ValueError, IndexError):
                continue
            targets.append(TargetProf(
                legacy_id=legacy,
                name=p["name"],
                institution=p["institution"],
                department=p["department__name"] or "",
                source_num_ratings=p["source_num_ratings"],
            ))
    return targets


def _quality_rating(rating: dict) -> float | None:
    """Average helpful + clarity to a 1-5 score (RMP doesn't expose a single overall)."""
    helpful = rating.get("helpfulRating")
    clarity = rating.get("clarityRating")
    vals = [v for v in (helpful, clarity) if isinstance(v, (int, float))]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def fetch_one(
    client: RMPClient,
    target: TargetProf,
    reviews_per_prof: int,
) -> list[dict]:
    rows: list[dict] = []
    try:
        for r in client.iter_ratings(target.gid, max_reviews=reviews_per_prof):
            text = (r.get("comment") or "").strip()
            if not text:
                continue
            rating = _quality_rating(r)
            if rating is None:
                continue
            rows.append({
                "professor_id_external": f"rmp:{target.legacy_id}",
                "professor_name": target.name,
                "institution": target.institution,
                "department": target.department,
                "course": (r.get("class") or "").strip(),
                "text": text,
                "rating": rating,
                "would_take_again": r.get("wouldTakeAgain"),
                "difficulty": r.get("difficultyRating"),
                "posted_at": r.get("date") or "",
                "source_url": (
                    f"https://www.ratemyprofessors.com/professor/"
                    f"{target.legacy_id}#rating-{r.get('legacyId')}"
                ),
            })
    except Exception as exc:
        logger.warning("scrape failed for %s (%s): %s",
                       target.name, target.legacy_id, exc)
    return rows


