# Ferlance

Ferlance is business intelligence for small and growing businesses, starting with Ghana. It turns the records owners already keep — spreadsheet exports, Mobile Money SMS alerts, stock counts and account balances — into trustworthy numbers, plain-language insights and grounded answers.

```text
import records -> validate every row -> scoped metrics + period comparison -> insights -> ask Lance
```

For how the system fits together, the product benchmarks behind the redesign, and what was removed and why, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Implementation status lives in [MVP_PROGRESS.md](MVP_PROGRESS.md) and the import rules in [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md).

## What it does

<<<<<<< HEAD
- **Overview** — revenue, profit after recorded costs, sales and average sale, each compared with the previous period of the same length; revenue-and-cost trend by day, week, month, quarter or year; a "Needs attention" list (losses, declines, low stock, duplicate files, rejected rows); top products and customers; a setup guide driven by real workspace state.
- **One scope everywhere** — every analytical page reads the same scope bar: all included files or a single file, plus a date range (presets anchor to the latest record, so historical uploads still work).
- **Products** — every product or service ranked by revenue, cost, profit, margin, ROI, units and records, with search and profitable/loss-making filters.
- **Insights** — deterministic findings with their supporting numbers, a period comparison, and optional Brave web research on declines and losses (product names and dates only are sent; results are cited leads, not proof).
- **Ask Lance** — saved, grounded conversations over every included file (SQLite FTS5 retrieval + OpenRouter/Groq), plus six instant answers calculated without any AI.
- **Inventory** — catalogue with SKU, unit cost and reorder levels; an auditable stock ledger (purchases, sales, adjustments) that cannot go negative; stocktake CSV imports. Sales files never change stock.
- **Financial position** — dated balances rolled into a point-in-time statement with completeness and stale-balance checks.
- **Data imports** — CSV, XLSX, TSV, TXT and Markdown tables, plus pasted Mobile Money SMS (MTN, Telecel, AirtelTigo). Every rejected row is listed with its reason, identical re-uploads are flagged, and any file can be switched out of business-wide numbers without deleting it.
- **Reports** — print-ready financial, inventory and financial-position reports.
- Light and dark themes; responsive down to phone width.
=======
## Current capabilities

- Create an account and initial business workspace.
- Authenticate with a signed bearer token.
- Upload CSV and XLSX sales files.
- Automatically import new or changed XLSX workbooks from a business-specific local folder.
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
>>>>>>> feat/dashboard-enterprise-trends

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000. The landing page is `/`; the workspace is `/app`.

Copy `.env.example` to `.env` to configure secrets and the optional AI and search providers. Set a strong `FERLANCE_SECRET_KEY` (32+ characters) for anything beyond local development. Data is stored under `data/` (SQLite, raw uploads, processed JSONL) — set `FERLANCE_DATA_DIR` to move it. That directory is local runtime state and is not tracked in git.

## Market research

<<<<<<< HEAD
Settings → Web research accepts a business-owned Brave Search API key, encrypted with a key derived from `FERLANCE_SECRET_KEY` (rotating the secret makes stored keys unreadable; reconnect afterwards). On the Insights page, "Research this period" looks for period-over-period declines and recorded item losses and searches for Ghanaian seasonal, weather, festive and market context. Only product labels, dates and the market are sent — never amounts or customers. When an AI provider is configured, Lance assesses the snippets with citations; results remain contextual leads, not causes.
=======
Excel folder imports are enabled by default. Each workspace's folder is created under `data/incoming/<business-id>/` (or under `FERLANCE_IMPORT_DIR` when configured); the exact path is shown on the **Data** page. Copy `.xlsx` workbooks there and Ferlance checks for stable files every five seconds. Updated workbooks are imported as new datasets; the source files remain in place, repeated scans of an unchanged file do not create duplicates, and Excel lock files are ignored. The backend must be running and have access to the folder. Folder imports obey the same 10 MB limit and row validation as regular uploads.

## Market research and financial position

The Insights workspace can connect a business-owned Brave Search API key. Set a strong, persistent `FERLANCE_SECRET_KEY` of at least 32 characters before saving the integration; Ferlance derives a separate Fernet key to encrypt credentials in the business integration table. Changing the application secret makes existing encrypted integration keys unreadable, so reconnect the provider after rotating it. The key is never returned to the browser after saving.

