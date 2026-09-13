# ProfIQ Hosting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ProfIQ deployable to free-tier infrastructure (Vercel + Google Cloud Run + Neon Postgres) via manual, locally-triggered deploy scripts — no CI/CD, no secrets in git.

**Architecture:** Two independent readiness changes to the tracked codebase (Django static-file serving + Postgres SSL + CORS config; frontend API base URL made configurable at build time), plus a `.env.deploy` contract and three gitignored shell scripts that wrap `gcloud`/`vercel`/`manage.py` commands. This plan produces and locally verifies all the code/config — it does **not** perform an actual cloud deployment. Actually running `deploy.sh` requires the user to first: install the `gcloud` and `vercel` CLIs (neither is installed on this machine), create a GCP project, create a Neon Postgres project, and populate real values in `backend/.env.deploy`. Those are manual account-setup steps outside this plan's scope.

**Tech Stack:** Django 5 + DRF (backend), WhiteNoise (static files), React/Vite (frontend), bash (deploy scripts).

**Spec:** `docs/superpowers/specs/2026-09-13-hosting-design.md`

## Global Constraints

- Free/cheapest tier only: Vercel (frontend), Google Cloud Run (backend), Neon Postgres (database) — no paid tiers, no Load Balancer.
- Manual deploys only, triggered locally. No GitHub Actions / CI/CD.
- `backend/.env.deploy` (real secrets) must never be committed — gitignored.
- `backend/deploy.sh`, `frontend/deploy.sh`, `backend/migrate-remote.sh` are one-off local convenience wrappers — gitignored, never committed.
- `backend/.env.deploy.example`, all application code changes (`settings.py`, `requirements.txt`, `frontend/src/lib/api.js`, `README.md`), and `.gitignore` itself ARE committed normally — no secrets in any of them.
- `backend/Dockerfile` and `backend/.dockerignore` are already committed on the public repo — this is fine, no change needed (user confirmed 2026-09-13).
- Domain: `smafnanhaider.com` (+`www`) goes on Vercel for the frontend. The backend stays on its default `*.run.app` URL — no custom domain for Cloud Run.

---

### Task 1: Backend production readiness (WhiteNoise, Postgres SSL, CORS env var)

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/recommender/settings.py`

**Interfaces:**
- Produces: `STATIC_ROOT` (used by `collectstatic` and the Dockerfile's `RUN python manage.py collectstatic --noinput` step), `CORS_EXTRA_ORIGINS` env var (comma-separated, read by `deploy.sh` in Task 4).

- [ ] **Step 1: Add `gunicorn` and `whitenoise` to requirements.txt**

The Dockerfile (already committed) runs `gunicorn recommender.wsgi:application` as its `CMD`, but `gunicorn` is not in `requirements.txt` — the current Docker image would fail to start. Fix by editing `backend/requirements.txt`:

```diff
 Django>=5.0,<5.3
 djangorestframework==3.15.2
 django-cors-headers==4.4.0
 nltk==3.9.1
 pandas>=2.2.0
 python-dotenv==1.0.1
 requests>=2.32.0
 beautifulsoup4>=4.12.0
 praw>=7.7.1
+gunicorn>=22.0.0
+whitenoise>=6.7.0
```

- [ ] **Step 2: Install the new dependencies locally**

```bash
cd backend
pip install gunicorn whitenoise
```

- [ ] **Step 3: Verify install**

```bash
python -c "import gunicorn, whitenoise; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Add `STATIC_ROOT` and WhiteNoise storage config to settings.py**

`collectstatic` currently fails with `ImproperlyConfigured: You're using the staticfiles app without having set the STATIC_ROOT setting` — verified by running `python manage.py collectstatic --noinput` before this change. Edit `backend/recommender/settings.py`:

```diff
 STATIC_URL = "static/"
+STATIC_ROOT = BASE_DIR / "staticfiles"
 DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
+
+STORAGES = {
+    "default": {
+        "BACKEND": "django.core.files.storage.FileSystemStorage",
+    },
+    "staticfiles": {
+        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
+    },
+}
```

