"""Schema-flexible CSV ingestion for heterogeneous business data."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, TextIO, cast

import pandas as pd
from charset_normalizer import from_bytes


MISSING_TOKENS = {"", "na", "n/a", "nan", "none", "null", "unknown", "??", "-"}
DELIMITERS = (",", "\t", ";", "|")

DOMAIN_KEYWORDS: dict[str, set[str]] = {
    "transactions_sales": {"sale", "sales", "transaction", "txn", "revenue", "customer", "product", "order", "receipt"},
    "costs_cogs_procurement": {"cost", "cogs", "expense", "procurement", "purchase", "vendor", "supplier", "unitcost", "po", "material"},
    "budgets_variances": {"budget", "variance", "actual", "planned", "forecastvariance", "budgeted", "overbudget"},
    "projections_forecasting": {"projection", "projected", "forecast", "predicted", "scenario", "outlook", "estimate"},
    "payroll_compensation": {"payroll", "salary", "wage", "employee", "staff", "compensation", "grosspay", "netpay", "deduction"},
    "textual_memos_logs": {"memo", "note", "comment", "narrative", "message", "log", "description", "details", "text"},
}

CANONICAL_ALIASES: dict[str, set[str]] = {
    "record_id": {"id", "recordid", "transactionid", "txnid", "saleid", "invoiceid", "po", "ponumber", "employeeid", "expenseid"},
    "date": {"date", "transactiondate", "saledate", "orderdate", "invoicedate", "expensedate", "usagedate", "effectivedate", "period", "month"},
    "amount": {"amount", "salesamount", "amountpaid", "revenue", "sales", "total", "totalprice", "saleamount", "income", "grosssales", "value", "salary", "wage", "grosspay", "netpay", "compensation"},
    "cost": {"cost", "costamount", "unitcost", "unitcostusd", "actualcost", "actualcostusd", "totalcost", "totalcostusd", "expense", "expenseamount", "cogs", "subtotal"},
    "budget": {"budget", "budgeted", "budgetedcost", "budgetedcostusd", "planned", "plannedamount"},
    "variance": {"variance", "varianceusd", "variancepct", "variancepercent", "difference"},
    "quantity": {"quantity", "qty", "units", "unitssold", "usagequantity", "headcount", "count"},
    "unit_price": {"unitprice", "price", "sellingprice", "rate", "blendedrate", "hourlyrate"},
    "product": {"product", "productname", "item", "itemname", "itemdescription", "service", "servicename", "sku", "finishedproduct"},
    "customer": {"customer", "customername", "client", "clientname", "account", "accountname"},
    "vendor": {"vendor", "vendorname", "supplier", "suppliername", "provider", "cloudprovider"},
    "employee": {"employee", "employeename", "staff", "staffname", "worker", "workername"},
    "category": {"category", "type", "classification", "department", "costcenter", "phase", "status", "region", "branch"},
}

NUMERIC_CANONICAL = {"amount", "cost", "budget", "variance", "quantity", "unit_price"}
DATE_CANONICAL = {"date"}
TEXT_HINTS = {"memo", "note", "comment", "narrative", "message", "log", "description", "details", "text"}

WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100,
}


@dataclass(frozen=True)
class SourceInfo:
    encoding: str
    delimiter: str
    header_row: int
    checksum: str


class UniversalCSVIngestionEngine:
    """Ingest an arbitrary CSV into typed canonical records with quarantine details.

    The engine is deliberately independent from FastAPI and persistence. A caller can
    persist ``clean_df`` as rows plus ``_text_payload`` JSON, while retaining the
    manifest and quarantined rows for auditability.
    """

    def __init__(self, source: str | Path | BinaryIO | TextIO):
        self.source = source
        self._raw_bytes: bytes | None = None
        self._text: str | None = None
        self._source_info: SourceInfo | None = None
        self._raw_rows: list[list[str]] = []
        self._headers: list[str] = []
        self._quarantined: list[dict[str, Any]] = []
        self._mapping: dict[str, str] = {}

    def _read_bytes(self) -> bytes:
        if self._raw_bytes is not None:
            return self._raw_bytes
        if isinstance(self.source, (str, Path)):
            self._raw_bytes = Path(self.source).read_bytes()
        else:
            stream = cast(Any, self.source)
            if hasattr(stream, "seek"):
                stream.seek(0)
            value = stream.read()
            if isinstance(value, str):
                value = value.encode("utf-8")
            self._raw_bytes = bytes(value)
        return self._raw_bytes

    @staticmethod
    def _normal_key(value: Any) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower().replace("₵", "c"))

    def _decode(self, data: bytes) -> tuple[str, str]:
        if data.startswith(b"\xef\xbb\xbf"):
            return data.decode("utf-8-sig"), "utf-8-sig"
        detected = from_bytes(data).best()
        if detected is not None and detected.encoding:
            try:
                return str(detected), detected.encoding
            except UnicodeDecodeError:
                pass
        for encoding in ("utf-8", "latin-1"):
            try:
                return data.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        raise ValueError("Could not decode the CSV as UTF-8 or Latin-1.")

    def _find_header(self, rows: list[list[str]]) -> int:
        best_index, best_score = 0, -1
        known = set().union(*DOMAIN_KEYWORDS.values(), *CANONICAL_ALIASES.values())
        for index, row in enumerate(rows[:30]):
            cells = [self._normal_key(cell) for cell in row if str(cell).strip()]
            if not cells:
                continue
            score = sum(cell in known or any(alias in cell or cell in alias for alias in known) for cell in cells)
            score += min(len(cells), 8) / 100
            if score > best_score:
                best_index, best_score = index, score
        if not rows or not any(str(cell).strip() for cell in rows[best_index]):
            raise ValueError("The CSV does not contain a usable header row.")
        return best_index

    def detect_dialect_and_encoding(self) -> dict[str, Any]:
        """Detect encoding, delimiter, preamble/header row, and source checksum."""
        data = self._read_bytes()
        text, encoding = self._decode(data)
        sample = text[:100_000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters="\t,;|")
            delimiter = dialect.delimiter
        except csv.Error:
            counts = {delimiter: sample.count(delimiter) for delimiter in DELIMITERS}
            delimiter = max(counts, key=counts.get) if max(counts.values()) else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        header_row = self._find_header(rows)
        self._text = text
        self._raw_rows = rows
        checksum = hashlib.sha256(data).hexdigest()
        self._source_info = SourceInfo(encoding, delimiter, header_row, checksum)
        return {"encoding": encoding, "delimiter": delimiter, "header_row": header_row + 1, "checksum": checksum}

    def _ensure_parsed(self) -> None:
        if self._source_info is None:
            self.detect_dialect_and_encoding()
        assert self._source_info is not None
        header_index = self._source_info.header_row
        raw_headers = self._raw_rows[header_index]
        headers: list[str] = []
        seen: dict[str, int] = {}
        for position, header in enumerate(raw_headers):
            clean = str(header).replace("\ufeff", "").strip() or f"unnamed_{position + 1}"
            seen[clean] = seen.get(clean, 0) + 1
            headers.append(clean if seen[clean] == 1 else f"{clean}_{seen[clean]}")
        self._headers = headers

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None or str(value).strip().lower() in MISSING_TOKENS:
            return None
        text = str(value).strip().lower()
        percent = "%" in text
        parenthesized = text.startswith("(") and text.endswith(")")
        if text.startswith("(") != text.endswith(")"):
            raise ValueError(f"not numeric: {value!r}")
        if parenthesized:
            text = text[1:-1].strip()
        text = re.sub(r"\b(?:ghs|usd)\b", "", text)
        text = text.replace("gh₵", "").replace("gማ", "")
        text = text.translate(str.maketrans("", "", "$€£₵")).replace("%", "").strip()
        if text in WORD_NUMBERS:
            result = float(WORD_NUMBERS[text])
        else:
            if not re.fullmatch(r"[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?|\.\d+)", text):
                raise ValueError(f"not numeric: {value!r}")
            result = float(text.replace(",", ""))
        if not math.isfinite(result):
            raise ValueError(f"not numeric: {value!r}")
        if parenthesized:
            result = -abs(result)
        return result / 100 if percent else result

    @staticmethod
    def _date(value: Any) -> str | None:
        if value is None or str(value).strip().lower() in MISSING_TOKENS:
            return None
        text = str(value).strip()
        try:
            from dateutil import parser
            return parser.parse(text, dayfirst=False).date().isoformat()
        except Exception:
            try:
                parsed = pd.to_datetime(value, errors="coerce", dayfirst=False)
                if pd.isna(parsed):
                    raise ValueError(f"not a date: {value!r}")
                return cast(pd.Timestamp, parsed).date().isoformat()
            except Exception:
                raise ValueError(f"not a date: {value!r}")

    def infer_domain_and_mapping(self) -> dict[str, Any]:
        """Classify the file and map source headers to canonical fields."""
        self._ensure_parsed()
        normalized = [self._normal_key(header) for header in self._headers]
        scores = {domain: sum(any(keyword in header for keyword in keywords) for header in normalized) for domain, keywords in DOMAIN_KEYWORDS.items()}
        winner = max(scores, key=scores.get) if scores else "unknown"
        if scores.get("budgets_variances", 0) >= 2 and any("budget" in header or "variance" in header for header in normalized):
            winner = "budgets_variances"
        elif scores.get("payroll_compensation", 0) >= 2 and any("employee" in header or "salary" in header or "pay" in header for header in normalized):
            winner = "payroll_compensation"
        total = sum(scores.values())
        confidence = round(scores[winner] / max(len(normalized), 1) + (0.2 if scores[winner] >= 2 else 0), 3)
        confidence = min(confidence, 1.0)
        mapping: dict[str, str] = {}
        used: set[str] = set()
        for header, key in zip(self._headers, normalized):
            candidates = []
            for canonical, aliases in CANONICAL_ALIASES.items():
                score = max((1.5 if key == alias else 0.8 + len(alias) / 100 if len(alias) >= 4 and (alias in key or key in alias) else 0.0) for alias in aliases)
                candidates.append((canonical, score))
            canonical, score = max(candidates, key=lambda item: item[1])
            if score and canonical not in used:
                mapping[canonical] = header
                used.add(canonical)
        self._mapping = mapping
        return {"domain": winner, "confidence": confidence, "column_mapping": mapping, "domain_scores": scores}

    def sanitize_dataframe(self) -> pd.DataFrame:
        """Build a typed dataframe and quarantine rows with cast failures."""
        self._ensure_parsed()
        data_rows = self._raw_rows[self._source_info.header_row + 1 :] if self._source_info else []
        records: list[dict[str, Any]] = []
        for offset, row in enumerate(data_rows, start=(self._source_info.header_row + 2 if self._source_info else 2)):
            if not any(str(cell).strip() for cell in row) or str(row[0]).lstrip().startswith(("#", "//")):
                continue
            errors: list[str] = []
            padded = list(row[: len(self._headers)]) + [""] * max(0, len(self._headers) - len(row))
            raw = dict(zip(self._headers, padded))
            if len(row) > len(self._headers):
                errors.append(f"extra columns: {len(row) - len(self._headers)}")
            clean: dict[str, Any] = {}
            for header, value in raw.items():
                canonical = next((name for name, source in self._mapping.items() if source == header), None)
                target = canonical or header
                if target in NUMERIC_CANONICAL:
                    try:
                        clean[target] = self._number(value)
                    except ValueError as error:
                        errors.append(f"{header}: {error}")
                elif target in DATE_CANONICAL:
                    try:
                        clean[target] = self._date(value)
                    except ValueError as error:
                        errors.append(f"{header}: {error}")
                else:
                    text = "" if value is None else str(value).strip()
                    clean[target] = None if text.lower() in MISSING_TOKENS else text
            text_payload = {key: clean.get(key) for key in list(clean) if any(hint in self._normal_key(key) for hint in TEXT_HINTS) and clean.get(key) is not None}
            if text_payload:
                clean["_text_payload"] = json.dumps(text_payload, ensure_ascii=False)
            if errors:
                self._quarantined.append({"row_number": offset, "errors": errors, "raw": raw})
            else:
                records.append(clean)
        return pd.DataFrame(records)

    def process_file(self) -> dict[str, Any]:
        """Run detection, classification, sanitization, and return an audit manifest."""
        dialect = self.detect_dialect_and_encoding()
        classification = self.infer_domain_and_mapping()
        clean_df = self.sanitize_dataframe()
        type_summary = {column: str(dtype) for column, dtype in clean_df.dtypes.items()}
        return {
            "domain": classification["domain"],
            "confidence": classification["confidence"],
            "clean_df": clean_df,
            "quarantined_rows": self._quarantined,
            "schema_summary": {
                **dialect,
                **classification,
                "data_types": type_summary,
                "source_rows": len(self._raw_rows) - (self._source_info.header_row + 1 if self._source_info else 0),
                "accepted_rows": len(clean_df),
                "quarantined_count": len(self._quarantined),
            },
        }
