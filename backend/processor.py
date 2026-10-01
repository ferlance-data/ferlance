import csv
import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

REQUIRED_ALIASES = {
    "transaction_date": {"transaction_date", "date", "sale_date", "transactiondate"},
    "amount": {"amount", "sales_amount", "revenue", "total", "sale_amount"},
}
OPTIONAL_ALIASES = {
    "transaction_id": {"transaction_id", "id", "transactionid", "sale_id"},
    "product": {"product", "product_name", "item", "item_name"},
    "customer": {"customer", "customer_name", "client", "client_name"},
    "quantity": {"quantity", "qty", "units"},
}


@dataclass
class ProcessingResult:
    rows: list[dict[str, Any]]
    source_rows: int
    rejected_rows: int
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def _read_rows(path: Path, extension: str) -> list[dict[str, Any]]:
    if extension == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if extension == ".xlsx":
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.active
        values = list(sheet.values)
        workbook.close()
        if not values:
            return []
        headers = [str(value or "") for value in values[0]]
        return [dict(zip(headers, row)) for row in values[1:]]
    raise ValueError("Unsupported file type. Upload a CSV or XLSX file.")


def _columns(rows: list[dict[str, Any]]) -> dict[str, str]:
    if not rows:
        return {}
    available = {_key(name): str(name) for name in rows[0].keys()}
    result: dict[str, str] = {}
    for target, aliases in {**REQUIRED_ALIASES, **OPTIONAL_ALIASES}.items():
        for alias in aliases:
            if _key(alias) in available:
                result[target] = available[_key(alias)]
                break
    return result


def _number(value: Any) -> float:
    cleaned = re.sub(r"[^0-9.-]", "", str(value or "").replace("(", "-").replace(")", ""))
    if not cleaned or cleaned in {"-", ".", "-."}:
        raise ValueError("amount is not numeric")
    return float(cleaned)


def _date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    for format_text in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, format_text).date().isoformat()
        except ValueError:
            continue
    raise ValueError("transaction date is invalid")


def process_file(path: Path, extension: str) -> ProcessingResult:
    try:
        rows = _read_rows(path, extension)
    except (InvalidFileException, OSError, ValueError, zipfile.BadZipFile):
        if extension == ".xlsx":
            return ProcessingResult([], 0, 0, errors=["The XLSX file is malformed or unreadable."])
        raise
    if not rows:
        return ProcessingResult([], 0, 0, errors=["The file is empty or has no data rows."])
    columns = _columns(rows)
    missing = [field for field in REQUIRED_ALIASES if field not in columns]
    if missing:
        return ProcessingResult([], len(rows), len(rows), errors=[f"Missing required column: {field}." for field in missing])

    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    rejected = 0
    for index, source in enumerate(rows, start=2):
        try:
            output: dict[str, Any] = {
                "transaction_date": _date(source.get(columns["transaction_date"])),
                "amount": _number(source.get(columns["amount"])),
            }
            for field in OPTIONAL_ALIASES:
                if field in columns and source.get(columns[field]) not in (None, ""):
                    value = source.get(columns[field])
                    output[field] = _number(value) if field == "quantity" else str(value).strip()
            fingerprint = str(output.get("transaction_id") or hashlib.sha256(json.dumps(output, sort_keys=True).encode()).hexdigest())
            if fingerprint in seen:
                rejected += 1
                warnings.append(f"Row {index}: duplicate transaction rejected.")
                continue
            seen.add(fingerprint)
            normalized.append(output)
        except ValueError as error:
            rejected += 1
            warnings.append(f"Row {index}: {error}.")
    return ProcessingResult(normalized, len(rows), rejected, warnings=warnings)
