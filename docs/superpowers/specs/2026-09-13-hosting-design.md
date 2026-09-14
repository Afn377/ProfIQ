# ProfIQ Hosting — Design Spec

Status: implementation plan (`docs/superpowers/plans/2026-09-13-hosting-implementation.md`) executed
and committed 2026-09-13 — backend readiness (WhiteNoise/SSL/CORS/proxy-headers), frontend env var,
`.env.deploy.example`, deploy scripts, README section, `.gcloudignore`, `vercel.json` all shipped.
gcloud + vercel CLIs installed locally 2026-09-14. Revised 2026-09-14: database switched from Neon
to CockroachDB Serverless (see "Database capacity revision" below) — settings.py/requirements/docs
update for this is in progress. Not yet actually deployed to real infrastructure (no GCP/CockroachDB
accounts created yet).
Classification: architectural (new deployment subsystem, no existing deploy flow in repo).

## Goal

Get ProfIQ (Django/DRF backend + React/Vite frontend + Postgres + sentiment/recommender ML)
hosted on free/cheapest-tier infrastructure, with manual (non-CI/CD) deploys triggered locally,
and with zero hosting/deploy tooling committed to the remote GitHub repo.

## Standing constraint

The user has asked that hosting/deploy *secrets and scripts* never reach the remote repo. This
still rules out GitHub Actions CI/CD and any committed file containing real credentials. Revised
2026-09-13: the Dockerfile/.dockerignore pair is explicitly exempted — the user confirmed they're
fine committed on the public repo, no gitignoring needed. The constraint now applies specifically
to: `.env.deploy` (real secrets, must never be committed) and the three deploy shell scripts
(`deploy.sh`, `frontend/deploy.sh`, `migrate-remote.sh`) — kept local/gitignored since they're
one-off convenience wrappers, not something the repo needs to document.

## Platform decisions (already researched + decided)

Verified against current (2026) pricing/limits via live web search, not stale training data:

- **Frontend → Vercel** (free tier). Trivial static Vite/React build.
- **Database → CockroachDB Serverless** (free "Basic" tier: 10GB storage, $15/mo-equivalent free
  request-unit allowance, Postgres-wire-compatible). Superseded Neon — see "Database capacity
  revision" below. Uses the `django-cockroachdb` adapter (not plain `django.db.backends.postgresql`)
  since CockroachDB has real behavioral differences from Postgres despite wire compatibility.
- **Backend → Google Cloud Run** (free tier: 2M requests/mo, 360k vCPU-sec/mo,
  180k GiB-sec/mo, scales to zero when idle). Chosen over:
  - **Render free** — 512MB RAM, too tight once `sentence-transformers`/torch loads.
  - **Fly.io** — killed its free tier in Oct 2024; pure pay-as-you-go now.
  - **Railway** — free tier now effectively $1+/mo after a 30-day trial.
  - **Hugging Face Spaces** — Docker Space *creation* now requires a paid (PRO) plan as of 2026;
    free tier is Gradio/ZeroGPU only, not suited to a Django REST backend.

### Why Cloud Run's memory needs are modest

Per the graphify knowledge-graph trace of this codebase: the *live* sentiment path is VADER
(pure Python) plus an optional lightweight TF-IDF/LogReg classifier. DistilBERT
(`backend/sentiment/ml/train_bert.py`) is training/evaluation-only and never loads in the running
app (`Decision: Separate Offline ML from Online App`). Only the "similar professors" feature
lazily loads a MiniLM sentence-transformer (`backend/sentiment/ml/recommender.py`) on first use.
So 1-2 GiB of Cloud Run memory is sufficient — no need to provision for a full
Transformers+DistilBERT footprint.

## Database capacity revision (2026-09-14)

The original "Initial data: small demo seed" decision below is superseded. The user wants the
**full RMP professor catalog searchable in production** (~1.7M professors), not a demo seed.

**Why Neon doesn't work for this:** the local catalog was originally crawled to completion
(~1,702,454 professors, confirmed by an April canary scan) but a later `ingest_seed --reset`
wiped it; only 1,026,926 were recovered (see `data/rmp_gap_scan_checkpoint.json` /
`detect_rmp_gaps` command for the reconciliation effort in progress to restore the rest).
Estimating Postgres storage for the `Professor` table at full catalog size (~86 bytes raw content
per row, 4 btree indexes — `id` PK, `name`, `institution`, `external_ref`, all `db_index=True`)
lands around 450-500MB — Neon's entire free-tier budget (0.5GB/project), before `ProfessorStats`,
Django system tables, or MVCC bloat from the upsert-heavy crawl.

