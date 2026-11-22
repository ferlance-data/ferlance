"""Daily per-business data export to S3 (or a local folder) as Parquet.

Off unless FERLANCE_EXPORT_BUCKET (S3) or FERLANCE_EXPORT_DIR (local folder) is set. Once a day,
after FERLANCE_EXPORT_HOUR_UTC, every business gets a full snapshot of its data:

    <prefix>/business_id=<id>/dt=<YYYY-MM-DD>/<table>.parquet

Tables: ``sales_records`` (the records that count in analysis: processed, not excluded),
``datasets`` (import metadata), ``inventory_products`` (with stock on hand) and
``inventory_movements``. The layout is Hive-style, so Athena or Glue can query it directly.

The S3 user only needs ``s3:PutObject`` on ``<bucket>/<prefix>/*``: the exporter never reads,
lists or deletes. A re-run on the same day overwrites that day's files. Credentials come from the
standard AWS environment variables (loaded from .env by ``config``); they are never logged.

Each run is recorded in ``export_runs`` so administrators see failures. A business that fails is
retried on the next check, up to MAX_ATTEMPTS a day.
"""

from __future__ import annotations

import io
import json
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from . import config, dataset_store, db

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
CHECK_SECONDS = 15 * 60
STALE_RUN = timedelta(hours=1)  # a 'running' row older than this was interrupted and may be retried

TEXT_FIELDS = ("record_id", "transaction_date", "product", "customer", "vendor", "employee", "category")
NUMBER_FIELDS = ("amount", "cost", "budget", "variance", "quantity", "unit_price")


class Target(Protocol):
    description: str

    def put(self, key: str, body: bytes) -> None: ...


class LocalTarget:
    def __init__(self, root: str) -> None:
        from pathlib import Path

        self.root = Path(root)
        self.description = f"folder {self.root}"

    def put(self, key: str, body: bytes) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(body)
        tmp.replace(path)


class S3Target:
    def __init__(self, bucket: str, region: str | None) -> None:
        import boto3  # imported lazily: only deployments that export pay for it

        self.bucket = bucket
        self.description = f"s3://{bucket}"
        self._client = boto3.client("s3", region_name=region or None)

    def put(self, key: str, body: bytes) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/vnd.apache.parquet",
            ServerSideEncryption="AES256",
        )


def enabled() -> bool:
    return bool(config.EXPORT_BUCKET or config.EXPORT_DIR)


def destination() -> str | None:
    if config.EXPORT_BUCKET:
        return f"s3://{config.EXPORT_BUCKET}/{config.EXPORT_PREFIX}"
    if config.EXPORT_DIR:
        return f"{config.EXPORT_DIR}/{config.EXPORT_PREFIX}"
    return None


def make_target() -> Target:
    if config.EXPORT_BUCKET:
        return S3Target(config.EXPORT_BUCKET, config.AWS_REGION)
    if config.EXPORT_DIR:
        return LocalTarget(config.EXPORT_DIR)
    raise RuntimeError("Data export is not configured.")


# ---------------------------------------------------------------- tables


