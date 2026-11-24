"""Credit-readiness report (PRD §9, G7): the business's track record, in a form a lender can trust.

Every figure comes from the ledger and states how much of it is backed by evidence:
- **statement-matched**: money in that matches a line on an imported MoMo or bank statement;
- **MoMo SMS**: payments pasted from MoMo messages (real messages, but pasted by the owner);
- **self-reported**: everything else (typed in, spreadsheets, notebook pages).
The readiness score is a transparent sum of points with the reason for each, and what would raise
it. It is guidance, never a credit decision.

Sharing is the owner's choice: a share is a **frozen snapshot** (not live access), behind a long
random link that expires and can be revoked, opened by anyone holding the link. Every view is
logged. Only the snapshot is shown: no records, names of customers or line items.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import dataset_store, db, debts, ledger, statements

MONTHS = 12
SHARE_DAYS = (7, 14, 30)


class CreditError(ValueError):
    status = 400


class NotFound(CreditError):
    status = 404


def _months(as_of: date) -> list[str]:
    year, month = as_of.year, as_of.month
    out = []
    for _ in range(MONTHS):
        out.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(out))


def _monthly(conn, business_id: str, first: str, last: str) -> dict[str, dict[str, int]]:
    rows = conn.execute(
        "SELECT substr(e.entry_date, 1, 7) AS month, a.type, a.system_key, SUM(l.amount_minor) AS amount "
        "FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id JOIN ledger_accounts a ON a.id = l.account_id "
        "WHERE e.business_id = ? AND e.status = 'posted' AND e.entry_date BETWEEN ? AND ? AND a.type IN ('income', 'expense') "
        "GROUP BY month, a.type, a.system_key",
        (business_id, first, last),
    ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        block = out.setdefault(row["month"], {"sales": 0, "income": 0, "expenses": 0, "cogs": 0})
        if row["type"] == "income":
            block["income"] += -row["amount"]
            if row["system_key"] == "sales":
                block["sales"] += -row["amount"]
        else:
            block["expenses"] += row["amount"]
            if row["system_key"] == "cogs":
                block["cogs"] += row["amount"]
    return out


def _balance(conn, business_id: str, key: str, as_of: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(l.amount_minor), 0) AS amount FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id JOIN ledger_accounts a ON a.id = l.account_id "
        "WHERE e.business_id = ? AND e.status = 'posted' AND a.system_key = ? AND e.entry_date <= ?",
        (business_id, key, as_of),
    ).fetchone()
    return row["amount"]


def _evidence(path: Path, business_id: str, first: str, last: str) -> dict[str, int]:
    """Money in over the period by how well it is evidenced (pesewas)."""
    matched = 0
    with db.connection(path) as conn:
        accounts = [row["account"] for row in conn.execute("SELECT DISTINCT account FROM statement_lines WHERE business_id = ?", (business_id,))]
    for account in accounts:
        for line in statements.view(path, business_id, account)["lines"]:
            if first <= line["date"] <= last and line["amount"] > 0 and line["status"] in ("matched", "booked") and line["booking"] not in ("owner", "transfer"):
                matched += ledger.to_minor(line["amount"])
    sms = 0
    for dataset in dataset_store.analysable(business_id):
        try:
            records = dataset_store.read_records(dataset)
        except dataset_store.RecordsUnavailableError:
            continue
        for record in records:
            day = str(record.get("transaction_date") or "")[:10]
            if record.get("category") == "momo_sale_received" and first <= day <= last:
                sms += ledger._minor_of(record, "amount")
    return {"statement_matched": matched, "momo_sms": sms}


def build(path: Path, business_id: str, as_of: date | None = None) -> dict[str, Any]:
    as_of = as_of or date.today()
    ledger.catch_up(path, business_id)
    months = _months(as_of)
    first, last = f"{months[0]}-01", as_of.isoformat()
    with db.connection(path) as conn:
        monthly = _monthly(conn, business_id, first, last)
        settings = ledger.settings(conn, business_id)
        inventory_start = _balance(conn, business_id, "inventory", (date.fromisoformat(first) - timedelta(days=1)).isoformat())
        inventory_end = _balance(conn, business_id, "inventory", last)
        business = conn.execute("SELECT name, currency FROM businesses WHERE id = ?", (business_id,)).fetchone()
        reconciled_accounts = conn.execute("SELECT COUNT(DISTINCT account) AS n FROM statement_lines WHERE business_id = ?", (business_id,)).fetchone()["n"]
    series = [{"month": m, **{k: ledger.from_minor(v) for k, v in monthly.get(m, {"sales": 0, "income": 0, "expenses": 0, "cogs": 0}).items()},
               "profit": ledger.from_minor(monthly.get(m, {}).get("income", 0) - monthly.get(m, {}).get("expenses", 0))} for m in months]
    active = [m for m in months if monthly.get(m, {}).get("sales", 0) > 0]
    sales = sum(monthly.get(m, {}).get("sales", 0) for m in months)
    income = sum(monthly.get(m, {}).get("income", 0) for m in months)
    expenses = sum(monthly.get(m, {}).get("expenses", 0) for m in months)
    cogs = sum(monthly.get(m, {}).get("cogs", 0) for m in months)
    evidence = _evidence(path, business_id, first, last)
    matched = min(evidence["statement_matched"], sales)
    sms = min(evidence["momo_sms"], max(sales - matched, 0))
    self_reported = max(sales - matched - sms, 0)
    book = debts.book(path, business_id, as_of)
    receivables = book["totals"]["owed_to_us"]
    late_90 = receivables["buckets"]["61_90"] + receivables["buckets"]["over_90"]
    average_stock = (inventory_start + inventory_end) / 2
    turnover = round(cogs / average_stock, 1) if average_stock > 0 and cogs > 0 else None
    active_sales = [monthly[m]["sales"] for m in active]
    steadiness = None
    if len(active_sales) >= 3:
        mean = sum(active_sales) / len(active_sales)
        spread = (sum((v - mean) ** 2 for v in active_sales) / len(active_sales)) ** 0.5
        steadiness = round(1 - min(spread / mean, 1), 2) if mean else None

    facts = {
        "months_with_sales": len(active),
        "sales": ledger.from_minor(sales),
        "net_profit": ledger.from_minor(income - expenses),
        "net_margin_pct": round((income - expenses) / income * 100, 1) if income else None,
        "gross_margin_pct": round((sales - cogs) / sales * 100, 1) if sales and cogs else None,
        "evidence": {"statement_matched": ledger.from_minor(matched), "momo_sms": ledger.from_minor(sms), "self_reported": ledger.from_minor(self_reported),
                     "statement_matched_pct": round(matched / sales * 100, 1) if sales else 0.0, "momo_sms_pct": round(sms / sales * 100, 1) if sales else 0.0},
        "receivables": {"owed": receivables["total"], "late_over_60_days": round(late_90, 2), "late_share_pct": round(late_90 / receivables["total"] * 100, 1) if receivables["total"] else 0.0},
        "stock_turnover": turnover,
        "sales_steadiness": steadiness,
        "books_start": settings["books_start"],
        "reconciled_accounts": reconciled_accounts,
    }
    score, parts = _score(facts)
    return {
        "business": business["name"], "currency": business["currency"] or "GHS", "as_of": last, "from": first,
        "monthly": series, "facts": facts, "score": score, "parts": parts,
        "disclaimer": "A summary of the business's own records in Ferlance, with evidence levels shown. It is not a credit decision, an audit or financial advice.",
    }


def _score(facts: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Points out of 100, each with the reason and what would raise it. Deterministic and explained."""
    parts = []

    def add(name: str, points: float, out_of: int, why: str, raise_by: str | None) -> None:
        parts.append({"name": name, "points": round(min(points, out_of)), "out_of": out_of, "why": why, "raise": raise_by})

    months = facts["months_with_sales"]
    add("Track record", months / 12 * 25, 25, f"{months} of the last 12 months have sales in the books.",
        None if months >= 12 else f"Each more month of recorded sales adds about 2 points ({12 - months} to go).")
    share = facts["evidence"]["statement_matched_pct"] + facts["evidence"]["momo_sms_pct"] * 0.5
    add("Evidence", share / 100 * 25, 25,
        f"{facts['evidence']['statement_matched_pct']}% of sales match a MoMo or bank statement; {facts['evidence']['momo_sms_pct']}% come from MoMo messages.",
        None if facts["evidence"]["statement_matched_pct"] >= 90 else "Import your MoMo and bank statements on Reconcile so more sales are matched.")
    margin = facts["net_margin_pct"]
    add("Profitability", 0 if margin is None or margin <= 0 else min(margin, 20) / 20 * 15, 15,
        "No profit recorded yet." if margin is None else f"Net margin over the year: {margin}%.",
        None if margin is not None and margin >= 20 else "Record all costs and keep prices above cost; a steady positive margin raises this.")
    steady = facts["sales_steadiness"]
    add("Steady sales", 0 if steady is None else steady * 15, 15,
        "Needs at least 3 months of sales." if steady is None else f"Month-to-month sales steadiness: {round(steady * 100)}%.",
        None if steady is not None and steady >= 0.8 else "Regular monthly sales records (no gaps) raise this.")
    late = facts["receivables"]["late_share_pct"]
    owed = facts["receivables"]["owed"]
    add("Collecting debts", 10 if not owed else (1 - late / 100) * 10, 10,
        "No customer debts outstanding." if not owed else f"{late}% of what customers owe is over 60 days late.",
        None if not owed or late < 10 else "Chase debts over 60 days (Debt book reminders) or settle them.")
    complete = (5 if facts["books_start"] else 0) + min(facts["reconciled_accounts"], 2) * 2.5
    add("Complete books", complete, 10,
        f"Books start date {'set' if facts['books_start'] else 'not set'}; {facts['reconciled_accounts']} account(s) with statements.",
        None if complete >= 10 else "Set where you stand on day one (Books) and import statements for your MoMo wallet and bank.")
    return sum(part["points"] for part in parts), parts


