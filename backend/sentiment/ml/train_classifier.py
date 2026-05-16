"""Train the TF-IDF + Logistic Regression sentiment model."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix, f1_score,
)
from sklearn.pipeline import Pipeline

from .dataset import split_corpus
from .labels import LABELS


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=3,
            max_df=0.95,
            sublinear_tf=True,
            strip_accents="unicode",
            lowercase=True,
        )),
        ("clf", LogisticRegression(
            class_weight="balanced",
            max_iter=2000,
            C=1.0,
            solver="lbfgs",
            random_state=42,
        )),
    ])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--corpus", type=Path, default=Path("data/ml/corpus.parquet"))
    p.add_argument("--out", type=Path, default=Path("data/ml/sentiment_clf.joblib"))
    p.add_argument("--metrics-out", type=Path, default=Path("data/ml/clf_metrics.json"))
    args = p.parse_args(argv)

    print(f"[train_clf] loading corpus from {args.corpus}", flush=True)
    split = split_corpus(args.corpus)
    print(f"[train_clf] split sizes:\n{split.describe()}", flush=True)

    X_train = split.train["text"].tolist()
    y_train = split.train["label"].tolist()
    X_val   = split.val["text"].tolist()
    y_val   = split.val["label"].tolist()
    X_test  = split.test["text"].tolist()
    y_test  = split.test["label"].tolist()

    pipe = build_pipeline()
    t0 = time.time()
    print("[train_clf] fitting TF-IDF + LogReg ...", flush=True)
    pipe.fit(X_train, y_train)
    fit_seconds = time.time() - t0

    def evaluate(name: str, X, y_true) -> dict:
        y_pred = pipe.predict(X)
        acc = accuracy_score(y_true, y_pred)
        macro = f1_score(y_true, y_pred, average="macro", labels=list(LABELS))
        weighted = f1_score(y_true, y_pred, average="weighted", labels=list(LABELS))
        cm = confusion_matrix(y_true, y_pred, labels=list(LABELS)).tolist()
        report = classification_report(
            y_true, y_pred, labels=list(LABELS), output_dict=True, zero_division=0,
        )
        print(f"[train_clf] {name}: acc={acc:.4f} macro_f1={macro:.4f} "
              f"weighted_f1={weighted:.4f}", flush=True)
        return {
            "accuracy": acc,
            "macro_f1": macro,
            "weighted_f1": weighted,
            "confusion_matrix": cm,
            "labels": list(LABELS),
            "per_class": {l: report[l] for l in LABELS},
        }

    metrics = {
        "model": "tfidf_logreg",
        "fit_seconds": round(fit_seconds, 2),
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_test": len(X_test),
        "val": evaluate("val", X_val, y_val),
        "test": evaluate("test", X_test, y_test),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, args.out, compress=3)
    args.metrics_out.write_text(json.dumps(metrics, indent=2))
    print(f"[train_clf] saved {args.out} ({args.out.stat().st_size/1024:.1f} KB) "
          f"and metrics {args.metrics_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
