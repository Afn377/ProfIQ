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
    """VADER's compound, then let the strongest idiom set a floor or ceiling.

    A recommendation like "do not take" is the point of a review; it should
    not be outvoted by adjectives. So instead of adding, the dominant idiom
    pulls the score at least as far as its target: min() for negative,
    max() for positive. Several idioms agreeing don't stack.
    """
    base = _ANALYZER.polarity_scores(text)["compound"]
    targets = [t for p, t in NEGATIVE_IDIOMS + POSITIVE_IDIOMS if p.search(text)]
    if not targets:
        return base
    dominant = max(targets, key=abs)
    adjusted = min(base, dominant) if dominant < 0 else max(base, dominant)
    return max(-1.0, min(1.0, adjusted))


# Dashboard themes: which topics a review talks about.
THEME_KEYWORDS = {
    "clarity": ("clear", "explain", "explains", "confusing", "unclear", "organized", "lecture", "lectures", "examples"),
    "fairness": ("fair", "unfair", "biased", "lenient", "harsh"),
    "workload": ("workload", "homework", "assignments", "easy", "hard", "heavy", "projects", "reading"),
    "helpfulness": ("helpful", "unhelpful", "office hours", "responsive", "supportive", "approachable", "cares"),
    "engagement": ("engaging", "boring", "passionate", "monotone", "interesting", "funny", "dry"),
    "grading": ("grade", "grades", "grading", "exam", "exams", "test", "tests", "quiz", "curve"),
}


def extract_themes(text: str) -> list[str]:
    """A theme is present if one of its keywords appears as a whole word.

    Single words match on word boundaries so "hard" does not fire inside
    "hardly". Multi-word phrases ("office hours") are matched as substrings
    since they cannot accidentally sit inside another word.
    """
    lowered = text.lower()
    found = []
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if " " in kw:
                hit = kw in lowered
            else:
                hit = re.search(rf"\b{re.escape(kw)}\b", lowered) is not None
            if hit:
                found.append(theme)
                break
    return found


def classify(compound: float) -> str:
    # VADER's own recommended thresholds.
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


# Star ratings nudge the text score without replacing it.
_RATING_BLEND_WEIGHT = 0.30


def _rating_to_compound(rating: float) -> float:
    # 1 star -> -1.0, 3 -> 0.0, 5 -> +1.0
    return max(-1.0, min(1.0, (float(rating) - 3.0) / 2.0))


def analyze_text(text: str, rating: float | None = None) -> dict:
    scores = _ANALYZER.polarity_scores(text or "")
    compound = _adjusted_compound(text or "")
    if rating is not None:
        compound = (1 - _RATING_BLEND_WEIGHT) * compound + _RATING_BLEND_WEIGHT * _rating_to_compound(rating)
        compound = max(-1.0, min(1.0, compound))
    return {
        "compound": compound,
        "positive": scores["pos"],
        "neutral": scores["neu"],
        "negative": scores["neg"],
        "label": classify(compound),
        "themes": extract_themes(text or ""),
    }


# ---------------------------------------------------------------------------
# Per-professor aggregation

def compute_recommendation_score(avg_compound: float, positive_ratio: float, review_count: int) -> float:
    """Combine sentiment and positivity into a 0-100 score, shrunk toward 50
    when there are few reviews.

    One glowing review is weak evidence. confidence = n / (n + k) is how much
    we trust the raw score; the rest of the weight sits on a neutral 50. With
    k = 10, one review moves the score 9 percent of the way; 100 reviews, 91.
    """
    sentiment_component = (avg_compound + 1) * 50      # -1..1 -> 0..100
    ratio_component = positive_ratio * 100
    base = 0.6 * sentiment_component + 0.4 * ratio_component

    k = 10
    confidence = review_count / (review_count + k) if review_count > 0 else 0.0
    shrunk = confidence * base + (1 - confidence) * 50
    return max(0.0, min(100.0, round(shrunk, 2)))


def aggregate_stats(sentiments: list[dict]) -> dict:
    """Roll a professor's per-review results into one stats dict."""
    n = len(sentiments)
    if n == 0:
        return {
            "review_count": 0, "avg_compound": 0.0,
            "positive_count": 0, "neutral_count": 0, "negative_count": 0,
            "theme_counts": {}, "recommendation_score": 0.0,
        }
    avg = sum(s["compound"] for s in sentiments) / n
    pos = sum(1 for s in sentiments if s["label"] == "positive")
    neu = sum(1 for s in sentiments if s["label"] == "neutral")
    neg = n - pos - neu
    theme_counts: dict[str, int] = {}
    for s in sentiments:
        for t in s.get("themes", []):
            theme_counts[t] = theme_counts.get(t, 0) + 1
    return {
        "review_count": n,
        "avg_compound": round(avg, 4),
        "positive_count": pos, "neutral_count": neu, "negative_count": neg,
        "theme_counts": theme_counts,
        "recommendation_score": compute_recommendation_score(avg, pos / n, n),
    }
