"""Sentiment scoring for review text."""
from __future__ import annotations

from pathlib import Path

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# Use the lexicon shipped in the repo so nothing downloads at runtime.
_LOCAL_NLTK_DATA = Path(__file__).resolve().parents[1] / "nltk_data"
if _LOCAL_NLTK_DATA.exists() and str(_LOCAL_NLTK_DATA) not in nltk.data.path:
    nltk.data.path.insert(0, str(_LOCAL_NLTK_DATA))

_ANALYZER = SentimentIntensityAnalyzer()


def classify(compound: float) -> str:
    # VADER's own recommended thresholds.
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def analyze_text(text: str) -> dict:
    """Naive: plain VADER, nothing else."""
    scores = _ANALYZER.polarity_scores(text or "")
    return {
        "compound": scores["compound"],
        "positive": scores["pos"],
        "neutral": scores["neu"],
        "negative": scores["neg"],
        "label": classify(scores["compound"]),
    }