- [ ] **Step 5: Add WhiteNoiseMiddleware**

WhiteNoise must sit directly after `SecurityMiddleware` (per WhiteNoise's own docs) so it can serve static files before any other middleware runs. Edit `backend/recommender/settings.py`:

```diff
 MIDDLEWARE = [
     "corsheaders.middleware.CorsMiddleware",
     "django.middleware.security.SecurityMiddleware",
+    "whitenoise.middleware.WhiteNoiseMiddleware",
     "django.contrib.sessions.middleware.SessionMiddleware",
```

- [ ] **Step 6: Require TLS on the Postgres connection**

Neon requires `sslmode=require`. Edit `backend/recommender/settings.py`:

```diff
 if os.environ.get("USE_POSTGRES") == "1":
     DATABASES = {
         "default": {
             "ENGINE": "django.db.backends.postgresql",
             "NAME": os.environ.get("DB_NAME", "recommender"),
             "USER": os.environ.get("DB_USER", "postgres"),
             "PASSWORD": os.environ.get("DB_PASSWORD", ""),
             "HOST": os.environ.get("DB_HOST", "localhost"),
             "PORT": os.environ.get("DB_PORT", "5432"),
+            "OPTIONS": {"sslmode": "require"},
         }
     }
```

- [ ] **Step 7: Allow extra CORS origins via env var**

Edit `backend/recommender/settings.py`:

```diff
 # CORS — allow the Vite dev server during development
 CORS_ALLOWED_ORIGINS = [
     "http://localhost:5173",
     "http://127.0.0.1:5173",
 ]
+_extra_origins = os.environ.get("CORS_EXTRA_ORIGINS", "")
+if _extra_origins:
+    CORS_ALLOWED_ORIGINS += [o.strip() for o in _extra_origins.split(",") if o.strip()]
 CORS_ALLOW_ALL_ORIGINS = DEBUG
```

- [ ] **Step 8: Verify with manage.py check**

```bash
cd backend
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 9: Verify collectstatic now works**

```bash
cd backend
python manage.py collectstatic --noinput
```

Expected: succeeds (no `ImproperlyConfigured` error), prints a count of copied files, and creates `backend/staticfiles/`.

- [ ] **Step 10: Run the existing backend test suite to confirm no regression**

```bash
cd backend
python manage.py test
python3 -m unittest sentiment.tests -v
```

Expected: all tests pass, same as before this change.

- [ ] **Step 11: Commit**

```bash
git add backend/requirements.txt backend/recommender/settings.py
git commit -m "feat: production-ready backend settings (whitenoise, postgres ssl, cors env var)"
```

---

### Task 2: Frontend API base URL configurable at build time

**Files:**
- Modify: `frontend/src/lib/api.js:1`

**Interfaces:**
- Consumes: nothing new.
- Produces: `VITE_API_BASE_URL` build-time env var, read by `frontend/deploy.sh` (Task 5).

- [ ] **Step 1: Make `BASE` read the env var with a dev-safe fallback**

The current hardcoded `"/api"` only works because `vite.config.js` proxies `/api` to `http://127.0.0.1:8000` in dev. In production there is no dev-server proxy, so the built frontend needs an absolute backend URL. Edit `frontend/src/lib/api.js`:

```diff
-const BASE = "/api";
+const BASE = import.meta.env.VITE_API_BASE_URL || "/api";
```

- [ ] **Step 2: Verify the default (no env var) build still targets `/api`**

```bash
cd frontend
rm -rf dist
npm run build
grep -o '"/api"' dist/assets/*.js | head -1
```

Expected: prints `"/api"` — confirms local/dev-proxy behavior is unchanged when `VITE_API_BASE_URL` isn't set.

- [ ] **Step 3: Verify a custom base URL gets baked into the build**

```bash
cd frontend
rm -rf dist
VITE_API_BASE_URL="https://profiq-backend-test.a.run.app/api" npm run build
grep -o 'https://profiq-backend-test\.a\.run\.app/api' dist/assets/*.js | head -1
```

Expected: prints the URL — confirms it's compiled into the bundle correctly.

- [ ] **Step 4: Clean up the test build**

```bash
cd frontend
rm -rf dist
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.js
git commit -m "feat: read API base URL from VITE_API_BASE_URL at build time"
```

---

### Task 3: Deploy secrets contract (.env.deploy.example + .gitignore)

**Files:**
- Create: `backend/.env.deploy.example`
- Modify: `.gitignore`

**Interfaces:**
- Produces: the full list of env var names (`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `USE_POSTGRES`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `CORS_EXTRA_ORIGINS`, `GCP_PROJECT_ID`, `GCP_REGION`, `CLOUD_RUN_SERVICE`, `VITE_API_BASE_URL`) that Tasks 4-6's scripts source from `backend/.env.deploy`.

- [ ] **Step 1: Add gitignore entries**

Edit `.gitignore`, appending a new section:

```diff
 # IDE
 .idea/
 .vscode/
+
+# Deploy artifacts (see docs/superpowers/specs/2026-09-13-hosting-design.md)
+backend/staticfiles/
+backend/.env.deploy
```

- [ ] **Step 2: Create the example env file**

Create `backend/.env.deploy.example`:

```bash
# Copy this file to backend/.env.deploy and fill in real values.
# backend/.env.deploy is gitignored — never commit real secrets.

# Django
DJANGO_SECRET_KEY=
DJANGO_DEBUG=0

# Postgres (Neon) — see https://neon.tech
USE_POSTGRES=1
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=5432

# CORS — comma-separated list of allowed frontend origins.
# Add the Vercel URL after Task 5's first deploy, and smafnanhaider.com once DNS is live.
CORS_EXTRA_ORIGINS=https://smafnanhaider.com,https://www.smafnanhaider.com

# Google Cloud Run
GCP_PROJECT_ID=
GCP_REGION=us-central1
CLOUD_RUN_SERVICE=profiq-backend

# Frontend build — set to the Cloud Run service URL after Task 4's first deploy
VITE_API_BASE_URL=
```

- [ ] **Step 3: Verify .env.deploy is actually ignored**

```bash
touch backend/.env.deploy
git check-ignore -v backend/.env.deploy
rm backend/.env.deploy
```

Expected: prints the matching `.gitignore` line (`.gitignore:<N>:backend/.env.deploy backend/.env.deploy`), confirming it's ignored.

- [ ] **Step 4: Verify staticfiles/ is ignored**

```bash
mkdir -p backend/staticfiles
git check-ignore -v backend/staticfiles/
rm -rf backend/staticfiles
```

Expected: prints the matching `.gitignore` line.

- [ ] **Step 5: Verify .env.deploy.example is NOT ignored (it should be committable)**

```bash
git check-ignore -v backend/.env.deploy.example; echo "exit code: $?"
```

Expected: no output, exit code `1` (not ignored).

- [ ] **Step 6: Commit**

```bash
git add .gitignore backend/.env.deploy.example
git commit -m "chore: add deploy env var contract and gitignore secrets/static output"
```

---

### Task 4: Backend deploy script

**Files:**
- Create: `backend/deploy.sh` (gitignored, not committed)

**Interfaces:**
- Consumes: `backend/.env.deploy` (Task 3's contract).
- Produces: a running Cloud Run service; prints its URL for use as `VITE_API_BASE_URL` in Task 5.

- [ ] **Step 1: Write the script**

Create `backend/deploy.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env.deploy ]; then
  echo "Missing backend/.env.deploy — copy .env.deploy.example and fill in real values." >&2
  exit 1
fi
set -a
source .env.deploy
set +a

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env.deploy}"
: "${DJANGO_SECRET_KEY:?Set DJANGO_SECRET_KEY in .env.deploy}"
GCP_REGION="${GCP_REGION:-us-central1}"
CLOUD_RUN_SERVICE="${CLOUD_RUN_SERVICE:-profiq-backend}"

