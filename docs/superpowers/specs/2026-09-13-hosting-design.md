# ProfIQ Hosting — Design Spec

Status: approved by user, not yet implemented (deploy scripts / .env.deploy not yet written).
Classification: architectural (new deployment subsystem, no existing deploy flow in repo).

## Goal

Get ProfIQ (Django/DRF backend + React/Vite frontend + Postgres + sentiment/recommender ML)
hosted on free/cheapest-tier infrastructure, with manual (non-CI/CD) deploys triggered locally,
and with zero hosting/deploy tooling committed to the remote GitHub repo.

## Standing constraint

The user has explicitly and repeatedly asked that hosting/deploy scaffolding never reach the
remote repo. This is the dominant constraint on the design — it rules out GitHub Actions CI/CD
and shapes which new files get gitignored vs. committed. Treat this as durable, not a one-off
for the initial round of changes.

## Platform decisions (already researched + decided)

Verified against current (2026) pricing/limits via live web search, not stale training data:

- **Frontend → Vercel** (free tier). Trivial static Vite/React build.
- **Database → Neon Postgres** (free tier: 0.5GB storage/project, autoscale to 8GB compute,
  suspends after 5 min idle, permanent free tier, no credit card). Matches the
  "PostgreSQL for Scale" decision already present in the codebase (psycopg already an optional
  dependency via `backend/requirements-postgres.txt`).
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

## Deploy mechanics (this session's decisions)

| Question | Decision |
|---|---|
| CI/CD vs manual | Manual only, triggered from your machine (or by Claude, with your go-ahead each time). No GitHub Actions. |
| Secrets | Local gitignored `backend/.env.deploy` holding real values; a deploy script sources it and passes `--set-env-vars` to `gcloud run deploy`. Never retype secrets, never commit them. |
| DB migrate/seed | Run locally: point `manage.py` at Neon via the same `.env.deploy` credentials (`USE_POSTGRES=1`) and run `migrate` / `ingest_seed --reset` from your machine. No Cloud Run Job. |
| Initial data | Small demo seed (`ingest_seed --reset` against `backend/data/seed_reviews.json`), not a full RMP crawl. |
| Domain | `smafnanhaider.com` (+ `www`) mapped to Vercel for the frontend — free, unmetered on Hobby, automatic Let's Encrypt SSL. Backend stays on its default `*.run.app` URL; not worth custom-domaining (Google's recommended path needs a paid Load Balancer, and Cloud Run's free native domain mapping is still preview-grade/not production-ready). Frontend already reads the backend URL via `VITE_API_BASE_URL` and CORS already allows arbitrary origins via `CORS_EXTRA_ORIGINS`, so the plain `run.app` URL costs nothing functionally. |

## Already implemented (uncommitted, local-only — done in an earlier part of this session)

These exist on disk right now and were verified (`manage.py check`, `collectstatic`) but are
**not committed**, per the standing constraint:

- `backend/Dockerfile` — python:3.12-slim, installs `requirements.txt` +
  `requirements-postgres.txt`, runs `collectstatic`, serves via gunicorn on `$PORT`. Gitignored.
- `backend/.dockerignore`. Gitignored.
- `backend/recommender/settings.py` — added WhiteNoise middleware + `STORAGES` config,
  `sslmode=require` for Postgres (Neon requires TLS), `CORS_EXTRA_ORIGINS` env var
  (comma-separated) merged into `CORS_ALLOWED_ORIGINS`. **This file is tracked** — the edit is
  an uncommitted working-tree change, left that way deliberately (see note below).
- `backend/requirements.txt` — added `gunicorn`, `whitenoise`. Tracked, uncommitted.
- `frontend/src/lib/api.js` — `BASE` now reads `import.meta.env.VITE_API_BASE_URL` at build
  time instead of hardcoding `/api` (which only worked via the Vite dev-server proxy). Tracked,
  uncommitted.
- `README.md` — added a "Deployment" section documenting the `gcloud run deploy` / `vercel --prod`
  commands and required env vars. Tracked, uncommitted.
- `.gitignore` — added entries for `backend/staticfiles/`, `graphify-out/`, `backend/Dockerfile`,
  `backend/.dockerignore`.

Note on the tracked-file edits (`settings.py`, `requirements.txt`, `api.js`, `README.md`,
`.gitignore`): these can't be gitignored since they're already tracked. They're being kept as
plain uncommitted working-tree changes — safe, since nothing reaches the remote unless someone
runs `git add`/`commit`/`push`. Whether to eventually commit these (they contain no secrets,
just config plumbing) is an open question for the user to decide later; default so far has been
"leave uncommitted, don't ask again mid-task."

## Still to build (not yet written)

- `backend/.env.deploy` — real secrets (Neon host/user/password/db name, a generated
  `DJANGO_SECRET_KEY`, the eventual Vercel URL for CORS). Gitignored, never committed.
- `backend/.env.deploy.example` — a template with key names only, no values. Proposed as the
  **one** file in this whole set that might actually get committed (so the repo documents what
  env vars deploy needs) — flagged to the user as a suggestion, not yet confirmed. Default to
  gitignoring this too, like everything else, unless the user says otherwise.
- `backend/deploy.sh` — sources `.env.deploy`, runs `gcloud run deploy profiq-backend --source .`
  with `--memory 2Gi --cpu 2 --timeout 300 --allow-unauthenticated` and the env vars from the
  file.
- `frontend/deploy.sh` — runs `vercel --prod` with `VITE_API_BASE_URL` set to the Cloud Run URL.
- `backend/migrate-remote.sh` — sources `.env.deploy`, exports `USE_POSTGRES=1` + `DB_*`, runs
  `manage.py migrate` then `manage.py ingest_seed --reset` against Neon.

All three scripts: local-only, gitignored, same treatment as the Dockerfile.

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

Per the brainstorming skill's architectural path, the next step after this spec is approved is
to invoke the **writing-plans** skill to turn "still to build" above into a concrete
implementation plan (the three shell scripts + the `.env.deploy.example` template), then execute
it. Do not jump straight to writing the scripts without going through writing-plans first, per
the skill's terminal-state rule.
