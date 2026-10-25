from pathlib import Path
from fastapi.testclient import TestClient
from backend import main


def _setup_client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)
    signup = client.post(
        "/api/auth/signup",
        json={"email": "newuser@example.com", "password": "password123", "business_name": "Accra Fresh Ltd"},
    )
    token = signup.json()["access_token"]
    business_id = signup.json()["business"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    return client, business_id, headers


def test_onboarding_flow(tmp_path, monkeypatch):
    client, business_id, headers = _setup_client(tmp_path, monkeypatch)

    # Initial status should be not onboarded
    res = client.get(f"/api/businesses/{business_id}/onboarding", headers=headers)
    assert res.status_code == 200
    assert res.json()["onboarded"] is False

    # Save onboarding details
    save = client.post(
        f"/api/businesses/{business_id}/onboarding",
        headers=headers,
        json={
            "business_type": "both",
            "goals": ["Expand to Kumasi", "Reach 25% gross margin"],
            "metrics_counted_on": ["Monthly Revenue", "MoMo Cashflow", "Inventory Reorder"],
            "data_sources": ["csv", "momo_sms"],
        },
    )
    assert save.status_code == 200
    assert save.json()["onboarded"] is True
    assert save.json()["business_type"] == "both"

    # Status check confirms
    check = client.get(f"/api/businesses/{business_id}/onboarding", headers=headers)
    assert check.json()["onboarded"] is True
    assert "Expand to Kumasi" in check.json()["goals"]


def test_momo_sms_source_ingestion(tmp_path, monkeypatch):
    client, business_id, headers = _setup_client(tmp_path, monkeypatch)

    sms_payload = {
        "sms_text": (
            "Payment received for GHS 250.00 from Kwame Kusi (0244111222). "
            "Current Balance: GHS 1,450.00. Reference: 10 boxes juice. "
            "Financial Transaction Id: MTN-891011. Date: 2026-03-20\n\n"
            "You have received GHS 180.00 from 233201999888 - YAABA OSEI. "
            "Trans ID: TC-334455. Balance: GHS 1,630.00. Date: 2026-03-21"
        )
    }
    momo_res = client.post(f"/api/businesses/{business_id}/sources/momo", headers=headers, json=sms_payload)
    assert momo_res.status_code == 200
    assert momo_res.json()["transactions_count"] == 2

    # Check dashboard snapshot
    snap_res = client.get(f"/api/businesses/{business_id}/dashboard-snapshot", headers=headers)
    assert snap_res.status_code == 200
    snapshot = snap_res.json()
    assert snapshot["kpis"]["total_revenue"] == 430.0
    assert snapshot["datasets_count"] >= 1
    assert "projections" in snapshot
    assert "top_5" in snapshot["products"]
    assert "worst_5" in snapshot["products"]


def test_markdown_and_txt_dataset_upload(tmp_path, monkeypatch):
    client, business_id, headers = _setup_client(tmp_path, monkeypatch)

    md_content = """# March Sales Report
| Date | Product | Amount | Cost | Customer |
| --- | --- | --- | --- | --- |
| 2026-03-01 | Web Design Service | 1200.00 | 200.00 | Apex Tech |
| 2026-03-02 | Cloud Consulting | 850.00 | 150.00 | BlueStar |
"""
    upload = client.post(
        f"/api/businesses/{business_id}/datasets",
        headers=headers,
        files={"file": ("report.md", md_content.encode("utf-8"), "text/markdown")},
    )
    assert upload.status_code == 200
    assert upload.json()["status"] == "processed"
    assert upload.json()["accepted_rows"] == 2


def test_sync_business_data_endpoint(tmp_path, monkeypatch):
    client, business_id, headers = _setup_client(tmp_path, monkeypatch)

    sync_res = client.post(f"/api/businesses/{business_id}/sync", headers=headers)
    assert sync_res.status_code == 200
    assert sync_res.json()["status"] == "synced"
    assert "snapshot" in sync_res.json()