**Options considered:** Neon free tier (rejected — capacity), Neon paid tier (rejected — breaks
the "free tier only" constraint), self-hosted Postgres on Oracle Cloud Always Free (200GB storage,
rejected — trades vendor-managed backups/security/networking for full sysadmin ownership, too much
overhead for a class project), CockroachDB Serverless free tier (**chosen** — 10GB storage, 20x
Neon's cap, Postgres-wire-compatible, smallest change to the already-built deploy plan).

**Consequence for `settings.py`:** `ENGINE` changes from `django.db.backends.postgresql` to
`django_cockroachdb` (a dedicated adapter, not the plain psycopg backend — CockroachDB has real
behavioral differences despite wire compatibility). Default port changes from `5432` to `26257`.
SSL changes from `sslmode=require` to `sslmode=verify-full` + `sslrootcert` pointing at a CA
certificate downloaded from the CockroachDB Cloud console when the cluster is created (public
cert, safe to commit — lives at `backend/certs/cockroachdb-ca.crt`, not created yet since no
CockroachDB account exists yet).

**Not yet addressed (follow-up, not part of this revision):** how to actually load ~1.7M rows
from the local SQLite catalog into the remote CockroachDB instance once it exists — a direct
`pg_dump`/`pg_restore` isn't available (local DB is SQLite), so this needs either a batched
Django `bulk_create` migration script or a JSON export/import step. Deferred until the local
catalog reconciliation (gap-scan + re-crawl, running in the background as of 2026-09-14) finishes
and a CockroachDB cluster actually exists to load into.

## Deploy mechanics (this session's decisions)

| Question | Decision |
|---|---|
| CI/CD vs manual | Manual only, triggered from your machine (or by Claude, with your go-ahead each time). No GitHub Actions. |
| Secrets | Local gitignored `backend/.env.deploy` holding real values; a deploy script sources it and passes `--set-env-vars` to `gcloud run deploy`. Never retype secrets, never commit them. |
| DB migrate/seed | Run locally: point `manage.py` at CockroachDB via the same `.env.deploy` credentials (`USE_POSTGRES=1`) and run `migrate` from your machine. No Cloud Run Job. |
| Initial data | Superseded 2026-09-14 — see "Database capacity revision" above. Full RMP catalog (~1.7M professors), not a demo seed. Load mechanism still to be designed. |
| Domain | `profiq.smafnanhaider.com` (subdomain, not the apex — changed 2026-09-14 per user request) mapped to Vercel for the frontend — free, unmetered on Hobby, automatic Let's Encrypt SSL. Backend stays on its default `*.run.app` URL; not worth custom-domaining (Google's recommended path needs a paid Load Balancer, and Cloud Run's free native domain mapping is still preview-grade/not production-ready). Frontend already reads the backend URL via `VITE_API_BASE_URL` and CORS already allows arbitrary origins via `CORS_EXTRA_ORIGINS`, so the plain `run.app` URL costs nothing functionally. |

## Implementation status (2026-09-14)

Everything below was built via `docs/superpowers/plans/2026-09-13-hosting-implementation.md`
(subagent-driven-development, DeepSeek implementer + per-task review + a final whole-branch
review that caught 3 Critical + 5 Important cross-task bugs, all fixed) and is committed on
`main`: `backend/Dockerfile`/`.dockerignore`/`.gcloudignore`, `backend/recommender/settings.py`
(WhiteNoise, `STORAGES`, Postgres SSL, `CORS_EXTRA_ORIGINS`, `SECURE_PROXY_SSL_HEADER`,
`CSRF_TRUSTED_ORIGINS`), `backend/requirements.txt` (`gunicorn`, `whitenoise`),
`frontend/src/lib/api.js` (`VITE_API_BASE_URL`), `frontend/vercel.json` (SPA rewrite),
`backend/.env.deploy.example`, `.gitignore`, README's "## Deployment" section, and the three
gitignored local-only deploy scripts (`backend/deploy.sh`, `frontend/deploy.sh`,
`backend/migrate-remote.sh`).

**Still needed** (tracked as a fresh, smaller change, not a new full plan — see "Database
capacity revision" above): swap `settings.py`'s Postgres config from Neon-shaped to CockroachDB-
shaped (`django_cockroachdb` engine, port 26257, `sslmode=verify-full`), add `django-cockroachdb`
to `requirements-postgres.txt`, update `.env.deploy.example`/README/deploy scripts' Neon
references to CockroachDB, and (later, once accounts exist) design the full-catalog data-load
step.

## Verification checklist (post-deploy, in lieu of automated tests — this is infra, not app code)

1. Script echoes the Cloud Run service URL and the Vercel deployment URL.
2. `curl <cloud-run-url>/api/summary/` returns JSON, not an error.
3. Load the Vercel site in a browser; confirm it fetches data (not stuck on a loading state).
4. Run a search query end-to-end; confirm results render.
5. Check the browser console for CORS errors — if present, confirm `CORS_EXTRA_ORIGINS` on
   Cloud Run matches the real Vercel URL exactly (scheme + host, no trailing slash).
6. Note expected first-hit latency: Cloud Run cold start + (on first "similar professors" call)
   a lazy MiniLM download from Hugging Face Hub. Slow is expected, not a bug.

## Next step when resumed

The original implementation plan is done (see "Implementation status" above). The
CockroachDB-vs-Neon swap is small and well-scoped enough to implement directly against this spec
(no separate plan document needed) — settings.py/requirements-postgres.txt/.env.deploy.example/
README/deploy-script edits, dispatched to DeepSeek per the user's standing instruction, reviewed,
committed. After that: install CLIs (done 2026-09-14), create GCP/Vercel/CockroachDB accounts
(user action, pending), then actually run the deploy scripts for the first time.
