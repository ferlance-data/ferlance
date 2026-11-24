"""Planning extras (PRD §9, G9): recurring expenses, budgets against actuals, the accountant's
year-end pack, and "download my data".

- **Recurring expenses** (rent, salaries paid outside payroll, subscriptions) never post on their
  own: each month they show as due, and the owner confirms (with the real amount) or skips.
  Confirmed months post Expense / paid-from account (``ledger._catch_up_recurring``).
- **Budgets** are per month and per income or expense account; actuals come from the ledger.
- **Year-end pack**: a zip of CSVs an accountant needs (trial balance, P&L, balance sheet, the
  year's journal, debtors, creditors, stock valuation) plus a README listing open caveats.
- **Download my data**: everything this business has in Ferlance, as CSVs, for the owner.
"""

from __future__ import annotations

import csv
import io
import uuid
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from . import db, debts, exports, ledger, tax

EXPENSE_ACCOUNTS = ("rent", "transport", "airtime", "utilities", "wages", "charges", "uncategorised")
PAY_FROM = ("cash", "bank", "momo_mtn", "momo_telecel", "momo_at", "momo_other")


class PlanningError(ValueError):
    status = 400


class NotFound(PlanningError):
    status = 404


def _month(value: str) -> str:
    try:
        return date.fromisoformat(f"{value}-01").isoformat()[:7]
    except ValueError as error:
        raise PlanningError("Use a month like 2026-11.") from error


def _next(month: str) -> str:
    year, number = int(month[:4]), int(month[5:])
    return f"{year + (number == 12):04d}-{1 if number == 12 else number + 1:02d}"


# ---------------------------------------------------------------- recurring expenses


