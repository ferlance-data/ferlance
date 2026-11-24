import csv
import io
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import config, db, main, planning


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    return TestClient(main.app)


def owner(client, email="ama@example.com"):
    signup = client.post("/api/auth/signup", json={"email": email, "password": "password123", "business_name": "Ama Provisions"}).json()
    return {"Authorization": f"Bearer {signup['access_token']}"}, f"/api/businesses/{signup['business']['id']}", signup["business"]["id"]


def expenses(client, headers, base, window="from=2026-01-01&to=2026-12-31"):
    pnl = client.get(f"{base}/books?{window}", headers=headers).json()["profit_and_loss"]["currencies"]
    return {item["key"]: item["amount"] for item in pnl[0]["expenses"]} if pnl else {}


def test_recurring_expenses_wait_for_confirmation(client):
    headers, base, business_id = owner(client)
    created = client.post(f"{base}/recurring", headers=headers, json={"name": "Shop rent", "account": "rent", "amount": 500, "paid_from": "momo_mtn",
                                                                       "day_of_month": 1, "start_month": "2026-09"})
    assert created.status_code == 200
    item = created.json()["id"]
    state = planning.recurring(config.DB_PATH, business_id, date(2026, 11, 24))
    assert [d["month"] for d in state["due"]] == ["2026-09", "2026-10", "2026-11"]
    assert expenses(client, headers, base) == {}  # nothing posts on its own

    assert client.post(f"{base}/recurring/{item}/decide", headers=headers, json={"month": "2026-09", "confirm": True}).status_code == 200
    assert client.post(f"{base}/recurring/{item}/decide", headers=headers, json={"month": "2026-10", "confirm": True, "amount": 550}).status_code == 200
    assert client.post(f"{base}/recurring/{item}/decide", headers=headers, json={"month": "2026-11", "confirm": False}).status_code == 200
    assert client.post(f"{base}/recurring/{item}/decide", headers=headers, json={"month": "2026-11", "confirm": True}).status_code == 400  # decided once
    assert expenses(client, headers, base) == {"rent": 1050}
    assert planning.recurring(config.DB_PATH, business_id, date(2026, 11, 24))["due"] == []

    assert client.delete(f"{base}/recurring/{item}/months/2026-10", headers=headers).status_code == 200
    assert expenses(client, headers, base) == {"rent": 500}
    assert client.post(f"{base}/recurring/{item}/decide", headers=headers, json={"month": "2026-10", "confirm": True}).status_code == 200
    assert expenses(client, headers, base) == {"rent": 1000}
    future = client.post(f"{base}/recurring/{item}/decide", headers=headers, json={"month": "2026-12", "confirm": True, "posted_on": "2099-12-01"})
    assert future.status_code == 400


def test_budgets_against_actuals(client):
    headers, base, _ = owner(client)
    client.post(f"{base}/datasets", headers=headers, files={"file": ("s.csv", b"transaction_date,product,amount,payment_method\n2026-11-03,Rice,900,cash\n", "text/csv")})
    client.post(f"{base}/datasets", headers=headers, files={"file": ("e.csv", b"transaction_date,category,cost\n2026-11-04,Fuel,130\n", "text/csv")})
    assert client.put(f"{base}/budgets", headers=headers, json={"month": "2026-11", "account": "transport", "amount": 100}).status_code == 200
    assert client.put(f"{base}/budgets", headers=headers, json={"month": "2026-11", "account": "sales", "amount": 1000}).status_code == 200
    assert client.put(f"{base}/budgets", headers=headers, json={"month": "2026-11", "account": "cash", "amount": 1}).status_code == 400  # not income or expense
    lines = {line["account"]: line for line in client.get(f"{base}/budgets?month=2026-11", headers=headers).json()["lines"]}
    assert lines["transport"]["actual"] == 130 and lines["transport"]["over"] is True and lines["transport"]["used_pct"] == 130
    assert lines["sales"]["actual"] == 900 and lines["sales"]["used_pct"] == 90 and lines["sales"]["over"] is False


def test_year_end_pack_and_my_data(client):
    headers, base, _ = owner(client)
    client.post(f"{base}/datasets", headers=headers, files={"file": ("s.csv", b"transaction_date,product,amount,payment_method\n2026-03-03,=cmd(),900,cash\n", "text/csv")})
    client.post(f"{base}/debts", headers=headers, json={"direction": "owed_to_us", "party_name": "Akosua", "amount": 200, "issued_on": "2026-10-02", "basis": "new_sale"})
    client.post(f"{base}/inventory/products", headers=headers, json={"name": "Rice 5kg", "unit": "bag", "unit_cost": 70, "opening_stock": 4})
    response = client.get(f"{base}/year-end.zip?year=2026", headers=headers)
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    pack = zipfile.ZipFile(io.BytesIO(response.content))
    assert set(pack.namelist()) == {"README.txt", "trial_balance.csv", "profit_and_loss.csv", "balance_sheet.csv", "journal.csv", "debtors.csv", "creditors.csv", "stock_valuation.csv"}
    trial = list(csv.DictReader(io.StringIO(pack.read("trial_balance.csv").decode())))
    assert round(sum(float(r["debit"]) for r in trial), 2) == round(sum(float(r["credit"]) for r in trial), 2)
    assert "Akosua" in pack.read("debtors.csv").decode()
    assert "280" in pack.read("stock_valuation.csv").decode()  # 4 × 70
    assert "not yet checked" in pack.read("README.txt").decode()

    data = client.get(f"{base}/my-data.zip", headers=headers)
    names = set(zipfile.ZipFile(io.BytesIO(data.content)).namelist())
    assert {"sales_records.csv", "journal.csv", "debts.csv", "invoices.csv", "inventory_movements.csv"} <= names
    sales = zipfile.ZipFile(io.BytesIO(data.content)).read("sales_records.csv").decode()
    assert "'=cmd()" in sales  # formula neutralised


def test_roles_and_isolation(client):
    headers, base, _ = owner(client)
    token = client.post(f"{base}/invites", headers=headers, json={"role": "manager"}).json()["token"]
    member = client.post("/api/auth/signup", json={"email": "m@example.com", "password": "password123", "invite_token": token}).json()
    manager = {"Authorization": f"Bearer {member['access_token']}"}
    assert client.get(f"{base}/budgets?month=2026-11", headers=manager).status_code == 200
    assert client.put(f"{base}/budgets", headers=manager, json={"month": "2026-11", "account": "rent", "amount": 1}).status_code == 403
    assert client.get(f"{base}/year-end.zip?year=2026", headers=manager).status_code == 403
    assert client.get(f"{base}/my-data.zip", headers=manager).status_code == 403
    item = client.post(f"{base}/recurring", headers=headers, json={"name": "Rent", "account": "rent", "amount": 5, "paid_from": "cash", "day_of_month": 1, "start_month": "2026-11"}).json()["id"]
    other_headers, other_base, _ = owner(client, "o@example.com")
    assert client.post(f"{other_base}/recurring/{item}/decide", headers=other_headers, json={"month": "2026-11", "confirm": True}).status_code == 404
    assert client.get(f"{base}/my-data.zip", headers=other_headers).status_code == 404
