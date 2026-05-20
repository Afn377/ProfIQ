"""Build per-professor embedding artifacts."""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def _aggregate(corpus: pd.DataFrame, max_chars: int = 4000) -> pd.DataFrame:
    """Group reviews into one clipped document per professor."""
    rows = []
    for (ext_id, name, inst, dept), g in corpus.groupby(
        ["professor_id_external", "professor_name", "institution", "department"],
        dropna=False,
    ):
        g = g.copy()
        g["len"] = g["text"].str.len()
        g = g.sort_values("len", ascending=False)
        chunks: list[str] = []
        used = 0
        for txt in g["text"]:
            t = str(txt).strip()
            if not t:
                continue
            if used + len(t) > max_chars and chunks:
                break
            chunks.append(t)
            used += len(t)
        if not chunks:
            continue
        rows.append({
            "id": ext_id,
            "label": f"{name} @ {inst}" if inst else name,
            "name": name,
            "institution": inst or "",
            "department": dept or "",
            "n_reviews": len(g),
            "doc": "  ".join(chunks),
        })
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--corpus", type=Path, default=Path("data/ml/corpus.parquet"))
    p.add_argument("--out", type=Path, default=Path("data/ml/prof_embeddings.npz"))
    p.add_argument("--meta-out", type=Path, default=Path("data/ml/prof_embeddings_meta.parquet"))
    p.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--max-chars", type=int, default=4000)
    p.add_argument("--min-reviews", type=int, default=3,
                   help="Skip profs with fewer than this many reviews")
    args = p.parse_args(argv)

    print(f"[embeddings] loading corpus from {args.corpus}", flush=True)
    df = pd.read_parquet(args.corpus)
    df["text"] = df["text"].astype(str)

    print(f"[embeddings] aggregating per-prof docs (min_reviews={args.min_reviews}) ...",
          flush=True)
    agg = _aggregate(df, max_chars=args.max_chars)
    agg = agg[agg["n_reviews"] >= args.min_reviews].reset_index(drop=True)
    print(f"[embeddings] {len(agg)} professors meet threshold", flush=True)

    from sentence_transformers import SentenceTransformer
    print(f"[embeddings] loading model {args.model} ...", flush=True)
    model = SentenceTransformer(args.model)

    t0 = time.time()
    vecs = model.encode(
        agg["doc"].tolist(),
        batch_size=args.batch,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype("float32")
    print(f"[embeddings] encoded {len(vecs)} docs in {time.time()-t0:.1f}s "
          f"-> shape={vecs.shape}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Cast to fixed-width unicode so numpy can load with allow_pickle=False.
    ids = np.asarray(agg["id"].astype(str).tolist(), dtype=np.str_)
    names = np.asarray(agg["label"].astype(str).tolist(), dtype=np.str_)
    np.savez_compressed(
        args.out,
        ids=ids,
        names=names,
        vecs=vecs,
    )
    agg[["id", "name", "institution", "department", "n_reviews"]].to_parquet(
        args.meta_out, index=False
    )
    print(f"[embeddings] saved {args.out} "
          f"({args.out.stat().st_size/1024/1024:.1f} MB) "
          f"and meta {args.meta_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
