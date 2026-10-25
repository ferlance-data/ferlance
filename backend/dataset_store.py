"""Dataset persistence: raw uploads, normalized JSONL records, and analysis scope.

Every imported file becomes one ``datasets`` row plus a JSONL file of accepted,
normalized records. Analytics, insights, research and Ask Lance all read records
through this module so that scope rules (failed files never count, excluded
files are left out of business-wide views) live in one place.
"""

import json
import uuid
from pathlib import Path
from typing import Any

from . import config, db
from .processor import ProcessingResult

DATASET_FIELDS = (
    "id",
    "filename",
    "extension",
    "status",
    "source_rows",
    "accepted_rows",
    "rejected_rows",
    "warnings",
    "errors",
    "created_at",
)
EXCLUDED = "excluded"


class RecordsUnavailableError(RuntimeError):
    """Processed records exist in metadata but cannot be read from storage."""


def serialize(row: dict[str, Any]) -> dict[str, Any]:
    item = {field: row[field] for field in DATASET_FIELDS}
    for field in ("warnings", "errors"):
        if isinstance(item[field], str):
            item[field] = json.loads(item[field])
    item["included"] = row.get("review_status") != EXCLUDED
    return item


def get(business_id: str, dataset_id: str) -> dict[str, Any] | None:
    return db.one(
        config.DB_PATH,
        "SELECT * FROM datasets WHERE id = ? AND business_id = ?",
        (dataset_id, business_id),
    )


def list_all(business_id: str) -> list[dict[str, Any]]:
    return db.many(
        config.DB_PATH,
        "SELECT * FROM datasets WHERE business_id = ? ORDER BY created_at DESC",
        (business_id,),
    )


def analysable(business_id: str) -> list[dict[str, Any]]:
    """Datasets that feed business-wide views: processed and not excluded by the owner."""
    return db.many(
        config.DB_PATH,
        "SELECT * FROM datasets WHERE business_id = ? AND status != 'failed' "
        "AND review_status != ? ORDER BY created_at DESC",
        (business_id, EXCLUDED),
    )


def _resolve(stored_path: str | None, directory: Path) -> Path | None:
    if not stored_path:
        return None
    path = Path(stored_path)
    if path.is_file():
        return path
    fallback = directory / path.name
    return fallback if fallback.is_file() else path


def read_records(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    path = _resolve(dataset.get("processed_path"), config.PROCESSED_DIR)
    if path is None:
        return []
    try:
        with path.open("r", encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]
    except (OSError, json.JSONDecodeError) as error:
        raise RecordsUnavailableError(
            f"Processed records for {dataset['filename']} are unavailable. Re-upload the file to restore them."
        ) from error


def records_for(datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for dataset in datasets:
        records.extend(read_records(dataset))
    return records


def combined_descriptor(datasets: list[dict[str, Any]]) -> dict[str, Any]:
    """A dataset-shaped summary used when a view spans every included file."""
    return {
        "id": "all",
        "filename": "All business data",
        "extension": "bulk",
        "status": "processed",
        "source_rows": sum(item["source_rows"] for item in datasets),
        "accepted_rows": sum(item["accepted_rows"] for item in datasets),
        "rejected_rows": sum(item["rejected_rows"] for item in datasets),
        "warnings": [],
        "errors": [],
        "created_at": datasets[0]["created_at"] if datasets else db.now(),
        "included": True,
        "files": len(datasets),
    }


def find_duplicate(business_id: str, checksum: str) -> dict[str, Any] | None:
    return db.one(
        config.DB_PATH,
        "SELECT id, filename, created_at FROM datasets WHERE business_id = ? AND checksum = ? "
        "AND status != 'failed' ORDER BY created_at LIMIT 1",
        (business_id, checksum),
    )


def save(
    business_id: str,
    dataset_id: str,
    filename: str,
    extension: str,
    raw_path: Path,
    result: ProcessingResult,
    checksum: str | None,
) -> dict[str, Any]:
    processed_path: Path | None = None
    status = "failed" if not result.rows else "partial" if result.rejected_rows or result.errors else "processed"
    if result.rows:
        processed_path = config.PROCESSED_DIR / f"{dataset_id}.jsonl"
        with processed_path.open("w", encoding="utf-8") as target:
            for row in result.rows:
                target.write(json.dumps(row, default=str) + "\n")
    db.insert(
        config.DB_PATH,
        "INSERT INTO datasets (id, business_id, filename, extension, raw_path, processed_path, status, "
        "source_rows, accepted_rows, rejected_rows, warnings, errors, created_at, checksum) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            dataset_id,
            business_id,
            filename,
            extension,
            str(raw_path),
            str(processed_path) if processed_path else None,
            status,
            result.source_rows,
            len(result.rows),
            result.rejected_rows,
            json.dumps(result.warnings),
            json.dumps(result.errors),
            db.now(),
            checksum,
        ),
    )
    return serialize(get(business_id, dataset_id) or {})


def new_id() -> str:
    return str(uuid.uuid4())


def set_included(business_id: str, dataset_id: str, included: bool) -> dict[str, Any] | None:
    db.insert(
        config.DB_PATH,
        "UPDATE datasets SET review_status = ? WHERE id = ? AND business_id = ?",
        ("accepted" if included else EXCLUDED, dataset_id, business_id),
    )
    row = get(business_id, dataset_id)
    return serialize(row) if row else None
