"""The quiet ledger: double-entry books built from what the business already records (PRD §9, G1).

Owners never see debits and credits. Every import, MoMo SMS and stock movement is turned into
balanced journal entries by a small set of posting rules, and the books' reports read only the
ledger. The accountant role sees the journal, the chart of accounts and the period lock.

Storage
-------
- Amounts are integer pesewas (``amount_minor``; debits positive, credits negative), per currency.
- The database enforces double entry (see the triggers in ``db.SCHEMA``): an entry can only become
  ``posted`` with two or more lines that sum to zero in every currency, and posted entries and
  their lines can never be updated or deleted. Corrections are reversing entries.

Sources
-------
Each origin has a source key (``dataset:<id>``, ``movement:<id>``, ``opening``, ``manual:<id>``).
``_sync`` makes the ledger's net for a key equal the lines its rule wants now: it reverses what is
there and posts the new lines, never deleting. ``catch_up`` re-syncs any source whose fingerprint
changed (an import included or excluded, a file posted to stock, the books start date moved), so
the books can be rebuilt idempotently for businesses that existed before the ledger.

Posting rules (each has a test)
-------------------------------
- Sales lines: receipt account by payment channel (cash, a MoMo wallet, bank), else
  *Sales receipts to allocate*; credit Sales. Negative amounts are refunds (the reverse).
- MoMo SMS: ``momo_sale_received`` → wallet / Sales; ``momo_expense_paid`` → *Expenses to
  categorise* / wallet. (Analytics counts the latter as revenue today; the differences check names it.)
- Cost on a sales line → Cost of goods sold / *Payments to allocate*, unless the file was posted to
  stock, in which case cost of goods sold comes from the stock movements only (no double count).
- Cost-only files (expenses) → an expense account chosen from the line's words / *Payments to allocate*.
- Stock: purchases → Inventory / *Payments to allocate*; sales → Cost of goods sold / Inventory;
  stocktakes and adjustments → Inventory / *Stock losses* (either direction); opening stock →
  Inventory / Opening balance equity. Valued at the movement's unit cost, else the product's; a
  movement with no cost is listed as an issue, never posted at zero. A value, once posted, is kept.
- Books start date: records dated before it stay in analytics only; stock movements before it
  post against Opening balance equity, so opening inventory equals the stock ledger's value.
- Undated records are booked on the day the file was imported, and listed as an issue.
- A posting dated inside a locked period is moved to the first open day.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Iterable

from . import analytics, dataset_store, db

TYPES = ("asset", "liability", "equity", "income", "expense")
# (system key, code, name, type)
DEFAULT_ACCOUNTS: tuple[tuple[str, str, str, str], ...] = (
    ("cash", "1000", "Cash on hand", "asset"),
    ("momo_mtn", "1010", "MTN Mobile Money", "asset"),
    ("momo_telecel", "1011", "Telecel Cash", "asset"),
    ("momo_at", "1012", "AT Money", "asset"),
    ("momo_other", "1013", "Mobile money (network not known)", "asset"),
    ("bank", "1020", "Bank", "asset"),
    ("receipts_clearing", "1090", "Sales receipts to allocate", "asset"),
    ("receivables", "1100", "Customers owe you (receivables)", "asset"),
    ("inventory", "1200", "Stock (inventory)", "asset"),
    ("fixed_assets", "1500", "Equipment and other fixed assets", "asset"),
    ("other_assets", "1900", "Other assets", "asset"),
    ("payables", "2000", "You owe suppliers (payables)", "liability"),
    ("payments_clearing", "2090", "Payments to allocate", "liability"),
    ("tax_payable", "2100", "VAT and levies payable", "liability"),
    ("loans", "2200", "Loans", "liability"),
    ("other_liabilities", "2900", "Other liabilities", "liability"),
    ("owner_capital", "3000", "Owner capital", "equity"),
    ("drawings", "3100", "Owner drawings", "equity"),
    ("retained_earnings", "3200", "Retained earnings", "equity"),
    ("opening_equity", "3300", "Opening balance equity", "equity"),
    ("other_equity", "3900", "Other equity", "equity"),
    ("sales", "4000", "Sales", "income"),
    ("other_income", "4900", "Other income", "income"),
    ("cogs", "5000", "Cost of goods sold", "expense"),
    ("shrinkage", "5100", "Stock losses and count differences", "expense"),
    ("rent", "6000", "Rent", "expense"),
    ("transport", "6010", "Transport and fuel", "expense"),
    ("airtime", "6020", "Data and airtime", "expense"),
    ("utilities", "6030", "Electricity and water", "expense"),
    ("wages", "6040", "Wages", "expense"),
    ("charges", "6050", "MoMo and bank charges", "expense"),
    ("uncategorised", "6900", "Expenses to categorise", "expense"),
)
CASH_KEYS = ("cash", "momo_mtn", "momo_telecel", "momo_at", "momo_other", "bank")
EXPENSE_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rent", ("rent", "lease")),
    ("transport", ("transport", "fuel", "petrol", "diesel", "trotro", "taxi", "uber", "bolt", "delivery", "freight")),
    ("airtime", ("airtime", "data bundle", "bundle", "internet", "credit top")),
    ("utilities", ("electric", "ecg", "prepaid", "water", "gwcl", "utility", "utilities")),
    ("wages", ("wage", "salary", "salaries", "payroll", "staff pay", "labour", "labor")),
    ("charges", ("charge", "e-levy", "elevy", "momo fee", "bank fee", "commission")),
)
# Financial-position categories → account; a cash-category account named like a wallet goes to that wallet.
POSITION_ACCOUNTS = {
    "cash": "cash", "bank": "bank", "receivables": "receivables", "inventory": "inventory",
    "fixed_assets": "fixed_assets", "other_assets": "other_assets", "payables": "payables", "loans": "loans",
    "other_liabilities": "other_liabilities", "owner_capital": "owner_capital",
    "retained_earnings": "retained_earnings", "other_equity": "other_equity",
}
RULES_VERSION = "1"


class LedgerError(ValueError):
    pass


# ---------------------------------------------------------------- basics


def to_minor(value: float | int | str) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_minor(value: int) -> float:
    return round(value / 100, 2)


def ensure_accounts(conn, business_id: str) -> dict[str, str]:
    """The business's accounts by system key (seeding the default chart on first use)."""
    rows = conn.execute("SELECT id, system_key FROM ledger_accounts WHERE business_id = ? AND system_key IS NOT NULL", (business_id,)).fetchall()
    found = {row["system_key"]: row["id"] for row in rows}
    for key, code, name, kind in DEFAULT_ACCOUNTS:
        if key in found:
            continue
        account_id = str(uuid.uuid4())
        conn.execute(
            "INSERT OR IGNORE INTO ledger_accounts (id, business_id, code, name, type, system_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (account_id, business_id, code, name, kind, key, db.now()),
        )
        row = conn.execute("SELECT id FROM ledger_accounts WHERE business_id = ? AND system_key = ?", (business_id, key)).fetchone()
        if row is None:  # the code was taken by an accountant's own account: give the default a free code
            conn.execute(
                "INSERT INTO ledger_accounts (id, business_id, code, name, type, system_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (account_id, business_id, f"{code}-{account_id[:4]}", name, kind, key, db.now()),
            )
            row = {"id": account_id}
        found[key] = row["id"]
    return found


