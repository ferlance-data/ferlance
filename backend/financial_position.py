import math
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from . import db

CATEGORIES: dict[str, dict[str, str]] = {
    "cash": {"group": "assets", "label": "Cash on hand"},
    "bank": {"group": "assets", "label": "Cash at bank"},
    "receivables": {"group": "assets", "label": "Accounts receivable"},
    "inventory": {"group": "assets", "label": "Inventory at recorded cost"},
    "fixed_assets": {"group": "assets", "label": "Fixed assets"},
    "other_assets": {"group": "assets", "label": "Other assets"},
    "payables": {"group": "liabilities", "label": "Accounts payable"},
    "loans": {"group": "liabilities", "label": "Loans and borrowings"},
    "other_liabilities": {"group": "liabilities", "label": "Other liabilities"},
    "owner_capital": {"group": "equity", "label": "Owner capital"},
    "retained_earnings": {"group": "equity", "label": "Retained earnings / accumulated loss"},
    "other_equity": {"group": "equity", "label": "Other equity"},
}


class FinancialPositionError(ValueError):
    pass


def record_balance(
    path: Path,
    business_id: str,
    user_id: str,
    category: str,
    account_name: str,
    as_of_date: date,
    amount: float,
    note: str,
) -> dict[str, Any]:
    if category not in CATEGORIES:
        raise FinancialPositionError("Choose a valid financial-position category.")
    account_name = account_name.strip()
    if not account_name:
        raise FinancialPositionError("Account name is required.")
    if len(account_name) > 120:
        raise FinancialPositionError("Account name must be 120 characters or fewer.")
    if not math.isfinite(amount):
        raise FinancialPositionError("Balance must be a finite number.")
    if CATEGORIES[category]["group"] != "equity" and amount < 0:
        raise FinancialPositionError("Asset and liability balances cannot be negative.")
    entry = {
        "id": str(uuid.uuid4()),
        "business_id": business_id,
        "category": category,
        "account_name": account_name,
        "as_of_date": as_of_date.isoformat(),
        "amount": amount,
        "note": note.strip(),
        "user_id": user_id,
        "created_at": db.now(),
    }
    with db.connection(path) as conn:
        conn.execute(
            "INSERT INTO financial_position_balances "
            "(id, business_id, category, account_name, as_of_date, amount, note, user_id, created_at) "
            "VALUES (:id, :business_id, :category, :account_name, :as_of_date, :amount, :note, :user_id, :created_at)",
            entry,
        )
    return entry


def position_as_of(path: Path, business_id: str, as_of_date: date) -> dict[str, Any]:
    balances = db.many(
        path,
        "WITH ranked AS ("
        " SELECT b.category, b.account_name, b.as_of_date, b.amount, b.note, b.created_at, "
        " ROW_NUMBER() OVER ("
        "  PARTITION BY b.category, b.account_name COLLATE NOCASE "
        "  ORDER BY b.as_of_date DESC, b.created_at DESC, b.id DESC"
        " ) AS position"
        " FROM financial_position_balances b"
        " WHERE b.business_id = ? AND b.as_of_date <= ?"
        ") SELECT category, account_name, as_of_date, amount, note, created_at"
        " FROM ranked WHERE position = 1 ORDER BY category, account_name COLLATE NOCASE",
        (business_id, as_of_date.isoformat()),
    )
    grouped: dict[str, list[dict[str, Any]]] = {group: [] for group in ("assets", "liabilities", "equity")}
    category_totals = {category: 0.0 for category in CATEGORIES}
    for item in balances:
        group = CATEGORIES[item["category"]]["group"]
        grouped[group].append(item)
        category_totals[item["category"]] += item["amount"]

    present_categories = {item["category"] for item in balances}
    missing_categories = [
        {"key": key, "label": value["label"], "group": value["group"]}
        for key, value in CATEGORIES.items()
        if key not in present_categories
    ]
    assets = sum(category_totals[key] for key, value in CATEGORIES.items() if value["group"] == "assets")
    liabilities = sum(category_totals[key] for key, value in CATEGORIES.items() if value["group"] == "liabilities")
    equity = sum(category_totals[key] for key, value in CATEGORIES.items() if value["group"] == "equity")
    stale_balances = [
        {"account_name": item["account_name"], "category": item["category"], "as_of_date": item["as_of_date"]}
        for item in balances
        if item["as_of_date"] < as_of_date.isoformat()
    ]
    complete = not missing_categories
    return {
        "as_of_date": as_of_date.isoformat(),
        "assets": grouped["assets"],
        "liabilities": grouped["liabilities"],
        "equity": grouped["equity"],
        "totals": {
            "assets": round(assets, 2),
            "liabilities": round(liabilities, 2),
            "equity": round(equity, 2),
            "liabilities_and_equity": round(liabilities + equity, 2),
            "balance_difference": round(assets - liabilities - equity, 2),
            "complete": complete,
            "balanced": complete and math.isclose(assets, liabilities + equity, abs_tol=0.01),
        },
        "missing_categories": missing_categories,
        "stale_balances": stale_balances,
        "warnings": [
            "This statement uses the latest balance entered on or before the report date for each account."
        ] + (
            ["Some required balance categories are missing; totals are partial and must not be treated as a complete balance sheet."]
            if missing_categories
            else []
        ) + (
            ["Some balances are carried forward from earlier dates; update them if the account changed before this report date."]
            if stale_balances
            else []
        ),
    }


def balance_history(path: Path, business_id: str, limit: int = 200) -> list[dict[str, Any]]:
    return db.many(
        path,
        "SELECT b.id, b.category, b.account_name, b.as_of_date, b.amount, b.note, "
        "b.created_at, u.email AS recorded_by "
        "FROM financial_position_balances b JOIN users u ON u.id = b.user_id "
        "WHERE b.business_id = ? ORDER BY b.as_of_date DESC, b.created_at DESC LIMIT ?",
        (business_id, limit),
    )
