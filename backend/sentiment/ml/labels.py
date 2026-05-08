"""Shared sentiment label helpers."""
from __future__ import annotations

LABELS = ("negative", "neutral", "positive")
LABEL_TO_ID: dict[str, int] = {l: i for i, l in enumerate(LABELS)}
ID_TO_LABEL: dict[int, str] = {i: l for i, l in enumerate(LABELS)}


def rating_to_label(rating: float) -> str:
    """Bucket a 1-5 rating into a 3-class sentiment label."""
    if rating <= 2.0:
        return "negative"
    if rating <= 3.5:
        return "neutral"
    return "positive"


def vader_label(compound: float) -> str:
    """Same thresholds as ``analyzer.classify`` so VADER baseline aligns."""
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"
