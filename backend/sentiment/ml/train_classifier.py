"""Train the TF-IDF + logistic regression sentiment model."""
import argparse
import json
import time
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline

from .dataset import split_corpus
from .labels import LABELS


def build_pipeline() -> Pipeline:
    # Naive: sklearn defaults.
    return Pipeline([("tfidf", TfidfVectorizer()), ("clf", LogisticRegression(max_iter=1000))])


def evaluate(pipe, X, y) -> dict:
    pred = pipe.predict(X)
    return {
        "accuracy": accuracy_score(y, pred),
        "macro_f1": f1_score(y, pred, average="macro", labels=list(LABELS)),
        "confusion": confusion_matrix(y, pred, labels=list(LABELS)).tolist(),
        "per_class": {l: classification_report(y, pred, labels=list(LABELS), output_dict=True, zero_division=0)[l] for l in LABELS},
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", type=Path, default=Path("data/ml/corpus.parquet"))
    p.add_argument("--out", type=Path, default=Path("data/ml/sentiment_clf.joblib"))
    p.add_argument("--metrics-out", type=Path, default=Path("data/ml/clf_metrics.json"))
    p.add_argument("--split-on", default="source_url")
    args = p.parse_args(argv)

    train, val, test = split_corpus(args.corpus, split_on=args.split_on)
    print(f"train={len(train)} val={len(val)} test={len(test)}")
    pipe = build_pipeline()
    t0 = time.time()
    pipe.fit(train.text, train.label)
    print(f"fit in {time.time()-t0:.0f}s")
    metrics = {"val": evaluate(pipe, val.text, val.label), "test": evaluate(pipe, test.text, test.label)}
    print(f"test accuracy = {metrics['test']['accuracy']:.4f}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, args.out, compress=3)
    args.metrics_out.write_text(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
