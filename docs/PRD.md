# Ferlance product requirements: update phase (v1.x)

| | |
| --- | --- |
| Status | Phase 1 (v1.x) delivered through v1.9.0; #9 in progress. Phase 2 (§9) drafted 2026-11-22 for owner review. |
| Baseline | v1.0.0, the React + TypeScript migration (PR #12, merged 2026-11-21) |
| Supersedes | `docs/UPDATE_PLAN.md`. The owner's original brief is kept verbatim in the appendix. |
| Related | `docs/PERSONAS.md`, `docs/ARCHITECTURE.md`, `docs/DATA_CONTRACT.md`, `docs/HANDOFF.md`, `CHANGELOG.md` |

## 1. Goals

1. **Less typing and more trust in stock and sales data.** Capture inventory from photos and documents (OCR), and keep the inventory and product catalogues in sync.
2. **Owners can bring their team in.** A guided onboarding flow, and an admin console for platform operators.
3. **A more mature, intentional interface.** One documented design system, with analytics visuals that are animated, responsive and accessible.
4. **Better answers from Ask Lance.** Improve retrieval only where it measurably helps, without slowing the app or adding running cost.
5. **Data out, for growth.** A durable, low-cost export path to AWS for analysis outside the app.
6. **Mobile.** An Expo app for iOS and Android, used for internal testing in this phase.

Every goal is judged against the four personas in `docs/PERSONAS.md`: a market trader on MoMo, a pharmacy owner, a services firm with an accountant, and a growing retailer on Excel.

## 2. Principles (unchanged from ARCHITECTURE.md)

- Deterministic numbers are the source of truth. The LLM explains numbers and never produces them.
- Missing is not zero. Nothing is dropped silently. One scope everywhere.
- No placeholder features. Each feature ships end to end or not at all.
- **New in this phase:** the low-end Android phone on mobile data is the reference device. A feature that regresses first-load weight or interaction latency there has to justify it in its PR.

## 3. Release plan and versioning

Ferlance follows [Semantic Versioning 2.0.0](https://semver.org/). The version lives in `frontend/package.json` and in `FastAPI(version=…)` in `backend/main.py`, and the two must match. Each release is tagged `vX.Y.Z` on its `main` merge commit and has an entry in `CHANGELOG.md` ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).

- **MAJOR:** an incompatible API or data change, such as a breaking change to an endpoint shape or a migration that cannot be rolled back.
- **MINOR:** each feature below.
- **PATCH:** fixes and follow-ups.
- Docs-only and tooling-only changes stay under *Unreleased* and ship with the next release.

| Version | Content | Features |
| --- | --- | --- |
| 1.0.0 | React migration (parity) | done |
| 1.0.x | Migration follow-ups (§5.0) | F0 |
| 1.1.0 | Design system and interface refinement | #7 |
| 1.2.0 | Insights that say what to do; free outside context (owner request, 2026-11-22) | A1 |
| 1.3.0 | Analytics visuals | #6 |
| 1.4.0 | Team access: roles, invites, business switcher, AI daily cap | #4 (4.2) |
| 1.5.0 | Onboarding flow and admin console | #4 (4.1, 4.4), #5 |
| 1.6.0 | OCR inventory capture | #1 |
| 1.7.0 | Inventory↔product sync | #2 |
| 1.8.0 | Retrieval improvements for Ask Lance | #8 |
| 1.9.0 | Data export to AWS | #3 |
| 1.10.0 | G1 ledger beside the existing reports (§9) | G1 |
| later | Expo mobile app (internal testing) and shared API types. **Deferred by the owner, 2026-11-22.** | #9 |

The order follows the agreed handoff plan. #6 builds on the #7 tokens. #2 reuses the #1 review flow. #3 and #9 carry the most external cost and credentials, so they come last.

## 4. Process (per-change gate)

Each feature has its own `feat/*` branch off `main` and its own PR. A PR is ready for the owner only when all of these are true:

1. **Persona check.** The PR description holds the persona table from `docs/PERSONAS.md`. It answers "Does the app provide ease, comfort and value to the Ghanaian SME?" for each persona the change targets. `/loop` runs a prompt on an interval, so it suits iterating on a change until the check passes, not a one-shot review. A one-shot check in the PR is the default.
2. **Verification.** The following must all pass:
   - `npm --prefix frontend run check`
   - `npm --prefix frontend run build`
   - `.venv/bin/pytest -q`
   - a browser check of the changed screens in light and dark at phone width (360–390 px) and on desktop, using `tools/verify`
   - for UI changes, the gzip size of the entry bundles, before and after
3. **`/code-review`.** Run it on the diff and apply the fixes. Add `/security-review` for anything touching auth, uploads, roles, secrets or external services.
4. **Release bookkeeping.** Add a CHANGELOG entry, bump the version in both places, and tag after merge.

Credentials (AWS, OCR provider, Expo/EAS) are requested only at the step that needs them. Secrets go in environment variables or the encrypted `business_integrations` store, and never in git.

## 5. Feature requirements

### 5.0 F0: Migration follow-ups (v1.0.x)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| F0.1 | Shrink the workspace first load, about 100 KB gzip today against 29 KB before the migration | Done in v1.0.1. The measured breakdown of the shell's minified JS was react-dom 65%, react-router 12%, TanStack Query 10% and app code 9%. React alone is about 60 KB gzip, so the original 60 KB target cannot be met on React. The budget is now **first-visit JS+CSS for `/app/overview` at 110 KB gzip or less on the wire**: v1.0.1 measures 108 KB, against about 383 KB before, because the server sent everything uncompressed. App-only releases should re-download 15 KB gzip or less (the vendor chunk is cached separately). Going further needs Preact (an owner decision, §8). |
| F0.2 | Stop the old date window flashing after a file switch with a preset range (`useScopedQuery`) | Done in v1.0.1. Each dataset stores its record date span, so presets resolve before the first request. |
| F0.3 | Product name sort can go Z→A (`nextSort`) | Done in v1.0.1 |
| F0.4 | Exercise a real AI provider once (Brave was removed; outside context is free) | A recorded run with the owner's AI key. Requested at this step. |

### 5.0a A1: Insights that say what to do (v1.2.0)

**Owner request:** go beyond "which product sells best". Tell owners what to sell more of, what to watch, what is doing badly and *why*, with suggestions. The AI answer should appear only when the owner taps for details. Drop Brave, because there is no key, and use free search.

| ID | Requirement | Acceptance |
| --- | --- | --- |
| A1.1 | Deterministic suggestions ranked by money at stake: sell more, decline, stopped, loss, margin squeeze, restock, slow stock, product or customer concentration, busiest day | Works with no AI key. A change needs at least 3 earlier sales before it is reported. Each signal degrades cleanly when cost, quantity, customer or a year of history is missing, and names what is missing. |
| A1.2 | Reasons with evidence and a confidence label; actions that are concrete | *Likely* means shown by the records; *possible* means context (calendar, seasonality, stock now). Every action names a product, quantity or price where one is known. |
| A1.3 | Tap for details. The AI explanation loads only then. | The server rebuilds the item, with nothing taken from the client. No customer names go into the prompt. Answers are cached per evidence. Rendering is safe (no HTML). |
| A1.4 | Free outside context only | A Ghana calendar plus keyless GDELT news. Lookups are bounded (wait 1 s or less, timeout 4 s) and never block the answer. Brave and SerpAPI are removed, and stored Brave keys are deleted. |

**Not yet done:** inventory matching uses exact names until #2 adds product mapping. The calendar must be reviewed each year.

### 5.1 #7: Design system and interface refinement (v1.1.0)

**Why:** The interface should feel mature and intentional. The owner's reference is a multi-brand, platform-agnostic design system (EarnIn, on Dribbble). We take its *principles*: tokens organised by tier, a component inventory, density and consistent rhythm. We do not copy its visuals or brand.

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 7.1 | A three-tier token system: primitive → semantic → component. It extends `src/styles/base.css` and keeps the current Lev-derived identity. | The tokens are documented in `docs/DESIGN_SYSTEM.md`. Light and dark both come from the semantic tier. No hard-coded colours outside the token files (checked with grep or lint). |
| 7.2 | A component inventory of the primitives in use: buttons, inputs, pills, cards, tables, dialogs, empty, loading and error states | Each primitive has documented variants and states, and is used consistently on every page |
| 7.3 | Responsive pass | No horizontal scroll at 360 px. Tap targets are at least 44 px. Tables have a phone layout. |
| 7.4 | Accessibility | WCAG 2.2 AA contrast in both themes, visible focus and keyboard reachability. An axe pass shows no serious violations. |
| 7.5 | The token set is shareable with design tools | Optional: export to Figma through the Figma connector for owner review |

**Non-goals:** a brand-new identity, a component library package, or theming per business.

### 5.2 #6: Analytics visuals (v1.2.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 6.1 | Circular visuals where they fit the data: a donut or ring for composition (revenue share by product or channel) and radial progress for goals or completeness, such as data completeness and the setup guide | Each chart has a text or table equivalent. Values are always labelled, never colour-only. |
| 6.2 | Animated and responsive charts | Transitions are 300 ms or less, run on the GPU (transform and opacity), and are disabled under `prefers-reduced-motion`. Charts resize with their container, with no layout shift. |
| 6.3 | Keep charts dependency-light | Extend the in-house SVG chart (`src/lib/chart`) first. A library is added only if it costs no more than 15 KB gzip on the routes that use it, and it is lazy-loaded. |
| 6.4 | Charts read the same scope as everything else | They use the existing scoped queries, with no new data paths |
| 6.5 | Honest visuals | A donut is never used for more than about 6 categories (the rest go into "Other"). Missing costs show as "missing", not as zero. |

**Risk:** Animation on low-end Android. Mitigation: profile on a throttled CPU in the browser check.

### 5.3 #4/#5: Onboarding, team access and admin console (v1.3.0)

**Current state:** `backend/routers/admin.py` already provides `GET /api/admin/capabilities`, `GET /api/admin/users` and `PATCH /api/admin/users/{id}/role`, gated by `FERLANCE_ADMIN_EMAILS`. Settings already has an admin card. This feature *extends* what exists. It does not build a second console.

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 4.1 | First-run onboarding driven by real state. The existing setup guide becomes a short guided flow: business profile, first import (file or MoMo SMS), optional stock, then a first question. | It can be skipped and resumed. Every step writes real data. No questionnaire whose answers go unused (ARCHITECTURE "What was removed"). |
| 4.2 | Team access: the owner invites a member (manager, accountant) to a business with a role | Invite by link or code, with expiry and single use. Roles are enforced server-side on every business-scoped route. There are tests for cross-tenant and cross-role denial. |
| 4.3 | Admin console for platform operators | Users and businesses list with search, role management, account disable and enable, and an audit log of admin actions. Admin routes go through `/security-review`. |
| 4.4 | Onboarding status is visible to admins | Admins can see who stalled at which step (aggregate counts, no business data) |

**Non-goals:** billing, impersonation, or SSO.

**Risk:** The role model touches every router. Mitigation: one dependency in `deps.py`, plus a test matrix.

### 5.4 #1: OCR inventory capture (v1.4.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 1.1 | Capture a photo or PDF of an invoice, delivery note or stock list. On phone this uses the camera. | Upload works on a flaky connection (retry, size cap, client-side image downscale) |
| 1.2 | Extract line items: name, quantity, unit cost, SKU and expiry where present | Field-level confidence is shown. The fixture set records the extraction accuracy. |
| 1.3 | **Review before write.** Extracted lines are a draft. The owner confirms, edits or rejects each line before any stock movement is written. | Nothing reaches the inventory ledger without confirmation. Rejected lines are kept with their reason. |
| 1.4 | Matching to existing products (exact SKU, then fuzzy name) with a suggested match | The owner can accept, change or create a product |
| 1.5 | The provider is pluggable behind one interface, chosen on cost and privacy, with a local fallback | Provider choice and cost per page are in the PR. The provider key is stored like other integration keys. |

**Risks:** Per-page provider cost. Supplier documents go to a third party (privacy), so this must be disclosed in the UI. Accuracy on low-quality photos.

**Decision needed at build time:** the provider. Candidates: a hosted OCR or document-AI API, a vision-capable LLM through the existing router, or local Tesseract as the fallback.

### 5.5 #2: Inventory↔product sync (v1.5.0)

Today, sales files never change stock (by design), and inventory products and sales products are separate name spaces.

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 2.1 | Product mapping: link sales product names (including per-shop variants) to inventory products | A mapping UI with suggestions. Unmapped names are listed, never dropped. |
| 2.2 | Optional sales→stock posting: the owner opts in per business and per import, and mapped sales post `sale` movements | It is idempotent per dataset. Excluding a file reverses its movements. The ledger still cannot go negative: conflicts are surfaced, not clamped. |
| 2.3 | Reconciliation view: expected stock vs counted stock | Variance by product after a stocktake |
| 2.4 | Shared review components with OCR (#1) | Same draft→confirm pattern |

**Risk:** Double-counting when a file is re-imported. Mitigation: the existing checksum and duplicate detection, plus idempotency keyed on the dataset.

### 5.6 #8: Retrieval improvements for Ask Lance (v1.6.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 8.1 | Measure first: a small eval set of real-shaped questions over the seeded demo data, scored for retrieval hit rate and answer grounding | A baseline score for the current FTS5 pipeline |
| 8.2 | Try hybrid retrieval: `sqlite-vec` embeddings next to FTS5 (reciprocal-rank fusion), in the same SQLite file | Adopt it only if it improves the eval, adds no more than 100 ms p95 to Ask Lance retrieval at demo scale and adds no hosted service. Embedding cost per import must be stated. |
| 8.3 | Keep deterministic answers deterministic | Instant questions and metrics never go through retrieval |

**Non-goal:** a hosted vector database. Reconsider it only if the per-business data outgrows SQLite.

**Outcome (v1.8.0).** Measured with `tools/eval/rag_eval.py`:

| Retriever | Precision@10 | Hit@10 | p95 latency |
| --- | --- | --- | --- |
| v1 FTS5 | 0.78 | 9/10 | 4 ms |
| v2 FTS5 (adopted) | 0.90 | 9/10 | 4 ms |
| v2 + embeddings | 0.91 | 10/10 | about 3,000 ms |

- **v2 FTS5** indexes record values only, drops common question words, applies the date scope and uses porter stemming.
- **v2 + embeddings** was not adopted: it misses the latency budget about 30 times over for a 0.01 gain.

### 5.7 #3: Data export to AWS (v1.7.0)

**Recommendation:** At SME scale a full data lake (Glue catalogue, Lake Formation, Athena over many sources) is overkill. It adds standing cost and operational load without improving the app. Start with a **scheduled, per-business Parquet export to S3**, partitioned by business and date. Athena can query it on demand, so it costs nothing while idle. It can grow into a lake later without rework.

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 3.1 | Scheduled export of normalised records, inventory movements and balances to S3 as Parquet | Runs off the request path. Failures are visible in admin. Monthly cost estimate in the PR. |
| 3.2 | Least-privilege IAM: a write-only role for the exporter. Encryption is on (SSE-S3 or KMS). | The IAM policy is reviewed in the PR. No AWS keys in git. |
| 3.3 | Tenant isolation is kept in the lake layout | One prefix per business. Deleting a business deletes its prefix. |
| 3.4 | Opt-in per deployment (environment config). The app runs unchanged without AWS. | Tests pass with AWS unset |

**Risks:** cost if exports are too frequent or unpartitioned, and data-residency questions for business records. **Credentials needed at this step:** an AWS account, region, bucket and IAM role.

### 5.8 #9: Expo mobile app (v1.8.0, internal testing)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| 9.1 | An Expo (React Native) app for iOS and Android covering sign-in, Overview, MoMo SMS paste, Ask Lance and OCR capture | Runs in Expo Go and as an EAS internal build |
| 9.2 | Shared API types: move `frontend/src/lib/types.ts` (and the API client contract) into a shared package used by web and mobile | One source of types. The web build is unchanged. |
| 9.3 | Auth suited to mobile: refresh tokens in the secure store. The backend must accept non-cookie refresh for mobile clients without weakening the web flow. | A security review of the auth change |
| 9.4 | Works on a budget Android phone on 3G | Cold start and screen timings recorded in the PR |

**Non-goals:** a store release or push notifications (later). **Credentials needed at this step:** an Expo/EAS account. Apple and Google developer accounts are needed only for later store builds.

## 6. Cross-cutting non-goals for v1.x

- Rewriting the backend, or replacing SQLite as the primary store.
- Multi-currency conversion. Mixed currencies are still reported, never summed.
- Payments, billing or subscriptions. (Phase 2 adds MoMo *payment requests* on invoices and debts, but Ferlance never holds or moves money.)
- External database connectors (removed for security reasons, see ARCHITECTURE).

## 7. Risks register

| Risk | Affects | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| First-load weight on mobile data | All | High | High | F0.1 bundle budget, lazy routes, and size checked in every UI PR |
| Animation jank on low-end Android | #6 | Medium | Medium | Transform and opacity only, reduced-motion, throttled-CPU check |
| OCR running cost and privacy | #1 | Medium | High | Pluggable provider, cost per page in the PR, disclosure, review before write |
| Role model regressions (tenant leaks) | #4 | Medium | Critical | One dependency, a denial test matrix, `/security-review` |
| Stock double-counting from sync | #2 | Medium | High | Opt-in posting, idempotency per dataset, reversal on exclude |
| Embeddings slow imports or add cost | #8 | Medium | Medium | Eval-gated adoption, latency budget, no hosted service |
| AWS standing cost and misconfiguration | #3 | Medium | High | Export-first design, least-privilege IAM, cost estimate, opt-in |
| Mobile auth weakens web security | #9 | Low | High | Separate mobile refresh path, security review |
| Copying the reference design too closely | #7 | Low | Medium | Principles only, keep the Ferlance identity |
| Only a mock LLM has been used, never a real provider | #8, Ask Lance | High | Medium | F0.4 real-provider run |

## 8. Open decisions (asked at the step that needs them)

1. The OCR provider (#1): cost against accuracy against privacy.
2. Whether sales→stock posting (#2) is off by default (recommended) or on.
3. AWS account, region and the residency stance (#3).
4. Expo/EAS account (#9).
5. Disabling the unused account-level skills and connectors (`docs/SKILLS_AUDIT.md`).
6. Whether to swap React for Preact (`preact/compat`) to cut about 55 KB gzip from the first visit. The cost: it reverses the React 19 choice, and React 19 APIs, Testing Library and TanStack Query would need re-verifying.

## 9. Phase 2: Ghana-first books (v2.x)

**Status:** draft for owner review, written 2026-11-22. It starts after #9, the Expo app.

### 9.1 Why, and where Ferlance stands

Ferlance today is a strong business-intelligence and stock tool:
- imports from files, MoMo SMS and invoice photos
- an inventory ledger
- plain-language advice and Ask Lance
- team roles
- a daily export

It is **not an accounting system**. The financial-position page is manual balances, "not a substitute for a general ledger" (§5, DATA_CONTRACT).

Measured against QuickBooks, Xero and Wave:

| Capability they all have | Ferlance at v1.9.0 |
| --- | --- |
| Double-entry books (chart of accounts, journals, period close) | Missing. Analytics on imported rows, plus manual balances. |
| Invoices, quotes and receipts, with payment status | Missing |
| Receivables and payables (who owes you, what you owe) | Missing. Only typed-in balance figures. |
| Bank and payment reconciliation | Partial. MoMo SMS is parsed, but not matched against books. |
| P&L, balance sheet and cash-flow statement from the books | Partial. Derived from imports, not from a ledger. |
| Tax: VAT and levies, withholding, filing-ready reports | Missing |
| Payroll | Missing |
| Accountant access and audit trail | Present: accountant role, append-only stock ledger and admin audit |
| Receipt capture and inventory | Ahead of Wave for small shops |

**Positioning:** don't try to out-QuickBooks QuickBooks. In Ghana the records exist, but not digitally:
- an exercise book of daily sales
- a debtors notebook by the till
- MoMo SMS as the cash book
- receipts in a drawer
- payments across cash, MTN MoMo, Telecel Cash and AT Money

The global tools assume someone types clean transactions in. **Ferlance becomes the easiest way for a Ghanaian business to get real books without doing bookkeeping.** An accountant-grade ledger runs underneath, but the owner never sees debits and credits.

### 9.2 Principles added for phase 2

- **The ledger is the source of truth for money.** Every money-moving capture (import, MoMo, invoice, debt, stock purchase, expense) posts balanced journal entries. Reports read the ledger, never the raw rows.
- **The owner never sees debits and credits.** Owners see plain events ("Ama paid GH₵ 200 of her debt"). The accountant role sees journals, the chart of accounts and period locks.
- **Capture stays draft → confirm.** Nothing posts to the ledger without the owner confirming it, the same pattern as OCR (#1) and sync (#2).
- **Tax rules are data, not code.** Rates and levies sit in a dated table with effective dates and a source note, because Ghana's rates changed in recent budgets. Every tax figure says which rule version it used.
- **Ferlance never holds or moves money.** It can show a MoMo "pay to" number or a provider payment link. It does not collect payments.

### 9.3 Release plan

| Version | Content | ID |
| --- | --- | --- |
| 1.10.0 | The quiet ledger, shown **beside** the existing reports (additive, hence MINOR) | G1 |
| 2.0.0 | Switch-over: the ledger becomes the source of truth for money reports, after an accountant signs off the chart of accounts and posting rules (a change to report semantics, hence MAJOR) | G1 |
| later | Expo app with offline capture in mind (§5.8). **Deferred by the owner, 2026-11-22.** | #9 |
| 1.11.0 | Debt book: customer and supplier credit (additive, so a minor; phase 2 features ship as 1.x minors until the 2.0.0 switch-over) | G2 |
| 1.14.0 | Invoices, quotes and receipts, shareable on WhatsApp (1.12.0 was deployment and backups; 1.13.0 the admin suite and dark theme). Done. | G3 |
| 1.15.0 | Read paper books: exercise-book pages to drafts. Done. | G4 |
| 1.16.0 | MoMo and bank reconciliation. Done. | G5 |
| 1.17.0 | Ghana tax and payroll basics (rates from GRA/SSNIT pages, pending accountant checks). Done. | G6 |
| 1.18.0 | Credit-readiness report. Done. | G7 |
| 2.7.0 | WhatsApp channel and local languages | G8 |
| 1.19.0 | Recurring expenses, budgets, year-end pack, data download. Done; branches still to come. | G9 |

**Order:**
- G1 comes first because every other feature posts to it.
- G2 and G3 are the most-used paper records and invoices.
- G4 and G5 make capture effortless.
- G6 needs an accountant's review.
- G7 needs months of ledger history to mean anything.
- G8 depends on a WhatsApp Business account and its costs.

### 9.4 Feature requirements

#### G1: The quiet ledger (v1.10.0 beside reports; v2.0.0 switch-over)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| G1.1 | A double-entry ledger (`journal_entries`, `journal_lines`). Every entry balances to zero per currency and is append-only. Corrections are reversing entries. | DB constraints and tests show no unbalanced entry can be stored. Edits are reversals plus re-posts, and the history stays visible. |
| G1.2 | A default chart of accounts for Ghanaian SMEs: cash, each MoMo wallet, bank, receivables, inventory, payables, VAT/levies payable, owner capital and drawings, sales, cost of sales, and common expenses (rent, transport, data/airtime, electricity/ECG, wages). | The accountant can add or rename accounts. Owners never need to choose one: capture forms map to accounts automatically. |
| G1.3 | Posting rules from existing captures: sales imports, MoMo SMS, OCR stock purchases, sync postings and stocktake variances | Each source has a documented rule and a test. Re-imports are idempotent (keyed on dataset, like #2). Excluding a file reverses its entries. |
| G1.4 | Opening balances, migrated from today's financial-position balances | A guided "where do you stand today" step. Existing balances become opening entries, and nothing is lost. |
| G1.5 | Reports from the ledger: P&L, balance sheet, cash-flow statement and trial balance, for any date range | The balance sheet balances by construction. Cash flow reconciles to cash and MoMo account movement. Missing data is still labelled, never shown as zero. |
| G1.6 | Accountant tools: journal view, manual journal (accountant role only), period lock, and export (CSV, plus a QuickBooks/Xero-compatible journal import) | A locked period refuses new postings. Exports open in QuickBooks Online and Xero import. |

**Risk:** It changes what every money number means. **Mitigation:** run old and new side by side for one release, with a visible "differences" check on the demo data.

#### G2: Debt book (v1.11.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| G2.1 | Record a credit sale ("Ama took 2 bags of rice, will pay Friday") and a supplier credit, in a form as quick as the notebook | Three taps on a phone. Posts receivable or payable entries. Works offline in the Expo app and syncs later. |
| G2.2 | Who owes what, and since when: per customer and per supplier, aged (current, 30, 60, 90+ days) | Totals match the ledger's receivables and payables |
| G2.3 | Reminders: a ready-made WhatsApp or SMS message with the amount and the owner's MoMo number, opened in the phone's own app | Nothing is sent automatically, and the owner sends it. Templates come in English and Twi (G8 adds more). |
| G2.4 | Part-payments and settlement, including matching an incoming MoMo SMS to an open debt | Suggested matches only, confirmed by the owner (feeds G5) |

#### G3: Invoices, quotes and receipts (v1.14.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| G3.1 | Create an invoice, quote or receipt from products and stock, in cedis by default, with business logo, TIN (optional) and a MoMo or bank "pay to" line | A PDF under 200 KB, shareable on WhatsApp. Sequential numbering per business, with no gaps. |
| G3.2 | Invoice status: sent, part-paid, paid, overdue. Paid invoices post to the ledger, and sales from stock post stock movements through #2. | Status matches the debt book. Voiding is a reversal, not a delete. |
| G3.3 | A GRA E-VAT mode for VAT-registered businesses | **Decision at build time:** integrate with GRA's E-VAT system, or produce compliant invoices for manual entry. Needs GRA documentation and an accountant's review. |

#### G4: Read paper books (v1.15.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| G4.1 | Photograph an exercise-book page: daily sales list, debtors page or expense list. It becomes draft lines through the existing OCR pipeline (#1). | Handwriting accuracy is measured on a fixture set of real-style pages (with consent) and recorded in the PR. Low-confidence lines are flagged. |
| G4.2 | Page type detection, with the owner able to correct it: sales, debts, expenses or stock | Each type maps to the matching G1 posting rule |
| G4.3 | Review before write, as in #1 | Nothing posts without confirmation. The page photo is not stored unless the owner opts in. |

**Risk:** Handwriting accuracy and cost per page. Mitigation: confidence flags, the typed-list fallback, and cost per page stated in the PR.

#### G5: MoMo and bank reconciliation (v1.16.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| G5.1 | Import statements: MTN MoMo, Telecel Cash and AT Money statement exports, plus bank CSV or PDF statements | Each format has a fixture and a parser test. Duplicates against SMS-parsed lines are detected. |
| G5.2 | Match statement lines to ledger entries (sales, debt payments, expenses, transfers between own wallets) | Suggested matches only. Unexplained lines are listed, never dropped. The reconciled balance equals the statement balance. |
| G5.3 | MoMo charges and levies are recorded as expenses automatically | Rates come from the G6 rules table |
| G5.4 | Later: direct provider APIs or an aggregator instead of SMS and statements | **Decision at build time:** which provider, its cost, and the business accounts it needs |

#### G6: Ghana tax and payroll basics (v1.17.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| G6.1 | A dated tax rules table covering VAT and levies, withholding tax and MoMo levies, with effective dates and a source note | Rates are **verified against current GRA publications and by an accountant before release**, not taken from memory. Every tax figure names its rule version. |
| G6.2 | VAT and levy calculation on invoices and purchases, and a period summary ready for filing | The summary ties to the ledger accounts |
| G6.3 | Withholding tax on supplier payments, with certificates to give suppliers | Posts to WHT payable |
| G6.4 | A small payroll: staff list, gross pay, SSNIT (employee and employer), PAYE, net pay, and payslips | Totals tie to the ledger. PAYE bands come from the rules table. Targets 1–20 staff. |

**Non-goal:** filing directly with GRA or SSNIT in this phase. Ferlance produces summaries an owner or accountant files.

#### G7: Credit-readiness report (v1.18.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| G7.1 | A business report: revenue trend, margins, MoMo-verified share of sales, debtor quality, stock turnover and months of history | Every figure comes from the ledger and states its coverage. Verified sources (MoMo statements, reconciled bank) are distinguished from typed-in data. |
| G7.2 | Owner-controlled sharing: a time-limited link or PDF with a verification code | Shared only by the owner, and revocable. The lender sees the report, not the records. Every view is logged. |
| G7.3 | A transparent readiness score with the reasons behind it | Not a credit decision. It explains what would raise it, such as "3 more months of reconciled MoMo". |
| G7.4 | Later: lender partnerships (microfinance, rural banks, fintech lenders) | **Business decision:** a revenue model and the data-sharing agreements |

**Risks:** regulatory (data protection, Ghana's Data Protection Act), and lenders over-trusting typed-in data. Mitigation: consent and audit logging, and verified versus typed-in data clearly labelled.

#### G8: WhatsApp channel and local languages (v2.7.0)

| ID | Requirement | Acceptance |
| --- | --- | --- |
| G8.1 | WhatsApp in: send a photo of a page or invoice, or a MoMo SMS, to the business's Ferlance number. It becomes a draft to confirm in the app. | Uses the WhatsApp Business Platform. Cost per conversation is stated in the PR. Messages are tied to a verified phone per business. |
| G8.2 | WhatsApp out: answers to "who owes me?", "today's sales" and "what should I restock?" | The same deterministic numbers as the app, with no AI needed for these |
| G8.3 | Twi first, then Ga and Ewe, for advice, reminders and key screens | Translations reviewed by native speakers. Numbers and amounts stay unambiguous. |
| G8.4 | Later: voice notes in, transcribed into drafts | **Decision at build time:** speech provider, cost and accuracy for Ghanaian languages |

#### G9: Standard additions (2.x patches)

- Recurring expenses (rent, salaries, subscriptions) that post on schedule after confirmation.
- Simple budgets against actuals per month.
- Branches: one business, several shops, with stock and sales per branch and a combined view.
- Year-end pack for the accountant: trial balance, ledgers, debtor and creditor lists, stock valuation, in one zip.
- Backup reassurance: the owner can download their own data at any time (reuses the #3 export).

### 9.5 Phase 2 risks

| Risk | Affects | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| Ledger changes what reported numbers mean | G1, all reports | High | High | Side-by-side release, differences check, MAJOR version |
| Wrong tax rates or rules | G6, G3 | Medium | Critical | Dated rules table, accountant sign-off, rule version shown on every figure |
| Handwriting OCR too inaccurate to trust | G4 | Medium | High | Confidence flags, review before write, typed fallback |
| WhatsApp Business costs and policy limits | G8, G2 | Medium | Medium | The owner's own WhatsApp for reminders first, platform API later |
| Sharing financial data with lenders | G7 | Medium | High | Consent, revocable links, view log, Data Protection Act review |
| Scope creep toward a full ERP | All | High | Medium | Each feature ships end to end, and G9 stays small |

### 9.6 Phase 2 open decisions

1. GRA E-VAT: integration or compliant invoices only (G3.3).
2. Which accountant reviews the chart of accounts, posting rules and tax rules (G1, G6).
3. MoMo provider APIs or an aggregator, and when (G5.4).
4. WhatsApp Business Platform account and budget (G8).
5. Lender partnerships and the revenue model for credit reports (G7.4).
6. Pricing for phase 2 features. Billing is still a v1 non-goal (§6), so it needs a decision before G7.

## Appendix: the owner's original brief (verbatim, from `docs/UPDATE_PLAN.md`)

> This is a skirmish for the update to be done after the migration of the interface for Ferlance
>
> This update features addition of new features, changing or updating old ones, moving on from old practices and testing existing ones to see where they break and where or how to fix them (you do them)
> The use of skills are not limited to what were indicated in the prompt, but they are a personal preference or a starter.
>
> The proposed updates:
> 1. OCR for updating and adding products to inventory
> 2. Syncing inventory and products (The motivation and idea are in similar vein).
> 3. Setting up and connecting to a data lake with AWS (thinking of doing this for the application) - prompt me where this or any other change or current inclusion, or possible direction may degrade the experience, performance or delivery of the proposed idea. Setup this up; prompt me for any credentials or details needed.
> 4. Onboarding steps/flow for users connected to an admin management console such that admins (admin users)
> 5. Develop (or prompt me if there already exists an admi nmanagement app or endpoint/suite within the app)
> 6. Better analytics design (use circular charts, animated and responsive visuals - use a design system or skill from the internet that would support this)
> 7. App-wide interface update/tweak (more responsive, clear interface giving off a more mature, intentional vibe; https://dribbble.com/shots/23850607-EarnIn-s-platform-and-device-agnostic-multi-brand-design-system . You can observe the video from this link to design a design system or update fetched, already existing or created one.
> 8. Suggesting update and improvement of RAG to a proper RAG with a vector database (if necessary - avoid if slows down app considerably or costs too much)
> 9. Implement mobile app version that works across IOS and android via expo for testing. Mobile app release would come later.
>
> You can break this down or update this document itself to give a more comprehensive and well structured or plan for the update (restructure and update this document first before starting updates)
> You can also break down these updates to planned chunks since they are huge updates (so as to avoid burning up too many tokens at once). But if you can, do it all in one session, fanning out subagents for each subtask or feature or skill - ensure a master agent to sign off, sync and avoid clashes over the devlopment process.
> Form or update a PRD stating and giving all information about requirements, changes, updates and keep track of app versions using a robust or standard versioning approach
