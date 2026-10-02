# Reusable Engineering Prompts

These prompts are saved for future ingestion, architecture, and data-quality work. They describe the desired behavior without requiring a particular client or file schema.

## PostgreSQL hybrid storage pattern

The engine's `clean_df` is suitable for a relational projection, while `_text_payload` and unmapped source fields belong in a document column. A production worker should persist the manifest and quarantine rows in separate audit tables.

```sql
CREATE TABLE normalized_business_records (
	id uuid PRIMARY KEY,
	tenant_id uuid NOT NULL,
	ingestion_id uuid NOT NULL,
	source_row_number integer NOT NULL,
	domain text NOT NULL,
	record_date date,
	record_id text,
	amount numeric(20, 4),
	cost numeric(20, 4),
	quantity numeric(20, 4),
	category text,
	product text,
	customer text,
	vendor text,
	employee text,
	text_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
	source_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
	created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX normalized_business_records_tenant_date_idx
	ON normalized_business_records (tenant_id, record_date);
CREATE INDEX normalized_business_records_payload_idx
	ON normalized_business_records USING gin (text_payload);
```

Use parameterized inserts or a validated bulk loader. Keep `tenant_id`, `ingestion_id`, and `source_row_number` on every row so retrieval and audits can enforce isolation and traceability. Do not store API keys or raw files in the record payload.

## Universal CSV ingestion engine

```text
Act as a Principal Data Engineer and Backend Architect. Design or improve a modular production-ready Python CSV ingestion engine for arbitrary heterogeneous business files. Support sales transactions, COGS and unit costs, procurement, budgets and variances, projections and forecasts, payroll, operational memos, and unstructured logs.

Implement these stages:
1. Detect UTF-8, UTF-8 BOM, and Latin-1-compatible encodings; detect comma, tab, semicolon, and pipe delimiters; skip blank/comment/preamble rows; handle ragged rows without silently losing data.
2. Classify the domain from semantic header signals and return confidence plus a manifest.
3. Normalize messy headers to canonical fields; cast dates to ISO, numeric values to floats, counts to numbers, categories to strings, and free text to a JSON payload.
4. Return clean records, exact row-level quarantine reasons, source checksum, detected encoding/delimiter, domain, confidence, mappings, types, and row counts.

Use strong typing, docstrings, bounded resource use, explicit errors, deterministic behavior, and unit tests. Do not fabricate dates or financial values. Keep the engine independent from HTTP and persistence so it can be used by FastAPI jobs, CLI tools, or batch workers.
```

## Schema inference review

```text
Review this heterogeneous business file ingestion design as a Principal Data Engineer. Check encoding detection, delimiter detection, preamble/header selection, duplicate headers, ragged rows, missing tokens, currency and percentage parsing, word-number handling, date ambiguity, domain confidence, canonical mapping collisions, quarantine fidelity, checksum calculation, memory limits, and tenant-safe persistence. Identify silent data corruption risks first, then propose focused tests and minimal fixes.
```

## Data-quality and quarantine review

```text
Review the ingestion output for auditability. Every rejected row must retain its source row number, raw values, and exact list of validation errors. Accepted data must preserve the distinction between missing, invalid, zero, and not-applicable values. Verify that extra columns are not silently discarded, dates are not fabricated, percentages have an explicit convention, and all schema decisions appear in a machine-readable manifest.
```

## RAG readiness review

```text
Design a tenant-scoped retrieval layer over normalized business records. Combine lexical retrieval with deterministic aggregates, preserve dataset and row provenance, cap retrieved context, and ensure the LLM receives evidence rather than raw files. Define indexing, re-indexing, deletion, access control, prompt grounding, unavailable-metric behavior, and tests for cross-dataset isolation.
```