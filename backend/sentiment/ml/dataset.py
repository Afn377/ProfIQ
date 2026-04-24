"""Load the corpus and split it deterministically."""
import hashlib
from pathlib import Path

import pandas as pd

from .labels import rating_to_label


def _bucket(key: str) -> str:
    """Hash a stable id into train / val / test at 70 / 15 / 15.

    The same key always lands in the same bucket, so a review's split
    never changes, even after more reviews are added to the corpus.
    """
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    pct = h % 100
    if pct < 70:
        return "train"
    if pct < 85:
        return "val"
    return "test"


def load_corpus(parquet: Path, split_on: str = "source_url") -> pd.DataFrame:
    """``split_on`` is which column decides the bucket: the review's own url
    (review-level split) or the professor's id (professor-level split)."""
    df = pd.read_parquet(parquet)
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"].str.len() >= 5].copy()
    df["label"] = df["rating"].apply(rating_to_label)
    df["bucket"] = df[split_on].astype(str).apply(_bucket)
    return df.reset_index(drop=True)


def split_corpus(parquet: Path, split_on: str = "source_url"):
    df = load_corpus(parquet, split_on=split_on)
    return (
        df[df.bucket == "train"].reset_index(drop=True),
        df[df.bucket == "val"].reset_index(drop=True),
        df[df.bucket == "test"].reset_index(drop=True),
    )
