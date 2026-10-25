"""Business-scoped retrieval over accepted records for Ask Lance (SQLite FTS5)."""

import re
from datetime import date
from pathlib import Path
from typing import Any

from . import dataset_store, db

DataAvailabilityError = dataset_store.RecordsUnavailableError
all_records = dataset_store.records_for


def _record_text(record: dict[str, Any]) -> str:
    return " ".join(f"{key} {value}" for key, value in record.items() if value not in (None, ""))


def _is_indexed(db_path: Path, business_id: str, dataset_id: str) -> bool:
    return bool(
        db.one(
            db_path,
            "SELECT rowid FROM rag_documents_fts WHERE business_id = ? AND dataset_id = ? LIMIT 1",
            (business_id, dataset_id),
        )
    )


def index_dataset(db_path: Path, business_id: str, dataset_id: str, records: list[dict[str, Any]]) -> None:
    if not records or _is_indexed(db_path, business_id, dataset_id):
        return
    with db.connection(db_path) as connection:
        connection.executemany(
            "INSERT INTO rag_documents_fts (document_id, business_id, dataset_id, content) VALUES (?, ?, ?, ?)",
            [(f"{dataset_id}:{index}", business_id, dataset_id, _record_text(record)) for index, record in enumerate(records)],
        )


def _query(question: str) -> str:
    terms = re.findall(r"[a-zA-Z0-9]{2,}", question.lower())
    return " OR ".join(f'"{term}"' for term in dict.fromkeys(terms))


def retrieve(db_path: Path, business_id: str, question: str, datasets: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    """Return the most relevant rows from the given datasets only (excluded files never leak in)."""
    if not datasets:
        return []
    for dataset in datasets:
        if not _is_indexed(db_path, business_id, dataset["id"]):
            index_dataset(db_path, business_id, dataset["id"], dataset_store.read_records(dataset))
    dataset_ids = [dataset["id"] for dataset in datasets]
    in_clause = ",".join("?" for _ in dataset_ids)
    match = _query(question)
    if match:
        rows = db.many(
            db_path,
            f"SELECT dataset_id, content FROM rag_documents_fts WHERE business_id = ? AND dataset_id IN ({in_clause}) "
            "AND rag_documents_fts MATCH ? ORDER BY rank LIMIT ?",
            (business_id, *dataset_ids, match, limit),
        )
    else:
        rows = db.many(
            db_path,
            f"SELECT dataset_id, content FROM rag_documents_fts WHERE business_id = ? AND dataset_id IN ({in_clause}) "
            "ORDER BY rowid DESC LIMIT ?",
            (business_id, *dataset_ids, limit),
        )
    names = {dataset["id"]: dataset["filename"] for dataset in datasets}
    return [{"dataset": names.get(row["dataset_id"], "Unknown dataset"), "evidence": row["content"]} for row in rows]


def context(
    db_path: Path,
    business_id: str,
    question: str,
    datasets: list[dict[str, Any]],
    from_date: date | None,
    to_date: date | None,
    analytics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "scope": "all accepted records across this business",
        "datasets": [{"filename": dataset["filename"], "accepted_rows": dataset["accepted_rows"]} for dataset in datasets],
        "analytics": analytics,
        "retrieved_evidence": retrieve(db_path, business_id, question, datasets),
    }
