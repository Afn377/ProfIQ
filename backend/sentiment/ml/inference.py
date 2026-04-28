"""Serve the trained classifier. Loaded lazily, degrades to nothing if absent."""
import logging
import re
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
CLF_PATH = ROOT / "data" / "ml" / "sentiment_clf.joblib"

_LOCK = threading.Lock()
_CLF = None          # None = not tried yet, False = tried and failed, else the pipeline

# Below this max probability a non-neutral call is treated as noise.
CONFIDENCE_FLOOR = 0.65

_QUESTION = re.compile(r"^\s*(does|do|is|are|was|will|can|should|anyone|who|what|where|when|why|how)\b", re.I)


def _load():
    global _CLF
    if _CLF is not None:
        return _CLF or None
    with _LOCK:
        if _CLF is not None:
            return _CLF or None
        try:
            import joblib
            if not CLF_PATH.exists():
                logger.info("no classifier at %s, running rules only", CLF_PATH)
                _CLF = False
                return None
            _CLF = joblib.load(CLF_PATH)
            logger.info("loaded classifier from %s", CLF_PATH)
        except Exception as exc:
            logger.warning("classifier failed to load (%s), running rules only", exc)
            _CLF = False
            return None
    return _CLF


def is_available() -> bool:
    return _load() is not None


def predict(text: str) -> dict | None:
    if not text or not text.strip():
        return None
    clf = _load()
    if clf is None:
        return None
    if _QUESTION.match(text) and text.rstrip().endswith("?"):
        # "Does he curve?" carries no sentiment; dont ask the model.
        return {"label": "neutral", "confidence": 1.0, "model": "question_guard"}
    probs = clf.predict_proba([text])[0]
    i = int(probs.argmax())
    label, conf = str(clf.classes_[i]), float(probs[i])
    if conf < CONFIDENCE_FLOOR and label != "neutral":
        return {"label": "neutral", "confidence": conf, "model": "tfidf_logreg+low_conf"}
    return {"label": label, "confidence": conf, "model": "tfidf_logreg"}


def reset():
    """Test hook."""
    global _CLF
    with _LOCK:
        _CLF = None
