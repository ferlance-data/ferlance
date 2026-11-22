"""The debt book (PRD §9, G2): who owes the business, and whom the business owes.

The paper notebook by the till, made quick: a credit sale or a supplier credit in a few taps,
part-payments, ageing, and suggested matches between incoming MoMo messages and open debts.

Every debt and payment is posted to the ledger (``ledger._catch_up_debts``), so the debt book's
totals equal the ledger's receivables and payables. Nothing is ever deleted: a mistake is voided,
which reverses its ledger entries, and the void is kept with who did it.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from . import dataset_store, db, ledger

DIRECTIONS = {"owed_to_us": "customer", "we_owe": "supplier"}
BASES = {"owed_to_us": ("new_sale", "recorded_sale"), "we_owe": ("recorded_purchase", "expense")}
METHODS = ("cash", "momo_mtn", "momo_telecel", "momo_at", "momo_other", "bank")
BUCKETS = ("not_due", "1_30", "31_60", "61_90", "over_90")


class DebtError(ValueError):
    status = 400


class NotFound(DebtError):
    status = 404


def phone_digits(phone: str) -> str:
    """A Ghana phone number in international form (233…), or '' when it does not look like one."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10 and digits.startswith("0"):
        digits = "233" + digits[1:]
    return digits if 9 <= len(digits) <= 15 else ""


def _party(conn, business_id: str, kind: str, name: str, phone: str) -> str:
    row = conn.execute("SELECT id, phone FROM debt_parties WHERE business_id = ? AND kind = ? AND name = ? COLLATE NOCASE", (business_id, kind, name)).fetchone()
    if row:
        if phone and phone != row["phone"]:
            conn.execute("UPDATE debt_parties SET phone = ? WHERE id = ?", (phone, row["id"]))
        return row["id"]
    party_id = str(uuid.uuid4())
    conn.execute("INSERT INTO debt_parties (id, business_id, kind, name, phone, created_at) VALUES (?, ?, ?, ?, ?, ?)", (party_id, business_id, kind, name, phone, db.now()))
    return party_id


def create_debt(path: Path, business_id: str, user_id: str, *, direction: str, party_name: str, phone: str, description: str, amount: float, issued_on: date, due_on: date | None, basis: str) -> dict[str, Any]:
    if direction not in DIRECTIONS:
        raise DebtError("Choose who owes whom.")
    if basis not in BASES[direction]:
        raise DebtError("Choose what this debt is for.")
    name = " ".join(party_name.split())
    if not name:
        raise DebtError("Enter a name.")
    amount_minor = ledger.to_minor(amount)
    if amount_minor <= 0:
        raise DebtError("The amount must be more than zero.")
    if due_on and due_on < issued_on:
        raise DebtError("The due date cannot be before the debt started.")
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        currency = ledger._currency(conn, business_id)
        party_id = _party(conn, business_id, DIRECTIONS[direction], name, phone.strip())
        debt_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO debts (id, business_id, party_id, direction, basis, description, amount_minor, currency, issued_on, due_on, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (debt_id, business_id, party_id, direction, basis, description.strip(), amount_minor, currency, issued_on.isoformat(), due_on.isoformat() if due_on else None, user_id, db.now()),
        )
    ledger.catch_up(path, business_id, user_id)
    return {"id": debt_id}


def _balance(conn, debt_id: str) -> int:
    row = conn.execute(
        "SELECT d.amount_minor - COALESCE((SELECT SUM(amount_minor) FROM debt_payments WHERE debt_id = d.id AND voided_at IS NULL), 0) AS balance FROM debts d WHERE d.id = ?",
        (debt_id,),
    ).fetchone()
    return row["balance"] if row else 0


def _momo_record(business_id: str, momo_ref: str) -> dict[str, Any] | None:
    dataset_id, _, transaction = momo_ref.partition(":")
    dataset = dataset_store.get(business_id, dataset_id)
    if not dataset or dataset["status"] == "failed" or dataset.get("review_status") == dataset_store.EXCLUDED:
        return None
    try:
        records = dataset_store.read_records(dataset)
    except dataset_store.RecordsUnavailableError:
        return None
    return next((r for r in records if str(r.get("transaction_id")) == transaction and r.get("category") in ("momo_sale_received", "momo_expense_paid")), None)


