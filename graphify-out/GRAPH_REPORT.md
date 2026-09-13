# Graph Report - .  (2026-09-13)

## Corpus Check
- 77 files · ~129,695 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 407 nodes · 495 edges · 52 communities detected
- Extraction: 91% EXTRACTED · 9% INFERRED · 1% AMBIGUOUS · INFERRED: 44 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Reddit AliasComment Matching Tests|Reddit Alias/Comment Matching Tests]]
- [[_COMMUNITY_Core Django App Models, Views & Scrapers|Core Django App: Models, Views & Scrapers]]
- [[_COMMUNITY_ML Stack & Hosting Dependencies (Docs)|ML Stack & Hosting Dependencies (Docs)]]
- [[_COMMUNITY_Project Description Tech Concepts|Project Description: Tech Concepts]]
- [[_COMMUNITY_Scraping & Embedding Management Commands|Scraping & Embedding Management Commands]]
- [[_COMMUNITY_Canary Detection Command|Canary Detection Command]]
- [[_COMMUNITY_Canary Purge & Package Init|Canary Purge & Package Init]]
- [[_COMMUNITY_Hosting & Deployment Plan|Hosting & Deployment Plan]]
- [[_COMMUNITY_React Frontend Components|React Frontend Components]]
- [[_COMMUNITY_ML Corpus Building Script|ML Corpus Building Script]]
- [[_COMMUNITY_Git Commit Date Spreading Script|Git Commit Date Spreading Script]]
- [[_COMMUNITY_Bulk RMP Analysis Command|Bulk RMP Analysis Command]]
- [[_COMMUNITY_RMP Directory Crawler Command|RMP Directory Crawler Command]]
- [[_COMMUNITY_Reddit Comment Tree Tests|Reddit Comment Tree Tests]]
- [[_COMMUNITY_Seed Data Ingestion Command|Seed Data Ingestion Command]]
- [[_COMMUNITY_Backend Stack Rationale (Description)|Backend Stack Rationale (Description)]]
- [[_COMMUNITY_Django Settings & Entrypoints|Django Settings & Entrypoints]]
- [[_COMMUNITY_Embedding Build Script|Embedding Build Script]]
- [[_COMMUNITY_BERT Training Script|BERT Training Script]]
- [[_COMMUNITY_Sentiment Classifier Training|Sentiment Classifier Training]]
- [[_COMMUNITY_Frontend Stack Rationale (Description)|Frontend Stack Rationale (Description)]]
- [[_COMMUNITY_Django Admin Config|Django Admin Config]]
- [[_COMMUNITY_Canary Detection Report|Canary Detection Report]]
- [[_COMMUNITY_Canary Smoke Test Report|Canary Smoke Test Report]]
- [[_COMMUNITY_Backend Test Docs (README)|Backend Test Docs (README)]]
- [[_COMMUNITY_Hosting Plan Next Steps|Hosting Plan Next Steps]]
- [[_COMMUNITY_Vite Config|Vite Config]]
- [[_COMMUNITY_Recommender Package Init|Recommender Package Init]]
- [[_COMMUNITY_RMP Teacher Data Class|RMP Teacher Data Class]]
- [[_COMMUNITY_Scrapers Package Init|Scrapers Package Init]]
- [[_COMMUNITY_Sentiment Package Init|Sentiment Package Init]]
- [[_COMMUNITY_Department Model|Department Model]]
- [[_COMMUNITY_Professors Package Init|Professors Package Init]]
- [[_COMMUNITY_Professors App Config|Professors App Config]]
- [[_COMMUNITY_Migrations Package Init|Migrations Package Init]]
- [[_COMMUNITY_Management Package Init|Management Package Init]]
- [[_COMMUNITY_Commands Package Init|Commands Package Init]]
- [[_COMMUNITY_Frontend HTML Title|Frontend HTML Title]]
- [[_COMMUNITY_Postgres Driver Dependency|Postgres Driver Dependency]]
- [[_COMMUNITY_Search Feature (README)|Search Feature (README)]]
- [[_COMMUNITY_Professor Detail Feature (README)|Professor Detail Feature (README)]]
- [[_COMMUNITY_Compare Feature (README)|Compare Feature (README)]]
- [[_COMMUNITY_Frontend Build Docs|Frontend Build Docs]]
- [[_COMMUNITY_Demo Video (README)|Demo Video (README)]]
- [[_COMMUNITY_CORS Headers Dependency|CORS Headers Dependency]]
- [[_COMMUNITY_Pandas Dependency|Pandas Dependency]]
- [[_COMMUNITY_Datasets Library Dependency|Datasets Library Dependency]]
- [[_COMMUNITY_Accelerate Library Dependency|Accelerate Library Dependency]]
- [[_COMMUNITY_Hosting Verification Checklist|Hosting Verification Checklist]]
- [[_COMMUNITY_Saved Query Answer|Saved Query Answer]]
- [[_COMMUNITY_RMP Pipeline Query Node|RMP Pipeline Query Node]]
- [[_COMMUNITY_ScrapingEmbedding Query Node|Scraping/Embedding Query Node]]

