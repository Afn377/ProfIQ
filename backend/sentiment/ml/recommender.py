"""Nearest-neighbour lookup over professor embeddings."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
EMB_PATH = ROOT / "data" / "ml" / "prof_embeddings.npz"

_INDEX = None


@dataclass
class Neighbor:
    external_ref: str
    label: str
    score: float


def _load():
    global _INDEX
    if _INDEX is None:
        d = np.load(EMB_PATH, allow_pickle=False)
        ids, names, vecs = d["ids"].astype(str), d["names"].astype(str), d["vecs"].astype("float32")
        _INDEX = (ids, names, vecs, {e: i for i, e in enumerate(ids.tolist())})
    return _INDEX


def similar(external_ref: str, k: int = 5) -> list[Neighbor]:
    ids, names, vecs, id_to_row = _load()
    row = id_to_row.get(external_ref)
    if row is None:
        return []
    q = vecs[row]
    # Vectors are unit length, so cosine is just the dot product, and one
    # matrix multiply scores every professor at once.
    sims = vecs @ q
    sims[row] = -1.0                       # exclude self
    top = np.argpartition(-sims, kth=min(k, len(sims) - 1))[:k]   # top k without a full sort
    top = top[np.argsort(-sims[top])]
    return [Neighbor(str(ids[i]), str(names[i]), float(sims[i])) for i in top if sims[i] > 0]
