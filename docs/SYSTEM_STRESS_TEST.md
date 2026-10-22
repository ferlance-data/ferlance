# Ferlance System Stress Test

**Audit date:** 2026-10-22

**Scope:** Current repository implementation of imports, analytics, Ask Lance/RAG, inventory, authentication, external research, dated financial-position reporting, and their automated tests.

## Executive assessment

Ferlance is a useful SME decision-support prototype, but it is not yet a finance-grade book of record or a substitute for accounting software. Stress testing found and corrected several defects that could distort reported sales, cost trends, cross-currency summaries, or session behavior. The current build passes the full automated suite.

The largest remaining gap is accounting architecture: the application does not maintain a double-entry general ledger, distinguish cost of goods sold from operating expenses, reconcile bank/cash balances, or produce an accountant-reviewed profit-and-loss statement. Labels and documentation must continue to describe calculated profit as *profit after recorded costs*, not formal net income.

## Work performed and fixes applied

| Area | Stress case / observed risk | Change |
| --- | --- | --- |
| Transaction ingestion | Two legitimate same-day sales with identical values and no transaction IDs were treated as duplicate fingerprints and one could be dropped. | Preserve identical rows when no unique transaction ID is supplied. Continue rejecting repeated IDs within a file. |
| Financial parsing | Text such as `10abc20` could be stripped into a plausible number; malformed comma grouping could also be accepted. | Require the whole amount to match a supported numeric format; validate comma grouping and finite values. Keep valid zero and leading-decimal amounts. |
| Blank amounts | A row with a date and a financial column but no financial value could be counted as a zero-value record. | Reject rows with no amount, cost, or unit-cost value. Cost-only rows remain valid. |
| Column mapping | When files included both specific and generic headers (for example `revenue` and `total`), set iteration could choose a different field nondeterministically. | Establish explicit, semantic alias priority and reject duplicate normalized headers in CSV/XLSX imports. |
| Profit/loss | A fully costed period with net-zero revenue could report profit as unavailable, hiding a valid loss. | Calculate profit whenever a non-cost-only period has complete costs, including zero or negative net revenue. |
| Cost trends | Missing row costs were implicitly summed as zero in cost trends. | Withhold cost trends if any accepted row in the selected period has no cost; show an explicit warning. |
| Cross-dataset currencies | Ask Lance could add GHS and USD amounts and label the result as a single currency. | Group cross-dataset analytics by currency and suppress consolidated totals when currencies differ; instruct Lance not to combine them. |
| RAG data availability | Missing or corrupt processed files could be silently skipped, yielding answers from incomplete business data. | Return an explicit 503 with a re-upload instruction rather than generating an incomplete answer. |
| Chat failure handling | A failed model request could leave an empty saved conversation. | Persist a new conversation only after a successful answer. |
| Refresh-token rotation | Two concurrent requests could both observe one refresh token as valid before either revoked it. | Rotate the token inside one SQLite `BEGIN IMMEDIATE` transaction and enforce single-use behavior. |
| Inventory concurrency | Concurrent sales against the same final unit could overdraw stock if checks were not serialized. | Regression-tested the existing immediate transaction: one concurrent sale succeeds, the other is rejected. |
| Stocktake input | A quantity such as `1,2` could be read as `12`. | Require valid thousands grouping in stocktake numeric fields. |

The behavior changes are documented in [README.md](../README.md) and [DATA_CONTRACT.md](./DATA_CONTRACT.md).

## Validation evidence

- Full regression suite: **76 passed**.
- The suite emitted **163 dependency deprecation warnings** from the installed Starlette/FastAPI/AnyIO stack. They did not fail tests, but the dependencies should be upgraded and revalidated before moving to a Python release that removes the deprecated asyncio API.
- Targeted stress regressions cover malformed and zero-valued financial inputs, identical transactions without IDs, explicit duplicate IDs/headers, incomplete-cost trends, zero-net-revenue loss, multi-currency business-wide Ask Lance context, corrupt processed records, provider failure persistence, concurrent refresh-token reuse, and concurrent inventory sales.
- Existing analytics stress case rolls up **10,080 records** and checks total preservation.
- `node --check frontend/assets/app.js` and `git diff --check` passed.
- The tracked local SQLite database was restored after the suite.

