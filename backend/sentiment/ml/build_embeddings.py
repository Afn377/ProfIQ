"""Build one embedding per professor from their review text."""
import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd


def aggregate(corpus: pd.DataFrame, max_chars: int = 4000) -> pd.DataFrame:
    """One document per professor: longest reviews first, clipped at max_chars."""
    rows = []
    for (ext_id, name, inst, dept), g in corpus.groupby(["professor_id_external", "professor_name", "institution", "department"], dropna=False):
        chunks, used = [], 0
        for t in g.text.astype(str).sort_values(key=lambda s: s.str.len(), ascending=False):
            t = t.strip()
            if not t: continue
            if used + len(t) > max_chars and chunks: break
            chunks.append(t); used += len(t)
        if chunks:
            rows.append({"id": ext_id, "label": f"{name} @ {inst}", "name": name, "institution": inst or "", "department": dept or "", "n_reviews": len(g), "doc": "  ".join(chunks)})
    return pd.DataFrame(rows)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", type=Path, default=Path("data/ml/corpus.parquet"))
    p.add_argument("--out", type=Path, default=Path("data/ml/prof_embeddings.npz"))
    p.add_argument("--meta-out", type=Path, default=Path("data/ml/prof_embeddings_meta.parquet"))
    p.add_argument("--limit", type=int, default=None, help="Only the first N professors")
    p.add_argument("--min-reviews", type=int, default=3)
    args = p.parse_args(argv)

    df = pd.read_parquet(args.corpus)
    agg = aggregate(df)
    agg = agg[agg.n_reviews >= args.min_reviews].reset_index(drop=True)
    if args.limit: agg = agg.head(args.limit)
    print(f"{len(agg)} professors to encode")

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    # Embed every review separately and average per professor. Concatenating
    # reviews into one document and encoding that silently truncated at 256
    # tokens, so the encoder saw ~29% of each professor's text. Mean-pooling
    # reads all of it: dept purity@5 went from 0.225 to 0.350 on 1000 profs.
    sub = df[df.professor_id_external.isin(set(agg.id))]
    t0 = time.time()
    rv = model.encode(sub.text.astype(str).tolist(), batch_size=128, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    per = pd.DataFrame(rv).groupby(sub.professor_id_external.values).mean().loc[agg.id]
    vecs = np.array(per.to_numpy(), dtype="float32")
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    print(f"encoded {len(sub)} reviews for {len(agg)} professors in {time.time()-t0:.1f}s -> {vecs.shape}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, ids=np.asarray(agg.id.astype(str), dtype=np.str_), names=np.asarray(agg.label, dtype=np.str_), vecs=vecs)
    agg[["id", "name", "institution", "department", "n_reviews"]].to_parquet(args.meta_out, index=False)
    print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
