import json
import time

import pyarrow.parquet as pq
import pytest
from botocore.stub import Stubber
from fastapi.testclient import TestClient

from backend import config, db, exports, main

DAY = "2026-11-22"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(config, "ADMIN_EMAILS", {"root@example.com"})
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    return TestClient(main.app)


def business(client, email="ama@example.com", name="Ama Retail"):
    signup = client.post("/api/auth/signup", json={"email": email, "password": "password123", "business_name": name}).json()
    headers = {"Authorization": f"Bearer {signup['access_token']}"}
    base = f"/api/businesses/{signup['business']['id']}"
    return headers, base, signup["business"]["id"]


def seed(client):
    headers, base, business_id = business(client)
    client.post(f"{base}/inventory/products", headers=headers, json={"name": "Rice 5kg", "unit": "bag", "unit_cost": 70, "opening_stock": 20})
    kept = "transaction_date,product,quantity,amount,channel\n2026-10-01,Rice 5kg,4,380,momo\n2026-10-02,Oil,,96,cash\n"
    left_out = "transaction_date,product,amount\n2026-10-03,Sugar,50\n"
    client.post(f"{base}/datasets", headers=headers, files={"file": ("kept.csv", kept.encode(), "text/csv")})
    excluded = client.post(f"{base}/datasets", headers=headers, files={"file": ("old.csv", left_out.encode(), "text/csv")}).json()
    client.patch(f"{base}/datasets/{excluded['id']}", headers=headers, json={"included": False})
    return headers, base, business_id


def test_local_export_writes_partitioned_parquet_snapshot(client, tmp_path, monkeypatch):
    _, _, business_id = seed(client)
    monkeypatch.setattr(config, "EXPORT_DIR", str(tmp_path / "out"))
    assert exports.run(day=DAY) == {"day": DAY, "exported": 1, "failed": 0, "skipped": 0, "backup": "ok"}

    folder = tmp_path / "out" / "exports" / f"business_id={business_id}" / f"dt={DAY}"
    assert sorted(p.name for p in folder.iterdir()) == ["datasets.parquet", "inventory_movements.parquet", "inventory_products.parquet", "manifest.json", "sales_records.parquet"]
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["files"]["sales_records.parquet"] == {"rows": 2, "bytes": (folder / "sales_records.parquet").stat().st_size}
    sales = pq.read_table(folder / "sales_records.parquet").to_pylist()
    # Only the records that count in analysis: the excluded file is left out.
    assert [(r["product"], r["quantity"], r["amount"], r["filename"]) for r in sales] == [("Rice 5kg", 4.0, 380.0, "kept.csv"), ("Oil", None, 96.0, "kept.csv")]
    assert sales[0]["transaction_date"].startswith("2026-10-01")
    assert pq.read_table(folder / "sales_records.parquet").schema.field("amount").type == "double"
    assert {r["filename"]: r["review_status"] for r in pq.read_table(folder / "datasets.parquet").to_pylist()}["old.csv"] == "excluded"
    product = pq.read_table(folder / "inventory_products.parquet").to_pylist()[0]
    assert product["name"] == "Rice 5kg" and product["quantity_on_hand"] == 20 and product["active"] is True

    # Done for the day: the scheduler does not export again unless forced (which overwrites).
    assert exports.run(day=DAY)["skipped"] == 1
    assert exports.run(day=DAY, force=True)["exported"] == 1
    run = db.one(config.DB_PATH, "SELECT status, attempts, row_count, objects FROM export_runs", ())
    assert run["status"] == "ok" and run["attempts"] == 2 and run["objects"] == 5 and run["row_count"] >= 5


def test_failures_are_recorded_retried_and_capped(client):
    _, _, business_id = seed(client)

    class Broken:
        description = "broken"

        def put(self, key, body):
            raise PermissionError("Access Denied")

    for attempt in range(1, exports.MAX_ATTEMPTS + 1):
        assert exports.run(day=DAY, target=Broken())["failed"] == 1
        run = db.one(config.DB_PATH, "SELECT status, attempts, error FROM export_runs WHERE business_id = ?", (business_id,))
        assert run["status"] == "failed" and run["attempts"] == attempt and "Access Denied" in run["error"]
    assert exports.run(day=DAY, target=Broken())["skipped"] == 1  # capped for the day

    written = {}

    class Working:
        description = "memory"

        def put(self, key, body):
            written[key] = body

    # An administrator's forced run still goes through, and clears the error.
    assert exports.run(day=DAY, force=True, target=Working())["exported"] == 1
    business_files = [key for key in written if "/_backup/" not in key]
    assert len(business_files) == 5 and business_files[-1].endswith("manifest.json")  # manifest last
    assert db.one(config.DB_PATH, "SELECT status, error FROM export_runs", ()) == {"status": "ok", "error": None}


