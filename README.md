# ProfIQ

ProfIQ is a professor search and comparison web app. It uses a Django backend and a React frontend to help students look up professors, view review-based sentiment, see common review themes, find similar professors, and compare multiple professors side by side.

## Project Structure

```text
backend/   Django API, database models, scrapers, sentiment analysis, ML helpers
frontend/  React/Vite user interface
notebooks/ ML evaluation notebook
```

## Main Features

- Search professors by name, school, department, or course.
- View professor detail pages with ratings, sentiment, themes, and live reviews.
- Compare selected professors.
- Find similar professors using review-text embeddings.
- Analyze review sentiment with VADER and optional trained ML models.

## Backend Setup

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
python manage.py migrate
python manage.py ingest_seed --reset
python manage.py runserver 8000
```

The backend runs at:

```text
http://127.0.0.1:8000
```

## Building the Database From Scratch

For a small local/demo database, run:

```bash
cd backend
python manage.py migrate
python manage.py ingest_seed --reset
```

`ingest_seed --reset` clears the existing local tables, loads `backend/data/seed_reviews.json`, runs sentiment analysis, and rebuilds professor stats.

For a larger database, start with an empty SQLite database, run migrations, crawl professor metadata from RateMyProfessors, then run analysis:

```bash
cd backend
python manage.py migrate
python manage.py crawl_rmp_directory --schools-limit 50 --min-ratings 1 --resume
python manage.py analyze_all_rmp --resume
```

The directory crawl builds the searchable professor catalog. The analysis command fetches bounded review pages, computes sentiment/theme aggregates, and stores `ProfessorStats`.

Optional recommender artifacts can be rebuilt after the ML corpus exists:

```bash
cd backend
python manage.py build_prof_embeddings
```

## Frontend Setup

Open a second terminal from the project root:

```bash
cd frontend
npm install
npm run dev
```

The frontend usually runs at:

```text
http://localhost:5173
```

## Useful Commands

Run backend tests:

```bash
cd backend
python manage.py test
```

Run sentiment unit tests:

```bash
cd backend
python3 -m unittest sentiment.tests -v
```

Build the frontend:

```bash
cd frontend
npm run build
```

## Demo

Demo video:

```text
https://youtu.be/o1A1l2W680g?si=4a1GuE1157LvYent
```

## Deployment

ProfIQ deploys manually (no CI/CD) to free-tier infrastructure: Vercel (frontend), Google Cloud
Run (backend), CockroachDB Serverless (database). Full design rationale in
`docs/superpowers/specs/2026-09-13-hosting-design.md`.

1. Copy `backend/.env.deploy.example` to `backend/.env.deploy` and fill in real values
   (CockroachDB Serverless credentials, a generated `DJANGO_SECRET_KEY`, your GCP project ID).
   Download the cluster's CA certificate from the CockroachDB Cloud console into
   `backend/certs/cockroachdb-ca.crt` (public cert, safe to commit).
2. Deploy the backend: `cd backend && ./deploy.sh`. Note the printed Cloud Run URL.
3. Add that URL **plus `/api`** as `VITE_API_BASE_URL` in `backend/.env.deploy` (e.g.
   `https://profiq-backend-xxxx.run.app/api`), then deploy the frontend:
   `cd frontend && ./deploy.sh`. Note the printed Vercel URL.
4. Add the Vercel URL to `CORS_EXTRA_ORIGINS` in `backend/.env.deploy` (alongside
   `smafnanhaider.com`), then re-run `cd backend && ./deploy.sh`.
5. Run database migrations and seed data once: `cd backend && ./migrate-remote.sh` (requires
   `pip install -r requirements-postgres.txt` in addition to `requirements.txt`, for the `psycopg`
   Postgres driver).
6. In the Vercel dashboard, add `smafnanhaider.com` and `www.smafnanhaider.com` as custom
   domains and point your registrar's DNS at Vercel per its instructions. The backend keeps its
   default `*.run.app` URL — no custom domain needed there.

`deploy.sh` (backend and frontend) and `migrate-remote.sh` are gitignored, local-only
convenience scripts — see `backend/.env.deploy.example` for the full list of required
environment variables.

## Notes

The large professor catalog stores professor metadata and summary ratings. Review text is mainly fetched live or processed during bounded analysis jobs, so the database does not need to permanently store every scraped review.
