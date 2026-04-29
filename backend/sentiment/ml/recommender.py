"""Nearest-neighbour lookup over professor embeddings."""
from dataclasses import dataclass
from pathlib import Path

import logging
import os
import threading

import numpy as np

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
EMB_PATH = ROOT / "data" / "ml" / "prof_embeddings.npz"

_INDEX = None
_ENCODER = None
_LOCK = threading.Lock()


@dataclass
class Neighbor:
    external_ref: str
    label: str
    score: float


def _load():
    global _INDEX
    if _INDEX is not None:
        return _INDEX or None
    with _LOCK:
        if _INDEX is not None:
            return _INDEX or None
        if not EMB_PATH.exists():
            logger.info("no embeddings at %s", EMB_PATH)
            _INDEX = False
            return None
        d = np.load(EMB_PATH, allow_pickle=False)
        ids, names, vecs = d["ids"].astype(str), d["names"].astype(str), d["vecs"].astype("float32")
        _INDEX = (ids, names, vecs, {e: i for i, e in enumerate(ids.tolist())})
    return _INDEX


def is_available() -> bool:
    return _load() is not None


def is_indexed(external_ref: str) -> bool:
    idx = _load()
    return idx is not None and external_ref in idx[3]


def _encoder():
    """Lazy MiniLM, for professors who werent in the offline build."""
    global _ENCODER
    if _ENCODER is not None:
        return _ENCODER or None
    with _LOCK:
        if _ENCODER is not None:
            return _ENCODER or None
        try:
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            from sentence_transformers import SentenceTransformer
            _ENCODER = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        except Exception as exc:
            logger.warning("encoder failed to load: %s", exc)
            _ENCODER = False
            return None
    return _ENCODER


def add_professor(external_ref: str, label: str, reviews: list[str]) -> bool:
    """Embed a professor on demand (mean of their reviews) and add to the live index."""
    enc = _encoder()
    if enc is None or not reviews:
        return False
    rv = enc.encode(reviews, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    vec = rv.mean(axis=0).astype("float32"); vec /= np.linalg.norm(vec)
    with _LOCK:
        idx = _INDEX if _INDEX else None
        if idx is None:
            ids, names, vecs = np.asarray([external_ref], dtype=np.str_), np.asarray([label], dtype=np.str_), vec[None, :]
        else:
            ids0, names0, vecs0, m = idx
            if external_ref in m:
                return True
            ids = np.concatenate([ids0, np.asarray([external_ref], dtype=np.str_)])
            names = np.concatenate([names0, np.asarray([label], dtype=np.str_)])
            vecs = np.vstack([vecs0, vec[None, :]])
        globals()["_INDEX"] = (ids, names, vecs, {e: i for i, e in enumerate(ids.tolist())})
    return True


def similar(external_ref: str, k: int = 5) -> list[Neighbor]:
    idx = _load()
    if idx is None:
        return []
    ids, names, vecs, id_to_row = idx
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
