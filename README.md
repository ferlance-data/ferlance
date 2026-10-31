# Ferlance

Ferlance is business intelligence for small and growing businesses, starting with Ghana. It turns the records owners already keep — spreadsheet exports, Mobile Money SMS alerts, stock counts and account balances — into trustworthy numbers, plain-language insights and grounded answers.

```text
import records -> validate every row -> scoped metrics + period comparison -> insights -> ask Lance
```

For how the system fits together, the product benchmarks behind the redesign, and what was removed and why, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Implementation status lives in [MVP_PROGRESS.md](MVP_PROGRESS.md) and the import rules in [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md).

## What it does

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

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000. The landing page is `/`; the workspace is `/app`.

Copy `.env.example` to `.env` to configure secrets and the optional AI and search providers. Set a strong `FERLANCE_SECRET_KEY` (32+ characters) for anything beyond local development. Data is stored under `data/` (SQLite, raw uploads, processed JSONL) — set `FERLANCE_DATA_DIR` to move it. That directory is local runtime state and is not tracked in git.

## Market research

Settings → Web research accepts a business-owned Brave Search API key, encrypted with a key derived from `FERLANCE_SECRET_KEY` (rotating the secret makes stored keys unreadable; reconnect afterwards). On the Insights page, "Research this period" looks for period-over-period declines and recorded item losses and searches for Ghanaian seasonal, weather, festive and market context. Only product labels, dates and the market are sent — never amounts or customers. When an AI provider is configured, Lance assesses the snippets with citations; results remain contextual leads, not causes.

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
