"""Shared scraper dataclasses and JSON helpers."""
from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import Any, Iterable


@dataclasses.dataclass
class ScrapedProfessor:
    name: str
    institution: str = ""
    department: str = ""
    bio: str = ""
    courses: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ScrapedReview:
    professor: str            # must match ScrapedProfessor.name
    source: str               # "RateMyProfessors" | "Reddit"
    text: str
    source_url: str = ""
    rating: float | None = None
    course: str = ""
    posted_at: str | None = None  # ISO-8601 string or None


def to_seed_format(
    professors: Iterable[ScrapedProfessor],
    reviews: Iterable[ScrapedReview],
) -> dict[str, Any]:
    """Collapse scraped rows into the JSON shape ingest_seed expects."""
    prof_map: dict[str, dict] = {}
    for p in professors:
        prof_map[p.name] = {
            "name": p.name,
            "institution": p.institution,
            "department": p.department,
            "bio": p.bio,
            "courses": list(dict.fromkeys(p.courses)),
            "reviews": [],
        }

    source_names: set[str] = set()
    dept_names: set[str] = set()
    course_codes: dict[str, dict] = {}

    for r in reviews:
        prof = prof_map.get(r.professor)
        if prof is None:
            # Drop reviews without a matching professor row.
            continue
        source_names.add(r.source)
        if prof.get("department"):
            dept_names.add(prof["department"])
        if r.course:
            course_codes.setdefault(r.course, {
                "code": r.course,
                "title": "",
                "department": prof.get("department", ""),
            })
            if r.course not in prof["courses"]:
                prof["courses"].append(r.course)
        prof["reviews"].append({
            "source": r.source,
            "course": r.course or None,
            "text": r.text,
            "rating": r.rating,
            "source_url": r.source_url,
            "posted_at": r.posted_at,
        })

    return {
        "sources": [
            {"name": name, "base_url": _source_base_url(name)}
            for name in sorted(source_names)
        ],
        "departments": [
            {"name": d, "code": ""} for d in sorted(dept_names)
        ],
        "courses": list(course_codes.values()),
        "professors": list(prof_map.values()),
    }


def _source_base_url(name: str) -> str:
    return {
        "RateMyProfessors": "https://www.ratemyprofessors.com",
        "Reddit": "https://www.reddit.com",
    }.get(name, "")


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


class Throttle:
    """Simple request delay helper."""

    def __init__(self, seconds: float) -> None:
        self._seconds = seconds
        self._last = 0.0

    def wait(self) -> None:
        now = time.time()
        delta = now - self._last
        if delta < self._seconds:
            time.sleep(self._seconds - delta)
        self._last = time.time()
