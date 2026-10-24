# Ferlance MVP

Ferlance is a business intelligence platform for African SMEs, initially focused on Ghana.

This repository contains the first post-research MVP slices, aligned with completed Sprint 3 and Sprint 4:

```text
create account -> create business -> upload sales data -> validate and clean -> inspect dataset history
```

The current slice includes JWT-backed authentication, a public landing page, a protected responsive app shell, reliable ingestion, deterministic revenue analytics, grounded insights, predefined business questions, OpenRouter-backed Ask Lance, and business-wide RAG.

For the authoritative implementation status, evidence, risks, and next done condition, see [MVP_PROGRESS.md](MVP_PROGRESS.md).
For the latest end-to-end stress-test results, corrected defects, and remaining finance/production gaps, see [docs/SYSTEM_STRESS_TEST.md](docs/SYSTEM_STRESS_TEST.md).

## Current capabilities

- Create an account and initial business workspace.
- Authenticate with a signed bearer token.
- Upload CSV and XLSX sales files.
- Normalize supported dates and currency-like numeric formats.
- Reject duplicate transaction IDs while preserving identical rows that lack IDs, since repeated same-value sales can be legitimate.
- Preserve accepted records as normalized JSONL.
- Record dataset status, row counts, warnings, and errors.
- View dataset history for the authenticated business.
- Read accepted normalized records for an uploaded dataset.
- View filtered revenue and daily/weekly/monthly/quarterly/yearly trends, product, customer, and KPI analytics.
- Browse a searchable, sortable full product list inferred from the selected upload.
- Manage a separate, business-scoped inventory catalogue with SKU, unit, unit cost, reorder levels, opening stock, and archive/restore.
- Record purchases, sales/stock issues, and signed adjustments in an auditable stock ledger; block movements that would take stock below zero.
- View on-hand quantities, low-stock alerts, recorded-cost stock estimates, movement history, and printable inventory reports.
- Import explicit CSV stocktakes to create products or reconcile counted quantities; sales-report imports never adjust inventory automatically.
- Review clean import summaries with accepted/rejected row counts and a searchable import history.
- Generate a printable financial report from the selected dataset and date range, including financial summary, item/customer performance, trends, insights, and data limitations.
- Configure business-encrypted Brave Search credentials for automatic research of detected sales declines and item losses, with source links and cautious, evidence-based Ask Lance context.
- Record dated account balances and generate or print an assets/liabilities/equity position statement for a selected date, including partial-total and stale-balance warnings.
- View per-item profit/loss, margin, and return on recorded item cost when complete cost data is available.
- View automatic, evidence-backed business insights on the dashboard, including product losses and the highest item return.
- Display financial values in Ghanaian cedi (`GHS`) using the Ghana locale.
- Use the browser interface at the root URL.
- Accept flexible sales, operating cost, procurement, cloud cost, and budget headers; see [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md).
- Rank products by revenue, transaction count, profit, or loss when the required cost data is available; select day, week, month, quarter, or year trend tabs.
- Upload unit-cost columns; when quantity is supplied, the processor calculates the record's total cost as unit cost multiplied by quantity.
- Ask Lance can produce grounded natural-language summaries through OpenRouter when `OPENROUTER_KEY` is configured in `.env`.
- Ask Lance supports saved, dataset-pinned conversations with follow-up questions and tenant-scoped history.
- Ask Lance uses business-scoped RAG over accepted rows from all processed datasets, with SQLite FTS5 retrieval and cross-dataset analytics.
- Use `backend.universal_ingestion.UniversalCSVIngestionEngine` for schema-flexible CSV ingestion across sales, costs, budgets, projections, payroll, procurement, and textual logs.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000.

The public landing page is at `/`; authenticated workspaces run at `/app`. Access tokens are short-lived JWTs held in the app session, while refresh sessions are rotated and revoked server-side through an HttpOnly cookie.

The service uses SQLite metadata and local files under `data/` by default. Set `FERLANCE_DATA_DIR` to change the storage directory.

## Market research and financial position

