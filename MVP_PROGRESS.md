# Ferlance MVP Progress Log

Last updated: 2026-10-01
Current branch: `feature/auth-shell-and-sprint-5`
Current commit: working tree changes on the auth and insights branch

This file tracks repository evidence. A Trello completion flag is not treated as proof that a feature works.

## Product outcome

Ferlance helps Ghanaian SMEs turn fragmented business records into understandable business intelligence. The MVP path is:

```text
business owner -> upload sales data -> validated dataset -> trustworthy metrics -> grounded insights
```

The initial research phase is treated as completed for this implementation workflow. Any research limitations remain assumptions to validate during pilot work; they do not block building the application.

## Sprint status

| Sprint | Scope | Status | Evidence |
| --- | --- | --- | --- |
| Research | Ghana SME context, technology adoption, pain points, and competitors | Assumed complete for implementation | Product brief and backlog context; research artifacts are not present in this repository |
| Sprint 1 | Primary user, value proposition, MVP and non-MVP scope | Partially evidenced | Backlog describes a small retail business owner and CSV/Excel upload through insights; formal specification artifact is not present |
| Sprint 2 | User flow, wireframes, schema, architecture, and conventions | Unverified | Backlog cards exist; implementation follows a minimal version of the proposed boundaries |
| Sprint 3 | Authentication through processed dataset history | Complete | Reliable ingestion contract, safe upload handling, persisted history, and records API validated by 12 focused tests; JWT/session hardening follows on this branch |
| Sprint 4 | Revenue, trend, product, customer, KPI, dashboard analytics, and grounded summary | Complete | Deterministic analytics API, date presets/filters, dashboard chart and tables, conditional metrics, grounded summary, and 18 passing tests |
| Sprint 5 | Deterministic insights, predefined questions, recommendations, and optional assistant | Complete | Structured comparison insights, anomaly thresholding, grounded product recommendations, six predefined questions, responsive app shell, and 24 passing tests |
| Sprint 6 | Pilot onboarding, usability testing, feedback, and bug fixing | Not started | No pilot evidence collected |

## Verified in the repository

- Account signup creates a user and initial business workspace.
- Passwords are hashed before storage.
- Signed bearer tokens protect business dataset routes.
- Users cannot access another business's dataset history.
- CSV and XLSX are accepted by extension.
- Required date and amount/revenue columns are checked.
- Dates and currency-like numeric values are normalized.
- Duplicate transaction IDs or row fingerprints are rejected with warnings.
- Valid rows are stored as normalized JSONL.
- Dataset metadata records status, source rows, accepted rows, rejected rows, warnings, and errors.
- The frontend supports signup, upload, processing feedback, and dataset history.
- Processor tests cover valid data, malformed rows, duplicates, missing columns, and empty files.
- API tests cover signup, upload, history, tenant isolation, and unsupported file types.
- Validation result: `.venv/bin/pytest -q` -> `18 passed, 1 warning`.
- Validation result: `.venv/bin/pytest -q` -> `24 passed, 1 warning` on the auth and Sprint 5 branch.
- Validation result: `/health` -> `200 {"status":"ok"}`.

## Auth and Sprint 5 decisions

These items are intentionally deferred beyond the ingestion milestone:

- Access tokens are standard short-lived JWTs; refresh sessions are server-side, hashed, rotated, revocable, and held in an HttpOnly SameSite cookie.
- The public landing page is `/`; the authenticated app shell is `/app` and bootstraps through refresh plus `/api/auth/me`.
- The optional natural-language assistant, LLM, and RAG remain deferred; deterministic insights are the source of truth.
- F-049 is treated as the deterministic Insight Engine scope because the exported backlog begins Sprint 5 with F-050; the engine covers summaries, comparisons, grounded recommendations, and structured evidence.
- Business profile enrichment, roles, business switching, and audit logging remain deferred beyond the current MVP boundary.

## Next bounded slice

**Sprint 6 pilot validation:** exercise onboarding, upload, dashboard, and insights with representative Ghanaian SME datasets; collect usability feedback and fix critical pilot issues.

Done condition:

```text
pytest passes -> browser onboarding/auth flow works -> representative pilot data produces trustworthy dashboard and insight states -> pilot feedback is recorded
```

Sprint 3 status: complete on `feature/reliable-ingestion-contract`. Uploads return `processed`, `partial`, or `failed`; malformed XLSX files are persisted as failed records; accepted records are available through a tenant-scoped read API; upload size and filename rendering risks are covered.

Sprint 4 status: implemented on `feature/sprint-4-analytics-dashboard`. The dashboard selects a processed dataset, filters inclusive date ranges, renders revenue KPIs and a daily trend chart, shows best/worst product and customer rankings, surfaces data-quality warnings, provides a deterministic grounded summary, and marks profit/inventory unavailable without source fields.

Sprint 5 status: implemented on `feature/auth-shell-and-sprint-5`. JWT auth/session flow, public landing page, protected app shell, deterministic comparison insights, anomaly thresholding, grounded recommendations, six predefined questions, responsive layout, and logout/reload behavior are implemented and browser-smoke validated.

## Scope guardrails

Keep the next slice focused on pilot evidence. Defer bank/Mobile Money/POS integrations, distributed processing, a data lake, complex ML, and chatbot-first work.

## Update protocol

For each meaningful change, update:

1. The sprint status and exact evidence.
2. The verified test or runtime check.
3. Remaining risks and assumptions.
4. The next bounded slice and its done condition.
