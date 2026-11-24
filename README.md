# Ferlance

Ferlance is business intelligence for small and growing businesses, starting with Ghana. It turns the records owners already keep — spreadsheet exports, Mobile Money SMS alerts, stock counts and account balances — into trustworthy numbers, plain-language insights and grounded answers.

```text
import records -> validate every row -> scoped metrics + period comparison -> insights -> ask Lance
```

For how the system fits together, the product benchmarks behind the redesign, and what was removed and why, read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Implementation status lives in [MVP_PROGRESS.md](MVP_PROGRESS.md) and the import rules in [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md). The update-phase requirements and release plan are in [docs/PRD.md](docs/PRD.md), the target users in [docs/PERSONAS.md](docs/PERSONAS.md), the design system in [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md), and release history in [CHANGELOG.md](CHANGELOG.md).

## What it does

- **Overview** — revenue, profit after recorded costs, sales and average sale, each compared with the previous period of the same length; revenue-and-cost trend by day, week, month, quarter or year; a "Needs attention" list (losses, declines, low stock, duplicate files, rejected rows); top products and customers; a setup guide driven by real workspace state.
- **One scope everywhere** — every analytical page reads the same scope bar: all included files or a single file, plus a date range (presets anchor to the latest record, so historical uploads still work).
- **Products** — every product or service ranked by revenue, cost, profit, margin, ROI, units and records, with search and profitable/loss-making filters.
- **Insights** — "What to do now": ranked, plain-language suggestions from your own records (what to sell more of, what is declining or losing money, what to restock, money tied up in slow stock), each with its evidence, likely reasons and actions; tap one for an AI explanation with free Ghanaian news context when AI is configured. Plus deterministic findings and a period comparison.
- **Ask Lance** — saved, grounded conversations over every included file (SQLite FTS5 retrieval + OpenRouter/Groq), plus six instant answers calculated without any AI.
- **Inventory** — catalogue with SKU, unit cost and reorder levels; an auditable stock ledger (purchases, sales, adjustments) that cannot go negative; stocktake CSV imports. Sales files never change stock.
- **Financial position** — dated balances rolled into a point-in-time statement with completeness and stale-balance checks.
- **Data imports** — CSV, XLSX, TSV, TXT and Markdown tables, plus pasted Mobile Money SMS (MTN, Telecel, AirtelTigo). Every rejected row is listed with its reason, identical re-uploads are flagged, and any file can be switched out of business-wide numbers without deleting it.
- **Reports** — print-ready financial, inventory and financial-position reports.
- Light and dark themes; responsive down to phone width.

## Run locally

The frontend build needs Node.js 20.19 or newer.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build          # writes frontend/dist, which FastAPI serves
.venv/bin/uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000. The landing page is `/`; the workspace is `/app` (pages live at `/app/overview`, `/app/products`, …; old `/app#page` links still work).

### Frontend development

```bash
.venv/bin/uvicorn backend.main:app --reload    # API on :8000
npm --prefix frontend run dev                  # Vite on :5173 with hot reload; /api is proxied to :8000
```

Open http://127.0.0.1:5173/app. Set `FERLANCE_API` to proxy to a different backend. Before pushing, run `npm --prefix frontend run check` (type-check, lint and unit tests).

Copy `.env.example` to `.env` to configure secrets and the optional AI and search providers. Set a strong `FERLANCE_SECRET_KEY` (32+ characters) for anything beyond local development. Data is stored under `data/` (SQLite, raw uploads, processed JSONL) — set `FERLANCE_DATA_DIR` to move it. That directory is local runtime state and is not tracked in git.

## Advice and AI explanations

Suggestions on the Insights page are calculated without AI. With an AI key configured (`OPENROUTER_KEY`, `GROQ_API_KEY` or `AGENTROUTER_API_KEY`), tapping a suggestion adds Lance's explanation, cached per suggestion. Outside context comes from free sources only: a built-in Ghana holiday and season calendar, and keyless GDELT news headlines (best effort). No search API key is needed.

