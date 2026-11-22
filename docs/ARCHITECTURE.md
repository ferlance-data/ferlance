# Ferlance architecture and product design

Ferlance turns the records small businesses already keep — spreadsheet exports, Mobile Money SMS alerts, stock counts and account balances — into trustworthy numbers, plain-language insights and grounded answers. This document describes how the system is put together, the product decisions behind the October 2026 redesign, and what was removed and why.

## Principles

1. **Deterministic numbers are the source of truth.** Every metric comes from `analytics.py`/`insights.py`. The language model explains numbers; it never produces them.
2. **Missing is not zero.** Profit needs a cost on every record; stock value needs a unit cost on every item; a balance sheet needs every category. When data is incomplete the UI says so instead of guessing.
3. **Nothing is dropped silently.** Every rejected row is stored with its reason and shown on the import.
4. **One scope everywhere.** Every analytical view answers "which files, which dates?" the same way (see *Scope* below).
5. **No placeholder features.** A capability ships only when it works end to end; anything that only looks like it works is removed.

## System overview

```text
Browser (React + TypeScript, built by Vite into frontend/dist)
  /            index.html + src/landing/main.ts     public marketing page (static markup) and auth dialog
  /app/*       app/index.html + src/app/main.tsx    workspace shell, client-side routed pages, views
        │  JSON over HTTPS — Bearer access token (memory) + HttpOnly refresh cookie
        ▼
FastAPI (backend/main.py) — wiring, lifespan, built frontend + SPA fallback, cache headers
  routers/auth.py            signup, login, refresh (single-use rotation), logout, profile
  routers/datasets.py        file uploads, Mobile Money SMS import, history, include/exclude
  routers/analytics.py       metrics + period comparison, insights and advice, instant questions, AI explanations
  routers/inventory.py       catalogue, stock ledger, stocktake CSV import
  routers/financial_position.py  dated balances and point-in-time statements
  routers/lance.py           Ask Lance conversations (LLM + retrieval)
  routers/admin.py           platform operator role management
        │
  deps.py          current user, business roles and permissions, date range, data scope, AI daily cap
  dataset_store.py import persistence and "which records count" rules
        │
  processor.py ─ universal_ingestion.py ─ sms_parser.py      ingestion (CSV/XLSX/TSV/TXT/MD/SMS)
  analytics.py ─ insights.py                                  deterministic metrics
  inventory.py ─ financial_position.py                        operational ledgers
  advisor.py ─ ghana_calendar.py                              plain-language advice (deterministic)
  rag.py (SQLite FTS5) ─ llm.py ─ news_context.py (GDELT)      optional AI and free news context
        │
  SQLite (metadata, ledgers, chats, FTS index)  +  data/raw (uploads)  +  data/processed (JSONL)
```

### Request lifecycle

1. `deps.current_user` validates the JWT access token. Every route under `/api/businesses/{id}` declares the permission it needs with `deps.business_access(...)`: `read`, `write_data`, `write_balances`, `use_ai`, `manage_team` or `manage_business`. The dependency looks up the user's role in `business_members` on every request.
   - **Roles:** owner (everything), manager (data, stock, balances, AI) and accountant (read, balances, AI).
   - **Denials:** a non-member gets 404, so the business's existence is not revealed; a member without the permission gets 403.
   - **Coverage test:** `tests/test_team.py` fails if a business route declares no permission, or if a mutating route only requires `read`.
2. Analytical routes depend on `deps.date_range` (validated before any data is read) and `deps.scope`, which resolves the dataset scope and reads records through `dataset_store`.
3. Routers stay thin: they translate HTTP to service calls and service errors to status codes.

### Scope

Every analytical endpoint (`/analytics`, `/insights`, `/insights/{id}/explain`, `/questions/*`, `/ask-lance`) accepts:

- `dataset_id` — omitted or `all` means **every processed file the owner has not excluded**; an id means that single file (even if excluded).
- `from` / `to` — an inclusive date window.

Previously the dashboard used all files while insights and research silently used only the latest file, so the same screen could disagree with itself. One rule now applies everywhere.

### Imports

