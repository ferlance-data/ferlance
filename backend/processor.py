import csv
import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from backend.sms_parser import MoMoSMSParser
from backend.universal_ingestion import UniversalCSVIngestionEngine

REQUIRED_ALIASES = {
    "transaction_date": {"transaction_date", "date", "sale_date", "transactiondate", "order_date", "usage_date", "expense_date", "invoice_date"},
}
FINANCIAL_ALIASES = {
    "amount": {"amount", "sales_amount", "revenue", "total", "sale_amount", "sales", "income", "gross_sales"},
    "cost": {"cost", "cost_amount", "expense", "expense_amount", "actual_cost", "actual_cost_usd", "total_cost", "total_cost_usd", "net_charged_cost", "net_charged_cost_usd", "unblended_cost_usd", "budgeted_cost_usd", "subtotal_usd"},
}
UNIT_COST_ALIASES = {"unit_cost", "cost_per_unit", "unit_cost_usd", "cost_per_unit_usd"}
OPTIONAL_ALIASES = {
    "transaction_id": {"transaction_id", "id", "transactionid", "sale_id", "expense_id", "po_number", "invoice_line_id"},
    "product": {"product", "product_name", "item", "item_name", "item_description", "service_name", "project_name"},
    "customer": {"customer", "customer_name", "client", "client_name", "vendor_name", "cloud_provider"},
    "quantity": {"quantity", "qty", "units", "usage_quantity"},
}
ALIAS_PRIORITY = {
    "transaction_date": ("transaction_date", "date", "sale_date", "transactiondate", "order_date", "usage_date", "expense_date", "invoice_date"),
    "amount": ("sales_amount", "revenue", "gross_sales", "sale_amount", "sales", "amount", "income", "total"),
    "cost": ("total_cost", "total_cost_usd", "actual_cost", "actual_cost_usd", "expense_amount", "cost_amount", "cost", "expense", "net_charged_cost", "net_charged_cost_usd", "unblended_cost_usd", "budgeted_cost_usd", "subtotal_usd"),
    "unit_cost": ("unit_cost", "cost_per_unit", "unit_cost_usd", "cost_per_unit_usd"),
    "transaction_id": ("transaction_id", "transactionid", "sale_id", "expense_id", "po_number", "invoice_line_id", "id"),
    "product": ("product_name", "product", "item_name", "item", "service_name", "project_name", "item_description"),
    "customer": ("customer_name", "customer", "client_name", "client", "vendor_name", "cloud_provider"),
    "quantity": ("quantity", "qty", "units", "usage_quantity"),
}