def test_unreadable_file_is_left_out_not_fatal(client, tmp_path, monkeypatch):
    headers, base, business_id = seed(client)
    kept = next(d for d in client.get(f"{base}/datasets", headers=headers).json() if d["filename"] == "kept.csv")
    processed = db.one(config.DB_PATH, "SELECT processed_path FROM datasets WHERE id = ?", (kept["id"],))["processed_path"]
    __import__("pathlib").Path(processed).unlink()
    monkeypatch.setattr(config, "EXPORT_DIR", str(tmp_path / "out"))
    assert exports.run(day=DAY)["exported"] == 1
    run = db.one(config.DB_PATH, "SELECT status, error FROM export_runs", ())
    assert run["status"] == "ok" and "kept.csv" in run["error"]
    manifest = json.loads((tmp_path / "out" / "exports" / f"business_id={business_id}" / f"dt={DAY}" / "manifest.json").read_text())
    assert manifest["unavailable_files"] == ["kept.csv"] and manifest["files"]["sales_records.parquet"]["rows"] == 0


def test_s3_target_writes_encrypted_objects_only(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    target = exports.S3Target("ferlance-bucket", "eu-west-1")
    with Stubber(target._client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "ferlance-bucket",
                "Key": "exports/business_id=b1/dt=2026-11-22/datasets.parquet",
                "Body": b"PAR1",
                "ContentType": "application/vnd.apache.parquet",
                "ServerSideEncryption": "AES256",
            },
        )
        target.put("exports/business_id=b1/dt=2026-11-22/datasets.parquet", b"PAR1")
        stub.assert_no_pending_responses()


def test_admin_export_status_and_run(client, tmp_path, monkeypatch):
    owner, _, _ = seed(client)
    root, _, _ = business(client, "root@example.com", "Root Co")
    for method, path in (("get", "/api/admin/exports"), ("post", "/api/admin/exports/run")):
        assert getattr(client, method)(path, headers=owner).status_code == 403

    assert client.get("/api/admin/exports", headers=root).json()["enabled"] is False
    assert client.post("/api/admin/exports/run", headers=root).status_code == 400

    monkeypatch.setattr(config, "EXPORT_DIR", str(tmp_path / "out"))
    assert client.post("/api/admin/exports/run", headers=root).status_code == 202
    for _ in range(100):
        if not exports.busy():
            break
        time.sleep(0.05)
    result = client.get("/api/admin/exports", headers=root).json()
    assert result["failed"] == 0 and result["enabled"] is True and result["running"] is False and result["problem"] is None
    assert {(run["business_name"], run["status"]) for run in result["runs"]} == {("Ama Retail", "ok"), ("Root Co", "ok")}
    assert all("records" not in run for run in result["runs"])
    audit = client.get("/api/admin/audit", headers=root).json()
    assert audit[0]["action"] == "export_run"

    # A second click while one is running is refused rather than starting a parallel export.
    assert exports._manual.acquire()
    try:
        assert client.post("/api/admin/exports/run", headers=root).status_code == 409
    finally:
        exports._manual.release()


def test_scheduler_waits_for_the_export_hour(monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(config, "EXPORT_HOUR_UTC", 2)
    assert not exports.due(datetime(2026, 11, 22, 1, 59, tzinfo=timezone.utc))
    assert exports.due(datetime(2026, 11, 22, 2, 0, tzinfo=timezone.utc))
    assert exports.start() is None  # nothing configured: no thread


def test_nightly_backup_can_be_restored(client, tmp_path, monkeypatch):
    import gzip
    import sqlite3
    import tarfile

    seed(client)
    monkeypatch.setattr(config, "EXPORT_DIR", str(tmp_path / "out"))
    summary = exports.run(day=DAY)
    assert summary["backup"] == "ok"
    folder = tmp_path / "out" / "exports" / "_backup" / f"dt={DAY}"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert set(manifest["files"]) == {"ferlance.sqlite3.gz", "files.tar.gz"}

    # Restoring: the database snapshot opens and holds the business; the files archive holds the imports.
    restored = tmp_path / "restored.sqlite3"
    restored.write_bytes(gzip.decompress((folder / "ferlance.sqlite3.gz").read_bytes()))
    with sqlite3.connect(restored) as conn:
        assert conn.execute("SELECT name FROM businesses").fetchone()[0] == "Ama Retail"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with tarfile.open(folder / "files.tar.gz") as archive:
        names = archive.getnames()
    assert any(name.startswith("raw/") for name in names) and any(name.startswith("processed/") for name in names)

    # Once a day: skipped on the next check, redone when an administrator forces it.
    assert exports.run(day=DAY)["backup"] == "skipped"
    assert exports.run(day=DAY, force=True)["backup"] == "ok"
    assert exports.status()["backup"]["status"] == "ok"
