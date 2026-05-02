"""Name lists used by canary checks."""
from __future__ import annotations

import json
import re
from importlib import resources
from typing import Iterable

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalise_name(name: str) -> str:
    """Normalize a name for set membership checks."""
    if not name:
        return ""
    s = _PUNCT_RE.sub(" ", name)
    s = _WS_RE.sub(" ", s)
    return s.strip().casefold()


def _flatten_categorised(payload: dict) -> Iterable[str]:
    for key, value in payload.items():
        if key.startswith("_"):
            continue
        if isinstance(value, list):
            yield from value


def _load(filename: str) -> frozenset[str]:
    with resources.files(__package__).joinpath(filename).open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return frozenset(
        normalise_name(n) for n in _flatten_categorised(payload) if n
    )


def _load_categories(filename: str, categories: Iterable[str]) -> frozenset[str]:
    """Like ``_load`` but only flattens the named categories."""
    with resources.files(__package__).joinpath(filename).open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    wanted = set(categories)
    out: list[str] = []
    for key, value in payload.items():
        if key in wanted and isinstance(value, list):
            out.extend(value)
    return frozenset(normalise_name(n) for n in out if n)


# High-confidence fictional-name categories.
_OBVIOUS_FICTIONAL_CATEGORIES = (
    "harry_potter",
    "lord_of_the_rings",
    "game_of_thrones",
    "star_wars",
    "anime_manga",
    "video_games",
)

# Broader list, including names that need manual review.
KNOWN_FICTIONAL: frozenset[str] = _load("fictional_characters.json")
OBVIOUS_FICTIONAL: frozenset[str] = _load_categories(
    "fictional_characters.json", _OBVIOUS_FICTIONAL_CATEGORIES,
)
BORDERLINE_FICTIONAL: frozenset[str] = KNOWN_FICTIONAL - OBVIOUS_FICTIONAL

KNOWN_JOKES: frozenset[str] = _load("joke_names.json")


# Known fictional institutions blocked from submissions.
FICTIONAL_INSTITUTIONS: tuple[str, ...] = (
    "Hogwarts School of Witchcraft & Wizardry",
    "Xavier's School for Gifted Youngsters",
    "Greendale Community College",
    "Starfleet Academy",
    "Bayside High School",
    "Sunnydale High School",
    "Springfield Elementary",
    "Faber College",
    "Hawkins High School",
    "Hawkins National Laboratory",
    "Wossamotta U",
)

# Normalized lookup set.
FICTIONAL_INSTITUTIONS_NORMALISED: frozenset[str] = frozenset(
    normalise_name(n) for n in FICTIONAL_INSTITUTIONS
)


__all__ = [
    "KNOWN_FICTIONAL",
    "OBVIOUS_FICTIONAL",
    "BORDERLINE_FICTIONAL",
    "KNOWN_JOKES",
    "FICTIONAL_INSTITUTIONS",
    "FICTIONAL_INSTITUTIONS_NORMALISED",
    "normalise_name",
]
