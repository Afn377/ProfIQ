"""Optional ML sentiment inference helpers."""
from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Resolve relative to the backend/ working dir.
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLF_PATH = ROOT / "data" / "ml" / "sentiment_clf.joblib"
DEFAULT_BERT_DIR = ROOT / "data" / "ml" / "sentiment_bert"

_LOCK = threading.Lock()
_CLF = None        # sklearn Pipeline or False sentinel for "tried & failed"
_BERT = None       # transformers pipeline or False sentinel
_BERT_DISABLED = os.environ.get("ML_BERT_LIVE", "").strip() not in {"1", "true", "yes"}


# Low-confidence predictions are treated as neutral.
try:
    CONFIDENCE_FLOOR = float(os.environ.get("ML_CONFIDENCE_FLOOR", "0.65"))
except ValueError:
    CONFIDENCE_FLOOR = 0.65


# Opinion words used to distinguish questions from review text.
_OPINION_TOKENS = frozenset({
    # negative
    "avoid", "avoided", "avoiding", "skip", "useless", "pointless",
    "worthless", "incompetent", "unprepared", "unprofessional", "rude",
    "condescending", "disrespectful", "arrogant", "lazy", "boring",
    "monotone", "tedious", "overwhelming", "unfair", "biased", "harsh",
    "horrible", "terrible", "awful", "nightmare", "dreadful", "unclear",
    "confusing", "vague", "nitpicky", "unhelpful", "unresponsive",
    "inaccessible", "disorganized", "demeaning", "belittling", "hated",
    "regret", "fail", "failing", "failed", "worst", "bad", "hate",
    "hates", "annoying", "trash", "garbage", "tough", "difficult",
    # positive
    "lifesaver", "godsend", "amazing", "fantastic", "incredible",
    "phenomenal", "engaging", "passionate", "knowledgeable",
    "approachable", "responsive", "thorough", "patient", "fair",
    "lenient", "supportive", "encouraging", "inspiring", "brilliant",
    "excellent", "wonderful", "outstanding", "exceptional", "favorite",
    "recommend", "recommended", "informative", "interesting",
    "enjoyable", "loved", "easygoing", "respectful", "helpful",
    "accommodating", "great", "good", "best", "love", "loves",
    "awesome", "kind", "nice", "decent", "cool", "chill", "easy",
})


_QUESTION_LEAD = re.compile(
    r"^\s*(?:does|do|did|is|are|was|were|has|have|had|will|would|can|"
    r"could|should|may|might|anyone|anybody|who|whom|what|whats|where|"
    r"when|why|how|whose|which)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[a-zA-Z']+")


def _is_opinionless_question(text: str) -> bool:
    """Return True for questions with no opinion words."""
    s = (text or "").strip()
    if not s:
        return False
    tokens = [w.lower() for w in _WORD_RE.findall(s)]
    if not tokens:
        return False
    if any(tok in _OPINION_TOKENS for tok in tokens):
        return False
    if s.endswith("?"):
        return True
    if "?" in s and _QUESTION_LEAD.match(s):
        return True
    if _QUESTION_LEAD.match(s) and len(tokens) <= 30:
        return True
    return False


@dataclass
class Prediction:
    label: str            # "negative" / "neutral" / "positive"
    confidence: float     # max softmax probability, in [0, 1]
    model: str            # which model produced it (e.g. "tfidf_logreg")


def _load_classifier(path: Path | None = None):
    global _CLF
    if _CLF is not None:
        return _CLF or None
    # Resolve at call time so tests can monkey-patch DEFAULT_CLF_PATH.
    if path is None:
        path = DEFAULT_CLF_PATH
    with _LOCK:
        if _CLF is not None:
            return _CLF or None
        try:
            import joblib
            if not path.exists():
                logger.info("ML classifier artifact not found at %s "
                            "- falling back to VADER", path)
                _CLF = False
                return None
            _CLF = joblib.load(path)
            logger.info("Loaded ML classifier from %s", path)
        except Exception as exc:
            logger.warning("Failed to load ML classifier (%s) - "
                           "falling back to VADER", exc)
            _CLF = False
            return None
    return _CLF


def _load_bert(model_dir: Path | None = None):
    global _BERT
    if _BERT_DISABLED:
        return None
    if _BERT is not None:
        return _BERT or None
    if model_dir is None:
        model_dir = DEFAULT_BERT_DIR
    with _LOCK:
        if _BERT is not None:
            return _BERT or None
        try:
            if not model_dir.exists():
                logger.info("BERT model dir not found at %s", model_dir)
                _BERT = False
                return None
            from transformers import pipeline
            _BERT = pipeline(
                task="text-classification",
                model=str(model_dir),
                tokenizer=str(model_dir),
                top_k=None,
                truncation=True,
                max_length=256,
            )
            logger.info("Loaded BERT classifier from %s", model_dir)
        except Exception as exc:
            logger.warning("Failed to load BERT classifier (%s)", exc)
            _BERT = False
            return None
    return _BERT


def predict(text: str) -> Optional[Prediction]:
    """Predict 3-class sentiment when the model is available."""
    if not text or not text.strip():
        return None
    clf = _load_classifier()
    if clf is None:
        return None

    if _is_opinionless_question(text):
        # Don't bother running the model — by construction the answer
        # should be neutral. Reporting 1.0 confidence here is honest:
        # the heuristic, not the model, is the source of certainty.
        return Prediction(
            label="neutral",
            confidence=1.0,
            model="tfidf_logreg+question_guard",
        )

    try:
        probs = clf.predict_proba([text])[0]
        idx = int(probs.argmax())
        label = str(clf.classes_[idx])
        confidence = float(probs[idx])
        if confidence < CONFIDENCE_FLOOR and label != "neutral":
            # Low-confidence predictions on a 3-class problem are
            # essentially noise; defer to neutral instead of leaking
            # spurious polarity into the UI.
            return Prediction(
                label="neutral",
                confidence=confidence,
                model="tfidf_logreg+low_conf",
            )
        return Prediction(
            label=label,
            confidence=confidence,
            model="tfidf_logreg",
        )
    except Exception as exc:
        logger.warning("ML predict failed: %s", exc)
        return None


def predict_bert(text: str) -> Optional[Prediction]:
    """Optional BERT prediction. Returns ``None`` when disabled or unavailable."""
    if not text or not text.strip():
        return None
    pipe = _load_bert()
    if pipe is None:
        return None
    try:
        out = pipe(text)
        scores = out[0] if (out and isinstance(out[0], list)) else out
        best = max(scores, key=lambda s: s["score"])
        return Prediction(
            label=str(best["label"]).lower(),
            confidence=float(best["score"]),
            model="distilbert",
        )
    except Exception as exc:
        logger.warning("BERT predict failed: %s", exc)
        return None


def is_available() -> bool:
    return _load_classifier() is not None


def reset() -> None:
    """Test hook: drop cached models so subsequent calls reload."""
    global _CLF, _BERT
    with _LOCK:
        _CLF = None
        _BERT = None