gcloud run deploy "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --source . \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --allow-unauthenticated \
  --set-env-vars "DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY},DJANGO_DEBUG=0,USE_POSTGRES=1,DB_NAME=${DB_NAME:-},DB_USER=${DB_USER:-},DB_PASSWORD=${DB_PASSWORD:-},DB_HOST=${DB_HOST:-},DB_PORT=${DB_PORT:-5432},CORS_EXTRA_ORIGINS=${CORS_EXTRA_ORIGINS:-}"

echo "Deployed. Service URL:"
gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --format='value(status.url)'
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x backend/deploy.sh
```

- [ ] **Step 3: Syntax-check it (cannot run it for real — gcloud CLI isn't installed and no GCP project exists yet)**

```bash
bash -n backend/deploy.sh
```

Expected: no output (exit code 0) — confirms valid bash syntax.

- [ ] **Step 4: Verify the missing-.env.deploy guard works**

```bash
cd backend
mv .env.deploy .env.deploy.bak 2>/dev/null || true
./deploy.sh; echo "exit code: $?"
mv .env.deploy.bak .env.deploy 2>/dev/null || true
```

Expected: prints `Missing backend/.env.deploy...` and exits non-zero, without attempting to call `gcloud`.

- [ ] **Step 5: No commit — leave this file untracked**

`backend/deploy.sh` isn't matched by any `.gitignore` pattern (only `.env.deploy` and `staticfiles/` are) — it stays local-only by convention, not enforcement. Verify it shows as untracked and do not `git add` it:

```bash
git status --short backend/deploy.sh
```

Expected: `?? backend/deploy.sh`.

---

### Task 5: Frontend deploy script

**Files:**
- Create: `frontend/deploy.sh` (not committed)

**Interfaces:**
- Consumes: `backend/.env.deploy` (specifically `VITE_API_BASE_URL`, filled in after Task 4's first real deploy).
- Produces: a live Vercel deployment; its URL gets added to `CORS_EXTRA_ORIGINS` and the backend redeployed (Task 4, run again).

- [ ] **Step 1: Write the script**

Create `frontend/deploy.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE="../backend/.env.deploy"
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing backend/.env.deploy — copy backend/.env.deploy.example and fill in real values." >&2
  exit 1
