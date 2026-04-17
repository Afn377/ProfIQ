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

def _load_encoder(model_name: str | None = None):
    """Lazy-load the sentence-transformer encoder once per process."""
    global _ENCODER
    if _ENCODER is not None:
        return _ENCODER or None
    name = model_name or DEFAULT_MODEL
    with _ENCODER_LOCK:
        if _ENCODER is not None:
            return _ENCODER or None
        try:
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            # Default to using the workspace cache shipped with the repo
            # so demo machines don't re-download the 80 MB model.
            cache_dir = ROOT / "data" / "ml" / "hf_cache"
            for var in (
                "HF_HOME", "HF_HUB_CACHE", "TRANSFORMERS_CACHE",
                "SENTENCE_TRANSFORMERS_HOME",
            ):
                os.environ.setdefault(var, str(cache_dir))
            from sentence_transformers import SentenceTransformer
            _ENCODER = SentenceTransformer(name)
            logger.info("Loaded recommender encoder %s", name)
        except Exception as exc:
            logger.warning("Failed to load recommender encoder %s (%s)", name, exc)
            _ENCODER = False
            return None
    return _ENCODER


def encoder_available() -> bool:
    """True if the on-the-fly encoder can be loaded (model present)."""
    return _load_encoder() is not None


def add_embedding(
    external_ref: str,
    label: str,
    doc: str,
    *,
    persist: bool = True,
    warm_path: Path | None = None,
) -> bool:
    """Add one runtime embedding to the live index."""
    if not external_ref or not (doc or "").strip():
        return False

    encoder = _load_encoder()
    if encoder is None:
        return False

    if warm_path is None:
        warm_path = DEFAULT_WARM_PATH

    try:
        import numpy as np
        vec = encoder.encode(
            [doc],
            batch_size=1,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype("float32")[0]
    except Exception as exc:
        logger.warning("Encoder failed for %s (%s)", external_ref, exc)
        return False

    with _LOCK:
        # Force initial state before merging.
        pass
    # Load outside the critical section.
    _load()

    with _LOCK:
        import numpy as np
        if _INDEX is None or _INDEX is False:
            # Start a warm-only index.
            ids = np.asarray([external_ref], dtype=np.str_)
            names = np.asarray([label or external_ref], dtype=np.str_)
            vecs = vec[None, :].astype("float32")
        else:
            cur_ids, cur_names, cur_vecs, cur_map = _INDEX
            if external_ref in cur_map:
                # Existing vectors win.
                return True
            ids = np.concatenate([
                cur_ids,
                np.asarray([external_ref], dtype=np.str_),
            ])
            names = np.concatenate([
                cur_names,
                np.asarray([label or external_ref], dtype=np.str_),
            ])
            vecs = np.vstack([cur_vecs, vec[None, :]]).astype("float32")

        id_to_row = {ext: i for i, ext in enumerate(ids.tolist())}
        globals()["_INDEX"] = (ids, names, vecs, id_to_row)

        if persist:
            try:
                _persist_warm(warm_path, external_ref, label or external_ref, vec)
            except Exception as exc:
                logger.warning("Failed to persist warm embedding for %s (%s)",
                               external_ref, exc)

    return True


def _persist_warm(warm_path: Path, external_ref: str, label: str, vec) -> None:
    """Append one row to the warm-cache npz."""
    import numpy as np

    warm_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_npz(warm_path)
    if existing is None:
        ids = np.asarray([external_ref], dtype=np.str_)
        names = np.asarray([label], dtype=np.str_)
        vecs = vec[None, :].astype("float32")
    else:
        old_ids, old_names, old_vecs = existing
        if external_ref in set(old_ids.tolist()):
            return  # already persisted
        ids = np.concatenate([old_ids, np.asarray([external_ref], dtype=np.str_)])
        names = np.concatenate([old_names, np.asarray([label], dtype=np.str_)])
        vecs = np.vstack([old_vecs, vec[None, :]]).astype("float32")

    # numpy.savez_compressed appends ".npz" if the path doesn't already
    # end in it, so we use a sibling temp filename with the same suffix.
    tmp = warm_path.with_name(warm_path.stem + ".tmp.npz")
    np.savez_compressed(tmp, ids=ids, names=names, vecs=vecs)
    os.replace(tmp, warm_path)


def reset() -> None:
    """Test hook: drop cached index so subsequent calls reload."""
    global _INDEX, _ENCODER
    with _LOCK:
        _INDEX = None
    with _ENCODER_LOCK:
        _ENCODER = None