- Uploads are streamed to `data/raw`, hashed (SHA-256) and processed. Accepted rows are written as normalized JSONL to `data/processed`; metadata, counts, warnings and errors go to `datasets`.
- An identical re-upload is flagged ("identical to *file* imported on *date*") because importing the same month twice is the most common way small businesses double-count.
- Files are never deleted from analysis destructively: the owner switches a file off (`PATCH /datasets/{id} {"included": false}`) and back on. The audit trail stays intact and Ask Lance conversations keep their references.
- Mobile Money SMS alerts (MTN MoMo, Telecel Cash, AirtelTigo Money) are parsed into the same record shape, with the raw text kept for audit.

### Analytics

`analyze()` returns totals, trends at five grains, product and customer rankings, profit when costs are complete, and data-quality warnings. `compare()` adds a **previous-period comparison** for the same-length window immediately before the selected one, and reports "no earlier period" instead of a misleading +100% when that window is empty.

### Advice ("What to do now")

`advisor.build` turns the scoped records (and the inventory list) into ranked, plain-language items: products to sell more of, decliners, loss-makers, squeezed margins, stock about to run out, money tied up in slow stock, and dependence on one product or customer. Each item carries its evidence, possible reasons labelled *likely* or *possible* (price vs volume, fewer vs smaller sales, regular buyers who stopped, out of stock, same time last year, Ghanaian holidays and seasons from `ghana_calendar.py`) and concrete actions. It is deterministic, needs no AI, and reports which missing columns would unlock more.

Tapping an item calls `POST /insights/{id}/explain`. The server rebuilds the item from the scope (nothing is taken from the client), optionally adds free news headlines from GDELT (`news_context.py`: keyless, rate-limited, best effort, short timeouts), and asks the AI provider chain for a short explanation. Customer names never go into the prompt; file text is wrapped as data. Explanations are cached per business and evidence, so repeat taps cost nothing.

### Ask Lance

1. All included files are read; a currency-aware analytics snapshot is built (mixed currencies are never summed).
2. `rag.retrieve` pulls the most relevant rows from an FTS5 index, restricted to the included files.
3. `llm.ask_lance` sends the snapshot, evidence and recent history to OpenRouter → Groq → AgentRouter, in order.
4. The conversation is persisted only after a successful answer.

Six **instant questions** (`/questions/*`) are calculated without any model, so the assistant is useful even when no AI provider is configured.

### Frontend

React 19 + TypeScript (strict) built by Vite. Two entries: the landing page keeps static markup for first paint and search engines, with a small TypeScript module for its interactions. The workspace is a single-page app.

- `src/styles/base.css` holds design tokens and primitives; `landing.css` and `app.css` build on them. Light and dark workspace themes share one token set; an inline script in `app/index.html` applies the saved theme before first paint.
- `src/lib/api.ts` keeps the access token in memory only. Concurrent 401s share one refresh, because refresh tokens are single-use. A failed refresh sends the user to `/?signin`.
- `src/app/workspace.tsx` provides identity, datasets, inventory and the **scope** (files + dates) to every view. Server data is cached with TanStack Query. Scoped reads (`useScopedQuery` in `src/app/hooks.ts`) put the resolved scope in their cache key, so changing the scope refetches and stale responses are discarded.
- `src/lib/router.tsx` is a small history router (links, active nav links, redirects). Navigations run in `startTransition`, so a lazy page keeps the current one on screen until its chunk loads. Date presets anchor to each dataset's stored `period` (its record date span), so the first scoped request already has the right window.
- `src/app/routes.tsx` lists the pages (`/app/<page>`); `Shell.tsx` renders the sidebar, top bar, scope bar and the routed view. Old `#page` links are redirected.
- Rendering safety: everything is rendered as text by React. `dangerouslySetInnerHTML`/`innerHTML` are banned by lint. `src/lib/markdown.tsx` turns Lance answers into elements, and links from API data pass through `safeHref` (http/https only).
- `src/lib/chart/BarChart.tsx` is a dependency-free SVG chart; `src/lib/reports.tsx` renders printable reports into `#print-report`.
- FastAPI serves `frontend/dist`: `/` and `/app/*` return the entry HTML (`no-cache`), and hashed files under `/assets` get `Cache-Control: public, max-age=31536000, immutable`. If the build is missing, pages return 503 with the build command.

## Data model (SQLite)

