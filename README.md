# Ferlance MVP

Ferlance is a business intelligence platform for African SMEs, initially focused on Ghana.

This repository contains the first post-research MVP slice, aligned with Sprint 3:

```text
create account -> create business -> upload sales data -> validate and clean -> inspect dataset history
```

The current slice focuses on reliable data ingestion. Revenue analytics, dashboards, predefined business questions, automated insights, LLM features, and RAG are follow-on slices.

For the authoritative implementation status, evidence, risks, and next done condition, see [MVP_PROGRESS.md](MVP_PROGRESS.md).

## Current capabilities

- Create an account and initial business workspace.
- Authenticate with a signed bearer token.
- Upload CSV and XLSX sales files.
- Normalize supported dates and currency-like numeric formats.
- Detect duplicate transaction IDs or duplicate row fingerprints.
- Preserve accepted records as normalized JSONL.
- Record dataset status, row counts, warnings, and errors.
- View dataset history for the authenticated business.
- Use the browser interface at the root URL.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000.

The service uses SQLite metadata and local files under `data/` by default. Set `FERLANCE_DATA_DIR` to change the storage directory.

## Project layout

```text
backend/             FastAPI application, SQLite persistence, security, and processing
frontend/            Minimal onboarding and upload interface
tests/               API and processor tests
tests/fixtures/      Valid and invalid representative CSV files
data/                Local SQLite, raw uploads, and processed output
```

The application creates SQLite metadata, raw uploads, and processed JSONL files on startup. Local runtime data is ignored by Git.

## API walkthrough

Create an account and business:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/signup \
	-H 'Content-Type: application/json' \
	-d '{"email":"owner@example.com","password":"password123","business_name":"Ama Retail"}'
```

Use the returned `access_token` and `business.id` to upload a dataset:

```bash
curl -X POST http://127.0.0.1:8000/api/businesses/<BUSINESS_ID>/datasets \
	-H 'Authorization: Bearer <ACCESS_TOKEN>' \
	-F 'file=@tests/fixtures/valid_sales.csv'
```

List dataset history:

```bash
curl http://127.0.0.1:8000/api/businesses/<BUSINESS_ID>/datasets \
	-H 'Authorization: Bearer <ACCESS_TOKEN>'
```

The health endpoint is available at `GET /health`.

## Test

```bash
.venv/bin/pytest -q
```

Supported uploads require date and amount/revenue columns. Optional columns include transaction ID, product, customer, and quantity. Invalid rows are rejected with warnings; the normalized JSONL output preserves accepted records without silently hiding the rejection counts.

## Dataset contract

Supported extensions are `.csv` and `.xlsx`. Column names are matched case-insensitively after removing spaces and punctuation.

Required fields:

- `transaction_date`, `date`, or `sale_date`
- `amount`, `sales_amount`, `revenue`, `total`, or `sale_amount`

Optional fields include transaction ID, product, customer, and quantity. Rows with invalid dates or amounts are rejected with row-level warnings. Duplicate IDs are rejected; when no ID exists, a stable fingerprint of the normalized row is used.

## MVP roadmap

1. **Sprint 3, ingestion:** authentication, business boundary, upload, validation, cleaning, storage, history, and useful errors.
2. **Sprint 4, analytics:** revenue, trends, products, customers, conditional profit/inventory metrics, KPI cards, and date filters.
3. **Sprint 5, insights:** deterministic summaries, anomaly detection, recommendations, and predefined business questions. Natural-language assistance follows the core product.
4. **Sprint 6, pilot validation:** representative datasets, pilot businesses, usability testing, feedback, and critical bug fixes.

Bank, Mobile Money, POS, large-scale data lake, complex ML, and chatbot-first work are outside the current slice.

## Known limitations

This is an MVP development foundation, not a production deployment:

- Storage is local SQLite and filesystem storage.
- The default signing secret is for development and must be replaced before deployment.
- Logout/revocation, richer business profiles, upload limits, malformed XLSX handling, and stronger production security controls remain follow-up work.
- Processed JSONL is currently an internal storage artifact; a stable read API will be added before analytics consumers depend on it.
- The frontend is an ingestion workspace, not the final analytics dashboard.

## Product principles

- Deterministic metrics are the source of truth; generated text cannot invent numerical results.
- Insights should be traceable to the dataset and calculations that produced them.
- Tenant boundaries and uploaded business data must be protected.
- Each sprint should produce a working, observable user path with focused tests.