def settings(conn, business_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT books_start, lock_date FROM ledger_settings WHERE business_id = ?", (business_id,)).fetchone()
    return dict(row) if row else {"books_start": None, "lock_date": None}


def _set_setting(conn, business_id: str, **values: Any) -> None:
    current = settings(conn, business_id)
    current.update(values)
    conn.execute(
        "INSERT INTO ledger_settings (business_id, books_start, lock_date, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(business_id) DO UPDATE SET books_start = excluded.books_start, lock_date = excluded.lock_date, updated_at = excluded.updated_at",
        (business_id, current["books_start"], current["lock_date"], db.now()),
    )


def _currency(conn, business_id: str) -> str:
    row = conn.execute("SELECT currency FROM businesses WHERE id = ?", (business_id,)).fetchone()
    return (row["currency"] if row and row["currency"] else "GHS").upper()


def _open_day(day: str, lock_date: str | None) -> str:
    if lock_date and day <= lock_date:
        return (date.fromisoformat(lock_date) + timedelta(days=1)).isoformat()
    return day


Line = tuple[str, str, int, str]  # account id, currency, amount_minor (debit +), description


def _post(conn, business_id: str, day: str, memo: str, source_key: str, kind: str, lines: Iterable[Line], user_id: str | None) -> str | None:
    merged: dict[tuple[str, str, str], int] = defaultdict(int)
    for account_id, currency, amount, description in lines:
        merged[(account_id, currency, description)] += amount
    kept = [(key, amount) for key, amount in merged.items() if amount]
    if not kept:
        return None
    entry_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO journal_entries (id, business_id, entry_date, memo, source_key, kind, status, user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?)",
        (entry_id, business_id, day, memo[:300], source_key, kind, user_id, db.now()),
    )
    for (account_id, currency, description), amount in kept:
        conn.execute(
            "INSERT INTO journal_lines (id, entry_id, business_id, account_id, currency, amount_minor, description) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), entry_id, business_id, account_id, currency, amount, description[:300]),
        )
    conn.execute("UPDATE journal_entries SET status = 'posted' WHERE id = ?", (entry_id,))  # the trigger checks the balance
    return entry_id


def _net(conn, business_id: str, source_key: str) -> dict[tuple[str, str, str], int]:
    rows = conn.execute(
        "SELECT e.entry_date, l.account_id, l.currency, SUM(l.amount_minor) AS amount FROM journal_lines l "
        "JOIN journal_entries e ON e.id = l.entry_id WHERE e.business_id = ? AND e.source_key = ? AND e.status = 'posted' "
        "GROUP BY e.entry_date, l.account_id, l.currency",
        (business_id, source_key),
    ).fetchall()
    return {(row["entry_date"], row["account_id"], row["currency"]): row["amount"] for row in rows if row["amount"]}


Posting = tuple[str, str, list[Line]]  # day, memo, lines


