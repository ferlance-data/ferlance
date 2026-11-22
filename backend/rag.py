"""Business-scoped retrieval over accepted records for Ask Lance (SQLite FTS5).

Measured with tools/eval/rag_eval.py (PRD 8.1). v2 changes, each justified by that eval:
- Only record *values* are indexed. Indexing field names ("product", "customer") made every row
  match a question that used those words.
- Common question words ("how", "did", "my", "sales") are dropped from the query.
- The question's date scope is applied, so "this month" questions do not get last quarter's rows.
- The porter stemmer matches "payments" with "payment" and "bought" phrasing with product rows.
A hosted vector database was not added: see the eval notes in the PR for why.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from . import dataset_store, db

DataAvailabilityError = dataset_store.RecordsUnavailableError
all_records = dataset_store.records_for

# Words that say how a question is asked, not what it is about.
STOPWORDS = frozenset(
    """a about all am an and any are as at be been buy bought by can could did do does doing for from get got had has have
    how i in is it its last me month my of on or our sales sale sell selling sold show so than that the their them then
    there these this those to us was we week were what when where which who whom why will with would year you your
    much many most more less tell give list""".split()
)


def _record_text(record: dict[str, Any]) -> str:
    """Searchable text: the record's values only."""
    return " ".join(str(value) for key, value in record.items() if value not in (None, "") and key != "currency")


def _is_indexed(db_path: Path, business_id: str, dataset_id: str) -> bool:
    return bool(
        db.one(
            db_path,
            "SELECT rowid FROM rag_records_fts WHERE business_id = ? AND dataset_id = ? LIMIT 1",
            (business_id, dataset_id),
        )
    )


def index_dataset(db_path: Path, business_id: str, dataset_id: str, records: list[dict[str, Any]]) -> None:
    if not records or _is_indexed(db_path, business_id, dataset_id):
        return
    with db.connection(db_path) as connection:
        connection.executemany(
            "INSERT INTO rag_records_fts (document_id, business_id, dataset_id, record_date, record, content) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (f"{dataset_id}:{index}", business_id, dataset_id, str(record.get("transaction_date") or ""), json.dumps(record, default=str), _record_text(record))
                for index, record in enumerate(records)
            ],
        )


def query_terms(question: str) -> list[str]:
    terms = [term for term in re.findall(r"[a-zA-Z0-9]{2,}", question.lower()) if term not in STOPWORDS]
    return list(dict.fromkeys(terms))


def _match(question: str) -> str:
    return " OR ".join(f'"{term}"' for term in query_terms(question))


def retrieve(
    db_path: Path,
    business_id: str,
    question: str,
    datasets: list[dict[str, Any]],
    limit: int = 20,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, Any]]:
    """The most relevant rows from the given datasets only (excluded files never leak in), within the date scope."""
    if not datasets:
        return []
    for dataset in datasets:
        if not _is_indexed(db_path, business_id, dataset["id"]):
            index_dataset(db_path, business_id, dataset["id"], dataset_store.read_records(dataset))
    dataset_ids = [dataset["id"] for dataset in datasets]
    in_clause = ",".join("?" for _ in dataset_ids)
    where = f"business_id = ? AND dataset_id IN ({in_clause})"
    params: list[Any] = [business_id, *dataset_ids]
    if from_date:
        where += " AND record_date >= ?"
        params.append(from_date.isoformat())
    if to_date:
        where += " AND record_date <= ?"
        params.append(to_date.isoformat())
    match = _match(question)
    if match:
        rows = db.many(
            db_path,
            f"SELECT dataset_id, content, record FROM rag_records_fts WHERE {where} AND rag_records_fts MATCH ? ORDER BY rank LIMIT ?",
            (*params, match, limit),
        )
    else:
        rows = db.many(
            db_path,
            f"SELECT dataset_id, content, record FROM rag_records_fts WHERE {where} ORDER BY record_date DESC LIMIT ?",
            (*params, limit),
        )
    names = {dataset["id"]: dataset["filename"] for dataset in datasets}
    return [{"dataset": names.get(row["dataset_id"], "Unknown dataset"), "evidence": row["content"], "record": json.loads(row["record"])} for row in rows]


def context(
    db_path: Path,
    business_id: str,
    question: str,
    datasets: list[dict[str, Any]],
    from_date: date | None,
    to_date: date | None,
    analytics: dict[str, Any],
) -> dict[str, Any]:
    evidence = retrieve(db_path, business_id, question, datasets, from_date=from_date, to_date=to_date)
    return {
        "scope": "all accepted records across this business",
        "datasets": [{"filename": dataset["filename"], "accepted_rows": dataset["accepted_rows"]} for dataset in datasets],
        "analytics": analytics,
        "retrieved_evidence": [{"dataset": row["dataset"], "evidence": row["evidence"]} for row in evidence],
    }
