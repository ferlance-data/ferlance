# Ferlance MVP

Ferlance is a business intelligence platform for African SMEs, initially focused on Ghana.

This repository contains the first post-research MVP slices, aligned with completed Sprint 3 and Sprint 4:

```text
create account -> create business -> upload sales data -> validate and clean -> inspect dataset history
```

The current slice includes JWT-backed authentication, a public landing page, a protected responsive app shell, reliable ingestion, deterministic revenue analytics, grounded insights, and predefined business questions. LLM features and RAG remain follow-on slices.

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
- Read accepted normalized records for an uploaded dataset.
- View filtered revenue, trend, product, customer, and KPI analytics.
- View grounded comparison insights and six predefined business questions.
- Display financial values in Ghanaian cedi (`GHS`) using the Ghana locale.
- Use the browser interface at the root URL.
- Accept flexible sales, operating cost, procurement, cloud cost, and budget headers; see [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md).
- Rank products by revenue, transaction count, profit, or loss when the required cost data is available.
- Ask Lance can produce grounded natural-language summaries through Groq when `GROQ_API_KEY` is configured in `.env`.
- Ask Lance supports saved, dataset-pinned conversations with follow-up questions and tenant-scoped history.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000.

The public landing page is at `/`; authenticated workspaces run at `/app`. Access tokens are short-lived JWTs held in the app session, while refresh sessions are rotated and revoked server-side through an HttpOnly cookie.

The service uses SQLite metadata and local files under `data/` by default. Set `FERLANCE_DATA_DIR` to change the storage directory.

## Project layout

```text
backend/             FastAPI application, SQLite persistence, security, and processing
frontend/            Structured landing page, authenticated app shell, and shared assets
tests/               API and processor tests
tests/fixtures/      Valid and invalid representative CSV files
data/                Local SQLite, raw uploads, and processed output
```

The frontend is a dependency-free structured client: `frontend/landing.html` is the public entry page, `frontend/index.html` is the authenticated app shell, and shared behavior/styles live under `frontend/assets/`.

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

Read normalized records for a dataset:

```bash
curl http://127.0.0.1:8000/api/businesses/<BUSINESS_ID>/datasets/<DATASET_ID>/records \
	-H 'Authorization: Bearer <ACCESS_TOKEN>'
```

The health endpoint is available at `GET /health`.

## Test

```bash
.venv/bin/pytest -q
```

Supported uploads require a recognized date and at least one recognized revenue or cost column. Optional columns include transaction ID, product or service, customer or supplier, and quantity. Cost-only files are retained as costs with zero revenue and can power gross-profit metrics without inflating sales. Invalid rows are rejected with warnings; the normalized JSONL output preserves accepted records without silently hiding the rejection counts. Uploads return `processed` when all rows are accepted, `partial` when some rows are rejected, and `failed` when no rows can be accepted. See [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) for the complete category-by-category contract and examples.

## Dataset contract

Supported extensions are `.csv` and `.xlsx`. Column names are matched case-insensitively after removing spaces and punctuation.

Required fields:

- `transaction_date`, `date`, or `sale_date`
- `amount`, `sales_amount`, `revenue`, `total`, or `sale_amount`

Optional fields include transaction ID, product, customer, and quantity. Rows with invalid dates or amounts are rejected with row-level warnings. Duplicate IDs are rejected; when no ID exists, a stable fingerprint of the normalized row is used.

## MVP roadmap

1. **Sprint 3, ingestion:** complete for the current MVP slice: authentication, business boundary, upload, validation, cleaning, storage, history, records, and useful errors.
2. **Sprint 4, analytics:** revenue, trends, products, customers, conditional profit/inventory metrics, KPI cards, and date filters.
3. **Sprint 5, insights:** deterministic summaries, anomaly detection, recommendations, and predefined business questions. Natural-language assistance follows the core product.
4. **Sprint 6, pilot validation:** representative datasets, pilot businesses, usability testing, feedback, and critical bug fixes.

Bank, Mobile Money, POS, large-scale data lake, complex ML, and chatbot-first work are outside the current slice.

## Known limitations

This is an MVP development foundation, not a production deployment:

- Storage is local SQLite and filesystem storage.
- The default signing secret is for development and must be replaced before deployment.
- Richer business profiles, roles, audit logging, and stronger production deployment controls remain follow-up work; logout and refresh-session revocation are implemented.
- Processed JSONL remains an internal storage artifact; normalized records are exposed through the tenant-scoped dataset records API.
- Profit and inventory analytics remain unavailable unless future input schemas provide the required source fields.
- LLM features and RAG remain future slices; deterministic metrics and insights are the current source of truth.

## Product principles

- Deterministic metrics are the source of truth; generated text cannot invent numerical results.
- Insights should be traceable to the dataset and calculations that produced them.
- Tenant boundaries and uploaded business data must be protected.
- Each sprint should produce a working, observable user path with focused tests.