## God Nodes (most connected - your core abstractions)
1. `Command` - 12 edges
2. `CommentTreeWalkTests` - 11 edges
3. `ProfIQ (Project)` - 9 edges
4. `App route shell` - 8 edges
5. `AliasMatcherNicknameTests` - 8 edges
6. `Review model` - 8 edges
7. `Google Cloud Run (Backend Hosting)` - 8 edges
8. `Frontend API client` - 7 edges
9. `Professor detail page` - 7 edges
10. `Professor comparison page` - 7 edges

## Surprising Connections (you probably didn't know these)
- `ProfIQ (Project)` --conceptually_related_to--> `praw (Reddit API wrapper)`  [AMBIGUOUS]
  README.md → backend/requirements.txt
- `ProfIQ (Project)` --references--> `README.md Deployment section (uncommitted edit)`  [AMBIGUOUS]
  README.md → docs/superpowers/specs/2026-09-13-hosting-design.md
- `RateMyProfessors (external data source)` --semantically_similar_to--> `praw (Reddit API wrapper)`  [INFERRED] [semantically similar]
  README.md → backend/requirements.txt
- `Django REST framework` --references--> `Django Backend`  [INFERRED]
  backend/requirements.txt → README.md
- `ProfIQ (Project)` --references--> `ProfIQ (Resume Description)`  [INFERRED]
  README.md → Description.MD

## Hyperedges (group relationships)
- **ProfIQ Hosting Stack (Vercel + Cloud Run + Neon)** — hosting_vercel, hosting_neon_postgres, hosting_cloud_run [INFERRED 0.85]
- **Manual, Gitignored Deploy Workflow** — hosting_env_deploy, hosting_deploy_sh, hosting_frontend_deploy_sh, hosting_migrate_remote_sh [INFERRED 0.80]
- **ProfIQ Sentiment/Recommender ML Stack** — requirements_nltk, requirements_scikit_learn, requirements_sentence_transformers, requirements_transformers [INFERRED 0.75]

## Communities

### Community 0 - "Reddit Alias/Comment Matching Tests"
Cohesion: 0.04
Nodes (10): AliasMatcherBasicTests, AliasMatcherNicknameTests, AliasMatcherSentenceSliceTests, CleanBodyTests, InstitutionKeywordTests, QueryShapingTests, Tests for the lazy Reddit helper., Sentence-slice matching cases. (+2 more)

### Community 1 - "Core Django App: Models, Views & Scrapers"
Cohesion: 0.06
Nodes (43): Sentiment aggregate statistics, Review sentiment analyzer, Recommendation score calculator, Review theme extractor, Scraped professor record, Scraped review record, Scraped data seed formatter, Hashed train validation test corpus split (+35 more)

### Community 2 - "ML Stack & Hosting Dependencies (Docs)"
Cohesion: 0.06
Nodes (41): Decision: Keep Raw Review Storage Bounded, 350K Review ML Corpus, pandas / NumPy / PyArrow / joblib, Why Cloud Run's Memory Needs Are Modest, Decision: Separate Offline ML from Online App, Initial Data Decision: Demo Seed, Not Full Crawl, README.md Deployment section (uncommitted edit), backend/sentiment/ml/recommender.py (lazy MiniLM loader) (+33 more)

