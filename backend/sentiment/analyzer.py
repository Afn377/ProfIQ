"""Sentiment scoring for review text."""
from __future__ import annotations

import re
from pathlib import Path

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# Use the lexicon shipped in the repo so nothing downloads at runtime.
_LOCAL_NLTK_DATA = Path(__file__).resolve().parents[1] / "nltk_data"
if _LOCAL_NLTK_DATA.exists() and str(_LOCAL_NLTK_DATA) not in nltk.data.path:
    nltk.data.path.insert(0, str(_LOCAL_NLTK_DATA))

_ANALYZER = SentimentIntensityAnalyzer()

# Words that carry weight in professor reviews but score wrong or not at all
# in general English. VADER's scale is -4..+4.
ACADEMIC_LEXICON = {
    "avoid": -2.8, "skip": -2.0, "useless": -2.5, "pointless": -2.3,
    "incompetent": -3.0, "unprepared": -2.0, "rude": -2.5, "condescending": -2.5,
    "boring": -1.8, "monotone": -1.5, "tedious": -1.5, "unfair": -2.5,
    "harsh": -1.5, "unclear": -1.5, "confusing": -1.5, "disorganized": -2.0,
    "unhelpful": -2.0, "regret": -1.8, "praying": -2.0, "pray": -2.0,
    "lifesaver": 3.0, "godsend": 3.0, "engaging": 2.5, "passionate": 2.3,
    "knowledgeable": 2.2, "approachable": 2.0, "patient": 1.8, "fair": 1.8,
    "lenient": 1.5, "supportive": 2.2, "inspiring": 2.5, "recommend": 1.8,
    "helpful": 1.8, "accommodating": 2.0, "cares": 1.5,
}
_ANALYZER.lexicon.update(ACADEMIC_LEXICON)

# Multi-word phrases a per-word lexicon cannot see. (pattern, target score).
NEGATIVE_IDIOMS = [
    (re.compile(r"\bavoid\s+(?:him|her|them|this|at\s+all\s+costs)\b", re.I), -0.9),
    (re.compile(r"\b(?:do\s*not|don'?t|never)\s+take\b", re.I), -0.85),
    (re.compile(r"\bwould\s*not?\s+recommend\b", re.I), -0.8),
    (re.compile(r"\bstart\s+praying\b", re.I), -0.8),
    (re.compile(r"\bworst\s+(?:professor|class|teacher|prof)\b", re.I), -0.85),
    (re.compile(r"\bwaste\s+of\s+(?:time|money)\b", re.I), -0.85),
    (re.compile(r"\bstay\s+away\b", re.I), -0.75),
]
POSITIVE_IDIOMS = [
    (re.compile(r"\b(?:highly|definitely|would)\s+recommend\b", re.I), 0.8),
    (re.compile(r"\bbest\s+(?:professor|class|teacher|prof)\b", re.I), 0.85),
    (re.compile(r"\beasy\s+a\b", re.I), 0.5),
    (re.compile(r"\bsaved\s+my\s+(?:grade|gpa|semester)\b", re.I), 0.85),
    (re.compile(r"\b(?:really|truly)\s+cares\b", re.I), 0.7),
]


def _adjusted_compound(text: str) -> float:
    """VADER's compound, then naive idiom handling: add each matched target."""
    compound = _ANALYZER.polarity_scores(text)["compound"]
    for pattern, target in NEGATIVE_IDIOMS + POSITIVE_IDIOMS:
        if pattern.search(text):
            compound += target
    return max(-1.0, min(1.0, compound))


def classify(compound: float) -> str:
    # VADER's own recommended thresholds.
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def analyze_text(text: str) -> dict:
    scores = _ANALYZER.polarity_scores(text or "")
    compound = _adjusted_compound(text or "")
    return {
        "compound": compound,
        "positive": scores["pos"],
        "neutral": scores["neu"],
        "negative": scores["neg"],
        "label": classify(compound),
    }
