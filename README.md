# ProfIQ

ProfIQ is a professor search and comparison web app. It uses a Django backend and a React frontend to help students look up professors, view review-based sentiment, see common review themes, find similar professors, and compare multiple professors side by side.

## Project Structure

```text
backend/   Django API, database models, scrapers, sentiment analysis, ML helpers
frontend/  React/Vite user interface
notebooks/ ML evaluation notebook
scripts/   report builder scripts
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

Rebuild the project report:

```bash
python scripts/build_final_report.py
python scripts/build_final_report_pdf.py
```

## Demo and Report

Demo video:

```text
https://youtu.be/o1A1l2W680g?si=4a1GuE1157LvYent
```

Final report files:

```text
ProfIQ_Project_Report.docx
ProfIQ_Project_Report.pdf
```

## Notes

The large professor catalog stores professor metadata and summary ratings. Review text is mainly fetched live or processed during bounded analysis jobs, so the database does not need to permanently store every scraped review.

