"""Sentiment scoring and theme extraction for review text."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer


# Use the vendored VADER lexicon when available.
_LOCAL_NLTK_DATA = Path(__file__).resolve().parents[1] / "nltk_data"
if _LOCAL_NLTK_DATA.exists():
    path_str = str(_LOCAL_NLTK_DATA)
    if path_str not in nltk.data.path:
        nltk.data.path.insert(0, path_str)


def _ensure_lexicon() -> None:
    """Make sure the VADER lexicon is available; try to download if missing."""
    try:
        nltk.data.find("sentiment/vader_lexicon.zip")
        return
    except LookupError:
        pass
    try:
        nltk.download("vader_lexicon", quiet=True)
    except Exception:
        # Offline runs depend on the vendored lexicon.
        pass


_ensure_lexicon()
_ANALYZER = SentimentIntensityAnalyzer()


# Extra VADER weights for common professor-review words.

ACADEMIC_LEXICON: dict[str, float] = {
    # --- negative ---
    "avoid": -2.8,
    "avoided": -2.5,
    "avoiding": -2.5,
    "skip": -2.0,
    "skipped": -1.8,
    "useless": -2.5,
    "pointless": -2.3,
    "worthless": -2.8,
    "incompetent": -3.0,
    "unprepared": -2.0,
    "unprofessional": -2.5,
    "rude": -2.5,
    "condescending": -2.5,
    "disrespectful": -2.5,
    "arrogant": -2.0,
    "lazy": -1.8,
    "boring": -1.8,
    "monotone": -1.5,
    "tedious": -1.5,
    "overwhelming": -1.5,
    "overwhelmed": -1.2,
    "unfair": -2.5,
    "biased": -2.0,
    "harsh": -1.5,
    "horrible": -2.8,
    "terrible": -2.8,
    "awful": -2.5,
    "nightmare": -2.5,
    "dreadful": -2.5,
    "unclear": -1.5,
    "confusing": -1.5,
    "vague": -1.2,
    "nitpicky": -1.5,
    "unhelpful": -2.0,
    "unresponsive": -1.8,
    "inaccessible": -1.5,
    "disorganized": -2.0,
    "demeaning": -2.5,
    "belittling": -2.5,
    "hated": -2.5,
    "regret": -1.8,
    "dropped": -1.0,
    "fail": -1.5,
    "failing": -1.5,
    "failed": -1.2,

    # --- positive ---
    "lifesaver": +3.0,
    "lifesaving": +3.0,
    "godsend": +3.0,
    "amazing": +2.8,
    "fantastic": +2.8,
    "incredible": +2.5,
    "phenomenal": +2.8,
    "engaging": +2.5,
    "passionate": +2.3,
    "knowledgeable": +2.2,
    "approachable": +2.0,
    "responsive": +1.8,
    "thorough": +1.5,
    "patient": +1.8,
    "fair": +1.8,
    "lenient": +1.5,
    "supportive": +2.2,
    "encouraging": +2.0,
    "inspiring": +2.5,
    "brilliant": +2.5,
    "excellent": +2.5,
    "wonderful": +2.3,
    "outstanding": +2.5,
    "exceptional": +2.5,
    "favorite": +2.2,
    "recommend": +1.8,
    "recommended": +1.8,
    "informative": +1.8,
    "interesting": +1.5,
    "enjoyable": +2.0,
    "loved": +2.5,
    "easygoing": +1.8,
    "respectful": +1.8,
    "helpful": +1.8,
    "available": +1.0,
    "accommodating": +2.0,
}

_ANALYZER.lexicon.update(ACADEMIC_LEXICON)


# Multi-word phrases that VADER usually handles poorly.

NEGATIVE_IDIOMS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\bavoid\s+(?:him|her|them|it|this|that|at\s+all\s+costs|like\s+the\s+plague)\b", re.I), -0.9),
    (re.compile(r"\b(?:do\s*not|don'?t|never|do\s+not\s+ever)\s+take\b", re.I), -0.85),
    (re.compile(r"\bwould\s*not?\s+recommend\b", re.I), -0.8),
    (re.compile(r"\bdo\s*not\s+recommend\b", re.I), -0.8),
    (re.compile(r"\bworst\s+(?:professor|class|teacher|prof|instructor)\b", re.I), -0.85),
    (re.compile(r"\b(?:save|waste(?:d)?)\s+your\s+(?:money|time|tuition)\b", re.I), -0.8),
    (re.compile(r"\bdrop\s+(?:this|the|his|her)\s+class\b", re.I), -0.7),
    (re.compile(r"\brun\s+away\b", re.I), -0.7),
    (re.compile(r"\bnot\s+worth\s+(?:it|the\s+(?:time|money|trouble))\b", re.I), -0.6),
    (re.compile(r"\bsteer\s+clear\b", re.I), -0.7),
    (re.compile(r"\bstay\s+away\b", re.I), -0.75),
    (re.compile(r"\bwaste\s+of\s+(?:time|money|tuition)\b", re.I), -0.85),
    (re.compile(r"\bregret(?:ted)?\s+taking\b", re.I), -0.8),
    (re.compile(r"\bhardest\s+class\s+(?:i|i've|i\s+have)\s+ever\b", re.I), -0.5),
    (re.compile(r"\bdoes(?:n'?t| not)\s+(?:care|teach)\b", re.I), -0.7),
]

POSITIVE_IDIOMS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\b(?:highly|definitely|would|absolutely|100%)\s+recommend\b", re.I), +0.8),
    (re.compile(r"\btake\s+(?:him|her|them|this\s+class|his\s+class|her\s+class)\b", re.I), +0.55),
    (re.compile(r"\bbest\s+(?:professor|class|teacher|prof|instructor)\b", re.I), +0.85),
    (re.compile(r"\bone\s+of\s+the\s+best\b", re.I), +0.7),
    (re.compile(r"\beasy\s+a\b", re.I), +0.5),
    (re.compile(r"\bsaved\s+my\s+(?:grade|gpa|life|semester)\b", re.I), +0.85),
    (re.compile(r"\bgo(?:es)?\s+above\s+and\s+beyond\b", re.I), +0.75),
    (re.compile(r"\b(?:really|truly)\s+cares\b", re.I), +0.7),
    (re.compile(r"\bworth\s+(?:every\s+penny|the\s+(?:wait|effort|time))\b", re.I), +0.7),
    (re.compile(r"\bcan'?t\s+(?:wait\s+to|recommend)\s+(?:take|her|him|enough)\b", re.I), +0.7),
]


def _adjusted_compound(text: str) -> float:
    """Run VADER, then apply phrase-level adjustments."""
    base = _ANALYZER.polarity_scores(text or "")["compound"]
    if not text:
        return base

    matched_targets: list[float] = []
    for pattern, target in NEGATIVE_IDIOMS:
        if pattern.search(text):
            matched_targets.append(target)
    for pattern, target in POSITIVE_IDIOMS:
        if pattern.search(text):
            matched_targets.append(target)

    if not matched_targets:
        return max(-1.0, min(1.0, base))

    dominant = max(matched_targets, key=abs)
    adjusted = min(base, dominant) if dominant < 0 else max(base, dominant)
    return max(-1.0, min(1.0, adjusted))


# Keyword themes used by the dashboard.

THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "clarity": (
        "clear", "clarity", "explain", "explains", "explained", "lucid",
        "articulate", "confusing", "unclear", "vague", "muddled",
        "organized", "disorganized", "structure", "structured", "lecture",
        "lectures", "notes", "slides", "examples",
    ),
    "fairness": (
        "fair", "unfair", "fairly", "biased", "unbiased", "lenient",
        "harsh", "strict grader", "fair grader",
    ),
    "workload": (
        "workload", "assignments", "homework", "busy work", "overloaded",
        "easy", "hard", "heavy", "light", "manageable", "time-consuming",
        "project", "projects", "paper", "papers", "reading", "readings",
        "lab", "labs", "problem sets", "psets",
    ),
    "helpfulness": (
        "helpful", "unhelpful", "available", "office hours", "responsive",
        "support", "supportive", "approachable", "accessible",
        "cares", "caring", "email", "emails", "responds", "replies",
        "feedback", "accommodating",
    ),
    "engagement": (
        "engaging", "boring", "passionate", "enthusiastic", "monotone",
        "dull", "interesting", "inspiring", "dry",
        "funny", "humor", "discussion", "discussions", "participation",
        "interactive", "energy",
    ),
    "grading": (
        "grade", "grades", "grader", "grading", "exam", "exams", "tough exams",
        "easy grader", "strict", "test", "tests", "quiz", "quizzes",
        "midterm", "midterms", "final", "curve", "curves", "rubric",
    ),
}


def extract_themes(text: str) -> list[str]:
    """Return the list of theme names mentioned in ``text``."""
    lowered = text.lower()
    found: list[str] = []
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            # word-boundary match; multi-word keywords just need substring match
            if " " in kw:
                if kw in lowered:
                    found.append(theme)
                    break
            elif re.search(rf"\b{re.escape(kw)}\b", lowered):
                found.append(theme)
                break
    return found


def classify(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


# ---------------------------------------------------------------------------
# Public API

# Star ratings nudge the text score without replacing it.
_RATING_BLEND_WEIGHT = 0.30


def _rating_to_compound(rating: float) -> float:
    """Map a 1–5 RMP-style rating onto VADER's [-1, 1] compound scale."""
    # 1 -> -1.0, 2 -> -0.5, 3 -> 0.0, 4 -> +0.5, 5 -> +1.0
    return max(-1.0, min(1.0, (float(rating) - 3.0) / 2.0))