## Admin console

Platform administrators use a separate app at `/admin`, with its own sign-in, tokens and session cookie. Admin accounts can be created there only for emails listed in `FERLANCE_ADMIN_EMAILS`.

## Deploying

Ferlance deploys as one Docker web service: the `Dockerfile` builds the React frontend, and FastAPI serves it alongside the API. The data folder must live on a lasting disk. `deploy/aws/user-data.sh` sets up a single AWS EC2 server with HTTPS and no domain needed, and `render.yaml` is a paid Render alternative. A restorable backup goes to S3 every night. See `docs/DEPLOY.md`.

## Books (double-entry ledger)

The Books page keeps real double-entry books automatically from imports, MoMo SMS and stock movements (`backend/ledger.py`). Owners see profit and loss, what the business owns and owes, and money in and out in plain words. The "For your accountant" tab has the journal, manual journals, a period lock, the chart of accounts and a CSV journal export. The database refuses unbalanced or edited entries, and corrections are reversals. Posting rules are listed at the top of `backend/ledger.py`. In v1.10 the books sit beside the dashboards; a comparison card names every difference.

## Debt book

The Debt book page records who owes the business and whom it owes: credit sales, supplier credit, part-payments and voids, aged by how late they are (`backend/debts.py`). Reminders open the owner's own WhatsApp or SMS with the message filled in, and MoMo messages that may pay a debt are suggested for the owner to confirm. Every debt and payment is posted to the ledger, so the debt book's totals equal the books' receivables and payables.

## Daily data export

Set `FERLANCE_EXPORT_BUCKET` (with `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_REGION`) to send each business's data to S3 once a day, after `FERLANCE_EXPORT_HOUR_UTC` (default 02:00 UTC). Or set `FERLANCE_EXPORT_DIR` to write the same files to a folder. Each business gets four Parquet files a day, under `exports/business_id=<id>/dt=<YYYY-MM-DD>/`: `sales_records`, `datasets`, `inventory_products` and `inventory_movements`. A `manifest.json` (run id, row counts, sizes) is written last, so a folder whose manifest is missing or mismatched holds an interrupted run. The layout is Hive-style, so Athena or Glue can query it as-is.

The AWS user needs one permission only: `s3:PutObject` on `arn:aws:s3:::<bucket>/exports/*`. The exporter never reads, lists or deletes, and every object is written with SSE-S3 encryption. Never use root account keys. Administrators see each business's latest run, and any failure, on the Admin page, and can run an export on demand.

## Project layout

```text
backend/
  main.py               app wiring: routers, built frontend, lifespan, cache headers
  deps.py               auth, tenancy, date range and data-scope dependencies
  dataset_store.py      import persistence and scope rules
  routers/              auth, admin, datasets, analytics, inventory, financial_position, lance
  processor.py, universal_ingestion.py, sms_parser.py   ingestion
  analytics.py, insights.py                             deterministic metrics
  inventory.py, financial_position.py                   operational ledgers
  advisor.py, ghana_calendar.py                         plain-language advice
  llm.py, rag.py, news_context.py                       optional AI and free news context
frontend/                React 19 + TypeScript + Vite
  index.html            landing page (static markup) + src/landing/main.ts
  app/index.html        workspace entry -> src/app/main.tsx
  src/lib/              api client, types, formatting, scope, icons, chart, markdown, reports, toasts
  src/app/              shell, routes, workspace/scope context, data hooks, components, views/*
  src/styles/           base.css (design tokens + primitives), landing.css, app.css
  dist/                 build output served by FastAPI (not committed)
tests/                  API, ingestion, analytics, ledger and LLM tests
docs/                   architecture, data contract, PRD, personas, stress-test notes
```

The frontend is built with Vite (`npm --prefix frontend run build`). Hashed bundles are cached for a year; HTML always revalidates.

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
npm --prefix frontend run build     # the serving tests check the real build
.venv/bin/pytest -q
npm --prefix frontend run check     # type-check, lint, unit tests
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