def _sync(conn, business_id: str, source_key: str, fingerprint: str, desired: list[Posting], issues: list[str], user_id: str | None, kind: str = "auto") -> bool:
    """Make the ledger's net for ``source_key`` equal ``desired``. Append-only: reverse, then repost."""
    lock = settings(conn, business_id)["lock_date"]
    desired = [(_open_day(day, lock), memo, lines) for day, memo, lines in desired]
    want: dict[tuple[str, str, str], int] = defaultdict(int)
    for day, _, lines in desired:
        for account_id, currency, amount, _ in lines:
            want[(day, account_id, currency)] += amount
    want = {key: amount for key, amount in want.items() if amount}
    current = _net(conn, business_id, source_key)
    changed = current != want
    if changed:
        by_day: dict[str, list[Line]] = defaultdict(list)
        for (day, account_id, currency), amount in current.items():
            by_day[_open_day(day, lock)].append((account_id, currency, -amount, "Reversal"))
        for day, lines in sorted(by_day.items()):
            _post(conn, business_id, day, f"Reversal: {source_key}", source_key, "reversal", lines, user_id)
        for day, memo, lines in desired:
            _post(conn, business_id, day, memo, source_key, kind, lines, user_id)
    conn.execute(
        "INSERT INTO ledger_sources (business_id, source_key, fingerprint, issues, synced_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(business_id, source_key) DO UPDATE SET fingerprint = excluded.fingerprint, issues = excluded.issues, synced_at = excluded.synced_at",
        (business_id, source_key, fingerprint, json.dumps(issues), db.now()),
    )
    return changed


# ---------------------------------------------------------------- posting rules


def _words(record: dict[str, Any], *keys: str) -> str:
    return " ".join(str(record.get(key) or "") for key in keys).casefold()


def _wallet(text: str) -> str | None:
    if any(word in text for word in ("telecel", "vodafone", "voda cash")):
        return "momo_telecel"
    if any(word in text for word in ("airteltigo", "at money", "tigo")):
        return "momo_at"
    if any(word in text for word in ("mtn", "momo", "mobile money")):
        # Ghanaians say "momo" for MTN Mobile Money; a bare "mobile money" names no network.
        return "momo_mtn" if ("mtn" in text or "momo" in text) else "momo_other"
    return None


def receipt_account(record: dict[str, Any]) -> str:
    """Where money from a sale went, from the line's payment words. Unknown → the receipts clearing account."""
    channel = _words(record, "channel", "payment_method", "payment", "method", "mode", "category")
    if record.get("category") in ("momo_sale_received", "momo_expense_paid"):
        return _wallet(_words(record, "channel")) or "momo_other"
    wallet = _wallet(channel)
    if wallet:
        return wallet
    if re.search(r"\bcash\b", channel):
        return "cash"
    if any(word in channel for word in ("bank", "card", "transfer", "cheque", "pos")):
        return "bank"
    return "receipts_clearing"


def expense_account(record: dict[str, Any]) -> str:
    text = _words(record, "category", "product", "vendor", "record_id")
    for key, words in EXPENSE_WORDS:
        if any(word in text for word in words):
            return key
    return "uncategorised"


def _record_day(record: dict[str, Any], fallback: str) -> tuple[str, bool]:
    value = str(record.get("transaction_date") or "")[:10]
    try:
        return date.fromisoformat(value).isoformat(), True
    except ValueError:
        return fallback, False