The Insights workspace can connect a business-owned Brave Search API key. Set a strong, persistent `FERLANCE_SECRET_KEY` of at least 32 characters before saving the integration; Ferlance derives a separate Fernet key to encrypt credentials in the business integration table. Changing the application secret makes existing encrypted integration keys unreadable, so reconnect the provider after rotating it. The key is never returned to the browser after saving.

With a Brave connection and a selected dataset, Ferlance automatically searches when report data indicates a period-over-period revenue decline or a recorded product loss, and repeats the search when the dataset or date filter changes. The search uses product labels, the report dates, and Ghana market terms for seasonality, weather, environmental conditions, festivals, holidays, and market context. Transaction rows, financial amounts, and customer details are not sent to Brave. Search results are linked in the Insights workspace and can be included in the printable financial report. Ask Lance assesses the returned snippets only when an LLM provider is configured; otherwise the sources remain available and the UI reports that automated source analysis is unavailable. Search results are contextual leads, not verified explanations or proof of causation. Provider usage may incur charges, and live external search requires a valid Brave API key and internet connectivity.

The Financial position workspace accepts manually entered, dated balances for cash, bank, receivables, inventory value, fixed assets, liabilities, and equity. A report for a selected date uses the latest balance entered on or before that date for each account; older carried-forward balances are marked stale. Missing categories remain missing rather than being treated as zero, so totals may be partial. Record zero balances for categories that do not apply if you want the category-completeness check to pass. These append-only balance snapshots support an operational point-in-time statement; they are not a complete general ledger, automatic inventory valuation, or accountant-reviewed financial statement.

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

The universal ingestion engine returns typed records, row-level quarantine reasons, domain classification confidence, canonical mappings, checksum, encoding, delimiter, and schema metadata. See [docs/REUSABLE_PROMPTS.md](docs/REUSABLE_PROMPTS.md) for reusable engineering prompts.

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

The existing MVP upload path requires a recognized date and at least one recognized revenue, total-cost, or unit-cost column. The standalone universal engine also supports date-less records such as BOM lines, while preserving the limitation that time-based analytics need dates. Optional columns include transaction ID, product or service, customer or supplier, and quantity. Cost-only files are retained as costs with zero revenue and do not inflate sales; they cannot produce profit until revenue and costs are available together. Invalid rows are rejected with warnings; the normalized JSONL output preserves accepted records without silently hiding the rejection counts. Duplicate transaction IDs are rejected, but identical rows without IDs are preserved because they may represent separate legitimate sales. Uploads return `processed` when all rows are accepted, `partial` when some rows are rejected, and `failed` when no rows can be accepted. See [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md) for the complete category-by-category contract and examples.

## Dataset contract

Supported extensions are `.csv` and `.xlsx`. Column names are matched case-insensitively after removing spaces and punctuation.

Required fields:

- `transaction_date`, `date`, or `sale_date`
- `amount`, `sales_amount`, `revenue`, `total`, or `sale_amount`

Optional fields include transaction ID, product, customer, and quantity. Rows with invalid dates or amounts are rejected with row-level warnings. Duplicate transaction IDs are rejected. Identical rows without IDs are retained because the processor cannot reliably distinguish a duplicated import from two genuine equal-value transactions.

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
- Inventory analytics remain unavailable until stock snapshots or stock movements are provided.
- Profit after recorded costs requires revenue and cost on every accepted record in the selected period; incomplete cost data is deliberately shown as unavailable rather than assumed to be zero.
- ROI is profit after recorded item cost divided by recorded item cost, not net return; unassigned overhead, tax, financing, and currency conversion are not inferred. The legacy API field is named `gross_profit`, but it is not a formal accounting gross-profit measure.
- Multi-currency totals are not converted to a common currency; Ask Lance groups cross-dataset metrics by currency and does not offer a consolidated monetary total.
- LLM features and RAG are available when configured; deterministic metrics and insights remain the source of truth.

## Product principles

- Deterministic metrics are the source of truth; generated text cannot invent numerical results.
- Insights should be traceable to the dataset and calculations that produced them.
- Tenant boundaries and uploaded business data must be protected.
- Each sprint should produce a working, observable user path with focused tests.
