"""Nightly, restorable backup of the whole app's data, sent next to the daily export.

The Parquet export (``exports.py``) is for analysis and cannot be loaded back. This backup can:

    <prefix>/_backup/dt=<YYYY-MM-DD>/ferlance.sqlite3.gz   the database (a consistent snapshot)
    <prefix>/_backup/dt=<YYYY-MM-DD>/files.tar.gz          uploaded files and processed records
    <prefix>/_backup/dt=<YYYY-MM-DD>/manifest.json         written last: sizes and checksums

It lives under the export prefix, so the write-only IAM policy (``s3:PutObject`` on
``<bucket>/exports/*``) already covers it. To restore, download the three files and follow
docs/DEPLOY.md ("Restore from a backup").

The database is copied with SQLite's online backup API, so the snapshot is consistent even while
the app is writing. Files are streamed through temporary files on the data disk, never held whole
in memory.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, db

logger = logging.getLogger(__name__)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _put_file(target: Any, key: str, path: Path, content_type: str) -> None:
    put_file = getattr(target, "put_file", None)
    if put_file:
        put_file(key, path, content_type)
    else:  # simple targets (tests) only take bytes
        target.put(key, path.read_bytes())


def make_backup(target: Any, day: str) -> dict[str, Any]:
    """Write one backup for ``day``. Returns what was written; raises on failure."""
    prefix = f"{config.EXPORT_PREFIX}/_backup/dt={day}"
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=config.DATA_DIR, prefix=".backup-") as scratch:
        work = Path(scratch)
        snapshot = work / "ferlance.sqlite3"
        source = sqlite3.connect(config.DB_PATH)
        try:
            copy = sqlite3.connect(snapshot)
            with copy:
                source.backup(copy)
            copy.close()
        finally:
            source.close()
        database = work / "ferlance.sqlite3.gz"
        with snapshot.open("rb") as raw, gzip.open(database, "wb", compresslevel=6) as packed:
            shutil.copyfileobj(raw, packed)
        files = work / "files.tar.gz"
        with tarfile.open(files, "w:gz") as archive:
            for folder, name in ((config.RAW_DIR, "raw"), (config.PROCESSED_DIR, "processed")):
                if folder.is_dir():
                    archive.add(folder, arcname=name)
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "day": day,
            "files": {
                "ferlance.sqlite3.gz": {"bytes": database.stat().st_size, "sha256": _sha256(database)},
                "files.tar.gz": {"bytes": files.stat().st_size, "sha256": _sha256(files)},
            },
            "restore": "See docs/DEPLOY.md, 'Restore from a backup'.",
        }
        _put_file(target, f"{prefix}/ferlance.sqlite3.gz", database, "application/gzip")
        _put_file(target, f"{prefix}/files.tar.gz", files, "application/gzip")
        target.put(f"{prefix}/manifest.json", json.dumps(manifest, indent=2).encode())
    return {"bytes": sum(item["bytes"] for item in manifest["files"].values())}


def run(target: Any, day: str, force: bool = False) -> str:
    """Back up once a day (or again when forced). Returns 'ok', 'skipped' or 'failed'; failures are recorded."""
    now = db.now()
    with db.connection(config.DB_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status, attempts FROM backup_runs WHERE day = ?", (day,)).fetchone()
        if row and not force and (row["status"] == "ok" or row["attempts"] >= 3):
            return "skipped"
        conn.execute(
            "INSERT INTO backup_runs (day, status, attempts, started_at) VALUES (?, 'running', 1, ?) "
            "ON CONFLICT(day) DO UPDATE SET status = 'running', attempts = attempts + 1, error = NULL, started_at = excluded.started_at, finished_at = NULL",
            (day, now),
        )
    try:
        result = make_backup(target, day)
    except Exception as error:
        message = f"{error.__class__.__name__}: {error}"[:500]
        logger.warning("Backup failed: %s", message)
        db.insert(config.DB_PATH, "UPDATE backup_runs SET status = 'failed', error = ?, finished_at = ? WHERE day = ?", (message, db.now(), day))
        return "failed"
    db.insert(config.DB_PATH, "UPDATE backup_runs SET status = 'ok', bytes = ?, finished_at = ? WHERE day = ?", (result["bytes"], db.now(), day))
    return "ok"


def latest() -> dict[str, Any] | None:
    return db.one(config.DB_PATH, "SELECT day, status, attempts, bytes, error, finished_at FROM backup_runs ORDER BY day DESC LIMIT 1")