| Table | Purpose |
| --- | --- |
| `users`, `businesses`, `refresh_sessions` | identity, businesses, hashed single-use refresh sessions. A rotated token gets a one-shot 60 s grace (`replaced_by`), so a refresh whose response is lost on a flaky connection does not sign the user out. |
| `business_members`, `business_invites` | who can access which business, and in what role. Invites are single-use hashed links that expire after 7 days. |
| `ai_usage` | uncached AI calls per business per day (`FERLANCE_AI_DAILY_LIMIT`, default 100) |
| `datasets` | one row per import: status, counts, warnings, `checksum`, `review_status` (`accepted`/`excluded`) |
| `inventory_products`, `inventory_movements` | catalogue and append-only stock ledger |
| `financial_position_balances` | append-only dated balances |
| `business_integrations` | Fernet-encrypted third-party keys (currently unused; kept for future provider keys) |
| `insight_explanations` | cached AI explanations of advice items, keyed by the item's evidence |
| `chat_conversations`, `chat_messages` | saved Ask Lance threads |
| `rag_documents_fts` | FTS5 index of accepted rows |

Runtime data under `data/` is local state and is not tracked in git.

## Product benchmarks: what we borrowed

The redesign studied products that already solve parts of Ferlance's job and kept what fits an SME owner in Ghana.

| Product | What it does well | What Ferlance adopted |
| --- | --- | --- |
| **Lev** (lev.com) | Calm, editorial interface; an agent that shows its working, cites sources and offers follow-ups | The visual language (IBM Plex, ink-green surfaces, mint accent, hairline grids, pill controls); Ask Lance's composer, evidence line and suggestion chips |
| **Shopify Analytics / Square Dashboard** | Every KPI shows a change against the previous period; one global date picker | `compare()` and delta chips on every KPI; one scope bar shared by all analytical pages |
| **Shopify setup guide / Stripe onboarding** | A checklist derived from real account state instead of a questionnaire | The Overview setup guide (import, stock, balances, ask) replaces the old goals/metrics wizard whose answers nothing used |
| **Loyverse / Bumpa** (POS and inventory popular with African SMEs) | Low-stock alerts and a simple stock ledger next to sales | Inventory stays a separate auditable ledger; low stock surfaces in the Overview "Needs attention" list |
| **QuickBooks / Wave** | Statement of financial position and printable reports | Financial position and print-ready financial, inventory and position reports |
| **Fathom / Spotlight Reporting** | Narrative, exception-first reporting | "Needs attention" list: losses, declines, low stock, duplicate files and rejected rows in one place |
| **Julius AI / spreadsheet copilots** | Ask questions of your own data | Ask Lance over business-wide records, plus instant calculated answers that need no AI |

## What was removed, and why

| Removed | Why |
| --- | --- |
| External connectors (PostgreSQL, MongoDB, POS, external SQLite) | Postgres/Mongo/POS "tests" reported success without connecting (POS returned success even when the network call failed); the SQLite connector let any user read any SQLite file on the server by path; credentials were stored in plaintext; no connector ever imported data. |
| Dashboard snapshot cache and `/sync` | Duplicated `/analytics`, swallowed errors on upload, and returned a shape the frontend did not read. Analytics are computed on demand, which is fast at SME data sizes. |
| "Macroeconomic projections" | Hard-coded inflation and exchange rates presented as live benchmarks, and labels such as "Business in Danger" derived from them. Replaced by a factual previous-period comparison; external context comes from cited web research instead. |
| Onboarding questionnaire (goals, metrics, data sources) | Stored answers were never used by any feature. Replaced by the state-driven setup guide. |
| Separate Catalogue page and top/worst modal | Both showed the same product rankings. Merged into one sortable, filterable Products page. |
| Runtime data in git (`data/ferlance.sqlite3`, raw uploads, processed JSONL) | Real business records and password hashes do not belong in version control. |

## Fixed along the way

- The previous frontend called `selectedDataset()` and `filterParams()`, which were never defined, so the workspace failed after sign-in; several forms posted payloads the API rejected (Mobile Money, connectors, onboarding).
- CSV `unit_cost` columns were treated as the total cost of the line, overstating profit whenever quantity was above one. Unit cost is now multiplied by quantity, matching the XLSX path and the data contract.
- Blank quantities or costs in CSV imports were stored as `null` and crashed product analytics; blanks are now treated as absent.
- Concurrent requests that both hit an expired access token each tried to use the single-use refresh token, so one of them signed the user out. They now share one refresh.
- `AGENTROUTER_MODELS` was split into single characters instead of model names.
- Ask Lance sent the oldest twelve messages of a long conversation as history instead of the most recent twelve.
- An administrator could remove their own admin role and lock the workspace out of administration.
