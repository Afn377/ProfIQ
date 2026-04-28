"""Fine-tune DistilBERT on a small subsample as a comparison model."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, f1_score

from .dataset import split_corpus
from .labels import LABELS

LABEL2ID = {l: i for i, l in enumerate(LABELS)}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", type=Path, default=Path("data/ml/corpus.parquet"))
    p.add_argument("--train-n", type=int, default=2000)
    p.add_argument("--test-n", type=int, default=1000)
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--max-len", type=int, default=128)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--out", type=Path, default=Path("data/ml/sentiment_bert"))
    p.add_argument("--metrics-out", type=Path, default=Path("data/ml/bert_metrics.json"))
    args = p.parse_args(argv)

    from datasets import Dataset
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, DataCollatorWithPadding, Trainer, TrainingArguments

    train, _, test = split_corpus(args.corpus)
    train = train.sample(args.train_n, random_state=42)
    test = test.sample(args.test_n, random_state=42)

    tok = AutoTokenizer.from_pretrained("distilbert-base-uncased")
    def to_hf(df):
        ds = Dataset.from_dict({"text": df.text.tolist(), "label": [LABEL2ID[l] for l in df.label]})
        return ds.map(lambda b: tok(b["text"], truncation=True, max_length=args.max_len), batched=True)
    train_ds, test_ds = to_hf(train), to_hf(test)

    model = AutoModelForSequenceClassification.from_pretrained("distilbert-base-uncased", num_labels=3)

    def compute_metrics(ev):
        pred = ev.predictions.argmax(-1)
        return {"accuracy": accuracy_score(ev.label_ids, pred), "macro_f1": f1_score(ev.label_ids, pred, average="macro")}

    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(args.out / "_trainer"), num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch, per_device_eval_batch_size=64,
            learning_rate=2e-5, logging_steps=25, report_to=[], save_strategy="no", seed=42,
        ),
        train_dataset=train_ds, eval_dataset=test_ds, compute_metrics=compute_metrics,
        data_collator=DataCollatorWithPadding(tok),   # reviews differ in length; pad each batch
    )
    t0 = time.time()
    trainer.train()
    fit_s = time.time() - t0
    m = trainer.evaluate()
    pred = trainer.predict(test_ds).predictions.argmax(-1)
    per_class_recall = {l: float(((pred == i) & (test_ds["label"] == np.array(i))).sum() / max((np.array(test_ds["label"]) == i).sum(), 1)) for l, i in LABEL2ID.items()}
    metrics = {"model": "distilbert-base-uncased", "train_n": args.train_n, "test_n": args.test_n, "epochs": args.epochs,
               "fit_seconds": round(fit_s), "accuracy": m["eval_accuracy"], "macro_f1": m["eval_macro_f1"], "recall": per_class_recall}
    args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_out.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