def _minor_of(record: dict[str, Any], field: str) -> int:
    value = record.get(field)
    return to_minor(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def record_rule(record: dict[str, Any], domain: str) -> str:
    """Which posting rule a line follows: 'momo_expense', 'expense' or 'sale'. Shared with the differences check."""
    if record.get("category") == "momo_expense_paid":
        return "momo_expense"
    if domain == "cost" or (not _minor_of(record, "amount") and _minor_of(record, "cost") > 0):
        return "expense"  # cost-only files, and cost-only lines inside a sales file (e.g. rent)
    return "sale"


def _stock_posted_lines(conn, business_id: str) -> Any:
    """A test for 'this line became a stock movement when its file was posted' (mirrors sync.post_dataset)."""
    from . import sync

    link_map = {row["sales_name_norm"]: row["product_id"] for row in conn.execute("SELECT sales_name_norm, product_id FROM product_links WHERE business_id = ?", (business_id,))}
    by_name = {sync._norm(row["name"]): dict(row) for row in conn.execute("SELECT id, name FROM inventory_products WHERE business_id = ?", (business_id,))}

    def posted(record: dict[str, Any]) -> bool:
        name = str(record.get("product") or "").strip()
        if not name or float(record.get("amount") or 0) <= 0 or record.get("quantity") is None:
            return False
        return sync.resolve(name, link_map, by_name) is not None

    return posted


def dataset_postings(conn, business_id: str, dataset: dict[str, Any], accounts: dict[str, str], books_start: str | None) -> tuple[list[Posting], list[str]]:
    if dataset["status"] == "failed" or dataset.get("review_status") == dataset_store.EXCLUDED:
        return [], []
    try:
        records = dataset_store.read_records(dataset)
    except dataset_store.RecordsUnavailableError as error:
        return [], [str(error)]
    stocked = conn.execute("SELECT status FROM dataset_stock_posts WHERE dataset_id = ?", (dataset["id"],)).fetchone()
    in_stock = _stock_posted_lines(conn, business_id) if stocked and stocked["status"] == "posted" else None
    profile = analytics._data_profile(analytics._present([dict(r) for r in records]))
    default_currency = _currency(conn, business_id)
    imported_day = str(dataset["created_at"])[:10]
    by_day: dict[str, list[Line]] = defaultdict(list)
    undated = before_start = cost_from_stock = 0
    name = dataset["filename"]
    for record in records:
        day, dated = _record_day(record, imported_day)
        if not dated:
            undated += 1
        if books_start and day < books_start:
            before_start += 1
            continue
        currency = str(record.get("currency") or default_currency).upper()
        amount, cost = _minor_of(record, "amount"), _minor_of(record, "cost")
        label = str(record.get("product") or record.get("customer") or name)[:120]
        lines = by_day[day]
        rule = record_rule(record, profile["domain"])
        if rule == "momo_expense":
            wallet = accounts[receipt_account(record)]
            lines += [(accounts["uncategorised"], currency, amount, label), (wallet, currency, -amount, label)]
            continue
        if rule == "expense":
            expense = accounts[expense_account(record)]
            lines += [(expense, currency, cost, label), (accounts["payments_clearing"], currency, -cost, label)]
            continue
        receipt = accounts[receipt_account(record)]
        lines += [(receipt, currency, amount, label), (accounts["sales"], currency, -amount, label)]
        if cost:
            if in_stock and in_stock(record):  # its cost is booked by the stock movement instead
                cost_from_stock += 1
            else:
                lines += [(accounts["cogs"], currency, cost, label), (accounts["payments_clearing"], currency, -cost, label)]
    issues = []
    if undated:
        issues.append(f"{undated} line(s) in {name} have no date and are booked on the import day, {imported_day}.")
    if before_start:
        issues.append(f"{before_start} line(s) in {name} are before your books start and are in analytics only.")
    if cost_from_stock:
        issues.append(f"Costs of {cost_from_stock} line(s) in {name} come from stock, because those sales were posted to stock.")
    postings = [(day, f"Sales and costs from {name}", lines) for day, lines in sorted(by_day.items())]
    return postings, issues


def movement_postings(conn, business_id: str, movement: dict[str, Any], accounts: dict[str, str], books_start: str | None, posted_value: int | None) -> tuple[list[Posting], list[str]]:
    day = str(movement["created_at"])[:10]
    quantity = float(movement["quantity_delta"])
    if posted_value is not None:  # once valued, a movement keeps the value it was posted at
        value = posted_value
    else:
        unit_cost = movement["unit_cost"] if movement["unit_cost"] is not None else movement["product_cost"]
        if unit_cost is None:
            return [], [f"{movement['product_name']}: a {movement['movement_type']} of {abs(quantity):g} has no unit cost, so it is not in the books yet."]
        value = abs(to_minor(abs(quantity) * float(unit_cost)))
    if not value:
        return [], []
    currency = _currency(conn, business_id)
    label = f"{movement['product_name']} ({movement['movement_type']})"
    inventory = accounts["inventory"]
    kind = movement["movement_type"]
    if kind == "opening" or (books_start and day < books_start):
        counter = accounts["opening_equity"]
    elif kind == "purchase":
        counter = accounts["payments_clearing"]
    elif kind == "sale" or str(movement["source"]).startswith("sales-reversal:"):
        counter = accounts["cogs"]  # a file's stock sales, and their reversal when the file is left out
    else:  # adjustment, stocktake
        counter = accounts["shrinkage"]
    signed = value if quantity > 0 else -value
    return [(day, label, [(inventory, currency, signed, label), (counter, currency, -signed, label)])], []


# ---------------------------------------------------------------- catch-up


def _fingerprints(conn, business_id: str) -> dict[str, str]:
    return {row["source_key"]: row["fingerprint"] for row in conn.execute("SELECT source_key, fingerprint FROM ledger_sources WHERE business_id = ?", (business_id,))}


def catch_up(path: Path, business_id: str, user_id: str | None = None) -> int:
    """Bring the ledger up to date with every import and stock movement. Returns sources re-synced."""
    changed = 0
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        accounts = ensure_accounts(conn, business_id)
        start = settings(conn, business_id)["books_start"]
        known = _fingerprints(conn, business_id)
        datasets = conn.execute(
            "SELECT d.*, p.status AS stock_status FROM datasets d LEFT JOIN dataset_stock_posts p ON p.dataset_id = d.id WHERE d.business_id = ?",
            (business_id,),
        ).fetchall()
        for row in datasets:
            dataset = dict(row)
            fingerprint = f"{RULES_VERSION}:{start}:{dataset['status']}:{dataset.get('review_status')}:{dataset['stock_status']}"
            key = f"dataset:{dataset['id']}"
            if known.get(key) == fingerprint:
                continue
            postings, issues = dataset_postings(conn, business_id, dataset, accounts, start)
            changed += _sync(conn, business_id, key, fingerprint, postings, issues, user_id)
        movements = conn.execute(
            "SELECT m.*, p.name AS product_name, p.unit_cost AS product_cost FROM inventory_movements m "
            "JOIN inventory_products p ON p.id = m.product_id WHERE m.business_id = ?",
            (business_id,),
        ).fetchall()
        for row in movements:
            movement = dict(row)
            key = f"movement:{movement['id']}"
            previous = known.get(key)
            if previous and previous.startswith(f"{RULES_VERSION}:{start}:valued"):
                continue
            posted = _net(conn, business_id, key)
            posted_value = abs(sum(amount for (_, account, _), amount in posted.items() if account == accounts["inventory"])) or None
            postings, issues = movement_postings(conn, business_id, movement, accounts, start, posted_value)
            state = "valued" if postings or (not issues) else "unvalued"
            fingerprint = f"{RULES_VERSION}:{start}:{state}"
            if previous == fingerprint:
                continue
            changed += _sync(conn, business_id, key, fingerprint, postings, issues, user_id)
    return changed


# ---------------------------------------------------------------- opening balances


def proposed_opening(path: Path, business_id: str, start: date) -> dict[str, Any]:
    """Opening balances suggested from the financial-position snapshots (latest on or before the start)."""
    from . import financial_position

    position = financial_position.position_as_of(path, business_id, start)
    has_stock = db.one(path, "SELECT 1 FROM inventory_movements WHERE business_id = ? LIMIT 1", (business_id,)) is not None
    lines, notes = [], []
    for group in ("assets", "liabilities", "equity"):
        for item in position[group]:
            if item["category"] == "inventory" and has_stock:
                notes.append(f"Stock comes from your stock records, so the '{item['account_name']}' balance is not used.")
                continue
            key = POSITION_ACCOUNTS[item["category"]]
            if item["category"] == "cash":
                key = _wallet(item["account_name"].casefold()) or key
            lines.append({"account": key, "account_name": item["account_name"], "category": item["category"], "amount": item["amount"], "as_of_date": item["as_of_date"]})
    return {"start_date": start.isoformat(), "lines": lines, "notes": notes}


def confirm_opening(path: Path, business_id: str, start: date, lines: list[dict[str, Any]], user_id: str) -> dict[str, Any]:
    """Set the books start date and post opening balances; everything is re-synced to the new start."""
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        accounts = ensure_accounts(conn, business_id)
        lock = settings(conn, business_id)["lock_date"]
        if lock and start.isoformat() <= lock:
            raise LedgerError("The books start date is inside a locked period.")
        types = {key: kind for key, _, _, kind in DEFAULT_ACCOUNTS}
        currency = _currency(conn, business_id)
        posting: list[Line] = []
        for line in lines:
            key = line["account"]
            if key not in accounts or key == "opening_equity" or types.get(key) not in ("asset", "liability", "equity"):
                raise LedgerError(f"Unknown opening account: {key}.")
            amount = to_minor(line["amount"])
            debit = amount if types[key] == "asset" else -amount
            label = str(line.get("account_name") or key)[:120]
            posting += [(accounts[key], currency, debit, label), (accounts["opening_equity"], currency, -debit, label)]
        _set_setting(conn, business_id, books_start=start.isoformat())
        # Opening balances sit on the day before the books start.
        day = (start - timedelta(days=1)).isoformat()
        _sync(conn, business_id, "opening", f"{start.isoformat()}", [(day, "Opening balances", posting)], [], user_id, kind="opening")
    catch_up(path, business_id, user_id)
    return {"books_start": start.isoformat()}


# ---------------------------------------------------------------- accountant tools


def manual_journal(path: Path, business_id: str, day: date, memo: str, lines: list[dict[str, Any]], user_id: str) -> str:
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        ensure_accounts(conn, business_id)
        lock = settings(conn, business_id)["lock_date"]
        if lock and day.isoformat() <= lock:
            raise LedgerError(f"The books are locked up to {lock}.")
        currency = _currency(conn, business_id)
        posting: list[Line] = []
        for line in lines:
            account = conn.execute("SELECT id FROM ledger_accounts WHERE id = ? AND business_id = ? AND active = 1", (line["account_id"], business_id)).fetchone()
            if not account:
                raise LedgerError("Account not found.")
            debit, credit = to_minor(line.get("debit") or 0), to_minor(line.get("credit") or 0)
            if debit < 0 or credit < 0 or bool(debit) == bool(credit):
                raise LedgerError("Each line needs a debit or a credit, not both.")
            posting.append((account["id"], str(line.get("currency") or currency).upper(), debit - credit, str(line.get("description") or "")))
        totals: dict[str, int] = defaultdict(int)
        for _, cur, amount, _ in posting:
            totals[cur] += amount
        if len(posting) < 2 or any(totals.values()):
            raise LedgerError("Debits and credits must be equal.")
        entry_key = f"manual:{uuid.uuid4()}"
        entry_id = _post(conn, business_id, day.isoformat(), memo, entry_key, "manual", posting, user_id)
        assert entry_id
        return entry_id


def set_lock(path: Path, business_id: str, lock_date: date | None, user_id: str) -> None:
    """Move or clear the period lock. Every change is logged with who made it (reopening a period is visible)."""
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if lock_date and lock_date > date.today():
            raise LedgerError("You can only lock days that have passed.")
        before = settings(conn, business_id)["lock_date"]
        after = lock_date.isoformat() if lock_date else None
        if before == after:
            return
        _set_setting(conn, business_id, lock_date=after)
        conn.execute(
            "INSERT INTO ledger_lock_log (id, business_id, user_id, before_date, after_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), business_id, user_id, before, after, db.now()),
        )


def lock_history(path: Path, business_id: str, limit: int = 10) -> list[dict[str, Any]]:
    return db.many(
        path,
        "SELECT g.before_date, g.after_date, g.created_at, u.email AS user_email FROM ledger_lock_log g LEFT JOIN users u ON u.id = g.user_id "
        "WHERE g.business_id = ? ORDER BY g.created_at DESC LIMIT ?",
        (business_id, limit),
    )


def add_account(path: Path, business_id: str, code: str, name: str, kind: str) -> dict[str, Any]:
    if kind not in TYPES:
        raise LedgerError("Choose a valid account type.")
    with db.connection(path) as conn:
        ensure_accounts(conn, business_id)
        if conn.execute("SELECT 1 FROM ledger_accounts WHERE business_id = ? AND code = ?", (business_id, code)).fetchone():
            raise LedgerError("That account code is already used.")
        account_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO ledger_accounts (id, business_id, code, name, type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (account_id, business_id, code, name, kind, db.now()),
        )
    return {"id": account_id, "code": code, "name": name, "type": kind}


def rename_account(path: Path, business_id: str, account_id: str, name: str) -> None:
    with db.connection(path) as conn:
        if not conn.execute("UPDATE ledger_accounts SET name = ? WHERE id = ? AND business_id = ?", (name, account_id, business_id)).rowcount:
            raise LedgerError("Account not found.")


# ---------------------------------------------------------------- reports


def accounts(path: Path, business_id: str) -> list[dict[str, Any]]:
    with db.connection(path) as conn:
        ensure_accounts(conn, business_id)
    return db.many(path, "SELECT id, code, name, type, system_key, active FROM ledger_accounts WHERE business_id = ? ORDER BY code", (business_id,))


def _balances(path: Path, business_id: str, start: str | None, end: str) -> list[dict[str, Any]]:
    clause = "AND e.entry_date >= ?" if start else ""
    params: tuple = (business_id, *( (start,) if start else ()), end)
    return db.many(
        path,
        f"""
        SELECT a.id, a.code, a.name, a.type, a.system_key, l.currency, SUM(l.amount_minor) AS amount
        FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id JOIN ledger_accounts a ON a.id = l.account_id
        WHERE e.business_id = ? AND e.status = 'posted' {clause} AND e.entry_date <= ?
        GROUP BY a.id, l.currency HAVING SUM(l.amount_minor) != 0 ORDER BY a.code
        """,
        params,
    )


def _natural(row: dict[str, Any]) -> int:
    """Balance in the account's natural direction (assets and expenses debit; the rest credit)."""
    return row["amount"] if row["type"] in ("asset", "expense") else -row["amount"]


def trial_balance(path: Path, business_id: str, as_of: date) -> dict[str, Any]:
    rows = _balances(path, business_id, None, as_of.isoformat())
    by_currency: dict[str, dict[str, Any]] = {}
    for row in rows:
        block = by_currency.setdefault(row["currency"], {"currency": row["currency"], "lines": [], "debit": 0, "credit": 0})
        debit, credit = max(row["amount"], 0), max(-row["amount"], 0)
        block["lines"].append({"code": row["code"], "name": row["name"], "type": row["type"], "debit": from_minor(debit), "credit": from_minor(credit)})
        block["debit"] += debit
        block["credit"] += credit
    for block in by_currency.values():
        block["balanced"] = block["debit"] == block["credit"]
        block["debit"], block["credit"] = from_minor(block["debit"]), from_minor(block["credit"])
    return {"as_of": as_of.isoformat(), "currencies": list(by_currency.values())}


def profit_and_loss(path: Path, business_id: str, start: date, end: date) -> dict[str, Any]:
    rows = [row for row in _balances(path, business_id, start.isoformat(), end.isoformat()) if row["type"] in ("income", "expense")]
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        block = out.setdefault(row["currency"], {"currency": row["currency"], "income": [], "expenses": [], "total_income": 0, "total_expenses": 0})
        value = _natural(row)
        item = {"code": row["code"], "name": row["name"], "key": row["system_key"], "amount": from_minor(value)}
        if row["type"] == "income":
            block["income"].append(item)
            block["total_income"] += value
        else:
            block["expenses"].append(item)
            block["total_expenses"] += value
    for block in out.values():
        cogs = sum(to_minor(item["amount"]) for item in block["expenses"] if item["key"] == "cogs")
        block["gross_profit"] = from_minor(block["total_income"] - cogs)
        block["net_profit"] = from_minor(block["total_income"] - block["total_expenses"])
        block["total_income"], block["total_expenses"] = from_minor(block["total_income"]), from_minor(block["total_expenses"])
    return {"from": start.isoformat(), "to": end.isoformat(), "currencies": list(out.values())}


def balance_sheet(path: Path, business_id: str, as_of: date) -> dict[str, Any]:
    rows = _balances(path, business_id, None, as_of.isoformat())
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        block = out.setdefault(row["currency"], {"currency": row["currency"], "assets": [], "liabilities": [], "equity": [], "earnings": 0})
        value = _natural(row)
        if row["type"] in ("income", "expense"):
            block["earnings"] += value if row["type"] == "income" else -value
            continue
        group = {"asset": "assets", "liability": "liabilities", "equity": "equity"}[row["type"]]
        block[group].append({"code": row["code"], "name": row["name"], "key": row["system_key"], "amount": from_minor(value)})
    for block in out.values():
        block["equity"].append({"code": "", "name": "Profit to date (not yet closed)", "key": "earnings", "amount": from_minor(block["earnings"])})
        totals = {group: sum(to_minor(item["amount"]) for item in block[group]) for group in ("assets", "liabilities", "equity")}
        block["totals"] = {group: from_minor(value) for group, value in totals.items()}
        block["balanced"] = totals["assets"] == totals["liabilities"] + totals["equity"]
        clearing = [item for item in block["assets"] + block["liabilities"] if item["key"] in ("receipts_clearing", "payments_clearing")]
        block["to_allocate"] = clearing
        del block["earnings"]
    return {"as_of": as_of.isoformat(), "currencies": list(out.values())}


def cash_flow(path: Path, business_id: str, start: date, end: date) -> dict[str, Any]:
    """Direct method: money in and out of cash, MoMo wallets and bank, by what the other side was."""
    rows = db.many(
        path,
        """
        SELECT e.id AS entry_id, a.system_key, a.type, l.currency, l.amount_minor
        FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id JOIN ledger_accounts a ON a.id = l.account_id
        WHERE e.business_id = ? AND e.status = 'posted' AND e.entry_date BETWEEN ? AND ?
        """,
        (business_id, start.isoformat(), end.isoformat()),
    )
    entries: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        entries[row["entry_id"]].append(row)
    groups = ("sales", "expenses", "stock", "owner", "loans", "opening", "other")
    out: dict[str, dict[str, int]] = {}
    for lines in entries.values():
        for currency in {line["currency"] for line in lines}:
            mine = [line for line in lines if line["currency"] == currency]
            cash = sum(line["amount_minor"] for line in mine if line["system_key"] in CASH_KEYS)
            if not cash:
                continue
            others = [line for line in mine if line["system_key"] not in CASH_KEYS]
            keys = {line["system_key"] for line in others}
            kinds = {line["type"] for line in others}
            if "opening_equity" in keys:
                group = "opening"
            elif kinds & {"income"} or keys & {"receivables", "receipts_clearing"}:
                group = "sales"
            elif keys & {"inventory", "cogs", "payables"}:
                group = "stock"
            elif keys & {"owner_capital", "drawings"}:
                group = "owner"
            elif keys & {"loans"}:
                group = "loans"
            elif kinds & {"expense"} or keys & {"payments_clearing"}:
                group = "expenses"
            else:
                group = "other"
            block = out.setdefault(currency, {name: 0 for name in groups})
            block[group] += cash
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "currencies": [
            {"currency": currency, "lines": {name: from_minor(value) for name, value in block.items()}, "net": from_minor(sum(block.values()))}
            for currency, block in out.items()
        ],
        "note": "Only money recorded against cash, a MoMo wallet or the bank counts. Sales whose payment method is unknown wait in 'Sales receipts to allocate'.",
    }


