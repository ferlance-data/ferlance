"""MoMo and bank statements, and reconciliation (PRD §9, G5).

The rule: **an imported statement checks the books; it does not add to them.** MoMo SMS imports,
debt payments, receipts and manual journals already post to the wallets and the bank, so posting
every statement line would count money twice. Instead:

1. **Import:** CSV or XLSX (no PDF yet). Columns are found by common names, or the owner maps
   them. Each line gets a key (its transaction ID, otherwise date + amount + balance after), so
   overlapping monthly exports add nothing twice. The file is checked against itself (each
   balance follows the last) before anything else.
2. **Match**, worked out every time the page is read (never stored as truth): transaction ID first,
   then the exact amount within ±2 days, one-to-one. Candidates are the *events* on that account:
   sales records whose payment went there, debt payments and receipts, manual journals and other
   statements' bookings. When several fit, the line is only *suggested*. If a matched import is
   later left out, its lines simply become unmatched again.
3. **Book** what the books don't have yet, from a fixed list of categories (below). Bookings are
   a ledger source (``stmt:<line id>``, synced by ``ledger.catch_up``), so they are reversible and
   follow the books start date. Fees and levies on a line are booked to MoMo and bank charges, only
   when the owner says so.
4. **Reconcile:** for each account, statement closing balance minus books balance, explained cedi
   by cedi: the opening gap, statement lines not in the books, fees not booked, and book entries
   with no statement line. Whatever is left is "unexplained" and should be zero.

Real export layouts from MTN, Telecel, AT and the banks have not been verified yet.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import dataset_store, db, debts, ledger

ACCOUNTS = {"momo_mtn": "MTN Mobile Money", "momo_telecel": "Telecel Cash", "momo_at": "AT Money", "momo_other": "Mobile money (other)", "bank": "Bank"}
FIELDS = ("date", "description", "reference", "amount", "credit", "debit", "fee", "balance_after", "balance_before", "type")
ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("transaction date", "trans date", "txn date", "date", "value date", "posting date", "date/time", "datetime", "time"),
    "description": ("description", "narration", "details", "particulars", "remarks", "from name", "to name", "name", "memo"),
    "reference": ("transaction id", "trans id", "txn id", "financial transaction id", "reference", "ref", "ref no", "reference no", "external id"),
    "amount": ("amount", "amount ghs", "amount (ghs)", "transaction amount", "value"),
    "credit": ("credit", "credits", "money in", "paid in", "deposit", "deposits", "cr"),
    "debit": ("debit", "debits", "money out", "paid out", "withdrawal", "withdrawals", "dr"),
    "fee": ("fee", "fees", "charge", "charges", "e-levy", "elevy", "levy", "commission"),
    "balance_after": ("balance after", "bal after", "balance", "closing balance", "running balance", "new balance", "available balance"),
    "balance_before": ("balance before", "bal before", "opening balance", "previous balance"),
    "type": ("type", "trans type", "transaction type", "dr/cr", "cr/dr", "direction"),
}
INFLOW_WORDS = ("receive", "received", "credit", "cash in", "deposit", "transfer from", "payment received", "incoming", "refund", "cr")
OUTFLOW_WORDS = ("send", "sent", "debit", "cash out", "withdraw", "payment", "transfer to", "purchase", "airtime", "bill", "outgoing", "dr")
MAX_ROWS = 5000
MATCH_DAYS = 2
CATEGORIES_IN = ("sale_recorded", "new_sale", "owner", "transfer", "debt_payment", "other_income")
CATEGORIES_OUT = ("payment_recorded", "expense", "owner", "transfer", "debt_payment")


class StatementError(ValueError):
    status = 400


class NotFound(StatementError):
    status = 404


def _key(text: Any) -> str:
    return " ".join(str(text or "").casefold().replace("_", " ").split())


# ---------------------------------------------------------------- reading files


def read_rows(content: bytes, filename: str) -> list[list[str]]:
    """All rows of the first sheet as text (statements often have title rows above the header)."""
    name = filename.lower()
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        rows = [["" if value is None else (value.isoformat() if hasattr(value, "isoformat") else str(value)) for value in row] for row in book.active.iter_rows(values_only=True)]
        book.close()
        return rows[:MAX_ROWS]
    if name.endswith((".csv", ".txt", ".tsv")):
        text = content.decode("utf-8-sig", errors="replace")
        first = next((line for line in text.splitlines() if line.strip()), "")
        delimiter = "\t" if "\t" in first else ";" if first.count(";") > first.count(",") else ","
        return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)][:MAX_ROWS]
    raise StatementError("Upload the statement as CSV or Excel (XLSX). PDF statements are not supported yet.")


def find_header(rows: list[list[str]]) -> int:
    """The first row that looks like column names: a date column plus at least two other known names."""
    for index, row in enumerate(rows[:30]):
        names = {_key(cell) for cell in row}
        if any(alias in names for alias in ALIASES["date"]) and sum(any(alias in names for alias in ALIASES[field]) for field in FIELDS) >= 3:
            return index
    raise StatementError("Could not find the column names. Choose the columns yourself.")


def suggest_mapping(header: list[str]) -> dict[str, int | None]:
    names = [_key(cell) for cell in header]
    mapping: dict[str, int | None] = {}
    taken: set[int] = set()
    for field in ("balance_before", "balance_after", "reference", "fee", "credit", "debit", "amount", "type", "date", "description"):
        mapping[field] = None
        for alias in ALIASES[field]:  # aliases are in order of preference
            hits = [i for i, name in enumerate(names) if name == alias and i not in taken]
            if hits:
                mapping[field] = hits[0]
                taken.add(hits[0])
                break
    return {field: mapping.get(field) for field in FIELDS}


def preview(content: bytes, filename: str) -> dict[str, Any]:
    rows = read_rows(content, filename)
    try:
        header_row = find_header(rows)
        mapping = suggest_mapping(rows[header_row])
        confident = mapping["date"] is not None and (mapping["amount"] is not None or mapping["credit"] is not None or mapping["debit"] is not None)
    except StatementError:
        header_row, mapping, confident = 0, {field: None for field in FIELDS}, False
    return {"header_row": header_row, "columns": rows[header_row] if rows else [], "sample": rows[header_row + 1: header_row + 6], "mapping": mapping, "confident": confident}


_NUMBER = re.compile(r"-?\(?[\d,]*\.?\d+\)?")


def _money(value: Any) -> int | None:
    text = str(value or "").replace("GHS", "").replace("GH₵", "").replace("₵", "").replace(" ", "").strip()
    if not text or text in ("-", "—"):
        return None
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")")) or text.upper().endswith("DR")
    match = _NUMBER.search(text.replace("(", "").replace(")", ""))
    if not match:
        return None
    amount = ledger.to_minor(match.group().lstrip("-").replace(",", ""))
    return -amount if negative else amount


_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d %B %Y", "%m/%d/%Y")


def _date(value: Any, month_first: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    head = re.split(r"[ T](?=\d{1,2}:\d{2})", text)[0].strip()
    formats = ("%m/%d/%Y",) + _DATE_FORMATS if month_first else _DATE_FORMATS
    for fmt in formats:
        try:
            return datetime.strptime(head, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _month_first(values: list[str]) -> bool:
    """Ghana writes day/month. Only read month/day when some second number is over 12 (e.g. 11/24/2026)."""
    for value in values:
        parts = re.findall(r"\d+", str(value))
        if len(parts) >= 3 and len(parts[0]) <= 2 and int(parts[1]) > 12 >= int(parts[0]):
            return True
    return False


def parse(rows: list[list[str]], header_row: int, mapping: dict[str, int | None]) -> tuple[list[dict[str, Any]], list[str]]:
    """Statement lines with a signed amount (money in +, out -), the fee (always positive), and checks."""
    if mapping.get("date") is None or not any(mapping.get(f) is not None for f in ("amount", "credit", "debit")):
        raise StatementError("Choose at least the date column and the amount (or money in / money out) columns.")

    def cell(row: list[str], field: str) -> str:
        index = mapping.get(field)
        return row[index] if index is not None and index < len(row) else ""

    body = [row for row in rows[header_row + 1:] if any(str(c).strip() for c in row)]
    month_first = _month_first([cell(row, "date") for row in body])
    lines, problems = [], []
    for number, row in enumerate(body, start=header_row + 2):
        day = _date(cell(row, "date"), month_first)
        credit, debit = _money(cell(row, "credit")), _money(cell(row, "debit"))
        amount = _money(cell(row, "amount"))
        fee = abs(_money(cell(row, "fee")) or 0)
        after, before = _money(cell(row, "balance_after")), _money(cell(row, "balance_before"))
        if day is None:
            problems.append(f"Row {number}: no readable date, skipped.")
            continue
        if credit is not None or debit is not None:
            signed = abs(credit or 0) - abs(debit or 0)
        elif amount is None:
            problems.append(f"Row {number}: no amount, skipped.")
            continue
        elif before is not None and after is not None and abs(after - before + fee) == abs(amount):
            signed = after - before + fee  # the balance change decides the direction
        elif amount < 0:
            signed = amount
        else:
            words = _key(cell(row, "type")) + " " + _key(cell(row, "description"))
            if any(re.search(rf"\b{re.escape(w)}\b", words) for w in OUTFLOW_WORDS) and not any(re.search(rf"\b{re.escape(w)}\b", words) for w in ("receive", "received", "cash in", "deposit", "credit")):
                signed = -amount
            else:
                signed = amount
        if signed == 0:
            continue
        reference = " ".join(cell(row, "reference").split())[:80]
        description = " ".join(cell(row, "description").split())[:200]
        key = f"id:{reference}" if reference else f"{day}|{signed}|{after}|{description[:40]}"
        lines.append({"date": day, "description": description, "reference": reference, "amount": signed, "fee": fee, "balance_after": after, "key": key})
    # Each line's balance should follow from the one before: a break means a missing page or a wrong sign.
    for previous, current in zip(lines, lines[1:]):
        if previous["balance_after"] is not None and current["balance_after"] is not None:
            expected = previous["balance_after"] + current["amount"] - current["fee"]
            if expected != current["balance_after"]:
                problems.append(f"Balance jumps on {current['date']}: expected {ledger.from_minor(expected):,.2f}, the statement says {ledger.from_minor(current['balance_after']):,.2f}. A page may be missing, or the order is reversed.")
                break
    return lines, problems


def import_statement(path: Path, business_id: str, user_id: str, account: str, filename: str, content: bytes, header_row: int, mapping: dict[str, int | None]) -> dict[str, Any]:
    if account not in ACCOUNTS:
        raise StatementError("Choose which wallet or bank account this statement is for.")
    rows = read_rows(content, filename)
    lines, problems = parse(rows, header_row, mapping)
    if not lines:
        raise StatementError("No statement lines could be read. " + " ".join(problems[:3]))
    # Oldest first (many exports list newest first), keeping the file's order within a day.
    if len(lines) > 1 and lines[0]["date"] > lines[-1]["date"]:
        lines.reverse()
    import_id = str(uuid.uuid4())
    added = 0
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for position, line in enumerate(lines):
            cursor = conn.execute(
                "INSERT OR IGNORE INTO statement_lines (id, business_id, import_id, account, line_key, position, txn_date, description, reference, amount_minor, fee_minor, balance_after_minor) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), business_id, import_id, account, line["key"], position, line["date"], line["description"], line["reference"], line["amount"], line["fee"], line["balance_after"]),
            )
            added += cursor.rowcount
        conn.execute(
            "INSERT INTO statement_imports (id, business_id, account, filename, new_lines, duplicate_lines, checks, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (import_id, business_id, account, filename[:120], added, len(lines) - added, json.dumps(problems[:20]), user_id, db.now()),
        )
    return {"id": import_id, "account": account, "lines": len(lines), "new_lines": added, "duplicates": len(lines) - added, "checks": problems[:20]}


# ---------------------------------------------------------------- candidates and matching


def _candidates(conn, business_id: str, account: str, first: str, last: str) -> list[dict[str, Any]]:
    """Money events the books already hold on this account in the period (± the match window)."""
    start = (date.fromisoformat(first) - timedelta(days=MATCH_DAYS)).isoformat()
    end = (date.fromisoformat(last) + timedelta(days=MATCH_DAYS)).isoformat()
    accounts = ledger.ensure_accounts(conn, business_id)
    found: list[dict[str, Any]] = []
    # 1. Sales and MoMo records (event level, so two identical payments on a day stay two).
    for dataset in dataset_store.analysable(business_id):
        try:
            records = dataset_store.read_records(dataset)
        except dataset_store.RecordsUnavailableError:
            continue
        for index, record in enumerate(records):
            day = str(record.get("transaction_date") or "")[:10]
            if not day or not start <= day <= end or ledger.receipt_account(record) != account:
                continue
            amount = ledger._minor_of(record, "amount")
            signed = -amount if record.get("category") == "momo_expense_paid" else amount
            if signed:
                found.append({"id": f"record:{dataset['id']}:{index}", "date": day, "amount": signed, "txn": str(record.get("transaction_id") or ""),
                              "label": str(record.get("product") or record.get("customer") or dataset["filename"])[:80], "source": f"dataset:{dataset['id']}"})
    # 2. Every other source on this account, netted per source and day (single events by nature).
    rows = conn.execute(
        "SELECT e.source_key, e.entry_date, SUM(l.amount_minor) AS amount, MIN(e.memo) AS memo FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id "
        "WHERE e.business_id = ? AND e.status = 'posted' AND l.account_id = ? AND e.entry_date BETWEEN ? AND ? "
        "AND e.source_key NOT LIKE 'dataset:%' AND e.source_key != 'opening' GROUP BY e.source_key, e.entry_date HAVING SUM(l.amount_minor) != 0",
        (business_id, accounts[account], start, end),
    ).fetchall()
    for row in rows:
        found.append({"id": f"{row['source_key']}@{row['entry_date']}", "date": row["entry_date"], "amount": row["amount"], "txn": "", "label": row["memo"][:80], "source": row["source_key"]})
    return found


def _lines(conn, business_id: str, account: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM statement_lines WHERE business_id = ? AND account = ? ORDER BY txn_date, import_id, position", (business_id, account)
    ).fetchall()]


def match(lines: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """line id -> {status, candidate, suggestions}. One-to-one; ambiguity only suggests."""
    result: dict[str, dict[str, Any]] = {}
    own = {f"stmt:{line['id']}" for line in lines}
    pool = {c["id"]: c for c in candidates if c["source"] not in own}  # a booked line is not its own match
    used: set[str] = set()
    for line in lines:
        if line["booking"] and line["booking"] != "debt_payment":
            result[line["id"]] = {"status": "booked", "candidate": None, "suggestions": []}
    # Chosen by the owner earlier, if that event still exists.
    for line in lines:
        ref = line.get("match_ref")
        if line["id"] not in result and ref and ref in pool and ref not in used and pool[ref]["amount"] == line["amount_minor"]:
            used.add(ref)
            result[line["id"]] = {"status": "matched", "candidate": pool[ref], "suggestions": []}
    # Transaction ID, then exact amount within the window.
    for line in lines:
        if line["id"] in result or not line["reference"]:
            continue
        hit = next((c for c in pool.values() if c["id"] not in used and c["txn"] and c["txn"] == line["reference"] and c["amount"] == line["amount_minor"]), None)
        if hit:
            used.add(hit["id"])
            result[line["id"]] = {"status": "matched", "candidate": hit, "suggestions": []}
    for line in lines:
        if line["id"] in result:
            continue
        day = date.fromisoformat(line["txn_date"])
        fits = [c for c in pool.values() if c["id"] not in used and c["amount"] == line["amount_minor"] and abs((date.fromisoformat(c["date"]) - day).days) <= MATCH_DAYS]
        rivals = [other for other in lines if other["id"] not in result and other["id"] != line["id"] and other["amount_minor"] == line["amount_minor"]
                  and any(abs((date.fromisoformat(c["date"]) - date.fromisoformat(other["txn_date"])).days) <= MATCH_DAYS for c in fits)]
        if len(fits) == 1 and not rivals:
            used.add(fits[0]["id"])
            result[line["id"]] = {"status": "matched", "candidate": fits[0], "suggestions": []}
        else:
            result[line["id"]] = {"status": "suggested" if fits else "unmatched", "candidate": None, "suggestions": fits[:5]}
    return result


def view(path: Path, business_id: str, account: str) -> dict[str, Any]:
    """Statement lines with their match state, and the reconciliation for the account."""
    if account not in ACCOUNTS:
        raise NotFound("Unknown account.")
    ledger.catch_up(path, business_id)
    with db.connection(path) as conn:
        books_start = ledger.settings(conn, business_id)["books_start"]
        lines = [line for line in _lines(conn, business_id, account) if not books_start or line["txn_date"] >= books_start]
        if not lines:
            return {"account": account, "label": ACCOUNTS[account], "lines": [], "summary": None, "books_start": books_start}
        first, last = lines[0]["txn_date"], lines[-1]["txn_date"]
        candidates = _candidates(conn, business_id, account, first, last)
        accounts = ledger.ensure_accounts(conn, business_id)

        def books_balance(as_of: str) -> int:
            row = conn.execute(
                "SELECT COALESCE(SUM(l.amount_minor), 0) AS amount FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id "
                "WHERE e.business_id = ? AND e.status = 'posted' AND l.account_id = ? AND e.entry_date <= ?",
                (business_id, accounts[account], as_of),
            ).fetchone()
            return row["amount"]

        books_open = books_balance((date.fromisoformat(first) - timedelta(days=1)).isoformat())
        books_close = books_balance(last)
    matches = match(lines, candidates)
    matched_ids = {m["candidate"]["id"] for m in matches.values() if m["candidate"]}
    in_period = [c for c in candidates if first <= c["date"] <= last]
    unmatched_books = [c for c in in_period if c["id"] not in matched_ids and not c["source"].startswith("stmt:")]

    has_balance = lines[0]["balance_after_minor"] is not None and lines[-1]["balance_after_minor"] is not None
    stmt_open = lines[0]["balance_after_minor"] - lines[0]["amount_minor"] + lines[0]["fee_minor"] if has_balance else None
    stmt_close = lines[-1]["balance_after_minor"] if has_balance else None
    not_in_books = sum(l["amount_minor"] for l in lines if matches[l["id"]]["status"] in ("unmatched", "suggested"))
    fees_unbooked = sum(l["fee_minor"] for l in lines if l["fee_minor"] and not l["fee_booked"])
    only_in_books = sum(c["amount"] for c in unmatched_books)
    summary = {
        "first": first, "last": last, "statement_opening": _out(stmt_open), "statement_closing": _out(stmt_close),
        "books_opening": ledger.from_minor(books_open), "books_closing": ledger.from_minor(books_close),
        "difference": _out(stmt_close - books_close if has_balance else None),
        "explained": [],
        "unmatched_lines": sum(1 for m in matches.values() if m["status"] in ("unmatched", "suggested")),
    }
    if has_balance:
        parts = [
            ("Different starting balances (the opening gap)", stmt_open - books_open),
            ("Statement lines not in the books yet", not_in_books),
            ("Fees and levies not booked yet", -fees_unbooked),
            ("In the books but not on the statement", -only_in_books),
        ]
        summary["explained"] = [{"reason": reason, "amount": ledger.from_minor(amount)} for reason, amount in parts if amount]
        summary["unexplained"] = ledger.from_minor((stmt_close - books_close) - sum(amount for _, amount in parts))
    out_lines = []
    for line in lines:
        state = matches[line["id"]]
        out_lines.append({
            "id": line["id"], "date": line["txn_date"], "description": line["description"], "reference": line["reference"],
            "amount": ledger.from_minor(line["amount_minor"]), "fee": ledger.from_minor(line["fee_minor"]), "fee_booked": bool(line["fee_booked"]),
            "balance_after": _out(line["balance_after_minor"]), "status": state["status"], "booking": line["booking"],
            "booking_detail": json.loads(line["booking_detail"] or "null"),
            "matched_to": _public(state["candidate"]), "suggestions": [_public(c) for c in state["suggestions"]],
        })
    return {"account": account, "label": ACCOUNTS[account], "lines": out_lines, "summary": summary,
            "only_in_books": [_public(c) for c in unmatched_books], "books_start": books_start}


def _out(value: int | None) -> float | None:
    return None if value is None else ledger.from_minor(value)


def _public(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    return {"id": candidate["id"], "date": candidate["date"], "amount": ledger.from_minor(candidate["amount"]), "label": candidate["label"]}


# ---------------------------------------------------------------- owner actions


def _line(conn, business_id: str, line_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM statement_lines WHERE id = ? AND business_id = ?", (line_id, business_id)).fetchone()
    if not row:
        raise NotFound("Statement line not found.")
    return dict(row)


def choose_match(path: Path, business_id: str, user_id: str, line_id: str, candidate_id: str | None) -> None:
    with db.connection(path) as conn:
        line = _line(conn, business_id, line_id)
        if line["booking"]:
            raise StatementError("Undo the booking first.")
        conn.execute("UPDATE statement_lines SET match_ref = ?, updated_by = ?, updated_at = ? WHERE id = ?", (candidate_id, user_id, db.now(), line_id))


def book(path: Path, business_id: str, user_id: str, line_id: str, category: str, detail: dict[str, Any]) -> dict[str, Any]:
    """Put a statement line into the books with one of the fixed categories."""
    with db.connection(path) as conn:
        line = _line(conn, business_id, line_id)
        books_start = ledger.settings(conn, business_id)["books_start"]
    if line["booking"]:
        raise StatementError("This line is already booked. Undo it first.")
    if books_start and line["txn_date"] < books_start:
        raise StatementError("This line is before your books start; its money is in the opening balances.")
    inflow = line["amount_minor"] > 0
    allowed = CATEGORIES_IN if inflow else CATEGORIES_OUT
    if category not in allowed:
        raise StatementError("Choose one of the listed kinds for this line.")
    stored: dict[str, Any] = {}
    if category == "expense":
        key = str(detail.get("expense") or "uncategorised")
        if key not in ("rent", "transport", "airtime", "utilities", "wages", "charges", "uncategorised"):
            raise StatementError("Choose a kind of spending.")
        stored["expense"] = key
    if category == "transfer":
        other = str(detail.get("other_account") or "")
        if other not in ledger.CASH_KEYS or other == line["account"]:
            raise StatementError("Choose the other account (cash, bank or a wallet).")
        stored["other_account"] = other
    if category == "debt_payment":
        debt_id = str(detail.get("debt_id") or "")
        payment = debts.add_payment(path, business_id, user_id, debt_id, amount=abs(line["amount_minor"]) / 100, paid_on=date.fromisoformat(line["txn_date"]),
                                    method=line["account"], momo_ref=None)
        stored.update({"debt_id": debt_id, "payment_id": payment["id"]})
    with db.connection(path) as conn:
        ref = None
        if category == "debt_payment":
            ref = f"debtpay:{stored['payment_id']}@{line['txn_date']}"
        conn.execute(
            "UPDATE statement_lines SET booking = ?, booking_detail = ?, match_ref = COALESCE(?, match_ref), updated_by = ?, updated_at = ? WHERE id = ?",
            (category, json.dumps(stored), ref, user_id, db.now(), line_id),
        )
    ledger.catch_up(path, business_id, user_id)
    return {"id": line_id, "booking": category}


def unbook(path: Path, business_id: str, user_id: str, line_id: str) -> None:
    with db.connection(path) as conn:
        line = _line(conn, business_id, line_id)
    detail = json.loads(line["booking_detail"] or "{}")
    if line["booking"] == "debt_payment" and detail.get("payment_id"):
        debts.void_payment(path, business_id, user_id, detail["payment_id"])
    with db.connection(path) as conn:
        conn.execute("UPDATE statement_lines SET booking = NULL, booking_detail = NULL, match_ref = NULL, updated_by = ?, updated_at = ? WHERE id = ?", (user_id, db.now(), line_id))
    ledger.catch_up(path, business_id, user_id)


def book_fees(path: Path, business_id: str, user_id: str, account: str) -> int:
    with db.connection(path) as conn:
        books_start = ledger.settings(conn, business_id)["books_start"] or "0000-00-00"
        count = conn.execute(
            "UPDATE statement_lines SET fee_booked = 1, updated_by = ?, updated_at = ? WHERE business_id = ? AND account = ? AND fee_minor > 0 AND fee_booked = 0 AND txn_date >= ?",
            (user_id, db.now(), business_id, account, books_start),
        ).rowcount
    ledger.catch_up(path, business_id, user_id)
    return count


# ---------------------------------------------------------------- ledger source


def postings(line: dict[str, Any], accounts: dict[str, str], currency: str) -> list[ledger.Posting]:
    """What a booked line (and its booked fee) adds to the books. Used by ledger.catch_up."""
    day, amount, money_account = line["txn_date"], line["amount_minor"], accounts[line["account"]]
    label = (line["description"] or line["reference"] or "Statement line")[:120]
    detail = json.loads(line["booking_detail"] or "{}")
    lines: list[ledger.Line] = []
    category = line["booking"]
    if category and category != "debt_payment":
        if category == "sale_recorded":
            counter = "receipts_clearing"
        elif category == "payment_recorded":
            counter = "payments_clearing"
        elif category == "new_sale":
            counter = "sales"
        elif category == "other_income":
            counter = "other_income"
        elif category == "expense":
            counter = detail.get("expense", "uncategorised")
        elif category == "owner":
            counter = "owner_capital" if amount > 0 else "drawings"
        else:  # transfer
            counter = detail["other_account"]
        lines += [(money_account, currency, amount, label), (accounts[counter], currency, -amount, label)]
    if line["fee_booked"] and line["fee_minor"]:
        lines += [(accounts["charges"], currency, line["fee_minor"], f"Fee: {label}"), (money_account, currency, -line["fee_minor"], f"Fee: {label}")]
    return [(day, f"Statement: {label}", lines)] if lines else []


def fingerprint(line: dict[str, Any], books_start: str | None) -> str:
    raw = f"{books_start}:{line['booking']}:{line['booking_detail']}:{line['fee_booked']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def overview(path: Path, business_id: str) -> dict[str, Any]:
    """Which accounts have statements, and the latest imports with their checks."""
    rows = db.many(
        path,
        "SELECT account, COUNT(*) AS lines, MIN(txn_date) AS first, MAX(txn_date) AS last FROM statement_lines WHERE business_id = ? GROUP BY account",
        (business_id,),
    )
    imports = db.many(path, "SELECT account, filename, new_lines, duplicate_lines, checks, created_at FROM statement_imports WHERE business_id = ? ORDER BY created_at DESC LIMIT 20", (business_id,))
    return {
        "accounts": [{**row, "label": ACCOUNTS.get(row["account"], row["account"])} for row in rows],
        "imports": [{**row, "checks": json.loads(row["checks"])} for row in imports],
        "choices": ACCOUNTS,
    }