def add_recurring(path: Path, business_id: str, user_id: str, *, name: str, account: str, amount: float, paid_from: str, day_of_month: int, start_month: str, end_month: str | None) -> dict[str, Any]:
    name = " ".join(name.split())
    if not name:
        raise PlanningError("Name the expense.")
    if account not in EXPENSE_ACCOUNTS or paid_from not in PAY_FROM:
        raise PlanningError("Choose the kind of expense and where it is paid from.")
    start = _month(start_month)
    end = _month(end_month) if end_month else None
    if end and end < start:
        raise PlanningError("The last month cannot be before the first.")
    item_id = str(uuid.uuid4())
    db.insert(path, "INSERT INTO recurring_items (id, business_id, name, account, amount_minor, paid_from, day_of_month, start_month, end_month, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (item_id, business_id, name[:120], account, ledger.to_minor(amount), paid_from, day_of_month, start, end, user_id, db.now()))
    return {"id": item_id}


def stop_recurring(path: Path, business_id: str, item_id: str) -> None:
    with db.connection(path) as conn:
        if not conn.execute("UPDATE recurring_items SET active = 0 WHERE id = ? AND business_id = ?", (item_id, business_id)).rowcount:
            raise NotFound("Not found.")


def recurring(path: Path, business_id: str, today: date | None = None) -> dict[str, Any]:
    """Items, plus every month up to now that is due and not yet confirmed or skipped."""
    today = today or date.today()
    this_month = today.isoformat()[:7]
    items = db.many(path, "SELECT * FROM recurring_items WHERE business_id = ? ORDER BY active DESC, name COLLATE NOCASE", (business_id,))
    decided = {(r["item_id"], r["month"]): r for r in db.many(path, "SELECT * FROM recurring_posts WHERE business_id = ?", (business_id,))}
    due = []
    for item in items:
        if not item["active"]:
            continue
        month = item["start_month"]
        while month <= this_month and (not item["end_month"] or month <= item["end_month"]):
            day = f"{month}-{item['day_of_month']:02d}"
            if (item["id"], month) not in decided and day <= today.isoformat():
                due.append({"item_id": item["id"], "name": item["name"], "month": month, "due_on": day, "amount": ledger.from_minor(item["amount_minor"]), "account": item["account"], "paid_from": item["paid_from"]})
            month = _next(month)
    return {
        "items": [{"id": i["id"], "name": i["name"], "account": i["account"], "amount": ledger.from_minor(i["amount_minor"]), "paid_from": i["paid_from"],
                   "day_of_month": i["day_of_month"], "start_month": i["start_month"], "end_month": i["end_month"], "active": bool(i["active"])} for i in items],
        "due": sorted(due, key=lambda d: d["due_on"]),
        "history": [{"item_id": r["item_id"], "month": r["month"], "status": r["status"], "amount": ledger.from_minor(r["amount_minor"]), "posted_on": r["posted_on"]}
                    for r in sorted(decided.values(), key=lambda r: r["month"], reverse=True)[:50]],
    }


def decide(path: Path, business_id: str, user_id: str, item_id: str, month: str, confirm: bool, amount: float | None, posted_on: date | None) -> None:
    month = _month(month)
    item = db.one(path, "SELECT * FROM recurring_items WHERE id = ? AND business_id = ?", (item_id, business_id))
    if not item:
        raise NotFound("Not found.")
    day = posted_on or date.fromisoformat(f"{month}-{item['day_of_month']:02d}")
    if day > date.today():
        raise PlanningError("You can only confirm payments that have happened.")
    minor = ledger.to_minor(amount) if amount is not None else item["amount_minor"]
    if confirm and minor <= 0:
        raise PlanningError("The amount must be more than zero.")
    with db.connection(path) as conn:
        try:
            conn.execute("INSERT INTO recurring_posts (item_id, month, business_id, status, amount_minor, posted_on, decided_by, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                         (item_id, month, business_id, "confirmed" if confirm else "skipped", minor, day.isoformat(), user_id, db.now()))
        except Exception as error:  # the primary key: one decision per item and month
            raise PlanningError("That month is already confirmed or skipped.") from error
    ledger.catch_up(path, business_id, user_id)


def undo(path: Path, business_id: str, user_id: str, item_id: str, month: str) -> None:
    with db.connection(path) as conn:
        if not conn.execute("DELETE FROM recurring_posts WHERE item_id = ? AND month = ? AND business_id = ?", (item_id, _month(month), business_id)).rowcount:
            raise NotFound("Not found.")
    ledger.catch_up(path, business_id, user_id)


# ---------------------------------------------------------------- budgets


def set_budget(path: Path, business_id: str, month: str, account: str, amount: float) -> None:
    month = _month(month)
    keys = {key for key, _, _, kind in ledger.DEFAULT_ACCOUNTS if kind in ("income", "expense")}
    if account not in keys:
        raise PlanningError("Choose an income or expense account.")
    if amount <= 0:
        db.insert(path, "DELETE FROM budgets WHERE business_id = ? AND month = ? AND account = ?", (business_id, month, account))
        return
    db.insert(path, "INSERT INTO budgets (business_id, month, account, amount_minor, updated_at) VALUES (?, ?, ?, ?, ?) "
              "ON CONFLICT(business_id, month, account) DO UPDATE SET amount_minor = excluded.amount_minor, updated_at = excluded.updated_at",
              (business_id, month, account, ledger.to_minor(amount), db.now()))


def budget_vs_actual(path: Path, business_id: str, month: str) -> dict[str, Any]:
    month = _month(month)
    ledger.catch_up(path, business_id)
    first = f"{month}-01"
    last = f"{_next(month)}-01"
    with db.connection(path) as conn:
        rows = conn.execute(
            "SELECT a.system_key AS key, a.name, a.type, SUM(l.amount_minor) AS amount FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id "
            "JOIN ledger_accounts a ON a.id = l.account_id WHERE e.business_id = ? AND e.status = 'posted' AND e.entry_date >= ? AND e.entry_date < ? "
            "AND a.type IN ('income', 'expense') AND a.system_key IS NOT NULL GROUP BY a.system_key",
            (business_id, first, last),
        ).fetchall()
    actual = {row["key"]: (-row["amount"] if row["type"] == "income" else row["amount"]) for row in rows}
    budgets = {row["account"]: row["amount_minor"] for row in db.many(path, "SELECT account, amount_minor FROM budgets WHERE business_id = ? AND month = ?", (business_id, month))}
    names = {key: (name, kind) for key, _, name, kind in ledger.DEFAULT_ACCOUNTS if kind in ("income", "expense")}
    lines = []
    for key in sorted(set(actual) | set(budgets), key=lambda k: (names.get(k, ("", "z"))[1], names.get(k, (k,))[0])):
        if key not in names:
            continue
        name, kind = names[key]
        budget, spent = budgets.get(key), actual.get(key, 0)
        lines.append({"account": key, "name": name, "type": kind, "budget": ledger.from_minor(budget) if budget is not None else None,
                      "actual": ledger.from_minor(spent), "used_pct": round(spent / budget * 100) if budget else None,
                      "over": bool(budget) and (spent > budget if kind == "expense" else False)})
    return {"month": month, "lines": lines}


# ---------------------------------------------------------------- year-end pack and data download


def _csv(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    buffer = io.StringIO()
    columns = columns or (list(rows[0].keys()) if rows else ["empty"])
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Spreadsheet formula injection: neutralise cells that start like a formula.
        writer.writerow({k: (f"'{v}" if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v) for k, v in row.items()})
    return buffer.getvalue()


def year_end_pack(path: Path, business_id: str, year: int) -> bytes:
    first, last = date(year, 1, 1), date(year, 12, 31)
    ledger.catch_up(path, business_id)
    trial = ledger.trial_balance(path, business_id, last)
    pnl = ledger.profit_and_loss(path, business_id, first, last)
    sheet = ledger.balance_sheet(path, business_id, last)
    book = debts.book(path, business_id, last)
    tables = exports.tables(business_id)
    stock = [{"name": p["name"], "unit": p["unit"], "quantity_on_hand": p["quantity_on_hand"], "unit_cost": p["unit_cost"],
              "value": round((p["quantity_on_hand"] or 0) * (p["unit_cost"] or 0), 2) if p["unit_cost"] is not None else ""} for p in tables["inventory_products"]]
    journal_rows = [row for row in csv.DictReader(io.StringIO(ledger.journal_csv(path, business_id))) if row["Date"][:4] == str(year)]
    with db.connection(path) as conn:
        settings = ledger.settings(conn, business_id)
    unchecked = tax.unchecked(path, business_id, {rule["id"] for rule in tax.RULES})
    readme = (
        f"Year-end pack for {year}, made by Ferlance on {date.today().isoformat()}.\n\n"
        f"Books start date: {settings['books_start'] or 'not set'}. Period lock: {settings['lock_date'] or 'none'}.\n"
        "Amounts are in the business's currency; each CSV has one block per currency where relevant.\n"
        "Clearing accounts ('Sales receipts to allocate', 'Payments to allocate') hold money whose cash, MoMo or bank account was not known.\n"
        + (f"Tax rules not yet checked by an accountant: {', '.join(unchecked)}.\n" if unchecked else "All tax rules have been checked.\n")
        + "This pack is prepared from the business's own records and is not an audit.\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pack:
        pack.writestr("README.txt", readme)
        pack.writestr("trial_balance.csv", _csv([{**line, "currency": block["currency"]} for block in trial["currencies"] for line in block["lines"]], ["currency", "code", "name", "type", "debit", "credit"]))
        pack.writestr("profit_and_loss.csv", _csv([{"currency": b["currency"], "section": section, **line} for b in pnl["currencies"] for section in ("income", "expenses") for line in b[section]], ["currency", "section", "code", "name", "amount"]))
        pack.writestr("balance_sheet.csv", _csv([{"currency": b["currency"], "section": section, **line} for b in sheet["currencies"] for section in ("assets", "liabilities", "equity") for line in b[section]], ["currency", "section", "code", "name", "amount"]))
        pack.writestr("journal.csv", _csv(journal_rows, list(journal_rows[0].keys()) if journal_rows else ["Date"]))
        pack.writestr("debtors.csv", _csv([d for d in book["debts"] if d["direction"] == "owed_to_us" and d["status"] == "open"], ["party_name", "description", "issued_on", "due_on", "amount", "paid", "balance", "age"]))
        pack.writestr("creditors.csv", _csv([d for d in book["debts"] if d["direction"] == "we_owe" and d["status"] == "open"], ["party_name", "description", "issued_on", "due_on", "amount", "paid", "balance", "age"]))
        pack.writestr("stock_valuation.csv", _csv(stock, ["name", "unit", "quantity_on_hand", "unit_cost", "value"]))
    return buffer.getvalue()


def my_data(path: Path, business_id: str) -> bytes:
    """Everything this business has in Ferlance, as CSVs (the owner's own copy)."""
    ledger.catch_up(path, business_id)
    tables = exports.tables(business_id)
    book = debts.book(path, business_id)
    from . import invoices  # imported here: invoices imports ledger at module level

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as pack:
        pack.writestr("README.txt", f"All records of this business in Ferlance, exported on {date.today().isoformat()}. One CSV per kind of record.\n")
        for name, rows in tables.items():
            pack.writestr(f"{name}.csv", _csv(rows, [column for column, _ in exports.SCHEMAS[name]]))
        pack.writestr("journal.csv", ledger.journal_csv(path, business_id))
        pack.writestr("debts.csv", _csv(book["debts"], ["direction", "party_name", "phone", "description", "issued_on", "due_on", "amount", "paid", "balance", "status"]))
        pack.writestr("invoices.csv", _csv(invoices.listing(path, business_id), ["number", "kind", "customer_name", "issued_on", "due_on", "net", "tax", "total", "paid", "status"]))
    return buffer.getvalue()
