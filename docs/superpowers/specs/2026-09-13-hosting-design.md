# ProfIQ Hosting — Design Spec

Status: approved by user. Dockerfile/.dockerignore committed and pushed; everything else
(settings.py/requirements.txt/api.js/README edits, .env.deploy(.example), deploy scripts)
still needs to be written — see "Actually implemented" below, corrected 2026-09-13.
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

## Actually implemented (verified 2026-09-13, corrects earlier stale claims in this doc)

This session's git history rewrites (report-generation purge, repo delete/recreate) reset the
working tree to whatever was last actually committed, which turned out to be less than this spec
previously claimed. Re-verified against the real files on disk:

- `backend/Dockerfile` — exists, committed, pushed to the public repo. Per the revised standing
  constraint above, this is fine as-is.
- `backend/.dockerignore` — same: exists, committed, pushed. Fine as-is.
- `backend/recommender/settings.py` — **NOT actually edited.** No WhiteNoise, no `STORAGES`
  config, no `sslmode=require`, no `CORS_EXTRA_ORIGINS`. Still needs to be written.
- `backend/requirements.txt` — **NOT actually edited.** No `gunicorn`, no `whitenoise`. Still
  needs to be added.
- `frontend/src/lib/api.js` — **NOT actually edited.** `BASE` is still hardcoded to `"/api"`.
  Still needs the `VITE_API_BASE_URL` change.
- `README.md` — **NOT actually edited.** No "Deployment" section exists. Still needs to be
  written.
- `.gitignore` — **NOT actually edited.** None of the previously-claimed entries exist.

## Still to build (not yet written)

- `backend/recommender/settings.py` edits — WhiteNoise middleware + `STORAGES` config,
  `sslmode=require` for Postgres (Neon requires TLS), `CORS_EXTRA_ORIGINS` env var
  (comma-separated) merged into `CORS_ALLOWED_ORIGINS`. Tracked file, fine to commit (no secrets,
  just config plumbing).
- `backend/requirements.txt` — add `gunicorn`, `whitenoise`. Tracked, fine to commit.
- `frontend/src/lib/api.js` — `BASE` reads `import.meta.env.VITE_API_BASE_URL` at build time
  instead of hardcoding `/api`. Tracked, fine to commit.
- `README.md` — add a "Deployment" section documenting the `gcloud run deploy` / `vercel --prod`
  commands and required env vars. Tracked, fine to commit.
- `backend/.env.deploy` — real secrets (Neon host/user/password/db name, a generated
  `DJANGO_SECRET_KEY`, the eventual Vercel URL for CORS). Gitignored, never committed.
- `backend/.env.deploy.example` — a template with key names only, no values. This one should be
  committed, so the repo documents what env vars deploy needs.
- `backend/deploy.sh` — sources `.env.deploy`, runs `gcloud run deploy profiq-backend --source .`
  with `--memory 2Gi --cpu 2 --timeout 300 --allow-unauthenticated` and the env vars from the
  file. Local-only, gitignored (one-off convenience wrapper, not documentation).
- `frontend/deploy.sh` — runs `vercel --prod` with `VITE_API_BASE_URL` set to the Cloud Run URL.
  Local-only, gitignored.
- `backend/migrate-remote.sh` — sources `.env.deploy`, exports `USE_POSTGRES=1` + `DB_*`, runs
  `manage.py migrate` then `manage.py ingest_seed --reset` against Neon. Local-only, gitignored.
- `.gitignore` — add entries for `backend/staticfiles/` (build artifact) and `backend/.env.deploy`
  (secrets). `graphify-out/` is a separate tool's output, unrelated to hosting — leave it out of
  this change unless the user asks.

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
