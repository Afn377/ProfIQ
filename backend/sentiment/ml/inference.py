"""Serve the trained classifier. Naive: load at import time."""
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[2]
CLF_PATH = ROOT / "data" / "ml" / "sentiment_clf.joblib"

_CLF = joblib.load(CLF_PATH)


def predict(text: str) -> dict | None:
    if not text or not text.strip():
        return None
    probs = _CLF.predict_proba([text])[0]
    i = int(probs.argmax())
    return {"label": str(_CLF.classes_[i]), "confidence": float(probs[i]), "model": "tfidf_logreg"}
