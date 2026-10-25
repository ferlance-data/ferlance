from fastapi.testclient import TestClient

from backend import config, db, main

SALES = b"date,amount,product,cost\n2026-03-01,100,Rice,60\n2026-03-02,50,Oil,70\n2026-03-08,300,Rice,180\n"


def _setup_client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post(
        "/api/auth/signup",
        json={"email": "newuser@example.com", "password": "password123", "business_name": "Accra Fresh Ltd"},
    )
    token = signup.json()["access_token"]
    business_id = signup.json()["business"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    return client, business_id, headers


def test_momo_sms_source_ingestion_feeds_business_analytics(tmp_path, monkeypatch):
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
    momo = client.post(f"/api/businesses/{business_id}/sources/momo", headers=headers, json=sms_payload)
    assert momo.status_code == 200
    assert momo.json()["transactions_count"] == 2
    assert momo.json()["total_amount"] == 430.0
    assert momo.json()["dataset"]["status"] == "processed"

    analytics = client.get(f"/api/businesses/{business_id}/analytics", headers=headers)
    assert analytics.status_code == 200
    assert analytics.json()["kpis"]["total_revenue"] == 430.0
    assert analytics.json()["dataset"]["id"] == "all"

    unparseable = client.post(f"/api/businesses/{business_id}/sources/momo", headers=headers, json={"sms_text": "hello there friend"})
    assert unparseable.status_code == 400


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


def test_duplicate_upload_is_flagged_and_can_be_excluded(tmp_path, monkeypatch):
    client, business_id, headers = _setup_client(tmp_path, monkeypatch)
    base = f"/api/businesses/{business_id}"

    first = client.post(f"{base}/datasets", headers=headers, files={"file": ("march.csv", SALES, "text/csv")})
    second = client.post(f"{base}/datasets", headers=headers, files={"file": ("march-copy.csv", SALES, "text/csv")})
    assert first.json()["included"] is True
    assert not any("identical" in warning for warning in first.json()["warnings"])
    assert "identical to march.csv" in second.json()["warnings"][0]

    doubled = client.get(f"{base}/analytics", headers=headers).json()
    assert doubled["kpis"]["total_revenue"] == 900.0

    excluded = client.patch(f"{base}/datasets/{second.json()['id']}", headers=headers, json={"included": False})
    assert excluded.status_code == 200
    assert excluded.json()["included"] is False
    corrected = client.get(f"{base}/analytics", headers=headers).json()
    assert corrected["kpis"]["total_revenue"] == 450.0
    assert corrected["dataset"]["files"] == 1

    # An excluded file can still be opened on its own.
    single = client.get(f"{base}/analytics", headers=headers, params={"dataset_id": second.json()["id"]})
    assert single.status_code == 200

    missing = client.patch(f"{base}/datasets/not-a-dataset", headers=headers, json={"included": False})
    assert missing.status_code == 404


def test_analytics_compares_with_previous_period(tmp_path, monkeypatch):
    client, business_id, headers = _setup_client(tmp_path, monkeypatch)
    base = f"/api/businesses/{business_id}"
    client.post(f"{base}/datasets", headers=headers, files={"file": ("march.csv", SALES, "text/csv")})

    week_two = client.get(f"{base}/analytics", headers=headers, params={"from": "2026-03-08", "to": "2026-03-14"}).json()
    comparison = week_two["comparison"]
    assert comparison["available"] is True
    assert comparison["previous_period"] == {"from": "2026-03-01", "to": "2026-03-07"}
    assert comparison["metrics"]["revenue"] == {"current": 300.0, "previous": 150.0, "change_pct": 100.0}
    assert comparison["metrics"]["gross_profit"]["previous"] == 20.0

    everything = client.get(f"{base}/analytics", headers=headers).json()
    assert everything["comparison"]["available"] is False
    assert "projections" not in everything


def test_removed_placeholder_endpoints_are_gone(tmp_path, monkeypatch):
    client, business_id, headers = _setup_client(tmp_path, monkeypatch)
    base = f"/api/businesses/{business_id}"
    assert client.post(f"{base}/sync", headers=headers).status_code == 404
    assert client.get(f"{base}/dashboard-snapshot", headers=headers).status_code == 404
    assert client.get(f"{base}/sources/connections", headers=headers).status_code == 404
