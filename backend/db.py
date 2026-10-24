import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS businesses (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, business_id TEXT NOT NULL, filename TEXT NOT NULL, extension TEXT NOT NULL, raw_path TEXT NOT NULL, processed_path TEXT, status TEXT NOT NULL, source_rows INTEGER NOT NULL, accepted_rows INTEGER NOT NULL, rejected_rows INTEGER NOT NULL, warnings TEXT NOT NULL, errors TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(business_id) REFERENCES businesses(id));
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
CREATE TABLE IF NOT EXISTS business_fx_rates (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    source_currency TEXT NOT NULL,
    target_currency TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    rate REAL NOT NULL CHECK(rate > 0),
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(business_id, source_currency, target_currency, effective_date),
    FOREIGN KEY(business_id) REFERENCES businesses(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
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
CREATE VIRTUAL TABLE IF NOT EXISTS rag_documents_fts USING fts5(document_id UNINDEXED, business_id UNINDEXED, dataset_id UNINDEXED, content);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection(path: Path) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize(path: Path) -> None:
    with connection(path) as db:
        db.executescript(SCHEMA)
        user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
        if "role" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'owner'")
        if "full_name" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''")
        dataset_columns = {row[1] for row in db.execute("PRAGMA table_info(datasets)").fetchall()}
        if "checksum" not in dataset_columns:
            db.execute("ALTER TABLE datasets ADD COLUMN checksum TEXT")
        if "review_status" not in dataset_columns:
            db.execute("ALTER TABLE datasets ADD COLUMN review_status TEXT NOT NULL DEFAULT 'accepted'")
        if "overlap_details" not in dataset_columns:
            db.execute("ALTER TABLE datasets ADD COLUMN overlap_details TEXT NOT NULL DEFAULT '[]'")
        movement_columns = {row[1] for row in db.execute("PRAGMA table_info(inventory_movements)").fetchall()}
        if "unit_cost" not in movement_columns:
            db.execute("ALTER TABLE inventory_movements ADD COLUMN unit_cost REAL")
        if "stock_value_after" not in movement_columns:
            db.execute("ALTER TABLE inventory_movements ADD COLUMN stock_value_after REAL")


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
