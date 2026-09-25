import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS businesses (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS datasets (id TEXT PRIMARY KEY, business_id TEXT NOT NULL, filename TEXT NOT NULL, extension TEXT NOT NULL, raw_path TEXT NOT NULL, processed_path TEXT, status TEXT NOT NULL, source_rows INTEGER NOT NULL, accepted_rows INTEGER NOT NULL, rejected_rows INTEGER NOT NULL, warnings TEXT NOT NULL, errors TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(business_id) REFERENCES businesses(id));
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