### Community 3 - "Project Description: Tech Concepts"
Cohesion: 0.09
Nodes (27): Canary Detection / Data-Quality Validation, Cosine Similarity Recommendation, Decision: Make Cleanup Conservative, Decision: Treat External Data as Unreliable, Decision: Logistic Regression in Live Path, Decision: Separate Offline ML from Online App, DistilBERT Sentiment Model, Domain-Tuned Sentiment Layer (+19 more)

### Community 4 - "Scraping & Embedding Management Commands"
Cohesion: 0.11
Nodes (12): BaseCommand, Command, Build the saved similar-professor embedding index., Command, Run configured RMP and Reddit scrapes., dump_and_maybe_ingest(), Shared helpers used by the scrape_* management commands., timestamped_output() (+4 more)

### Community 5 - "Canary Detection Command"
Cohesion: 0.14
Nodes (11): Command, _fuzzy(), _is_rmp_anagram(), _looks_palindromic(), _normalise_institution_query(), Read-only checks for likely placeholder professor records., Return top OpenAlex institution matches., Return the best fuzzy institution match. (+3 more)

### Community 6 - "Canary Purge & Package Init"
Cohesion: 0.13
Nodes (12): _flatten_categorised(), _load(), _load_categories(), normalise_name(), Name lists used by canary checks., Normalize a name for set membership checks., Like ``_load`` but only flattens the named categories., Command (+4 more)

### Community 7 - "Hosting & Deployment Plan"
Cohesion: 0.13
Nodes (20): frontend/src/lib/api.js (VITE_API_BASE_URL edit), Google Cloud Run (Backend Hosting), Deploy Mechanics Decisions, backend/deploy.sh, Hosting Design Goal, backend/Dockerfile (gitignored), backend/.dockerignore (gitignored), backend/.env.deploy (gitignored secrets) (+12 more)

### Community 8 - "React Frontend Components"
Cohesion: 0.23
Nodes (19): Add professor modal, Frontend API client, App route shell, Compare bar, Professor comparison page, Comparison context and local storage state, Selected professor ID set, Score and theme formatting helpers (+11 more)

### Community 9 - "ML Corpus Building Script"
Cohesion: 0.21
Nodes (13): fetch_one(), jsonl_to_parquet(), load_checkpoint(), main(), _quality_rating(), Build the review corpus used by ML training scripts., Append rows to the JSONL sidecar., Pick high-review professors from the largest schools.      Only includes profs w (+5 more)

### Community 10 - "Git Commit Date Spreading Script"
Cohesion: 0.23
Nodes (14): build_segments(), collect_commits(), fit_gaps(), git(), local(), main(), parse_when(), plan() (+6 more)

### Community 11 - "Bulk RMP Analysis Command"
Cohesion: 0.24
Nodes (8): Command, _fresh_checkpoint(), _legacy_id_from_ref(), _load_checkpoint(), Build ProfessorStats rows from RMP review pages., Fetch and analyze one professor's reviews., Extract the legacy ID from ``"rmp:<legacy_id>"`` refs., _save_checkpoint()

### Community 12 - "RMP Directory Crawler Command"
Cohesion: 0.26
Nodes (7): Command, _fresh_checkpoint(), _load_checkpoint(), Crawl RMP directory metadata into the local DB., Page through all teachers at ``school`` and upsert them., Save checkpoint on SIGTERM so we can resume cleanly., _save_checkpoint()

### Community 13 - "Reddit Comment Tree Tests"
Cohesion: 0.33
Nodes (2): CommentTreeWalkTests, Comment-tree walking cases.

### Community 14 - "Seed Data Ingestion Command"
Cohesion: 0.32
Nodes (3): Command, Load seed reviews and rebuild local stats., Aggregate per-professor analytics into ProfessorStats rows.

