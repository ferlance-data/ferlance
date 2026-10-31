from pathlib import Path
import uuid

from openpyxl import Workbook

from backend import config, db
from backend.folder_imports import FolderImporter


def _write_workbook(path: Path, revenue: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Date", "Revenue", "Product"])
    sheet.append(["2026-01-02", revenue, "Rice"])
    workbook.save(path)


def test_folder_imports_new_and_changed_workbooks_once(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    business_id = "business-1"
    db.insert(
        config.DB_PATH,
        "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("user-1", "owner@example.com", "hash", db.now()),
    )
    db.insert(
        config.DB_PATH,
        "INSERT INTO businesses (id, user_id, name, created_at, currency) VALUES (?, ?, ?, ?, ?)",
        (business_id, "user-1", "Ama Retail", db.now(), config.DEFAULT_CURRENCY),
    )

    import_dir = tmp_path / "incoming"
    business_dir = import_dir / business_id
    business_dir.mkdir(parents=True)
    workbook_path = business_dir / "sales.xlsx"
    _write_workbook(workbook_path, "1250.50")

    def import_watched_file(business_id: str, source_path: Path) -> dict:
        suffix = source_path.suffix.lower()
        if source_path.stat().st_size > config.MAX_UPLOAD_BYTES:
            raise ValueError("File is larger than the 10 MB upload limit.")
        dataset_id = str(uuid.uuid4())
        raw_path = config.RAW_DIR / f"{dataset_id}{suffix}"
        import shutil
        shutil.copyfile(source_path, raw_path)
        from backend.processor import process_file
        result = process_file(raw_path, suffix)
        # Simple save without full dataset_store
        import json
        db.insert(
            config.DB_PATH,
            "INSERT INTO datasets (id, business_id, filename, extension, raw_path, processed_path, status, source_rows, accepted_rows, rejected_rows, warnings, errors, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (dataset_id, business_id, source_path.name, suffix, str(raw_path), None, "processed", result.source_rows, len(result.rows), result.rejected_rows, json.dumps(result.warnings), json.dumps(result.errors), db.now()),
        )
        return {"id": dataset_id, "status": "processed", "errors": []}

    importer = FolderImporter(import_dir, config.DB_PATH, import_watched_file)

    importer.scan_once()
    assert db.many(config.DB_PATH, "SELECT id FROM datasets") == []

    importer.scan_once()
    datasets = db.many(config.DB_PATH, "SELECT id, filename, status FROM datasets")
    assert len(datasets) == 1
    assert datasets[0]["filename"] == "sales.xlsx"
    assert datasets[0]["status"] == "processed"
    assert db.one(config.DB_PATH, "SELECT status FROM folder_imports WHERE business_id = ?", (business_id,))["status"] == "processed"

    importer.scan_once()
    assert len(db.many(config.DB_PATH, "SELECT id FROM datasets")) == 1

    _write_workbook(workbook_path, "2000.00")
    importer.scan_once()
    importer.scan_once()
    assert len(db.many(config.DB_PATH, "SELECT id FROM datasets")) == 2