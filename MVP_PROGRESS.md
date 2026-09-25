# Ferlance MVP Progress Log

Last updated: 2026-09-25
Current branch: `feature/sprint-3-ingestion`
Current commit: `f06f56c feat: build Sprint 3 dataset ingestion MVP`

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
| Sprint 3 | Authentication through processed dataset history | In progress | Working code and passing tests cover the core path; acceptance gaps remain below |
| Sprint 4 | Revenue, trend, product, customer, KPI, and dashboard analytics | Not started | No analytics API or dashboard metrics implemented |
| Sprint 5 | Deterministic insights, predefined questions, recommendations, and optional assistant | Not started | No insight engine implemented |
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
- Validation result: `.venv/bin/pytest -q` -> `6 passed, 1 warning`.
- Validation result: `/health` -> `200 {"status":"ok"}`.

## Sprint 3 acceptance gaps

These items keep Sprint 3 in progress rather than complete:

- Handle malformed XLSX files as controlled failed dataset records instead of unhandled exceptions.
- Add valid XLSX, malformed XLSX, and failed-processing API tests.
- Define and test the complete processing error contract for failed and partially processed datasets.
- Add a stable processed-record read API for downstream analytics.
- Complete the business profile boundary or explicitly defer profile enrichment beyond business name.
- Add logout/token revocation if production-like authentication is required for the pilot.
- Add upload size/content checks and escape dataset filenames before rendering them in the browser.

## Next bounded slice

**Reliable ingestion contract:** upload representative valid CSV/XLSX, malformed XLSX, missing-column, and mixed-validity files through the API. Every case must produce a documented response and persisted history record without an unhandled exception. Accepted/rejected counts and warnings/errors must match the processed output, and processed records must be retrievable through a stable API contract.

Done condition:

```text
pytest passes -> API smoke path covers valid and invalid CSV/XLSX -> history is persisted -> processed records are readable -> planner review accepts the ingestion gate
```

## Scope guardrails

Keep the next slice focused on ingestion reliability. Defer bank/Mobile Money/POS integrations, distributed processing, a data lake, complex ML, and chatbot-first work. Begin Sprint 4 only after the ingestion contract is tested and reviewed.

## Update protocol

For each meaningful change, update:

1. The sprint status and exact evidence.
2. The verified test or runtime check.
3. Remaining risks and assumptions.
4. The next bounded slice and its done condition.