### Community 15 - "Backend Stack Rationale (Description)"
Cohesion: 0.33
Nodes (6): Decision: SQLite for Reproducibility, PostgreSQL for Scale, Django 5.x, django-cors-headers, Django REST Framework 3.15, PostgreSQL (psycopg), SQLite

### Community 16 - "Django Settings & Entrypoints"
Cohesion: 0.4
Nodes (5): Django management entry point, CORS development configuration, SQLite/PostgreSQL database configuration, Django REST Framework configuration, WSGI application

### Community 17 - "Embedding Build Script"
Cohesion: 0.5
Nodes (4): _aggregate(), main(), Build per-professor embedding artifacts., Group reviews into one clipped document per professor.

### Community 18 - "BERT Training Script"
Cohesion: 0.6
Nodes (4): compute_metrics_factory(), main(), Fine-tune DistilBERT for review sentiment., to_hf()

### Community 19 - "Sentiment Classifier Training"
Cohesion: 0.67
Nodes (3): build_pipeline(), main(), Train the TF-IDF + Logistic Regression sentiment model.

### Community 20 - "Frontend Stack Rationale (Description)"
Cohesion: 0.5
Nodes (4): React 18, React Router, Recharts, Vite 5

### Community 21 - "Django Admin Config"
Cohesion: 0.67
Nodes (2): ProfessorAdmin, ProfessorStatsAdmin

### Community 22 - "Canary Detection Report"
Cohesion: 0.67
Nodes (3): Canary detection report, 258 flagged records among 1702454 professors, Layer 1 pattern blacklist

### Community 23 - "Canary Smoke Test Report"
Cohesion: 1.0
Nodes (2): Layer 3 fake institution check, No institutions flagged in 25 checks

### Community 24 - "Backend Test Docs (README)"
Cohesion: 1.0
Nodes (2): Backend Test Suite, Sentiment Unit Tests

### Community 25 - "Hosting Plan Next Steps"
Cohesion: 1.0
Nodes (2): brainstorming Skill (architectural path), Next Step: Invoke writing-plans Skill

### Community 26 - "Vite Config"
Cohesion: 1.0
Nodes (1): Vite configuration

### Community 27 - "Recommender Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "RMP Teacher Data Class"
Cohesion: 1.0
Nodes (1): RateMyProfessors teacher record

### Community 29 - "Scrapers Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Sentiment Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 31 - "Department Model"
Cohesion: 1.0
Nodes (1): Academic department model

### Community 32 - "Professors Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 33 - "Professors App Config"
Cohesion: 1.0
Nodes (1): Professors Django app configuration

### Community 34 - "Migrations Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "Management Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Commands Package Init"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Frontend HTML Title"
Cohesion: 1.0
Nodes (1): ProfIQ Professor Recommendation System page title

### Community 38 - "Postgres Driver Dependency"
Cohesion: 1.0
Nodes (1): Optional PostgreSQL psycopg dependency

### Community 39 - "Search Feature (README)"
Cohesion: 1.0
Nodes (1): Search Professors Feature

### Community 40 - "Professor Detail Feature (README)"
Cohesion: 1.0
Nodes (1): Professor Detail Page

### Community 41 - "Compare Feature (README)"
Cohesion: 1.0
Nodes (1): Compare Professors Feature

### Community 42 - "Frontend Build Docs"
Cohesion: 1.0
Nodes (1): Frontend Production Build

### Community 43 - "Demo Video (README)"
Cohesion: 1.0
Nodes (1): Demo Video

### Community 44 - "CORS Headers Dependency"
Cohesion: 1.0
Nodes (1): django-cors-headers

### Community 45 - "Pandas Dependency"
Cohesion: 1.0
Nodes (1): pandas

### Community 46 - "Datasets Library Dependency"
Cohesion: 1.0
Nodes (1): datasets

### Community 47 - "Accelerate Library Dependency"
Cohesion: 1.0
Nodes (1): accelerate

### Community 48 - "Hosting Verification Checklist"
Cohesion: 1.0
Nodes (1): Post-Deploy Verification Checklist