This is automated functional and concurrency testing, not a sustained load, penetration, disaster-recovery, or live-provider test. Brave Search and production LLM APIs were not contacted. No browser UI code changed in this audit.

## Remaining material gaps, ranked

### P1 — Accounting correctness and reconciliation

1. **No general ledger or double-entry controls.** Revenue, costs, and expenses are inferred from flat-file columns. COGS, operating expenses, tax, discounts, refunds, owner draws, accruals, depreciation, and financing are not modeled as balanced journal entries.
2. **Separate sales and expense files do not form an audited P&L.** Ask Lance can retrieve both, but the system correctly cannot assert profit when corresponding costs are missing from sales rows. It cannot establish whether cost records are COGS, overhead, inventory purchases, or cash payments.
3. **Import overlap can still double-count across files.** Duplicate IDs are rejected within a file only. Repeated rows without IDs are intentionally retained, because they may be legitimate transactions. Overlapping exports or re-uploaded files need an explicit idempotency/overlap workflow before business-wide totals can be treated as consolidated.
4. **Currency conversion is unsupported.** Cross-dataset Ask Lance results are now separated by currency, but each uploaded dataset is treated as a single currency and no FX source, conversion date, or realized/unrealized exchange accounting exists. Do not combine currency-specific values manually.
5. **Financial position depends on manually entered balances.** It is an operational snapshot, not a trial balance or a complete financial statement. Its inventory value is independent from ledger stock values, and there is no reconciliation workflow to prove balances.

### P1 — Inventory valuation

Inventory value uses the product's current unit cost for all units on hand. It does not retain cost layers or calculate FIFO/weighted average, landed costs, expiry losses, multi-location stock, or accounting COGS. Purchases and sales in the inventory ledger do not automatically post accounting entries. Do not use its stock valuation as statutory inventory valuation.

### P2 — Production resilience and scale

1. **Upload processing is memory-bound.** The upload byte limit is enforced, but the processor materializes CSV/XLSX rows and normalized records in memory. A small compressed spreadsheet can expand substantially. No large-file sustained-load or ZIP-bomb test was run.
2. **Operational controls are incomplete.** There is no demonstrated backup/restore drill, structured audit-log export, data-retention workflow, or deployment monitoring/alerting.
3. **Authentication needs production hardening.** Login/signup rate limiting and automated abuse monitoring were not found in the reviewed implementation. The development signing secret remains the default unless deployment configuration replaces it; deployment must use a high-entropy persistent secret, HTTPS, secure cookies, and a managed secrets process.
4. **External integrations remain environment-dependent.** Live Brave Search behavior, quotas, billing, latency, and provider error conditions were not tested with a real key. LLM assessments can fail or be wrong; external context is not proof of causation.
5. **Dependency lifecycle needs attention.** The passing suite still emits deprecation warnings from the current web stack; pinned dependencies need a tested upgrade path before the deprecated runtime APIs are removed.

## Recommended next gates

1. Before relying on the product for bookkeeping, define and implement an auditable chart of accounts and journal-entry model, separating COGS, operating expenses, taxes, refunds, inventory purchases, and cash movements. Reconcile the trial balance and financial statements against accountant-prepared examples.
2. Define import lineage and overlap behavior: retain source-file checksums, transaction IDs, source-row references, and an explicit review/merge step. Never silently deduplicate identical transactions without a reliable key.
3. Specify currency per amount (including source, FX rate, effective date, and reporting currency) or enforce one currency per import and fail closed on ambiguous mixed-currency columns.
4. Add bounded streaming/row limits and adversarial XLSX decompression tests; run representative 10 MB upload and concurrent-user benchmarks before raising upload limits.
5. Before production deployment, enforce non-default secrets, login throttling, secure cookie/TLS configuration, backup/restore drills, access auditing, and a documented data-retention policy.
6. Pilot with reconciled Ghanaian SME records covering refunds, VAT, discounts, cash/mobile-money settlements, credit sales, stock purchases, shrinkage, supplier costs, and month-end closing. Record discrepancies against an accountant-approved ledger.
