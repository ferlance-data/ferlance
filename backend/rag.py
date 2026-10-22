import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from . import db
from .config import PROCESSED_DIR


class DataAvailabilityError(RuntimeError):
    pass


def resolve_processed_path(stored_path: str | None) -> Path | None:
    if not stored_path:
        return None
    path = Path(stored_path)
    if path.is_file():
        return path
    fallback = PROCESSED_DIR / path.name
    if fallback.is_file():
        return fallback
    return path


def _record_text(record: dict[str, Any]) -> str:
    return " ".join(f"{key} {value}" for key, value in record.items() if value not in (None, ""))


def _read_dataset_records(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    path = resolve_processed_path(dataset.get("processed_path"))
    if path is None:
        raise DataAvailabilityError(
            f"Processed records for {dataset['filename']} are unavailable. Re-upload the dataset before asking Lance."
        )
    try:
        with path.open("r", encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]
    except (OSError, json.JSONDecodeError) as error:
        raise DataAvailabilityError(
            f"Processed records for {dataset['filename']} are unavailable. Re-upload the dataset before asking Lance."
        ) from error


def index_dataset(db_path: Path, business_id: str, dataset_id: str, records: list[dict[str, Any]]) -> None:
    existing = db.one(db_path, "SELECT rowid FROM rag_documents_fts WHERE business_id = ? AND dataset_id = ? LIMIT 1", (business_id, dataset_id))
    if existing or not records:
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
    for dataset in datasets:
        existing = db.one(
            db_path,
            "SELECT rowid FROM rag_documents_fts WHERE business_id = ? AND dataset_id = ? LIMIT 1",
            (business_id, dataset["id"]),
        )
        if not existing:
            index_dataset(
                db_path,
                business_id,
                dataset["id"],
                _read_dataset_records(dataset),
            )
    match = _query(question)
    if match:
        rows = db.many(db_path, "SELECT dataset_id, content FROM rag_documents_fts WHERE business_id = ? AND rag_documents_fts MATCH ? ORDER BY rank LIMIT ?", (business_id, match, limit))
    else:
        rows = db.many(db_path, "SELECT dataset_id, content FROM rag_documents_fts WHERE business_id = ? ORDER BY rowid DESC LIMIT ?", (business_id, limit))
    dataset_names = {dataset["id"]: dataset["filename"] for dataset in datasets}
    return [{"dataset": dataset_names.get(row["dataset_id"], "Unknown dataset"), "evidence": row["content"]} for row in rows]


def all_records(datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for dataset in datasets:
        records.extend(_read_dataset_records(dataset))
    return records


def context(db_path: Path, business_id: str, question: str, datasets: list[dict[str, Any]], from_date: date | None, to_date: date | None, analytics: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": "all accepted records across this business",
        "datasets": [{"filename": dataset["filename"], "accepted_rows": dataset["accepted_rows"]} for dataset in datasets],
        "analytics": analytics,
        "retrieved_evidence": retrieve(db_path, business_id, question, datasets),
    }