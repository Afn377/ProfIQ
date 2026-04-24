"""Load the corpus and split it. Naive: a random split."""
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

from .labels import rating_to_label


def load_corpus(parquet: Path) -> pd.DataFrame:
    df = pd.read_parquet(parquet)
    df["text"] = df["text"].astype(str).str.strip()
    df = df[df["text"].str.len() >= 5].copy()
    df["label"] = df["rating"].apply(rating_to_label)
    return df.reset_index(drop=True)


def split_corpus(parquet: Path):
    df = load_corpus(parquet)
    train, rest = train_test_split(df, test_size=0.30)
    val, test = train_test_split(rest, test_size=0.50)
    return train, val, test