With a Brave connection and a selected dataset, Ferlance automatically searches when report data indicates a period-over-period revenue decline or a recorded product loss, and repeats the search when the dataset or date filter changes. The search uses product labels, the report dates, and Ghana market terms for seasonality, weather, environmental conditions, festivals, holidays, and market context. Transaction rows, financial amounts, and customer details are not sent to Brave. Search results are linked in the Insights workspace and can be included in the printable financial report. Ask Lance assesses the returned snippets only when an LLM provider is configured; otherwise the sources remain available and the UI reports that automated source analysis is unavailable. Search results are contextual leads, not verified explanations or proof of causation. Provider usage may incur charges, and live external search requires a valid Brave API key and internet connectivity.

The Financial position workspace accepts manually entered, dated balances for cash, bank, receivables, inventory value, fixed assets, liabilities, and equity. A report for a selected date uses the latest balance entered on or before that date for each account; older carried-forward balances are marked stale. Missing categories remain missing rather than being treated as zero, so totals may be partial. Record zero balances for categories that do not apply if you want the category-completeness check to pass. These append-only balance snapshots support an operational point-in-time statement; they are not a complete general ledger, automatic inventory valuation, or accountant-reviewed financial statement.
>>>>>>> feat/dashboard-enterprise-trends

## Project layout

```text
backend/
  main.py               app wiring: routers, static files, lifespan, cache headers
  deps.py               auth, tenancy, date range and data-scope dependencies
  dataset_store.py      import persistence and scope rules
  routers/              auth, admin, datasets, analytics, inventory, financial_position, integrations, lance
  processor.py, universal_ingestion.py, sms_parser.py   ingestion
  analytics.py, insights.py                             deterministic metrics
  inventory.py, financial_position.py                   operational ledgers
  llm.py, rag.py, market_research.py                    optional AI and web context
frontend/
  landing.html, index.html
  assets/css/           base.css (design tokens + primitives), landing.css, app.css
  assets/js/landing.js  public page
  assets/js/app/        api, state, dom, chart, markdown, reports, views/*
tests/                  API, ingestion, analytics, ledger and LLM tests
docs/                   architecture, data contract, stress-test notes
```

The frontend has no build step: plain ES modules and CSS served by FastAPI.

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

Supported files are `.csv`, `.xlsx`, `.tsv`, `.txt` (including Mobile Money SMS exports) and `.md` tables. Column names are matched case-insensitively after removing spaces and punctuation. Each row needs a date and at least one money column (revenue/amount, cost/expense, or unit cost — multiplied by quantity when quantity is present). Product, customer, quantity and transaction ID are optional. See [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md).

## MVP roadmap

1. **Sprint 3, ingestion:** complete for the current MVP slice: authentication, business boundary, upload, validation, cleaning, storage, history, records, and useful errors.
2. **Sprint 4, analytics:** revenue, trends, products, customers, conditional profit/inventory metrics, KPI cards, and date filters.
3. **Sprint 5, insights:** deterministic summaries, anomaly detection, recommendations, and predefined business questions. Natural-language assistance follows the core product.
4. **Sprint 6, pilot validation:** representative datasets, pilot businesses, usability testing, feedback, and critical bug fixes.

Live bank, Mobile Money API and POS integrations, a data lake, complex ML, and chatbot-first work are outside the current slice. Mobile Money is supported today by importing SMS alerts.

## Known limitations

This is an MVP foundation, not a production deployment:

- Storage is local SQLite and filesystem storage; one owner per business (no team roles yet).
- The default signing secret is for development and must be replaced before deployment.
- Profit after recorded costs needs a cost on every record in the selected period; incomplete costs are shown as unavailable rather than assumed to be zero. ROI and "gross profit" exclude unassigned overheads, tax, financing and currency conversion.
- Multi-currency totals are not converted; Ask Lance groups metrics by currency.
- Ask Lance needs an OpenRouter, Groq or AgentRouter key; instant answers and all deterministic views work without one.

## Product principles

- Deterministic metrics are the source of truth; generated text cannot invent numerical results.
- Insights should be traceable to the dataset and calculations that produced them.
- Tenant boundaries and uploaded business data must be protected.
- Each sprint should produce a working, observable user path with focused tests.
