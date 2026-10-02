import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from . import db


def _record_text(record: dict[str, Any]) -> str:
    return " ".join(f"{key} {value}" for key, value in record.items() if value not in (None, ""))


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
        if dataset.get("processed_path"):
            path = Path(dataset["processed_path"])
            try:
                with path.open("r", encoding="utf-8") as source:
                    index_dataset(db_path, business_id, dataset["id"], [json.loads(line) for line in source if line.strip()])
            except (OSError, json.JSONDecodeError):
                continue
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
        if not dataset.get("processed_path"):
            continue
        try:
            with Path(dataset["processed_path"]).open("r", encoding="utf-8") as source:
                records.extend(json.loads(line) for line in source if line.strip())
        except (OSError, json.JSONDecodeError):
            continue
    return records


def context(db_path: Path, business_id: str, question: str, datasets: list[dict[str, Any]], from_date: date | None, to_date: date | None, analytics: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": "all accepted records across this business",
        "datasets": [{"filename": dataset["filename"], "accepted_rows": dataset["accepted_rows"]} for dataset in datasets],
        "analytics": analytics,
        "retrieved_evidence": retrieve(db_path, business_id, question, datasets),
    }