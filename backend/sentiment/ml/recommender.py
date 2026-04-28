"""Nearest-neighbour lookup over professor embeddings. Naive: a Python loop."""
import math
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
    scored = []
    for i in range(len(vecs)):
        if i == row:
            continue
        v = vecs[i]
        dot = sum(a * b for a, b in zip(q, v))
        norm = math.sqrt(sum(a * a for a in q)) * math.sqrt(sum(b * b for b in v))
        scored.append((dot / norm, i))
    scored.sort(reverse=True)
    return [Neighbor(str(ids[i]), str(names[i]), float(s)) for s, i in scored[:k]]
