import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS businesses (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, business_id TEXT NOT NULL, filename TEXT NOT NULL, extension TEXT NOT NULL, raw_path TEXT NOT NULL, processed_path TEXT, status TEXT NOT NULL, source_rows INTEGER NOT NULL, accepted_rows INTEGER NOT NULL, rejected_rows INTEGER NOT NULL, warnings TEXT NOT NULL, errors TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(business_id) REFERENCES businesses(id));
CREATE TABLE IF NOT EXISTS folder_imports (
    business_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    modified_ns INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    dataset_id TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(business_id, filename),
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS refresh_sessions (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT, created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS chat_conversations (id TEXT PRIMARY KEY, business_id TEXT NOT NULL, user_id TEXT NOT NULL, dataset_id TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, FOREIGN KEY(business_id) REFERENCES businesses(id), FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(dataset_id) REFERENCES datasets(id));
CREATE TABLE IF NOT EXISTS chat_messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user', 'assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(conversation_id) REFERENCES chat_conversations(id));
CREATE TABLE IF NOT EXISTS inventory_products (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    sku TEXT,
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    unit_cost REAL,
    reorder_level REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS inventory_products_business_name
    ON inventory_products(business_id, name COLLATE NOCASE);
CREATE UNIQUE INDEX IF NOT EXISTS inventory_products_business_sku
    ON inventory_products(business_id, sku COLLATE NOCASE)
    WHERE sku IS NOT NULL AND sku != '';
CREATE TABLE IF NOT EXISTS inventory_movements (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    movement_type TEXT NOT NULL CHECK(movement_type IN ('opening', 'purchase', 'sale', 'adjustment', 'stocktake')),
    quantity_delta REAL NOT NULL,
    unit_cost REAL,
    stock_value_after REAL,
    note TEXT NOT NULL,
    source TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(business_id) REFERENCES businesses(id),
    FOREIGN KEY(product_id) REFERENCES inventory_products(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS inventory_movements_business_date
    ON inventory_movements(business_id, created_at DESC);
CREATE INDEX IF NOT EXISTS inventory_movements_product_date
    ON inventory_movements(product_id, created_at DESC);
CREATE TABLE IF NOT EXISTS product_links (
    business_id TEXT NOT NULL,
    sales_name_norm TEXT NOT NULL,
    sales_name TEXT NOT NULL,
    product_id TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(business_id, sales_name_norm),
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS dataset_stock_posts (
    dataset_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('posted', 'reversed')),
    summary TEXT,
    posted_at TEXT NOT NULL,
    reversed_at TEXT,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE INDEX IF NOT EXISTS inventory_movements_source ON inventory_movements(business_id, source);
CREATE TABLE IF NOT EXISTS stock_captures (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    source TEXT NOT NULL,
    filename TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft', 'confirmed', 'discarded')),
    lines TEXT NOT NULL,
    outcome TEXT,
    created_at TEXT NOT NULL,
    confirmed_at TEXT,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS admin_audit (
    id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_user_id TEXT,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS export_runs (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    day TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running', 'ok', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    row_count INTEGER,
    objects INTEGER,
    bytes INTEGER,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE(business_id, day),
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS ledger_accounts (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('asset', 'liability', 'equity', 'income', 'expense')),
    system_key TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL,
    UNIQUE(business_id, code),
    UNIQUE(business_id, system_key),
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS journal_entries (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    memo TEXT NOT NULL,
    source_key TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('auto', 'reversal', 'opening', 'manual')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'posted')),
    user_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE INDEX IF NOT EXISTS journal_entries_business_date ON journal_entries(business_id, entry_date);
CREATE INDEX IF NOT EXISTS journal_entries_source ON journal_entries(business_id, source_key);
CREATE TABLE IF NOT EXISTS journal_lines (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL,
    business_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    amount_minor INTEGER NOT NULL CHECK(amount_minor != 0),
    description TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(entry_id) REFERENCES journal_entries(id),
    FOREIGN KEY(account_id) REFERENCES ledger_accounts(id)
);
CREATE INDEX IF NOT EXISTS journal_lines_entry ON journal_lines(entry_id);
CREATE INDEX IF NOT EXISTS journal_lines_account ON journal_lines(account_id);
-- Double entry, enforced by the database: an entry becomes 'posted' only if it has two or more
-- lines summing to zero in every currency; posted entries and their lines never change.
CREATE TRIGGER IF NOT EXISTS journal_post_balanced BEFORE UPDATE OF status ON journal_entries
WHEN OLD.status = 'draft' AND NEW.status = 'posted' AND (
    (SELECT COUNT(*) FROM journal_lines WHERE entry_id = NEW.id) < 2
    OR EXISTS (SELECT 1 FROM journal_lines WHERE entry_id = NEW.id GROUP BY currency HAVING SUM(amount_minor) != 0)
)
BEGIN SELECT RAISE(ABORT, 'journal entry does not balance'); END;
CREATE TRIGGER IF NOT EXISTS journal_insert_as_draft BEFORE INSERT ON journal_entries
WHEN NEW.status IS NOT 'draft'
BEGIN SELECT RAISE(ABORT, 'journal entries start as drafts'); END;
CREATE TRIGGER IF NOT EXISTS journal_posted_immutable BEFORE UPDATE ON journal_entries
WHEN OLD.status = 'posted'
BEGIN SELECT RAISE(ABORT, 'posted journal entries cannot change'); END;
CREATE TRIGGER IF NOT EXISTS journal_posted_undeletable BEFORE DELETE ON journal_entries
WHEN OLD.status = 'posted'
BEGIN SELECT RAISE(ABORT, 'posted journal entries cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS journal_lines_draft_only BEFORE INSERT ON journal_lines
WHEN (SELECT status FROM journal_entries WHERE id = NEW.entry_id) IS NOT 'draft'
BEGIN SELECT RAISE(ABORT, 'lines can only be added to a draft entry'); END;
CREATE TRIGGER IF NOT EXISTS journal_lines_immutable BEFORE UPDATE ON journal_lines
WHEN (SELECT status FROM journal_entries WHERE id = OLD.entry_id) = 'posted'
BEGIN SELECT RAISE(ABORT, 'posted journal lines cannot change'); END;
CREATE TRIGGER IF NOT EXISTS journal_lines_undeletable BEFORE DELETE ON journal_lines
WHEN (SELECT status FROM journal_entries WHERE id = OLD.entry_id) = 'posted'
BEGIN SELECT RAISE(ABORT, 'posted journal lines cannot be deleted'); END;
CREATE TABLE IF NOT EXISTS ledger_sources (
    business_id TEXT NOT NULL,
    source_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    issues TEXT NOT NULL DEFAULT '[]',
    synced_at TEXT NOT NULL,
    PRIMARY KEY(business_id, source_key)
);
CREATE TABLE IF NOT EXISTS ledger_lock_log (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    before_date TEXT,
    after_date TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_settings (
    business_id TEXT PRIMARY KEY,
    books_start TEXT,
    lock_date TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS debt_parties (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('customer', 'supplier')),
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS debt_parties_name ON debt_parties(business_id, kind, name COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS debts (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    party_id TEXT NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('owed_to_us', 'we_owe')),
    basis TEXT NOT NULL CHECK(basis IN ('new_sale', 'recorded_sale', 'recorded_purchase', 'expense')),
    description TEXT NOT NULL DEFAULT '',
    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
    currency TEXT NOT NULL,
    issued_on TEXT NOT NULL,
    due_on TEXT,
    voided_at TEXT,
    voided_by TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(business_id) REFERENCES businesses(id),
    FOREIGN KEY(party_id) REFERENCES debt_parties(id)
);
CREATE INDEX IF NOT EXISTS debts_business ON debts(business_id, issued_on);
CREATE TABLE IF NOT EXISTS debt_payments (
    id TEXT PRIMARY KEY,
    debt_id TEXT NOT NULL,
    business_id TEXT NOT NULL,
    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
    paid_on TEXT NOT NULL,
    method TEXT NOT NULL CHECK(method IN ('cash', 'momo_mtn', 'momo_telecel', 'momo_at', 'momo_other', 'bank', 'momo_sms')),
    momo_ref TEXT,
    voided_at TEXT,
    voided_by TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(debt_id) REFERENCES debts(id)
);
CREATE INDEX IF NOT EXISTS debt_payments_debt ON debt_payments(debt_id);
-- One MoMo message settles at most one debt payment (while that payment stands).
CREATE UNIQUE INDEX IF NOT EXISTS debt_payments_momo_ref ON debt_payments(business_id, momo_ref) WHERE momo_ref IS NOT NULL AND voided_at IS NULL;
CREATE TABLE IF NOT EXISTS debt_settings (
    business_id TEXT PRIMARY KEY,
    pay_to TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backup_runs (
    day TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN ('running', 'ok', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    bytes INTEGER,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('invoice', 'quote', 'receipt')),
    seq INTEGER NOT NULL,
    number TEXT NOT NULL,
    party_id TEXT,
    customer_name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    issued_on TEXT NOT NULL,
    due_on TEXT,
    currency TEXT NOT NULL,
    total_minor INTEGER NOT NULL CHECK(total_minor > 0),
    notes TEXT NOT NULL DEFAULT '',
    debt_id TEXT,
    converted_from TEXT,
    voided_at TEXT,
    voided_by TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(business_id, kind, seq),
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE INDEX IF NOT EXISTS invoices_business ON invoices(business_id, issued_on);
CREATE TABLE IF NOT EXISTS invoice_lines (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    product_id TEXT,
    description TEXT NOT NULL,
    quantity REAL NOT NULL CHECK(quantity > 0),
    unit_price_minor INTEGER NOT NULL CHECK(unit_price_minor >= 0),
    line_total_minor INTEGER NOT NULL,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id)
);
CREATE INDEX IF NOT EXISTS invoice_lines_invoice ON invoice_lines(invoice_id);
CREATE TABLE IF NOT EXISTS invoice_settings (
    business_id TEXT PRIMARY KEY,
    tin TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    footer TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS page_captures (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('vision', 'text')),
    page_type TEXT NOT NULL,
    page_date TEXT,
    status TEXT NOT NULL CHECK(status IN ('draft', 'confirming', 'confirmed', 'discarded')),
    lines TEXT NOT NULL,
    outcome TEXT,
    created_at TEXT NOT NULL,
    confirmed_at TEXT,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS statement_imports (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    account TEXT NOT NULL,
    filename TEXT NOT NULL,
    new_lines INTEGER NOT NULL,
    duplicate_lines INTEGER NOT NULL,
    checks TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS statement_lines (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    import_id TEXT NOT NULL,
    account TEXT NOT NULL,
    line_key TEXT NOT NULL,
    position INTEGER NOT NULL,
    txn_date TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    reference TEXT NOT NULL DEFAULT '',
    amount_minor INTEGER NOT NULL,
    fee_minor INTEGER NOT NULL DEFAULT 0,
    balance_after_minor INTEGER,
    booking TEXT,
    booking_detail TEXT,
    fee_booked INTEGER NOT NULL DEFAULT 0,
    match_ref TEXT,
    updated_by TEXT,
    updated_at TEXT,
    UNIQUE(business_id, account, line_key),
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE INDEX IF NOT EXISTS statement_lines_account ON statement_lines(business_id, account, txn_date);
CREATE TABLE IF NOT EXISTS tax_rule_checks (
    business_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    checked_by TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    PRIMARY KEY(business_id, rule_id)
);
CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    name TEXT NOT NULL,
    ssnit_number TEXT NOT NULL DEFAULT '',
    tin TEXT NOT NULL DEFAULT '',
    basic_minor INTEGER NOT NULL CHECK(basic_minor >= 0),
    allowances_minor INTEGER NOT NULL DEFAULT 0 CHECK(allowances_minor >= 0),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS payroll_runs (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    month TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft', 'posted', 'void')),
    paid_from TEXT,
    paid_on TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    posted_at TEXT,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS payroll_runs_month ON payroll_runs(business_id, month) WHERE status != 'void';
CREATE TABLE IF NOT EXISTS payroll_lines (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    name TEXT NOT NULL,
    basic_minor INTEGER NOT NULL,
    allowances_minor INTEGER NOT NULL,
    gross_minor INTEGER NOT NULL,
    ssnit_employee_minor INTEGER NOT NULL,
    ssnit_employer_minor INTEGER NOT NULL,
    chargeable_minor INTEGER NOT NULL,
    paye_minor INTEGER NOT NULL,
    net_minor INTEGER NOT NULL,
    rules TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES payroll_runs(id)
);
CREATE TABLE IF NOT EXISTS credit_shares (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    lender TEXT NOT NULL DEFAULT '',
    token_hash TEXT NOT NULL UNIQUE,
    code TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS credit_share_views (
    id TEXT PRIMARY KEY,
    share_id TEXT NOT NULL,
    viewed_at TEXT NOT NULL,
    user_agent TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(share_id) REFERENCES credit_shares(id)
);
CREATE TABLE IF NOT EXISTS business_members (
    business_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('owner', 'manager', 'accountant')),
    created_at TEXT NOT NULL,
    PRIMARY KEY(business_id, user_id),
    FOREIGN KEY(business_id) REFERENCES businesses(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS business_members_user ON business_members(user_id);
CREATE TABLE IF NOT EXISTS business_invites (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('manager', 'accountant')),
    token_hash TEXT UNIQUE NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    accepted_by TEXT,
    accepted_at TEXT,
    revoked_at TEXT,
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS ai_usage (
    business_id TEXT NOT NULL,
    day TEXT NOT NULL,
    calls INTEGER NOT NULL,
    PRIMARY KEY(business_id, day)
);
CREATE TABLE IF NOT EXISTS insight_explanations (
    business_id TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(business_id, cache_key),
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS business_integrations (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(business_id, provider),
    FOREIGN KEY(business_id) REFERENCES businesses(id)
);
CREATE TABLE IF NOT EXISTS financial_position_balances (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    category TEXT NOT NULL,
    account_name TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    amount REAL NOT NULL,
    note TEXT NOT NULL,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(business_id) REFERENCES businesses(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS financial_position_lookup
    ON financial_position_balances(business_id, category, account_name, as_of_date DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS datasets_business_date ON datasets(business_id, created_at DESC);
-- v2 index: record values only (field names matched every row), the record date for scope
-- filtering, and the porter stemmer so "payments" finds "payment".
CREATE VIRTUAL TABLE IF NOT EXISTS rag_records_fts USING fts5(
    document_id UNINDEXED, business_id UNINDEXED, dataset_id UNINDEXED, record_date UNINDEXED, record UNINDEXED, content,
    tokenize = 'porter unicode61'
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection(path: Path) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connection(path) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA)
        user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'owner'")
        if "disabled_at" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN disabled_at TEXT")
        if "full_name" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''")
        dataset_columns = {row[1] for row in db.execute("PRAGMA table_info(datasets)").fetchall()}
        if "checksum" not in dataset_columns:
            db.execute("ALTER TABLE datasets ADD COLUMN checksum TEXT")
        if "review_status" not in dataset_columns:
            db.execute("ALTER TABLE datasets ADD COLUMN review_status TEXT NOT NULL DEFAULT 'accepted'")
        if "overlap_details" not in dataset_columns:
            db.execute("ALTER TABLE datasets ADD COLUMN overlap_details TEXT NOT NULL DEFAULT '[]'")
        # Record date span per file, so the UI can resolve date presets before any analytics request.
        # NULL means "not computed yet" (backfilled by dataset_store.backfill_periods); '' means "no dated records".
        if "period_from" not in dataset_columns:
            db.execute("ALTER TABLE datasets ADD COLUMN period_from TEXT")
        if "period_to" not in dataset_columns:
            db.execute("ALTER TABLE datasets ADD COLUMN period_to TEXT")
        # Every business has its creator as owner in the membership table (one code path for access).
        db.execute(
            "INSERT OR IGNORE INTO business_members (business_id, user_id, role, created_at) "
            "SELECT id, user_id, 'owner', created_at FROM businesses"
        )
        session_columns = {row[1] for row in db.execute("PRAGMA table_info(refresh_sessions)").fetchall()}
        if "replaced_by" not in session_columns:
            db.execute("ALTER TABLE refresh_sessions ADD COLUMN replaced_by TEXT")
        debt_columns = {row[1] for row in db.execute("PRAGMA table_info(debts)").fetchall()}
        if debt_columns and "tax_minor" not in debt_columns:
            # VAT and levies inside a debt's amount (from a VAT invoice): booked to 'VAT and levies payable'.
            db.execute("ALTER TABLE debts ADD COLUMN tax_minor INTEGER NOT NULL DEFAULT 0")
        payment_columns = {row[1] for row in db.execute("PRAGMA table_info(debt_payments)").fetchall()}
        if payment_columns and "wht_minor" not in payment_columns:
            # Withholding tax kept back from a supplier payment (paid to GRA, not the supplier).
            db.execute("ALTER TABLE debt_payments ADD COLUMN wht_minor INTEGER NOT NULL DEFAULT 0")
            db.execute("ALTER TABLE debt_payments ADD COLUMN wht_kind TEXT")
            db.execute("ALTER TABLE debt_payments ADD COLUMN wht_rule TEXT")
        invoice_columns = {row[1] for row in db.execute("PRAGMA table_info(invoices)").fetchall()}
        if invoice_columns and "tax_minor" not in invoice_columns:
            db.execute("ALTER TABLE invoices ADD COLUMN tax_minor INTEGER NOT NULL DEFAULT 0")
            db.execute("ALTER TABLE invoices ADD COLUMN taxes TEXT NOT NULL DEFAULT '[]'")
            db.execute("ALTER TABLE invoices ADD COLUMN tax_rule TEXT")
        if "scope" not in session_columns:
            # 'workspace' or 'admin': a refresh cookie only renews a session of its own kind.
            db.execute("ALTER TABLE refresh_sessions ADD COLUMN scope TEXT NOT NULL DEFAULT 'workspace'")
        # The v1 retrieval index (field names indexed, no dates) is replaced by rag_records_fts,
        # which rebuilds itself lazily per file on the next Ask Lance question.
        db.execute("DROP TABLE IF EXISTS rag_documents_fts")
        # Brave web research was removed in favour of free sources; drop any stored Brave keys.
        db.execute("DELETE FROM business_integrations WHERE provider = 'brave_search'")
        movement_columns = {row[1] for row in db.execute("PRAGMA table_info(inventory_movements)").fetchall()}
        if "unit_cost" not in movement_columns:
            db.execute("ALTER TABLE inventory_movements ADD COLUMN unit_cost REAL")
        if "stock_value_after" not in movement_columns:
            db.execute("ALTER TABLE inventory_movements ADD COLUMN stock_value_after REAL")
        business_columns = {row[1] for row in db.execute("PRAGMA table_info(businesses)").fetchall()}
        if "currency" not in business_columns:
            db.execute("ALTER TABLE businesses ADD COLUMN currency TEXT NOT NULL DEFAULT 'GHS'")


def repair_dataset_paths(path: Path, raw_dir: Path, processed_dir: Path) -> None:
    with connection(path) as db:
        rows = db.execute("SELECT id, raw_path, processed_path FROM datasets").fetchall()
        for row in rows:
            dataset_id, raw_path, processed_path = row["id"], row["raw_path"], row["processed_path"]
            updated_raw = raw_path
            updated_processed = processed_path
            if raw_path and not Path(raw_path).is_file():
                candidate = raw_dir / Path(raw_path).name
                if candidate.is_file():
                    updated_raw = str(candidate)
            if processed_path and not Path(processed_path).is_file():
                candidate = processed_dir / Path(processed_path).name
                if candidate.is_file():
                    updated_processed = str(candidate)
            if updated_raw != raw_path or updated_processed != processed_path:
                db.execute(
                    "UPDATE datasets SET raw_path = ?, processed_path = ? WHERE id = ?",
                    (updated_raw, updated_processed, dataset_id),
                )


def one(path: Path, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connection(path) as db:
        row = db.execute(query, params).fetchone()
        return dict(row) if row else None


def many(path: Path, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connection(path) as db:
        return [dict(row) for row in db.execute(query, params).fetchall()]


def insert(path: Path, query: str, params: tuple[Any, ...]) -> None:
    with connection(path) as db:
        db.execute(query, params)
