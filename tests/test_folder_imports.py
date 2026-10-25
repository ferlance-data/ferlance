from pathlib import Path

from openpyxl import Workbook

from backend import db, main
from backend.folder_imports import FolderImporter


def _write_workbook(path: Path, revenue: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Date", "Revenue", "Product"])
    sheet.append(["2026-01-02", revenue, "Rice"])
    workbook.save(path)


def test_folder_imports_new_and_changed_workbooks_once(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    db.initialize(main.DB_PATH)
    business_id = "business-1"
    db.insert(
        main.DB_PATH,
        "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("user-1", "owner@example.com", "hash", db.now()),
    )
    db.insert(
        main.DB_PATH,
        "INSERT INTO businesses VALUES (?, ?, ?, ?)",
        (business_id, "user-1", "Ama Retail", db.now()),
    )

    import_dir = tmp_path / "incoming"
    business_dir = import_dir / business_id
    business_dir.mkdir(parents=True)
    workbook_path = business_dir / "sales.xlsx"
    _write_workbook(workbook_path, "1250.50")
    importer = FolderImporter(import_dir, main.DB_PATH, main.import_watched_file)

    importer.scan_once()
    assert db.many(main.DB_PATH, "SELECT id FROM datasets") == []

    importer.scan_once()
    datasets = db.many(main.DB_PATH, "SELECT id, filename, status FROM datasets")
    assert len(datasets) == 1
    assert datasets[0]["filename"] == "sales.xlsx"
    assert datasets[0]["status"] == "processed"
    assert db.one(main.DB_PATH, "SELECT status FROM folder_imports WHERE business_id = ?", (business_id,))["status"] == "processed"

    importer.scan_once()
    assert len(db.many(main.DB_PATH, "SELECT id FROM datasets")) == 1

    _write_workbook(workbook_path, "2000.00")
    importer.scan_once()
    importer.scan_once()
    assert len(db.many(main.DB_PATH, "SELECT id FROM datasets")) == 2