def _text(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _number(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def tables(business_id: str) -> dict[str, list[dict[str, Any]]]:
    """Every table in a business's snapshot, as rows with a fixed set of columns."""
    datasets = dataset_store.list_all(business_id)
    sales: list[dict[str, Any]] = []
    for dataset in dataset_store.analysable(business_id):
        for record in dataset_store.read_records(dataset):
            row: dict[str, Any] = {"dataset_id": dataset["id"], "filename": dataset["filename"]}
            row.update({field: _text(record.get(field)) for field in TEXT_FIELDS})
            row.update({field: _number(record.get(field)) for field in NUMBER_FIELDS})
            extra = {k: v for k, v in record.items() if k not in TEXT_FIELDS and k not in NUMBER_FIELDS}
            row["extra"] = json.dumps(extra, default=str, sort_keys=True) if extra else None
            sales.append(row)
    dataset_rows = [
        {
            "id": d["id"],
            "filename": d["filename"],
            "status": d["status"],
            "review_status": d.get("review_status"),
            "source_rows": d["source_rows"],
            "accepted_rows": d["accepted_rows"],
            "rejected_rows": d["rejected_rows"],
            "period_from": d.get("period_from") or None,
            "period_to": d.get("period_to") or None,
            "created_at": d["created_at"],
        }
        for d in datasets
    ]
    products = db.many(
        config.DB_PATH,
        "SELECT p.id, p.sku, p.name, p.unit, p.unit_cost, p.reorder_level, p.active, p.created_at, p.updated_at, "
        "COALESCE((SELECT SUM(m.quantity_delta) FROM inventory_movements m WHERE m.product_id = p.id), 0) AS quantity_on_hand "
        "FROM inventory_products p WHERE p.business_id = ? ORDER BY p.name",
        (business_id,),
    )
    for product in products:
        product["active"] = bool(product["active"])
    movements = db.many(
        config.DB_PATH,
        "SELECT id, product_id, movement_type, quantity_delta, unit_cost, stock_value_after, note, source, created_at "
        "FROM inventory_movements WHERE business_id = ? ORDER BY created_at",
        (business_id,),
    )
    return {"sales_records": sales, "datasets": dataset_rows, "inventory_products": products, "inventory_movements": movements}


SCHEMAS: dict[str, list[tuple[str, str]]] = {
    "sales_records": [("dataset_id", "string"), ("filename", "string")]
    + [(f, "string") for f in TEXT_FIELDS]
    + [(f, "float64") for f in NUMBER_FIELDS]
    + [("extra", "string")],
    "datasets": [
        ("id", "string"), ("filename", "string"), ("status", "string"), ("review_status", "string"),
        ("source_rows", "int64"), ("accepted_rows", "int64"), ("rejected_rows", "int64"),
        ("period_from", "string"), ("period_to", "string"), ("created_at", "string"),
    ],
    "inventory_products": [
        ("id", "string"), ("sku", "string"), ("name", "string"), ("unit", "string"), ("unit_cost", "float64"),
        ("reorder_level", "float64"), ("active", "bool_"), ("created_at", "string"), ("updated_at", "string"),
        ("quantity_on_hand", "float64"),
    ],
    "inventory_movements": [
        ("id", "string"), ("product_id", "string"), ("movement_type", "string"), ("quantity_delta", "float64"),
        ("unit_cost", "float64"), ("stock_value_after", "float64"), ("note", "string"), ("source", "string"),
        ("created_at", "string"),
    ],
}


def to_parquet(name: str, rows: list[dict[str, Any]]) -> bytes:
    import pyarrow as pa  # imported lazily: ~60 MB in memory, only while exporting
    import pyarrow.parquet as pq

    schema = pa.schema([(column, getattr(pa, kind)()) for column, kind in SCHEMAS[name]])
    table = pa.Table.from_pylist([{column: row.get(column) for column, _ in SCHEMAS[name]} for row in rows], schema=schema)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="zstd")
    return buffer.getvalue()


# ---------------------------------------------------------------- runs


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _claim(business_id: str, day: str, force: bool) -> bool:
    """Take this business's run for the day, unless it already succeeded, is running, or ran out of attempts."""
    now = datetime.now(timezone.utc)
    stale = (now - STALE_RUN).isoformat()
    with db.connection(config.DB_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status, attempts, started_at FROM export_runs WHERE business_id = ? AND day = ?", (business_id, day)).fetchone()
        if row:
            running = row["status"] == "running" and row["started_at"] > stale
            if running or (not force and (row["status"] == "ok" or row["attempts"] >= MAX_ATTEMPTS)):
                return False
            conn.execute(
                "UPDATE export_runs SET status = 'running', attempts = attempts + 1, error = NULL, started_at = ?, finished_at = NULL WHERE business_id = ? AND day = ?",
                (now.isoformat(), business_id, day),
            )
        else:
            conn.execute(
                "INSERT INTO export_runs (id, business_id, day, status, attempts, started_at) VALUES (?, ?, ?, 'running', 1, ?)",
                (str(uuid.uuid4()), business_id, day, now.isoformat()),
            )
    return True


def _error_text(error: Exception) -> str:
    return f"{error.__class__.__name__}: {error}"[:500]


def export_business(business_id: str, target: Target, day: str) -> dict[str, int]:
    prefix = f"{config.EXPORT_PREFIX}/business_id={business_id}/dt={day}"
    rows = objects = size = 0
    for name, table_rows in tables(business_id).items():
        body = to_parquet(name, table_rows)
        target.put(f"{prefix}/{name}.parquet", body)
        rows += len(table_rows)
        objects += 1
        size += len(body)
    return {"rows": rows, "objects": objects, "bytes": size}


def run(force: bool = False, day: str | None = None, target: Target | None = None) -> dict[str, Any]:
    """Export every business that is due today. Returns counts; failures are recorded, not raised."""
    day = day or _today()
    summary = {"day": day, "exported": 0, "failed": 0, "skipped": 0}
    try:
        target = target or make_target()
    except Exception as error:  # e.g. boto3 missing or a bad region; record it so admins see it
        logger.error("Data export could not start: %s", _error_text(error))
        raise
    for business in db.many(config.DB_PATH, "SELECT id FROM businesses ORDER BY created_at"):
        business_id = business["id"]
        if not _claim(business_id, day, force):
            summary["skipped"] += 1
            continue
        try:
            result = export_business(business_id, target, day)
        except Exception as error:
            logger.warning("Data export failed for business %s: %s", business_id, _error_text(error))
            db.insert(
                config.DB_PATH,
                "UPDATE export_runs SET status = 'failed', error = ?, finished_at = ? WHERE business_id = ? AND day = ?",
                (_error_text(error), db.now(), business_id, day),
            )
            summary["failed"] += 1
            continue
        db.insert(
            config.DB_PATH,
            "UPDATE export_runs SET status = 'ok', row_count = ?, objects = ?, bytes = ?, error = NULL, finished_at = ? WHERE business_id = ? AND day = ?",
            (result["rows"], result["objects"], result["bytes"], db.now(), business_id, day),
        )
        summary["exported"] += 1
    return summary


def due(now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now.hour >= config.EXPORT_HOUR_UTC


def scheduler(stop: threading.Event) -> None:
    """Background loop: once the export hour has passed, export whatever is due today."""
    while not stop.is_set():
        if due():
            try:
                run()
            except Exception as error:
                logger.error("Scheduled data export failed: %s", _error_text(error))
        stop.wait(CHECK_SECONDS)


def start() -> tuple[threading.Thread, threading.Event] | None:
    if not enabled():
        return None
    stop = threading.Event()
    thread = threading.Thread(target=scheduler, args=(stop,), name="ferlance-export", daemon=True)
    thread.start()
    return thread, stop


def status(limit: int = 50) -> dict[str, Any]:
    """What administrators see: where exports go and each business's latest run (counts only, no records)."""
    rows = db.many(
        config.DB_PATH,
        """
        SELECT r.business_id, b.name AS business_name, r.day, r.status, r.attempts, r.row_count, r.objects, r.bytes, r.error, r.started_at, r.finished_at
        FROM export_runs r JOIN businesses b ON b.id = r.business_id
        WHERE r.day = (SELECT MAX(day) FROM export_runs x WHERE x.business_id = r.business_id)
        ORDER BY (r.status = 'failed') DESC, b.name
        LIMIT ?
        """,
        (limit,),
    )
    return {
        "enabled": enabled(),
        "destination": destination(),
        "hour_utc": config.EXPORT_HOUR_UTC,
        "failed": sum(1 for row in rows if row["status"] == "failed"),
        "runs": rows,
    }