### Community 49 - "Saved Query Answer"
Cohesion: 1.0
Nodes (1): Answer: Framework-Convention Bridge, Not Deliberate Coupling

### Community 50 - "RMP Pipeline Query Node"
Cohesion: 1.0
Nodes (1): RMP Review Analysis Pipeline (Community)

### Community 51 - "Scraping/Embedding Query Node"
Cohesion: 1.0
Nodes (1): Scraping & Embedding Management Commands (Community)

## Ambiguous Edges - Review These
- `Rating to sentiment label mapping` → `Optional classifier inference`  [AMBIGUOUS]
  backend/sentiment/ml/inference.py · relation: semantically_similar_to
- `ProfIQ (Project)` → `praw (Reddit API wrapper)`  [AMBIGUOUS]
  backend/requirements.txt · relation: conceptually_related_to
- `ProfIQ (Project)` → `README.md Deployment section (uncommitted edit)`  [AMBIGUOUS]
  docs/superpowers/specs/2026-09-13-hosting-design.md · relation: references

## Knowledge Gaps
- **135 isolated node(s):** `Vite configuration`, `Sentiment bar`, `Django management entry point`, `CORS development configuration`, `Root API and admin URL patterns` (+130 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Canary Smoke Test Report`** (2 nodes): `Layer 3 fake institution check`, `No institutions flagged in 25 checks`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Backend Test Docs (README)`** (2 nodes): `Backend Test Suite`, `Sentiment Unit Tests`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Hosting Plan Next Steps`** (2 nodes): `brainstorming Skill (architectural path)`, `Next Step: Invoke writing-plans Skill`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Vite Config`** (1 nodes): `Vite configuration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Recommender Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `RMP Teacher Data Class`** (1 nodes): `RateMyProfessors teacher record`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Scrapers Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Sentiment Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Department Model`** (1 nodes): `Academic department model`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Professors Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Professors App Config`** (1 nodes): `Professors Django app configuration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Migrations Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Management Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Commands Package Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Frontend HTML Title`** (1 nodes): `ProfIQ Professor Recommendation System page title`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Postgres Driver Dependency`** (1 nodes): `Optional PostgreSQL psycopg dependency`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Search Feature (README)`** (1 nodes): `Search Professors Feature`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Professor Detail Feature (README)`** (1 nodes): `Professor Detail Page`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Compare Feature (README)`** (1 nodes): `Compare Professors Feature`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Frontend Build Docs`** (1 nodes): `Frontend Production Build`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Demo Video (README)`** (1 nodes): `Demo Video`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `CORS Headers Dependency`** (1 nodes): `django-cors-headers`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Pandas Dependency`** (1 nodes): `pandas`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Datasets Library Dependency`** (1 nodes): `datasets`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Accelerate Library Dependency`** (1 nodes): `accelerate`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Hosting Verification Checklist`** (1 nodes): `Post-Deploy Verification Checklist`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Saved Query Answer`** (1 nodes): `Answer: Framework-Convention Bridge, Not Deliberate Coupling`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `RMP Pipeline Query Node`** (1 nodes): `RMP Review Analysis Pipeline (Community)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Scraping/Embedding Query Node`** (1 nodes): `Scraping & Embedding Management Commands (Community)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Rating to sentiment label mapping` and `Optional classifier inference`?**
  _Edge tagged AMBIGUOUS (relation: semantically_similar_to) - confidence is low._
- **What is the exact relationship between `ProfIQ (Project)` and `praw (Reddit API wrapper)`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `ProfIQ (Project)` and `README.md Deployment section (uncommitted edit)`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `Command` connect `Bulk RMP Analysis Command` to `Scraping & Embedding Management Commands`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Why does `Command` connect `Canary Detection Command` to `Scraping & Embedding Management Commands`?**
  _High betweenness centrality (0.028) - this node is a cross-community bridge._
- **Why does `_quality_rating()` connect `ML Corpus Building Script` to `Bulk RMP Analysis Command`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **What connects `Vite configuration`, `Sentiment bar`, `Django management entry point` to the rest of the system?**
  _135 weakly-connected nodes found - possible documentation gaps or missing edges._