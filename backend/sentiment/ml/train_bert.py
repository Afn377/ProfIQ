"""Fine-tune DistilBERT for review sentiment."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np

# Quiet noisy logs and disable telemetry / parallel tokenizer warnings.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix, f1_score,
)
from datasets import Dataset
from transformers import (
    AutoTokenizer, AutoModelForSequenceClassification,
    DataCollatorWithPadding, Trainer, TrainingArguments,
    set_seed,
)

from .dataset import split_corpus
from .labels import LABELS, LABEL_TO_ID, ID_TO_LABEL


def to_hf(df, tokenizer, max_length: int = 256) -> Dataset:
    ds = Dataset.from_dict({
        "text": df["text"].tolist(),
        "labels": [LABEL_TO_ID[l] for l in df["label"].tolist()],
    })
    ds = ds.map(
        lambda b: tokenizer(b["text"], truncation=True, max_length=max_length),
        batched=True, remove_columns=["text"],
    )
    return ds


def compute_metrics_factory():
    def _fn(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        return {
            "accuracy": accuracy_score(labels, preds),
            "macro_f1": f1_score(labels, preds, average="macro"),
            "weighted_f1": f1_score(labels, preds, average="weighted"),
        }
    return _fn


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--corpus", type=Path, default=Path("data/ml/corpus.parquet"))
    p.add_argument("--out-dir", type=Path, default=Path("data/ml/sentiment_bert"))
    p.add_argument("--metrics-out", type=Path, default=Path("data/ml/bert_metrics.json"))
    p.add_argument("--model", default="distilbert-base-uncased")
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--max-length", type=int, default=256)
    p.add_argument("--max-train", type=int, default=0,
                   help="Cap training rows (0 = use all). Useful for smoke tests.")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)

    set_seed(args.seed)

    print(f"[train_bert] loading corpus from {args.corpus}", flush=True)
    split = split_corpus(args.corpus)
    print(f"[train_bert] split sizes:\n{split.describe()}", flush=True)

    train_df = split.train
    if args.max_train and args.max_train < len(train_df):
        train_df = train_df.sample(n=args.max_train, random_state=args.seed)
        print(f"[train_bert] capped train to {len(train_df)} rows", flush=True)

    print(f"[train_bert] loading tokenizer + model: {args.model}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model,
        num_labels=len(LABELS),
        id2label=ID_TO_LABEL,
        label2id=LABEL_TO_ID,
    )

    train_ds = to_hf(train_df, tokenizer, args.max_length)
    val_ds   = to_hf(split.val,   tokenizer, args.max_length)
    test_ds  = to_hf(split.test,  tokenizer, args.max_length)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(args.out_dir / "_trainer"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=max(args.batch, 32),
        learning_rate=args.lr,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        save_total_limit=1,
        logging_steps=50,
        report_to=[],
        seed=args.seed,
        # CPU-friendly defaults
        dataloader_num_workers=0,
        fp16=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer),
        compute_metrics=compute_metrics_factory(),
    )

    print("[train_bert] starting fine-tune ...", flush=True)
    t0 = time.time()
    trainer.train()
    fit_seconds = time.time() - t0

    def evaluate(name: str, ds, df) -> dict:
        out = trainer.predict(ds)
        preds = np.argmax(out.predictions, axis=-1)
        y_true = [LABEL_TO_ID[l] for l in df["label"].tolist()]
        acc = accuracy_score(y_true, preds)
        macro = f1_score(y_true, preds, average="macro")
        weighted = f1_score(y_true, preds, average="weighted")
        cm = confusion_matrix(y_true, preds, labels=list(range(len(LABELS)))).tolist()
        report = classification_report(
            [ID_TO_LABEL[i] for i in y_true],
            [ID_TO_LABEL[i] for i in preds],
            labels=list(LABELS),
            output_dict=True, zero_division=0,
        )
        print(f"[train_bert] {name}: acc={acc:.4f} macro_f1={macro:.4f} "
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
        "model": "distilbert-base-uncased",
        "fit_seconds": round(fit_seconds, 2),
        "n_train": len(train_df),
        "n_val": len(split.val),
        "n_test": len(split.test),
        "epochs": args.epochs,
        "batch": args.batch,
        "lr": args.lr,
        "val": evaluate("val", val_ds, split.val),
        "test": evaluate("test", test_ds, split.test),
    }

    print(f"[train_bert] saving model to {args.out_dir}", flush=True)
    trainer.save_model(str(args.out_dir))
    tokenizer.save_pretrained(str(args.out_dir))
    args.metrics_out.write_text(json.dumps(metrics, indent=2))
    print(f"[train_bert] DONE - fit_seconds={metrics['fit_seconds']:.0f}s "
          f"test_macro_f1={metrics['test']['macro_f1']:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