def add_payment(path: Path, business_id: str, user_id: str, debt_id: str, *, amount: float | None, paid_on: date | None, method: str | None, momo_ref: str | None) -> dict[str, Any]:
    record = None
    if momo_ref:
        record = _momo_record(business_id, momo_ref)
        if not record:
            raise NotFound("That MoMo message was not found in your included imports.")
        amount = float(record["amount"])
        paid_on = date.fromisoformat(str(record["transaction_date"])[:10]) if record.get("transaction_date") else paid_on
        method = "momo_sms"
    if method not in METHODS + ("momo_sms",):
        raise DebtError("Choose how it was paid.")
    if amount is None or paid_on is None:
        raise DebtError("Enter the amount and the date.")
    amount_minor = ledger.to_minor(amount)
    if amount_minor <= 0:
        raise DebtError("The amount must be more than zero.")
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        debt = conn.execute("SELECT * FROM debts WHERE id = ? AND business_id = ?", (debt_id, business_id)).fetchone()
        if not debt:
            raise NotFound("Debt not found.")
        if debt["voided_at"]:
            raise DebtError("This debt was voided.")
        if record and (record["category"] == "momo_sale_received") != (debt["direction"] == "owed_to_us"):
            raise DebtError("That MoMo message goes the other way.")
        if paid_on.isoformat() < debt["issued_on"]:
            raise DebtError("A payment cannot be before the debt started.")
        balance = _balance(conn, debt_id)
        if amount_minor > balance:
            raise DebtError(f"That is more than the {ledger.from_minor(balance):,.2f} still owed.")
        if momo_ref and conn.execute("SELECT 1 FROM debt_payments WHERE business_id = ? AND momo_ref = ? AND voided_at IS NULL", (business_id, momo_ref)).fetchone():
            raise DebtError("That MoMo message is already matched to a payment.")
        payment_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO debt_payments (id, debt_id, business_id, amount_minor, paid_on, method, momo_ref, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (payment_id, debt_id, business_id, amount_minor, paid_on.isoformat(), method, momo_ref, user_id, db.now()),
        )
    ledger.catch_up(path, business_id, user_id)
    return {"id": payment_id, "balance": ledger.from_minor(balance - amount_minor)}


def void_debt(path: Path, business_id: str, user_id: str, debt_id: str) -> None:
    """Void a debt and its payments (their ledger entries are reversed; the rows stay, marked void)."""
    now = db.now()
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("UPDATE debts SET voided_at = ?, voided_by = ? WHERE id = ? AND business_id = ? AND voided_at IS NULL", (now, user_id, debt_id, business_id)).rowcount:
            if not conn.execute("SELECT 1 FROM debts WHERE id = ? AND business_id = ?", (debt_id, business_id)).fetchone():
                raise NotFound("Debt not found.")
            return
        conn.execute("UPDATE debt_payments SET voided_at = ?, voided_by = ? WHERE debt_id = ? AND voided_at IS NULL", (now, user_id, debt_id))
    ledger.catch_up(path, business_id, user_id)


def void_payment(path: Path, business_id: str, user_id: str, payment_id: str) -> None:
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("UPDATE debt_payments SET voided_at = ?, voided_by = ? WHERE id = ? AND business_id = ? AND voided_at IS NULL", (db.now(), user_id, payment_id, business_id)).rowcount:
            if not conn.execute("SELECT 1 FROM debt_payments WHERE id = ? AND business_id = ?", (payment_id, business_id)).fetchone():
                raise NotFound("Payment not found.")
            return
    ledger.catch_up(path, business_id, user_id)


def bucket(due: str, today: date) -> str:
    late = (today - date.fromisoformat(due)).days
    if late <= 0:
        return "not_due"
    return "1_30" if late <= 30 else "31_60" if late <= 60 else "61_90" if late <= 90 else "over_90"


