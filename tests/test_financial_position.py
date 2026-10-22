from fastapi.testclient import TestClient

from backend import main


def _client(tmp_path, monkeypatch, email="position@example.com"):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "position.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)
    signup = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "password123", "business_name": "Ama Retail"},
    )
    return client, signup.json()["business"]["id"], {
        "Authorization": f"Bearer {signup.json()['access_token']}"
    }


def test_point_in_time_position_carries_balances_forward_and_flags_gaps(tmp_path, monkeypatch):
    client, business_id, headers = _client(tmp_path, monkeypatch)
    endpoint = f"/api/businesses/{business_id}/financial-position"
    for category, name, amount in [
        ("bank", "Main bank", 1000),
        ("loans", "Equipment loan", 200),
        ("owner_capital", "Owner capital", 800),
    ]:
        response = client.post(
            f"{endpoint}/balances",
            headers=headers,
            json={
                "as_of_date": "2026-04-30",
                "category": category,
                "account_name": name,
                "amount": amount,
            },
        )
        assert response.status_code == 200

    historical = client.get(f"{endpoint}?as_of=2026-04-15", headers=headers).json()
    assert historical["assets"] == []
    assert historical["totals"]["assets"] == 0

    report = client.get(f"{endpoint}?as_of=2026-05-31", headers=headers).json()
    assert report["totals"]["assets"] == 1000
    assert report["totals"]["liabilities"] == 200
    assert report["totals"]["equity"] == 800
    assert report["totals"]["complete"] is False
    assert report["totals"]["balanced"] is False
    assert len(report["missing_categories"]) == 9
    assert len(report["stale_balances"]) == 3

    newer = client.post(
        f"{endpoint}/balances",
        headers=headers,
        json={
            "as_of_date": "2026-05-15",
            "category": "bank",
            "account_name": "Main bank",
            "amount": 900,
        },
    )
    assert newer.status_code == 200
    before_update = client.get(f"{endpoint}?as_of=2026-05-01", headers=headers).json()
    after_update = client.get(f"{endpoint}?as_of=2026-05-31", headers=headers).json()
    assert before_update["totals"]["assets"] == 1000
    assert after_update["totals"]["assets"] == 900


def test_position_balance_validation_history_and_tenant_scope(tmp_path, monkeypatch):
    client, first_business, first_headers = _client(tmp_path, monkeypatch, "first-position@example.com")
    second = client.post(
        "/api/auth/signup",
        json={
            "email": "second-position@example.com",
            "password": "password123",
            "business_name": "Other Business",
        },
    ).json()
    second_business = second["business"]["id"]
    second_headers = {"Authorization": f"Bearer {second['access_token']}"}
    endpoint = f"/api/businesses/{first_business}/financial-position"
    negative_asset = client.post(
        f"{endpoint}/balances",
        headers=first_headers,
        json={
            "as_of_date": "2026-06-01",
            "category": "cash",
            "account_name": "Till",
            "amount": -1,
        },
    )
    negative_equity = client.post(
        f"{endpoint}/balances",
        headers=first_headers,
        json={
            "as_of_date": "2026-06-01",
            "category": "retained_earnings",
            "account_name": "Accumulated result",
            "amount": -25,
        },
    )
    unauthorized = client.get(
        f"/api/businesses/{second_business}/financial-position?as_of=2026-06-30",
        headers=second_headers,
    )
    forbidden = client.get(
        f"/api/businesses/{first_business}/financial-position?as_of=2026-06-30",
        headers=second_headers,
    )
    history = client.get(f"{endpoint}/history", headers=first_headers)

    assert negative_asset.status_code == 400
    assert negative_equity.status_code == 200
    assert unauthorized.status_code == 200
    assert unauthorized.json()["assets"] == []
    assert forbidden.status_code == 404
    assert history.status_code == 200
    assert history.json()[0]["amount"] == -25
    assert history.json()[0]["recorded_by"] == "first-position@example.com"


def test_position_report_date_parsing(tmp_path, monkeypatch):
    client, business_id, headers = _client(tmp_path, monkeypatch)
    response = client.get(
        f"/api/businesses/{business_id}/financial-position?as_of=not-a-date",
        headers=headers,
    )
    assert response.status_code == 422
