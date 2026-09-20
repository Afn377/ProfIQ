# ML Artifacts Reproducibility Manifest

Everything under `backend/data/ml/` is generated and gitignored. This file documents the
exact provenance of the numbers reported in `Description.MD`, and how to reproduce them.
See the README's "Rebuilding ML Artifacts" section for the commands.

## Dataset

- Source: `backend/data/ml/corpus.parquet`, built by `sentiment.ml.build_corpus`
- Total reviews: 49,989
- Unique professors: 1,001
- Unique institutions: 21

## Train/validation/test split

- Method: SHA-256 hash of each review's `source_url`, bucketed 70/15/15 (see `sentiment/ml/dataset.py::_bucket`)
- Review-level, not professor-level: a professor's reviews can land in more than one split, since the
  hash key is the review's own `source_url`, not the professor's id.
- Sizes: train 35,033 | validation 7,529 | test 7,427

| Split | negative | neutral | positive | total |
| --- | ---: | ---: | ---: | ---: |
| train | 10,414 | 3,272 | 21,347 | 35,033 |
| validation | 2,270 | 676 | 4,583 | 7,529 |
| test | 2,163 | 654 | 4,610 | 7,427 |

## Models and seeds

- TF-IDF + Logistic Regression (`sentiment.ml.train_classifier`): `random_state=42`
- DistilBERT (`sentiment.ml.train_bert`): `--seed 42` (default), fine-tuned from `distilbert-base-uncased`
- MiniLM embeddings (`sentiment.ml.build_embeddings` / `manage.py build_prof_embeddings`): `sentence-transformers/all-MiniLM-L6-v2`, no training (embedding only)
- Package versions: lower-bounded in `backend/requirements.txt` (pandas>=2.2.0, scikit-learn>=1.5.0,
  numpy>=1.26.0, sentence-transformers>=3.0.0, transformers>=4.44.0, torch>=2.4.0) — not pinned exactly,
  so a rebuild may use newer point releases.

## Metrics (test set, 7,427 reviews unless noted)

| Model | Accuracy | Macro-F1 | Weighted-F1 |
| --- | ---: | ---: | ---: |
| VADER | 0.7735 | 0.5428 | 0.7471 |
| TF-IDF + Logistic Regression | 0.8161 | 0.7090 | 0.8336 |
| DistilBERT | 0.8566 | 0.6361 | 0.8313 |

## Recommender (purity@5, MiniLM embeddings)

- Department purity: 0.2304 vs. 0.0552 random baseline (4.17x lift)
- Institution purity: 0.0933 vs. 0.0499 random baseline (1.87x lift)

## Known gaps

- No training timestamp is currently recorded by the pipeline scripts — this manifest reflects the
  numbers as of the last time `Description.MD` was updated, not an automated run log.
- The train/val/test split is review-level (see above), so it does not test generalization to
  professors unseen during training. A professor-disjoint split is a possible future improvement.