@dataclass
class ProcessingResult:
    rows: list[dict[str, Any]]
    source_rows: int
    rejected_rows: int
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DuplicateColumnError(ValueError):
    pass


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def _extract_markdown_table(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return []
    # Header is line 0
    header_cols = [c.strip() for c in lines[0].strip("|").split("|")]
    # Line 1 is usually separator (| --- | --- |)
    data_lines = lines[2:] if len(lines) > 2 and all(set(c.strip()).issubset({"-", ":", " "}) for c in lines[1].strip("|").split("|")) else lines[1:]
    rows = []
    for line in data_lines:
        vals = [c.strip() for c in line.strip("|").split("|")]
        if len(vals) == len(header_cols):
            rows.append(dict(zip(header_cols, vals)))
    return rows


def _read_rows(path: Path, extension: str) -> list[dict[str, Any]]:
    if extension in (".csv", ".tsv", ".txt"):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            text = handle.read()
            if not text.strip():
                return []
            delimiter = "\t" if extension == ".tsv" or "\t" in text.splitlines()[0] else ","
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            headers = [_key(header) for header in reader.fieldnames or []]
            if len(headers) != len(set(headers)):
                raise DuplicateColumnError("The file contains duplicate column names.")
            return list(reader)
    if extension == ".md":
        with path.open("r", encoding="utf-8-sig") as handle:
            return _extract_markdown_table(handle.read())
    if extension == ".xlsx":
        workbook = load_workbook(path, read_only=True, data_only=True)
        sheet = workbook.active
        values = list(sheet.values)
        workbook.close()
        if not values:
            return []
        headers = [str(value or "") for value in values[0]]
        normalized_headers = [_key(header) for header in headers]
        if len(normalized_headers) != len(set(normalized_headers)):
            raise DuplicateColumnError("The XLSX file contains duplicate column names.")
        return [dict(zip(headers, row)) for row in values[1:]]
    raise ValueError("Unsupported file type. Upload CSV, TSV, XLSX, TXT, or Markdown.")


def _columns(rows: list[dict[str, Any]]) -> dict[str, str]:
    if not rows:
        return {}
    available = {_key(name): str(name) for name in rows[0].keys()}
    result: dict[str, str] = {}
    for target, aliases in {**REQUIRED_ALIASES, **FINANCIAL_ALIASES, "unit_cost": UNIT_COST_ALIASES, **OPTIONAL_ALIASES}.items():
        prioritized = ALIAS_PRIORITY.get(target, tuple(sorted(aliases, key=lambda item: (-len(item), item))))
        for alias in prioritized:
            if _key(alias) in available:
                result[target] = available[_key(alias)]
                break
    return result


def _number(value: Any) -> float:
    cleaned = "" if value is None else str(value).strip()
    if not cleaned:
        raise ValueError("amount is not numeric")
    cleaned = re.sub(r"(?i)\b(?:GHS|USD)\b", "", cleaned)
    cleaned = cleaned.replace("GH₵", "").translate(str.maketrans("", "", "$€£₵")).strip()
    parenthesized = cleaned.startswith("(") and cleaned.endswith(")")
    if cleaned.startswith("(") != cleaned.endswith(")"):
        raise ValueError("amount is not numeric")
    if parenthesized:
        cleaned = cleaned[1:-1].strip()
    if not re.fullmatch(r"[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?|\.\d+)", cleaned):
        raise ValueError("amount is not numeric")
    number = float(cleaned.replace(",", ""))
    if not math.isfinite(number):
        raise ValueError("amount must be finite")
    return -abs(number) if parenthesized else number


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
    if extension in (".txt", ".md"):
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1", errors="replace")
        momo_txns = MoMoSMSParser.parse_batch(content)
        if momo_txns:
            records = [tx.to_record() for tx in momo_txns]
            return ProcessingResult(
                records,
                source_rows=len(records),
                rejected_rows=0,
                warnings=[f"Detected and parsed {len(records)} Mobile Money SMS transactions."],
            )
        if extension == ".md":
            md_rows = _extract_markdown_table(content)
            if not md_rows:
                return ProcessingResult([], 0, 0, errors=["No markdown table or Mobile Money transactions found in file."])

    if extension == ".csv":
        try:
            if path.stat().st_size == 0:
                return ProcessingResult([], 0, 0, errors=["The file is empty or has no data rows."])
            universal = UniversalCSVIngestionEngine(path).process_file()
        except (OSError, UnicodeError, ValueError) as error:
            return ProcessingResult([], 0, 0, errors=[str(error)])
        normalized = []
        seen_records: set[str] = set()
        warnings = [
            f"Row {item['row_number']}: {'; '.join(item['errors'])}."
            for item in universal["quarantined_rows"]
        ]
        rejected_rows = len(universal["quarantined_rows"])
        is_usd = any(
            "usd" in str(col).lower() or "$" in str(col)
            for col in (
                list(universal.get("schema_summary", {}).get("column_mapping", {}).values())
                + list(universal.get("schema_summary", {}).get("headers", []))
                + [str(k) for k in universal["clean_df"].columns]
            )
        )
        for source in universal["clean_df"].to_dict(orient="records"):
            output = {
                key: None if isinstance(value, float) and math.isnan(value) else value
                for key, value in source.items()
            }
            if is_usd and "currency" not in output:
                output["currency"] = "USD"
            if "date" in output:
                output["transaction_date"] = output.pop("date")
            else:
                output["transaction_date"] = None
            if "record_id" in output:
                output["transaction_id"] = output.pop("record_id")
            fingerprint = json.dumps(output, sort_keys=True, default=str)
            if fingerprint in seen_records:
                rejected_rows += 1
                warnings.append("Duplicate normalized row rejected.")
                continue
            seen_records.add(fingerprint)
            if output.get("amount") is None:
                output["amount"] = 0.0
            for optional in ("cost", "quantity"):
                if optional in output and output[optional] is None:
                    del output[optional]
            normalized.append(output)
        return ProcessingResult(
            normalized,
            universal["schema_summary"]["source_rows"],
            rejected_rows,
            warnings=warnings,
        )
    try:
        rows = _read_rows(path, extension)
    except DuplicateColumnError as error:
        return ProcessingResult([], 0, 0, errors=[str(error)])
    except UnicodeDecodeError:
        return ProcessingResult(
            [], 0, 0,
            errors=["The CSV file is not valid UTF-8. Save it as UTF-8 and upload it again."],
        )
    except (InvalidFileException, OSError, ValueError, zipfile.BadZipFile):
        if extension == ".xlsx":
            return ProcessingResult([], 0, 0, errors=["The XLSX file is malformed or unreadable."])
        raise
    if not rows:
        return ProcessingResult([], 0, 0, errors=["The file is empty or has no data rows."])
    columns = _columns(rows)
    missing = [field for field in REQUIRED_ALIASES if field not in columns]
    if not any(field in columns for field in FINANCIAL_ALIASES) and "unit_cost" not in columns:
        missing.append("amount, cost, or unit cost")
    if missing:
        return ProcessingResult([], len(rows), len(rows), errors=[f"Missing required column: {field}." for field in missing])

    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_transaction_ids: set[str] = set()
    rejected = 0
    for index, source in enumerate(rows, start=2):
        try:
            amount_value = source.get(columns["amount"]) if "amount" in columns else None
            cost_value = source.get(columns["cost"]) if "cost" in columns else None
            unit_cost_value = source.get(columns["unit_cost"]) if "unit_cost" in columns else None
            has_amount = amount_value is not None and str(amount_value).strip() != ""
            has_cost = cost_value is not None and str(cost_value).strip() != ""
            has_unit_cost = unit_cost_value is not None and str(unit_cost_value).strip() != ""
            if not (has_amount or has_cost or has_unit_cost):
                raise ValueError("financial value is missing")
            output: dict[str, Any] = {
                "transaction_date": _date(source.get(columns["transaction_date"])),
                "amount": _number(amount_value) if has_amount else 0.0,
            }
            financial_headers = [columns[field] for field in FINANCIAL_ALIASES if field in columns]
            if "unit_cost" in columns:
                financial_headers.append(columns["unit_cost"])
            if any("usd" in _key(header) for header in financial_headers):
                output["currency"] = "USD"
            for field in ("quantity", "transaction_id", "product", "customer"):
                if field in columns and source.get(columns[field]) not in (None, ""):
                    value = source.get(columns[field])
                    output[field] = _number(value) if field == "quantity" else str(value).strip()
            if has_cost:
                output["cost"] = _number(cost_value)
            elif has_unit_cost:
                unit_cost = _number(unit_cost_value)
                output["cost"] = unit_cost * output.get("quantity", 1)
            transaction_id = output.get("transaction_id")
            if transaction_id and transaction_id in seen_transaction_ids:
                rejected += 1
                warnings.append(f"Row {index}: duplicate transaction ID rejected.")
                continue
            if transaction_id:
                seen_transaction_ids.add(transaction_id)
            normalized.append(output)
        except ValueError as error:
            rejected += 1
            warnings.append(f"Row {index}: {error}.")
    return ProcessingResult(normalized, len(rows), rejected, warnings=warnings)