def analyze_text(text: str, rating: float | None = None) -> dict:
    """Analyze one review and return sentiment fields."""
    base_scores = _ANALYZER.polarity_scores(text or "")
    compound = _adjusted_compound(text or "")

    if rating is not None:
        rating_compound = _rating_to_compound(rating)
        compound = (1 - _RATING_BLEND_WEIGHT) * compound + _RATING_BLEND_WEIGHT * rating_compound
        compound = max(-1.0, min(1.0, compound))

    # Optional model score; rules still work if artifacts are missing.
    ml_label: str | None = None
    ml_confidence: float | None = None
    ml_model: str | None = None
    try:
        from .ml import inference as ml_inference
        prediction = ml_inference.predict(text or "")
        if prediction is not None:
            ml_label = prediction.label
            ml_confidence = round(prediction.confidence, 4)
            ml_model = prediction.model
    except Exception:  # pragma: no cover - defensive
        pass

    return {
        "compound": compound,
        "positive": base_scores["pos"],
        "neutral": base_scores["neu"],
        "negative": base_scores["neg"],
        "label": classify(compound),
        "themes": extract_themes(text or ""),
        "ml_label": ml_label,
        "ml_confidence": ml_confidence,
        "ml_model": ml_model,
    }


def compute_recommendation_score(
    avg_compound: float,
    positive_ratio: float,
    review_count: int,
) -> float:
    """Combine sentiment and review volume into a 0-100 score."""
    sentiment_component = (avg_compound + 1) * 50  # -1..1 -> 0..100
    ratio_component = positive_ratio * 100

    base = 0.6 * sentiment_component + 0.4 * ratio_component

    # Shrink low-sample professors toward the middle.
    k = 10
    confidence = review_count / (review_count + k) if review_count >= 0 else 0
    shrunk = confidence * base + (1 - confidence) * 50
    return max(0.0, min(100.0, round(shrunk, 2)))


def aggregate_stats(sentiments: Iterable[dict]) -> dict:
    """Aggregate a collection of per-review sentiment dicts into summary stats."""
    sentiments = list(sentiments)
    n = len(sentiments)
    if n == 0:
        return {
            "review_count": 0,
            "avg_compound": 0.0,
            "positive_count": 0,
            "neutral_count": 0,
            "negative_count": 0,
            "theme_counts": {},
            "recommendation_score": 0.0,
        }

    avg_compound = sum(s["compound"] for s in sentiments) / n
    pos = sum(1 for s in sentiments if s["label"] == "positive")
    neu = sum(1 for s in sentiments if s["label"] == "neutral")
    neg = sum(1 for s in sentiments if s["label"] == "negative")

    theme_counts: dict[str, int] = {}
    for s in sentiments:
        for t in s.get("themes", []):
            theme_counts[t] = theme_counts.get(t, 0) + 1

    positive_ratio = pos / n
    score = compute_recommendation_score(avg_compound, positive_ratio, n)

    return {
        "review_count": n,
        "avg_compound": round(avg_compound, 4),
        "positive_count": pos,
        "neutral_count": neu,
        "negative_count": neg,
        "theme_counts": theme_counts,
        "recommendation_score": score,
    }