fi
set -a
source "$ENV_FILE"
set +a

: "${VITE_API_BASE_URL:?Set VITE_API_BASE_URL in backend/.env.deploy to the Cloud Run service URL (run backend/deploy.sh first)}"

npx vercel --prod --yes --build-env VITE_API_BASE_URL="$VITE_API_BASE_URL"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x frontend/deploy.sh
```

- [ ] **Step 3: Syntax-check it (cannot run it for real — vercel CLI isn't installed and no Vercel project is linked yet)**

```bash
bash -n frontend/deploy.sh
```

Expected: no output (exit code 0).

- [ ] **Step 4: Verify the missing-env-var guard works**

```bash
cd frontend
mv ../backend/.env.deploy ../backend/.env.deploy.bak 2>/dev/null || true
./deploy.sh; echo "exit code: $?"
mv ../backend/.env.deploy.bak ../backend/.env.deploy 2>/dev/null || true
```

Expected: prints `Missing backend/.env.deploy...` and exits non-zero.

- [ ] **Step 5: No commit — local-only script, leave untracked (same as Task 4 Step 5)**

---

### Task 6: Remote migrate/seed script

**Files:**
- Create: `backend/migrate-remote.sh` (not committed)

**Interfaces:**
- Consumes: `backend/.env.deploy`.
- Produces: migrated + seeded Neon database, run once after the first successful backend deploy.

- [ ] **Step 1: Write the script**

Create `backend/migrate-remote.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env.deploy ]; then
  echo "Missing backend/.env.deploy — copy .env.deploy.example and fill in real values." >&2
  exit 1
fi
set -a
source .env.deploy
set +a

export USE_POSTGRES=1
: "${DB_HOST:?Set DB_HOST in .env.deploy}"

