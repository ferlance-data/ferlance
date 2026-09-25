from pathlib import Path

from fastapi.testclient import TestClient

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
