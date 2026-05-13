"""Shared corpus split helpers for ML scripts."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .labels import LABELS, rating_to_label


@dataclass
class CorpusSplit:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame

    def describe(self) -> str:
        lines = []
        for name, df in [("train", self.train), ("val", self.val), ("test", self.test)]:
            counts = df["label"].value_counts().reindex(LABELS, fill_value=0)
            lines.append(
                f"  {name:5s}: {len(df):>6d} | "
                + " ".join(f"{l}={counts[l]}" for l in LABELS)
            )
        return "\n".join(lines)


def _bucket(source_url: str) -> str:
    """Hash a source_url to one of {train, val, test} with 70/15/15 split."""
    h = int(hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:8], 16)
    pct = h % 100
    if pct < 70:
        return "train"
    if pct < 85:
        return "val"
    return "test"


def load_corpus(parquet: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet)
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"].str.len() >= 5].copy()
    df["label"] = df["rating"].apply(rating_to_label)
    df["bucket"] = df["source_url"].apply(_bucket)
    return df.reset_index(drop=True)


def split_corpus(parquet: Path) -> CorpusSplit:
    df = load_corpus(parquet)
    return CorpusSplit(
        train=df[df["bucket"] == "train"].reset_index(drop=True),
        val=df[df["bucket"] == "val"].reset_index(drop=True),
        test=df[df["bucket"] == "test"].reset_index(drop=True),
    )
