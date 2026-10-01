from pathlib import Path
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend import main


def test_signup_upload_and_history_are_tenant_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)

    signup = client.post("/api/auth/signup", json={"email": "owner@example.com", "password": "password123", "business_name": "Ama Retail"})
    assert signup.status_code == 200
    token = signup.json()["access_token"]
    business_id = signup.json()["business"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    fixture = Path(__file__).parent / "fixtures" / "valid_sales.csv"

    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})
    assert upload.status_code == 200
    assert upload.json()["status"] == "processed"
    assert upload.json()["accepted_rows"] == 3

    records = client.get(f"/api/businesses/{business_id}/datasets/{upload.json()['id']}/records", headers=headers)
    assert records.status_code == 200
    assert records.json()["count"] == 3
    assert len(records.json()["records"]) == 3

    history = client.get(f"/api/businesses/{business_id}/datasets", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 1

    forbidden = client.get("/api/businesses/not-owned/datasets", headers=headers)
    assert forbidden.status_code == 404


def test_upload_rejects_unsupported_type(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "owner2@example.com", "password": "password123", "business_name": "Kojo Shop"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]
    response = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.txt", b"data", "text/plain")})
    assert response.status_code == 415


def test_upload_rejects_files_over_configured_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 4)
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "large@example.com", "password": "password123", "business_name": "Kojo Shop"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]

    response = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", b"12345", "text/csv")})

    assert response.status_code == 413


def _xlsx_bytes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Date", "Revenue", "Product"])
    sheet.append(["2026-01-02", "1250.50", "Rice"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_valid_xlsx_upload_has_readable_records(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "xlsx@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]

    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.xlsx", _xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

    assert upload.status_code == 200
    assert upload.json()["status"] == "processed"
    records = client.get(f"/api/businesses/{business_id}/datasets/{upload.json()['id']}/records", headers=headers)
    assert records.json()["records"][0]["product"] == "Rice"


def test_malformed_xlsx_is_failed_and_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "broken@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]

    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("broken.xlsx", b"not xlsx", "application/octet-stream")})

    assert upload.json()["status"] == "failed"
    assert upload.json()["errors"] == ["The XLSX file is malformed or unreadable."]
    history = client.get(f"/api/businesses/{business_id}/datasets", headers=headers)
    assert history.json()[0]["id"] == upload.json()["id"]
    records = client.get(f"/api/businesses/{business_id}/datasets/{upload.json()['id']}/records", headers=headers)
    assert records.json()["count"] == 0


def test_partial_upload_reports_rejected_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "partial@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]
    fixture = Path(__file__).parent / "fixtures" / "invalid_sales.csv"

    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})

    assert upload.json()["status"] == "partial"
    assert upload.json()["accepted_rows"] == 1
    assert upload.json()["rejected_rows"] == 2
    records = client.get(f"/api/businesses/{business_id}/datasets/{upload.json()['id']}/records", headers=headers)
    assert records.json()["count"] == upload.json()["accepted_rows"]