def journal(path: Path, business_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    entries = db.many(
        path,
        "SELECT e.id, e.entry_date, e.memo, e.source_key, e.kind, e.created_at, u.email AS user_email FROM journal_entries e "
        "LEFT JOIN users u ON u.id = e.user_id WHERE e.business_id = ? AND e.status = 'posted' ORDER BY e.entry_date DESC, e.created_at DESC LIMIT ? OFFSET ?",
        (business_id, limit, offset),
    )
    if not entries:
        return []
    marks = ",".join("?" for _ in entries)
    lines = db.many(
        path,
        f"SELECT l.entry_id, a.code, a.name, l.currency, l.amount_minor, l.description FROM journal_lines l JOIN ledger_accounts a ON a.id = l.account_id "
        f"WHERE l.entry_id IN ({marks}) ORDER BY a.code",
        tuple(e["id"] for e in entries),
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in lines:
        grouped[line["entry_id"]].append({
            "code": line["code"], "name": line["name"], "currency": line["currency"], "description": line["description"],
            "debit": from_minor(max(line["amount_minor"], 0)), "credit": from_minor(max(-line["amount_minor"], 0)),
        })
    return [{**entry, "lines": grouped[entry["id"]]} for entry in entries]


def journal_csv(path: Path, business_id: str) -> str:
    """Every posted line as a plain CSV journal (date, entry, account code and name, debit, credit, currency, memo)."""
    import csv
    import io

    rows = db.many(
        path,
        "SELECT e.entry_date, e.id, e.memo, a.code, a.name, l.currency, l.amount_minor, l.description FROM journal_lines l "
        "JOIN journal_entries e ON e.id = l.entry_id JOIN ledger_accounts a ON a.id = l.account_id "
        "WHERE e.business_id = ? AND e.status = 'posted' ORDER BY e.entry_date, e.created_at, e.id, a.code",
        (business_id,),
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Date", "Entry", "Account code", "Account", "Debit", "Credit", "Currency", "Memo", "Line description"])
    for row in rows:
        amount = row["amount_minor"]
        cells = [row["entry_date"], row["id"], row["code"], row["name"], f"{max(amount, 0) / 100:.2f}" if amount > 0 else "", f"{-amount / 100:.2f}" if amount < 0 else "", row["currency"], row["memo"], row["description"]]
        # Spreadsheet formula injection: a cell starting with = + - @ is read as a formula.
        writer.writerow([f"'{cell}" if isinstance(cell, str) and cell[:1] in ("=", "+", "-", "@") else cell for cell in cells])
    return buffer.getvalue()


def issues(path: Path, business_id: str) -> list[str]:
    rows = db.many(path, "SELECT issues FROM ledger_sources WHERE business_id = ? AND issues != '[]' ORDER BY source_key", (business_id,))
    return [issue for row in rows for issue in json.loads(row["issues"])]


_differences_cache: dict[tuple, dict[str, Any]] = {}


def differences(path: Path, business_id: str, start: date, end: date) -> dict[str, Any]:
    """Ledger sales against the analytics revenue for the same period, with every difference named.

    Analytics sums the ``amount`` of every included, dated record in the period. The ledger books
    MoMo payments made and expense lines as spending, leaves out lines before the books start,
    books undated lines on the import day, and may hold corrections moved past a locked period and
    manual journals. Anything left over is 'unexplained' and should be zero.

    Cached until the ledger changes (any re-sync or new entry), so a Books visit does not re-read
    every import file.
    """
    with db.connection(path) as conn:
        books_start = settings(conn, business_id)["books_start"]
        stamp = conn.execute(
            "SELECT (SELECT MAX(synced_at) FROM ledger_sources WHERE business_id = ?) AS synced, "
            "(SELECT MAX(created_at) FROM journal_entries WHERE business_id = ?) AS posted",
            (business_id, business_id),
        ).fetchone()
    key = (str(path), business_id, start, end, books_start, stamp["synced"], stamp["posted"])
    if key in _differences_cache:
        return _differences_cache[key]
    first, last = start.isoformat(), end.isoformat()
    analytics_total = 0
    explained: dict[str, int] = defaultdict(int)  # each amount is (analytics minus ledger) for that reason
    expected: dict[str, int] = defaultdict(int)  # ledger sales each import should produce in the period
    for dataset in dataset_store.analysable(business_id):
        try:
            records = dataset_store.read_records(dataset)
        except dataset_store.RecordsUnavailableError:
            continue
        imported_day = str(dataset["created_at"])[:10]
        domain = analytics._data_profile(analytics._present([dict(r) for r in records]))["domain"]
        for record in records:
            amount = _minor_of(record, "amount")
            day, dated = _record_day(record, imported_day)
            booked = record_rule(record, domain) == "sale" and first <= day <= last and not (books_start and day < books_start)
            if booked:
                expected[f"dataset:{dataset['id']}"] += amount
            if not dated:
                if booked:
                    explained["Undated lines, booked by the books on the import day"] -= amount
                continue
            if not first <= day <= last:
                continue
            analytics_total += amount
            if booked:
                continue
            rule = record_rule(record, domain)
            if rule == "momo_expense":
                explained["MoMo payments made (dashboards count them as revenue; the books treat them as spending)"] += amount
            elif rule == "expense":
                explained["Amounts on expense lines"] += amount
            else:
                explained["Lines before your books start (on the dashboards only)"] += amount
    rows = db.many(
        path,
        "SELECT e.source_key, SUM(-l.amount_minor) AS amount FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id "
        "JOIN ledger_accounts a ON a.id = l.account_id WHERE e.business_id = ? AND e.status = 'posted' AND a.system_key = 'sales' "
        "AND e.entry_date BETWEEN ? AND ? GROUP BY e.source_key",
        (business_id, first, last),
    )
    ledger_total = 0
    for row in rows:
        ledger_total += row["amount"]
        source = row["source_key"]
        if source.startswith("manual:"):
            explained["Manual journal entries"] -= row["amount"]
        elif source.startswith("dataset:"):
            explained["Corrections dated after a locked period"] -= row["amount"] - expected.pop(source, 0)
        else:
            explained["Other entries"] -= row["amount"]
    for missing in expected.values():  # an import expected in the books has no sales there in this period
        explained["Corrections dated after a locked period"] += missing
    unexplained = analytics_total - ledger_total - sum(explained.values())
    result = {
        "from": first,
        "to": last,
        "analytics_revenue": from_minor(analytics_total),
        "ledger_sales": from_minor(ledger_total),
        "explained": [{"reason": reason, "amount": from_minor(amount)} for reason, amount in explained.items() if amount],
        "unexplained": from_minor(unexplained),
    }
    if len(_differences_cache) > 64:
        _differences_cache.clear()
    _differences_cache[key] = result
    return result
