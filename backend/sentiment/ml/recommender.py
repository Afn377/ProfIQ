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
            # The model is bundled in the image. Without this, huggingface_hub
            # phones home to check for updates on every load and hangs for
            # minutes on Cloud Run (original project, commit 811b0a7).
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            # The image ships the model under data/ml/hf_cache, so point every
            # cache variable there. A dev machine with its own ~/.cache still
            # works because setdefault leaves an existing value alone.
            cache_dir = ROOT / "data" / "ml" / "hf_cache"
            if cache_dir.exists():
                for var in ("HF_HOME", "HF_HUB_CACHE", "SENTENCE_TRANSFORMERS_HOME"):
                    os.environ.setdefault(var, str(cache_dir))
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


def similar(external_ref: str, k: int = 5, among: set[str] | None = None) -> list[Neighbor]:
    """Top k by cosine. With `among`, only those refs are candidates, so a
    match in the right department is never lost for ranking low globally."""
    idx = _load()
    if idx is None:
        return []
    ids, names, vecs, id_to_row = idx
    row = id_to_row.get(external_ref)
    if row is None:
        return []
    if among is not None:
        rows = np.array([id_to_row[e] for e in among if e in id_to_row and e != external_ref], dtype=int)
        if rows.size == 0:
            return []
    else:
        rows = np.arange(len(ids))
    # Vectors are unit length, so cosine is just the dot product, and one
    # matrix multiply scores every candidate at once.
    sims = vecs[rows] @ vecs[row]
    sims[rows == row] = -1.0               # exclude self
    k = min(k, len(rows))
    top = np.argpartition(-sims, kth=k - 1)[:k] if k < len(rows) else np.arange(len(rows))
    top = top[np.argsort(-sims[top])]
    return [Neighbor(str(ids[rows[i]]), str(names[rows[i]]), float(sims[i])) for i in top if sims[i] > 0]