python manage.py migrate
python manage.py ingest_seed --reset
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x backend/migrate-remote.sh
```

- [ ] **Step 3: Syntax-check it (cannot run it for real — no Neon database exists yet)**

```bash
bash -n backend/migrate-remote.sh
```

Expected: no output (exit code 0).

- [ ] **Step 4: Verify the missing-.env.deploy guard works**

```bash
cd backend
mv .env.deploy .env.deploy.bak 2>/dev/null || true
./migrate-remote.sh; echo "exit code: $?"
mv .env.deploy.bak .env.deploy 2>/dev/null || true
```

Expected: prints `Missing backend/.env.deploy...` and exits non-zero.

- [ ] **Step 5: No commit — local-only script, leave untracked (same as Task 4 Step 5)**

---

### Task 7: README Deployment section

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: exact filenames/commands from Tasks 3-6 (`backend/.env.deploy.example`, `backend/deploy.sh`, `frontend/deploy.sh`, `backend/migrate-remote.sh`).

- [ ] **Step 1: Add the section**

Edit `README.md`, inserting before `## Notes`:

```diff
 ## Demo

 Demo video:

 ```text
 https://youtu.be/o1A1l2W680g?si=4a1GuE1157LvYent
 ```

+## Deployment
+
+ProfIQ deploys manually (no CI/CD) to free-tier infrastructure: Vercel (frontend), Google Cloud
+Run (backend), Neon Postgres (database). Full design rationale in
+`docs/superpowers/specs/2026-09-13-hosting-design.md`.
+
+1. Copy `backend/.env.deploy.example` to `backend/.env.deploy` and fill in real values (Neon
+   credentials, a generated `DJANGO_SECRET_KEY`, your GCP project ID).
+2. Deploy the backend: `cd backend && ./deploy.sh`. Note the printed Cloud Run URL.
+3. Add that URL as `VITE_API_BASE_URL` in `backend/.env.deploy`, then deploy the frontend:
+   `cd frontend && ./deploy.sh`. Note the printed Vercel URL.
+4. Add the Vercel URL to `CORS_EXTRA_ORIGINS` in `backend/.env.deploy` (alongside
+   `smafnanhaider.com`), then re-run `cd backend && ./deploy.sh`.
+5. Run database migrations and seed data once: `cd backend && ./migrate-remote.sh`.
+6. In the Vercel dashboard, add `smafnanhaider.com` and `www.smafnanhaider.com` as custom
+   domains and point your registrar's DNS at Vercel per its instructions. The backend keeps its
+   default `*.run.app` URL — no custom domain needed there.
+
+`deploy.sh` (backend and frontend) and `migrate-remote.sh` are gitignored, local-only
+convenience scripts — see `backend/.env.deploy.example` for the full list of required
+environment variables.
+
 ## Notes
```

- [ ] **Step 2: Verify referenced files actually exist**

```bash
test -f backend/.env.deploy.example && echo "env example: ok"
test -f backend/deploy.sh && echo "backend deploy script: ok"
test -f frontend/deploy.sh && echo "frontend deploy script: ok"
test -f backend/migrate-remote.sh && echo "migrate script: ok"
```

Expected: all four print `ok`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add deployment instructions"
```

---

## Self-Review Notes

- **Spec coverage:** Every "still to build" item from the spec has a task — settings.py/requirements.txt (Task 1), api.js (Task 2), .env.deploy.example + .gitignore (Task 3), deploy.sh (Task 4), frontend/deploy.sh (Task 5), migrate-remote.sh (Task 6), README (Task 7). The Domain decision (Vercel custom domain, backend on default URL) is documented in Task 7's README section and Task 3's `.env.deploy.example` comment rather than needing its own task, since it's a dashboard action (adding a domain in Vercel's UI) with no code artifact.
- **Not in scope (flagged, not silently skipped):** actually running any deploy script against real GCP/Vercel/Neon infrastructure. That requires the user to install `gcloud`/`vercel` CLIs and create accounts/projects first — ask the user whether they want help with that account setup as a follow-up once this plan's tasks are done.
- **Task 4/5/6 commit steps are intentionally "no commit"** — these three scripts are meant to stay untracked per the spec's constraint (they're not matched by any `.gitignore` pattern; untracked-by-convention rather than by enforcement). Flagged explicitly in each task rather than using the standard commit step, so an executor doesn't reflexively `git add` them.
