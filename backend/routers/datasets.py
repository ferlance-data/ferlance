"""Data imports: file uploads, Mobile Money SMS, history, and inclusion in analysis."""

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import config, dataset_store, db
from ..deps import owned_business, read_scope_records
from ..processor import ProcessingResult, process_file
from ..sms_parser import MoMoSMSParser

router = APIRouter(prefix="/api/businesses/{business_id}", tags=["data"])
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".tsv", ".txt", ".md"}


class MoMoBatchRequest(BaseModel):
    sms_text: str = Field(min_length=5, max_length=200_000)


class DatasetUpdate(BaseModel):
    included: bool


def _flag_duplicate(business_id: str, checksum: str, result: ProcessingResult) -> None:
    duplicate = dataset_store.find_duplicate(business_id, checksum)
    if duplicate:
        result.warnings.insert(
            0,
            f"This file is identical to {duplicate['filename']} imported on {duplicate['created_at'][:10]}. "
            "Exclude one copy from analysis to avoid double counting.",
        )


@router.post("/datasets")
def upload_dataset(file: UploadFile = File(...), business: dict = Depends(owned_business)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(415, "Unsupported file type. Upload a CSV, XLSX, TSV, TXT, or Markdown file.")
    dataset_id = dataset_store.new_id()
    raw_path = config.RAW_DIR / f"{dataset_id}{suffix}"
    digest = hashlib.sha256()
    try:
        with raw_path.open("wb") as target:
            total_bytes = 0
            while chunk := file.file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > config.MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Uploaded file is too large.")
                digest.update(chunk)
                target.write(chunk)
    except Exception:
        raw_path.unlink(missing_ok=True)
        raise
    result = process_file(raw_path, suffix)
    checksum = digest.hexdigest()
    if result.rows:
        _flag_duplicate(business["id"], checksum, result)
    return dataset_store.save(business["id"], dataset_id, file.filename or "dataset", suffix, raw_path, result, checksum)


@router.post("/sources/momo")
def import_momo_sms(payload: MoMoBatchRequest, business: dict = Depends(owned_business)) -> dict:
    transactions = MoMoSMSParser.parse_batch(payload.sms_text)
    if not transactions:
        single = MoMoSMSParser.parse_message(payload.sms_text)
        transactions = [single] if single else []
    if not transactions:
        raise HTTPException(400, "No Mobile Money transactions were found. Paste the full SMS text, including the amount and transaction ID.")
    dataset_id = dataset_store.new_id()
    raw_path = config.RAW_DIR / f"{dataset_id}.txt"
    raw_path.write_text(payload.sms_text, encoding="utf-8")
    rows = [transaction.to_record() for transaction in transactions]
    result = ProcessingResult(rows, len(rows), 0, warnings=[f"Parsed {len(rows)} Mobile Money SMS transactions."])
    checksum = hashlib.sha256(payload.sms_text.encode("utf-8")).hexdigest()
    _flag_duplicate(business["id"], checksum, result)
    dataset = dataset_store.save(
        business["id"], dataset_id, f"Mobile Money SMS ({len(rows)} transactions)", ".txt", raw_path, result, checksum
    )
    return {
        "status": "imported",
        "transactions_count": len(rows),
        "total_amount": round(sum(row["amount"] for row in rows), 2),
        "dataset": dataset,
        "records": rows,
    }


@router.get("/datasets")
def dataset_history(business: dict = Depends(owned_business)) -> list[dict]:
    return [dataset_store.serialize(item) for item in dataset_store.list_all(business["id"])]


@router.patch("/datasets/{dataset_id}")
def update_dataset(dataset_id: str, payload: DatasetUpdate, business: dict = Depends(owned_business)) -> dict:
    """Include or exclude a file from business-wide analytics without deleting its audit trail."""
    updated = dataset_store.set_included(business["id"], dataset_id, payload.included)
    if not updated:
        raise HTTPException(404, "Dataset not found.")
    return updated


@router.get("/datasets/{dataset_id}/records")
def dataset_records(dataset_id: str, business: dict = Depends(owned_business)) -> dict:
    dataset = dataset_store.get(business["id"], dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    records = read_scope_records([dataset])
    return {"dataset_id": dataset_id, "status": dataset["status"], "count": len(records), "records": records}


@router.get("/folder-imports")
def folder_import_status(business: dict = Depends(owned_business)) -> dict:
    """Report inbox workbooks that the background folder importer has picked up."""
    folder = config.IMPORT_DIR / business["id"]
    folder.mkdir(parents=True, exist_ok=True)
    imports = db.many(
        config.DB_PATH,
        "SELECT filename, status, error, dataset_id, updated_at FROM folder_imports WHERE business_id = ? ORDER BY updated_at DESC LIMIT 10",
        (business["id"],),
    )
    return {"folder": str(folder.resolve()), "imports": imports}
