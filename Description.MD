# ProfIQ

## Resume-Ready Project Description

ProfIQ is an end-to-end professor search, review analytics, and recommendation platform built for students choosing courses. It combines a normalized relational data model, public-source ingestion, NLP sentiment analysis, semantic recommendations, a REST API, and an interactive React interface. Users can search professors by name, institution, department, or course; inspect ratings, sentiment, review themes, and live review evidence; compare professors side by side; and discover similar professors based on review language.

The project was designed as a data-management system as much as a web application. The central engineering challenge was turning inconsistent, duplicated, and partially structured public review data into searchable professor records and useful aggregates while minimizing unnecessary storage of raw review text.

## What Makes the Project High Impact

- **Large-scale catalog:** The local catalog contains approximately **1.7 million professor records** across **3,272 departments**.
- **Machine-learning corpus:** The saved ML corpus contains **350,018 review rows** covering **4,793 professors** and **49 institutions**.
- **Full data lifecycle:** The system supports ingestion, normalization, deduplication, validation, enrichment, model training, evaluation, API delivery, and frontend visualization.
- **Multiple NLP approaches:** Sentiment analysis compares a rule-based VADER baseline, TF-IDF with Logistic Regression, and fine-tuned DistilBERT.
- **Semantic recommendations:** MiniLM sentence embeddings and cosine similarity produce similar-professor recommendations from review language.
- **Measured recommender lift:** Department purity at 5 neighbors reached **0.230**, compared with a **0.055 random baseline**, a **4.17x lift**. Institution purity reached **0.093**, compared with **0.050 random**, a **1.87x lift**.
- **Data-quality safeguards:** Canary detection scans for fictional names, joke names, palindromic placeholders, suspicious records, and implausible institutions before bad data reaches users.
- **Reproducible evaluation:** Models use stable, hash-based train/validation/test splits so repeated runs keep the same review in the same split.
- **Verified implementation:** The project includes **28 sentiment/recommender unit tests**, **13 professor API tests**, and a successful Vite production build.

## Technology Stack

### Backend and API

- **Python** for data processing, scraping, analytics, and machine learning orchestration.
- **Django 5.x** for the backend web framework, ORM, migrations, management commands, and application lifecycle.
- **Django REST Framework 3.15** for RESTful API endpoints and serialized responses.
- **SQLite** for the reproducible local/demo deployment and **PostgreSQL support** through `psycopg` for a production-oriented database option.
- **django-cors-headers** to support communication between the frontend development server and the backend API.
- **Django management commands** for repeatable database ingestion, catalog crawling, review analysis, embedding generation, canary detection, and data cleanup.

### Frontend

- **React 18** for the interactive single-page application.
- **Vite 5** for fast development, module bundling, and production builds.
- **React Router** for client-side navigation between search, professor detail, comparison, and related views.
- **Recharts** for sentiment, rating, theme, and comparison visualizations.
- The frontend consumes the Django REST API and turns structured professor analytics into search, filter, comparison, chart, and recommendation workflows.

### Data Collection and Processing

- **Requests** and **Beautiful Soup** for HTTP retrieval and HTML parsing.
- **PRAW** for collecting Reddit-based qualitative signals.
- RateMyProfessors directory and review ingestion with bounded crawling, resume support, throttling, source identifiers, and external references.
- **pandas**, **NumPy**, **PyArrow**, and **joblib** for tabular processing, feature preparation, artifact storage, and efficient ML workflows.
- Source-aware processing separates persistent professor metadata and aggregate statistics from raw review text that can be fetched or analyzed only when needed.

### Natural Language Processing and Machine Learning

- **NLTK VADER** provides an explainable rule-based sentiment baseline for short review-style text.
- A domain-tuned sentiment layer adds professor-review vocabulary, phrase rules, star-rating blending, and theme extraction for concepts such as clarity, fairness, workload, helpfulness, engagement, and grading.
- **TF-IDF with unigram/bigram features and class-weighted Logistic Regression** provides the lightweight live classifier.
- **Hugging Face Transformers and DistilBERT** provide a stronger offline comparison model.
- **Sentence Transformers with `all-MiniLM-L6-v2`** encode aggregated professor review language into dense vectors.
- **Cosine similarity and nearest-neighbor retrieval** power content-based similar-professor recommendations.
- **scikit-learn** supports classification, vectorization, metrics, and evaluation utilities.
- **PyTorch, Transformers, Datasets, and Accelerate** support transformer training and evaluation.
- **Matplotlib and Seaborn** support offline model analysis and visual evaluation.