# ---------------------------------------------------------------- sharing


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def share(path: Path, business_id: str, user_id: str, days: int, lender: str, consent: bool) -> dict[str, Any]:
    if not consent:
        raise CreditError("Tick the box to agree to share this summary.")
    if days not in SHARE_DAYS:
        raise CreditError("Choose 7, 14 or 30 days.")
    report = build(path, business_id)
    token = secrets.token_urlsafe(24)
    code = f"FER-{secrets.randbelow(10**8):08d}"
    report_id = str(uuid.uuid4())
    expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    db.insert(
        path,
        "INSERT INTO credit_shares (id, business_id, created_by, lender, token_hash, code, snapshot, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (report_id, business_id, user_id, lender.strip()[:120], _hash(token), code, json.dumps(report), expires, db.now()),
    )
    return {"id": report_id, "token": token, "code": code, "expires_at": expires}


def shares(path: Path, business_id: str) -> list[dict[str, Any]]:
    rows = db.many(
        path,
        "SELECT s.id, s.lender, s.code, s.expires_at, s.revoked_at, s.created_at, u.email AS created_by, "
        "(SELECT COUNT(*) FROM credit_share_views v WHERE v.share_id = s.id) AS views, (SELECT MAX(viewed_at) FROM credit_share_views v WHERE v.share_id = s.id) AS last_view "
        "FROM credit_shares s LEFT JOIN users u ON u.id = s.created_by WHERE s.business_id = ? ORDER BY s.created_at DESC",
        (business_id,),
    )
    now = db.now()
    return [{**row, "active": not row["revoked_at"] and row["expires_at"] > now} for row in rows]


def revoke(path: Path, business_id: str, share_id: str) -> None:
    with db.connection(path) as conn:
        if not conn.execute("UPDATE credit_shares SET revoked_at = ? WHERE id = ? AND business_id = ? AND revoked_at IS NULL", (db.now(), share_id, business_id)).rowcount:
            if not conn.execute("SELECT 1 FROM credit_shares WHERE id = ? AND business_id = ?", (share_id, business_id)).fetchone():
                raise NotFound("Share not found.")


def open_shared(path: Path, token: str, user_agent: str) -> dict[str, Any]:
    """The frozen snapshot behind a share link, if it is still live. Logs the view."""
    row = db.one(path, "SELECT * FROM credit_shares WHERE token_hash = ?", (_hash(token),))
    if not row or row["revoked_at"] or row["expires_at"] <= db.now():
        raise NotFound("This link has expired or was withdrawn by the business.")
    db.insert(path, "INSERT INTO credit_share_views (id, share_id, viewed_at, user_agent) VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), row["id"], db.now(), user_agent[:200]))
    return {**json.loads(row["snapshot"]), "code": row["code"], "shared_at": row["created_at"], "expires_at": row["expires_at"], "lender": row["lender"]}
