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