def book(path: Path, business_id: str, today: date | None = None) -> dict[str, Any]:
    """Open and settled debts with balances, ageing per side, and the pay-to details for reminders."""
    today = today or date.today()
    debts = db.many(
        path,
        "SELECT d.id, d.direction, d.basis, d.description, d.amount_minor, d.currency, d.issued_on, d.due_on, d.voided_at, d.created_at, "
        "p.id AS party_id, p.name AS party_name, p.phone, "
        "COALESCE((SELECT SUM(x.amount_minor) FROM debt_payments x WHERE x.debt_id = d.id AND x.voided_at IS NULL), 0) AS paid_minor "
        "FROM debts d JOIN debt_parties p ON p.id = d.party_id WHERE d.business_id = ? ORDER BY d.issued_on DESC, d.created_at DESC",
        (business_id,),
    )
    payments = db.many(
        path,
        "SELECT id, debt_id, amount_minor, paid_on, method, momo_ref, voided_at FROM debt_payments WHERE business_id = ? ORDER BY paid_on, created_at",
        (business_id,),
    )
    by_debt: dict[str, list[dict[str, Any]]] = {}
    for payment in payments:
        by_debt.setdefault(payment["debt_id"], []).append(
            {"id": payment["id"], "amount": ledger.from_minor(payment["amount_minor"]), "paid_on": payment["paid_on"], "method": payment["method"], "from_momo": bool(payment["momo_ref"]), "voided": bool(payment["voided_at"])}
        )
    sides = {direction: {"total": 0, "open": 0, "buckets": dict.fromkeys(BUCKETS, 0)} for direction in DIRECTIONS}
    rows = []
    for debt in debts:
        balance = 0 if debt["voided_at"] else debt["amount_minor"] - debt["paid_minor"]
        due = debt["due_on"] or debt["issued_on"]
        age = bucket(due, today) if balance > 0 else None
        if balance > 0:
            side = sides[debt["direction"]]
            side["total"] += balance
            side["open"] += 1
            side["buckets"][age] += balance
        rows.append({
            "id": debt["id"], "direction": debt["direction"], "basis": debt["basis"], "description": debt["description"],
            "party_id": debt["party_id"], "party_name": debt["party_name"], "phone": debt["phone"],
            "amount": ledger.from_minor(debt["amount_minor"]), "paid": ledger.from_minor(debt["paid_minor"]), "balance": ledger.from_minor(balance),
            "currency": debt["currency"], "issued_on": debt["issued_on"], "due_on": debt["due_on"], "age": age,
            "status": "voided" if debt["voided_at"] else "settled" if balance == 0 else "open",
            "payments": by_debt.get(debt["id"], []),
        })
    settings_row = db.one(path, "SELECT pay_to FROM debt_settings WHERE business_id = ?", (business_id,))
    business = db.one(path, "SELECT name, currency FROM businesses WHERE id = ?", (business_id,)) or {}
    return {
        "today": today.isoformat(),
        "business_name": business.get("name", ""),
        "currency": business.get("currency") or "GHS",
        "pay_to": settings_row["pay_to"] if settings_row else "",
        "totals": {
            direction: {"total": ledger.from_minor(side["total"]), "open": side["open"], "buckets": {k: ledger.from_minor(v) for k, v in side["buckets"].items()}}
            for direction, side in sides.items()
        },
        "debts": rows,
        "parties": db.many(path, "SELECT id, kind, name, phone FROM debt_parties WHERE business_id = ? ORDER BY name COLLATE NOCASE", (business_id,)),
    }


def set_pay_to(path: Path, business_id: str, pay_to: str) -> None:
    db.insert(
        path,
        "INSERT INTO debt_settings (business_id, pay_to, updated_at) VALUES (?, ?, ?) ON CONFLICT(business_id) DO UPDATE SET pay_to = excluded.pay_to, updated_at = excluded.updated_at",
        (business_id, pay_to.strip(), db.now()),
    )


def _name_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z]{3,}", (text or "").casefold()) if token not in {"customer", "mobile", "money", "momo", "payment"}}


def suggestions(path: Path, business_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """MoMo messages that may be payments of open debts: same phone number, or a shared name, and not more than the balance.

    Suggestions only; the owner confirms each one. A message already matched is never suggested again.
    """
    open_debts = [d for d in book(path, business_id)["debts"] if d["status"] == "open"]
    if not open_debts:
        return []
    used = {row["momo_ref"] for row in db.many(path, "SELECT momo_ref FROM debt_payments WHERE business_id = ? AND momo_ref IS NOT NULL AND voided_at IS NULL", (business_id,))}
    found = []
    for dataset in dataset_store.analysable(business_id):
        try:
            records = dataset_store.read_records(dataset)
        except dataset_store.RecordsUnavailableError:
            continue
        for record in records:
            category = record.get("category")
            if category not in ("momo_sale_received", "momo_expense_paid"):
                continue
            ref = f"{dataset['id']}:{record.get('transaction_id')}"
            if ref in used:
                continue
            direction = "owed_to_us" if category == "momo_sale_received" else "we_owe"
            who = str(record.get("customer") or "")
            phone = phone_digits(who)[-9:] if phone_digits(who) else ""
            for debt in open_debts:
                if debt["direction"] != direction or float(record.get("amount") or 0) > debt["balance"]:
                    continue
                if record.get("transaction_date") and str(record["transaction_date"])[:10] < debt["issued_on"]:
                    continue
                debt_phone = phone_digits(debt["phone"])[-9:] if debt["phone"] else ""
                by_phone = bool(phone and debt_phone and phone == debt_phone)
                by_name = bool(_name_tokens(who) & _name_tokens(debt["party_name"]))
                if by_phone or by_name:
                    found.append({
                        "momo_ref": ref, "debt_id": debt["id"], "party_name": debt["party_name"], "balance": debt["balance"],
                        "amount": float(record["amount"]), "date": str(record.get("transaction_date") or "")[:10], "from": who,
                        "reason": "same phone number" if by_phone else "similar name",
                    })
    found.sort(key=lambda item: (item["reason"] != "same phone number", item["date"]))
    return found[:limit]
