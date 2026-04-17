"""Cosine-neighbor lookup for similar professors."""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EMB_PATH = ROOT / "data" / "ml" / "prof_embeddings.npz"
DEFAULT_WARM_PATH = ROOT / "data" / "ml" / "prof_embeddings_warm.npz"
DEFAULT_MODEL = os.environ.get(
    "ML_RECOMMENDER_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

_LOCK = threading.Lock()
_INDEX = None  # tuple(ids, names, vecs, id_to_row) or False sentinel
_ENCODER = None  # SentenceTransformer instance (lazy)
_ENCODER_LOCK = threading.Lock()


@dataclass
class Neighbor:
    external_ref: str
    label: str
    score: float


def _load_npz(path: Path):
    """Load (ids, names, vecs) from an .npz, returning None on any failure."""
    try:
        if not path.exists():
            return None
        import numpy as np
        data = np.load(path, allow_pickle=False)
        ids = data["ids"].astype(str)
        names = data["names"].astype(str)
        vecs = data["vecs"].astype("float32")
        return ids, names, vecs
    except Exception as exc:
        logger.warning("Failed to load embeddings from %s (%s)", path, exc)
        return None


def _load(path: Path | None = None, warm_path: Path | None = None):
    global _INDEX
    if _INDEX is not None:
        return _INDEX or None
    if path is None:
        path = DEFAULT_EMB_PATH
    if warm_path is None:
        warm_path = DEFAULT_WARM_PATH
    with _LOCK:
        if _INDEX is not None:
            return _INDEX or None
        import numpy as np

        base = _load_npz(path)
        warm = _load_npz(warm_path)

        if base is None and warm is None:
            logger.info("Recommender embeddings not found at %s (warm=%s)",
                        path, warm_path)
            _INDEX = False
            return None

        if base is None:
            ids, names, vecs = warm
        elif warm is None:
            ids, names, vecs = base
        else:
            # Merge: trained index wins on duplicate external_ref.
            base_ids, base_names, base_vecs = base
            warm_ids, warm_names, warm_vecs = warm
            base_set = set(base_ids.tolist())
            keep = [i for i, x in enumerate(warm_ids) if x not in base_set]
            if keep:
                ids = np.concatenate([base_ids, warm_ids[keep]])
                names = np.concatenate([base_names, warm_names[keep]])
                vecs = np.vstack([base_vecs, warm_vecs[keep]])
            else:
                ids, names, vecs = base_ids, base_names, base_vecs

        id_to_row = {ext: i for i, ext in enumerate(ids.tolist())}
        _INDEX = (ids, names, vecs, id_to_row)
        logger.info(
            "Loaded prof embeddings from %s (n=%d, dim=%d, warm=%d)",
            path, len(ids), vecs.shape[1],
            0 if warm is None else len(warm[0]),
        )
    return _INDEX


def is_available() -> bool:
    return _load() is not None


def num_indexed() -> int:
    idx = _load()
    if idx is None:
        return 0
    ids, _, _, _ = idx
    return len(ids)


def is_indexed(external_ref: str) -> bool:
    idx = _load()
    if idx is None:
        return False
    _, _, _, id_to_row = idx
    return external_ref in id_to_row


def similar_by_external_ref(external_ref: str, k: int = 5) -> Optional[list[Neighbor]]:
    """Return up to ``k`` neighbors of ``external_ref``, excluding the query itself."""
    idx = _load()
    if idx is None:
        return None
    ids, names, vecs, id_to_row = idx
    row = id_to_row.get(external_ref)
    if row is None:
        return []
    import numpy as np
    query = vecs[row]
    sims = vecs @ query  # vecs are unit-norm so this is cosine similarity
    sims[row] = -1.0       # exclude self
    top = np.argpartition(-sims, kth=min(k, len(sims) - 1))[:k]
    top = top[np.argsort(-sims[top])]
    return [
        Neighbor(
            external_ref=str(ids[i]),
            label=str(names[i]),
            score=float(sims[i]),
        )
        for i in top
        if sims[i] > 0
    ]


# ---------------------------------------------------------------------------
# On-demand ("warm") embedding additions.
#
# When a user opens a professor that wasn't covered by the training
# corpus, the API can call :func:`add_embedding` with that professor's
# review text to embed them on the fly. The new vector is merged into
# the in-memory index atomically (under ``_LOCK``) and persisted to
# ``DEFAULT_WARM_PATH`` so it survives process restarts. Subsequent
# similarity lookups for that professor return real neighbors instantly
# without re-encoding.