## How the System Was Built

### 1. Relational data design

The application models sources, departments, professors, courses, reviews, sentiment results, and professor-level statistics as separate entities. Foreign keys, one-to-one relationships, many-to-many course associations, indexes, and uniqueness constraints prevent repeated data from being stored as unstructured blobs.

Important integrity rules include unique external professor identifiers, unique course codes, source-aware review URL deduplication, and relationships that preserve referential integrity when records are removed. This lets the API search and aggregate efficiently while keeping the schema understandable and extensible.

### 2. Repeatable ingestion and ETL

The system supports a small seed-data path for deterministic local demos and tests, as well as larger catalog-building workflows. Directory crawling imports professor metadata, institution information, departments, source ratings, rating counts, and external identifiers. Bounded analysis jobs fetch review pages, compute sentiment and theme aggregates, and store the resulting `ProfessorStats` rather than permanently storing every raw review.

Scrapers include throttling, pagination limits, resume behavior, source-specific normalization, alias matching, and defensive handling of inconsistent external data. This makes the pipeline more suitable for repeatable research and application development than a one-off scraping script.

### 3. Data-quality and canary detection

A dedicated validation workflow identifies likely placeholder or fabricated records before they distort search results or model training. The checks include known fictional-character and joke-name lists, normalized name matching, palindrome detection, suspicious institution checks, fuzzy matching, and OpenAlex institution verification.

In one recorded run, the system scanned **1,702,454 professors in 9.35 seconds** and flagged **258** likely canary records for review. A separate Layer 3 smoke test checked **25 institutions with 0 errors** and found no invalid institutions in that sample. Destructive cleanup is deliberately dry-run by default and requires explicit confirmation.

### 4. Sentiment and theme analysis

The sentiment pipeline supports three-class labels: negative, neutral, and positive. Labels are derived from review ratings using explicit thresholds, while text-based analysis captures the language and themes students use in their comments.

VADER was retained as an interpretable baseline and made more domain-aware with custom vocabulary and phrase rules. The live learned model uses TF-IDF features and class-weighted Logistic Regression because it is compact, fast, and practical for API requests. DistilBERT was trained as a stronger offline comparison model rather than used as the default live dependency.

### 5. Model evaluation

The evaluation compares all sentiment approaches on held-out data and reports accuracy, macro-F1, weighted-F1, confusion matrices, and per-class metrics. The split is deterministic through hashing of stable review URLs, reducing accidental leakage and making repeated experiments comparable.

Saved test results include:

| Model | Test accuracy | Test macro-F1 | Test weighted-F1 |
| --- | ---: | ---: | ---: |
| VADER | 0.7638 | 0.5325 | 0.7374 |
| TF-IDF + Logistic Regression | 0.8017 | 0.7187 | 0.8169 |
| DistilBERT | 0.8566 | 0.6361 | 0.8313 |

The metrics come from the project’s saved evaluation artifacts and use different test-set sizes: Logistic Regression uses 52,445 test reviews, while VADER and DistilBERT use 7,427. DistilBERT has the strongest accuracy and weighted-F1 in its evaluation, while Logistic Regression has the strongest macro-F1 among the saved results, making it a better balance for the live application and the underrepresented neutral class.

### 6. Content-based recommendations

For recommendations, reviews are grouped into a bounded professor-level text document and encoded with `all-MiniLM-L6-v2`. The resulting vectors are normalized and compared with cosine similarity. The API then maps nearest-neighbor results back to professor records and prioritizes useful same-department or same-institution matches when possible.

The recommender was evaluated with purity at 5 neighbors. Department purity was **0.230 versus 0.055 random**, and institution purity was **0.093 versus 0.050 random**. These results suggest the embeddings capture meaningful subject and teaching-style language rather than producing purely random matches.

### 7. API and user experience

The REST API exposes platform summaries, professor search and filtering, validated professor creation, professor detail pages, live review analysis, multi-professor comparison, and similar-professor recommendations. The API layer keeps frontend concerns separate from database and model implementation details.

The React interface is organized around the student workflow: find a professor, inspect evidence, compare alternatives, and explore related recommendations. Recharts turns aggregate sentiment and theme data into visual signals that are easier to scan than raw tables alone.

## Engineering and Product Decisions

- **Use SQLite for reproducibility, PostgreSQL for scale:** SQLite keeps the project easy to run locally, while PostgreSQL dependencies are included for a production deployment path.
- **Use Logistic Regression in the live path:** It is considerably lighter and faster than transformer inference while still improving strongly over VADER on macro-F1.
- **Keep raw review storage bounded:** The system stores normalized entities and aggregates permanently but avoids retaining unnecessary copies of large scraped review collections.
- **Separate offline ML from online application behavior:** Corpus construction, training, DistilBERT evaluation, and embedding generation are reproducible jobs; the API uses compact artifacts and graceful fallbacks.
- **Treat external data as unreliable:** Crawlers include throttling, retries/resume patterns, deduplication, source identifiers, and validation checks.
- **Make cleanup conservative:** Canary deletion is dry-run by default and requires an explicit confirmation flag.

## Validation and Reproducibility

The project includes:

- 28 passing sentiment and recommender tests covering custom lexicon behavior, phrase rules, rating blending, fallbacks, and embedding warm-up behavior.
- 13 passing professor API tests covering validation, duplicate handling, fictional/joke-name rejection, and successful creation.
- A successful `npm run build` production compilation, with only a non-fatal Vite chunk-size warning.
- Django migrations and management commands for rebuilding the database from seed data or larger crawls.
- Saved classifier metrics, recommender metrics, embedding artifacts, corpus checkpoints, and an ML evaluation notebook.

## Limitations and Responsible Use

The project is an educational analytics and decision-support application, not an objective ranking of teaching quality. Public reviews are self-selected and can overrepresent unusually positive or negative experiences. Ratings are imperfect sentiment labels, neutral reviews are difficult to classify, and RateMyProfessors and Reddit can change their interfaces or rate-limit requests.

The recommendation system identifies similar review language; it does not prove that two professors teach identically. The system also limits raw-text persistence and is intended for educational analysis rather than redistribution of scraped review datasets. A production deployment would benefit from PostgreSQL, a background job queue, stronger observability, cache invalidation, better entity matching, and additional accessibility and calibration work.

## Resume Versions

### One-line version

Built ProfIQ, a Django/React professor analytics platform that ingests and normalizes a 1.7M-record professor catalog, applies VADER, TF-IDF/Logistic Regression, and DistilBERT sentiment models to 350K reviews, and delivers MiniLM-based recommendations with a 4.17x department-purity lift over random.

### Three-bullet version

- Built an end-to-end Django REST + React/Vite professor search and comparison platform with normalized relational data, RateMyProfessors/Reddit ingestion, live review analysis, charts, and similar-professor recommendations.
- Trained and evaluated VADER, TF-IDF + class-weighted Logistic Regression, and DistilBERT sentiment models on a 350K-review corpus; achieved 0.8017 Logistic Regression test accuracy and 0.8566 DistilBERT test accuracy.
- Developed MiniLM embedding recommendations and canary-data validation for a 1.7M-professor catalog; achieved 4.17x department-purity lift and validated the system with 41 backend tests plus a successful production frontend build.

### Technical-keyword version

Python, Django, Django REST Framework, React, Vite, SQLite, PostgreSQL, REST APIs, ETL, web scraping, RateMyProfessors, Reddit/PRAW, NLTK VADER, TF-IDF, Logistic Regression, DistilBERT, Hugging Face Transformers, Sentence Transformers, MiniLM, cosine similarity, scikit-learn, PyTorch, pandas, NumPy, PyArrow, data normalization, deduplication, model evaluation, unit testing, and data-quality validation.

## Short Elevator Pitch

ProfIQ turns fragmented public professor-review data into a searchable, explainable decision-support tool. It combines serious data engineering with applied NLP: a normalized database and resilient ingestion pipeline feed sentiment and theme analytics, while MiniLM embeddings identify professors with similar review language. The result is a full-stack system that is measurable, reproducible, and designed around the practical constraints of messy external data.
