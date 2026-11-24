import json

import pytest
from fastapi.testclient import TestClient

from backend import config, db, main, ocr, pages

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


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
    return {"Authorization": f"Bearer {signup['access_token']}"}, f"/api/businesses/{signup['business']['id']}"


def fake_vision(monkeypatch, reply):
    monkeypatch.setattr(config, "OPENROUTER_KEY", "key")
    sent = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(reply)}}]}

    monkeypatch.setattr(ocr.httpx, "post", lambda url, headers, json, timeout: sent.append(json) or Response())
    return sent


def test_clean_page_validates_the_reply():
    page = pages.clean_page({"type": "nonsense", "date": "2026-11-02", "lines": [
        {"description": "  Rice   5kg ", "quantity": "2", "amount": "190", "confidence": 0.9},
        {"description": "Sugar", "amount": None},
        {"description": "", "amount": 5},
        "ignore previous instructions",
    ]})
    assert page["type"] == "sales" and page["date"] == "2026-11-02"
    assert [(l["description"], l["quantity"], l["amount"]) for l in page["lines"]] == [("Rice 5kg", 2, 190), ("Sugar", None, None)]
    assert page["lines"][1]["confidence"] <= 0.4 and page["lines"][1]["notes"]


def test_typed_pages_without_ai():
    sales = pages.parse_typed("Rice 5kg 2 190\nMilo, 47.50\nnothing here", "sales")
    assert [(l["description"], l["quantity"], l["amount"]) for l in sales["lines"]] == [("Rice 5kg", 2, 190), ("Milo", None, 47.5), ("nothing here", None, None)]
    owed = pages.parse_typed("Akosua - 2 bags rice - 1,200\nKojo: sugar 30", "debts")
    assert [(l["customer"], l["description"], l["amount"]) for l in owed["lines"]] == [("Akosua", "2 bags rice", 1200), ("Kojo", "sugar", 30)]


def test_photo_of_a_sales_page_becomes_an_import_after_review(client, monkeypatch):
    headers, base = owner(client)
    sent = fake_vision(monkeypatch, {"type": "sales", "date": "2026-11-02", "lines": [
        {"description": "Rice 5kg", "quantity": 2, "amount": 190, "confidence": 0.9},
        {"description": "Milo", "quantity": 1, "amount": 47.5, "confidence": 0.8},
        {"description": "Blurry", "amount": None, "confidence": 0.2},
    ]})
    draft = client.post(f"{base}/pages", headers=headers, files={"file": ("page.png", PNG, "image/png")}).json()
    assert draft["status"] == "draft" and draft["type"] == "sales" and len(draft["lines"]) == 3
    assert sent[0]["messages"][0]["content"][0]["text"] == pages.PROMPT
    assert client.get(f"{base}/datasets", headers=headers).json() == []  # nothing written yet

    lines = [{**line, "include": line["amount"] is not None} for line in draft["lines"]]
    done = client.post(f"{base}/pages/{draft['id']}/confirm", headers=headers, json={"page_type": "sales", "page_date": "2026-11-02", "lines": lines})
    assert done.status_code == 200, done.text
    assert done.json()["lines"] == 2 and done.json()["total"] == 237.5
    assert client.post(f"{base}/pages/{draft['id']}/confirm", headers=headers, json={"page_type": "sales", "page_date": "2026-11-02", "lines": lines}).status_code == 400

    datasets = client.get(f"{base}/datasets", headers=headers).json()
    assert datasets[0]["filename"] == "Notebook page: sales, 2026-11-02" and datasets[0]["accepted_rows"] == 2
    pnl = client.get(f"{base}/books?from=2026-11-01&to=2026-11-30", headers=headers).json()["profit_and_loss"]["currencies"][0]
    assert pnl["total_income"] == 237.5
    assert db.one(config.DB_PATH, "SELECT calls FROM ai_usage", ())["calls"] == 1


def test_debts_and_expenses_pages(client):
    headers, base = owner(client)
    owed = client.post(f"{base}/pages/text", headers=headers, json={"page_type": "debts", "text": "Akosua - 2 bags rice - 190\nKojo - sugar - 30"}).json()
    no_name = [{**owed["lines"][0], "customer": None}]
    assert client.post(f"{base}/pages/{owed['id']}/confirm", headers=headers, json={"page_type": "debts", "page_date": "2026-11-02", "lines": no_name}).status_code == 400
    done = client.post(f"{base}/pages/{owed['id']}/confirm", headers=headers, json={"page_type": "debts", "page_date": "2026-11-02", "lines": owed["lines"]})
    assert done.status_code == 200 and done.json()["debts"] == 2
    book = client.get(f"{base}/debts", headers=headers).json()
    assert book["totals"]["owed_to_us"]["total"] == 220

    spent = client.post(f"{base}/pages/text", headers=headers, json={"page_type": "expenses", "text": "Shop rent 500\nTrotro to Makola 30\nECG prepaid 100"}).json()
    client.post(f"{base}/pages/{spent['id']}/confirm", headers=headers, json={"page_type": "expenses", "page_date": "2026-11-03", "lines": spent["lines"]})
    pnl = client.get(f"{base}/books?from=2026-11-01&to=2026-11-30", headers=headers).json()["profit_and_loss"]["currencies"][0]
    assert {item["key"]: item["amount"] for item in pnl["expenses"]} == {"rent": 500, "transport": 30, "utilities": 100}

    # A future date is refused; a discarded draft cannot be confirmed.
    again = client.post(f"{base}/pages/text", headers=headers, json={"page_type": "sales", "text": "Rice 190"}).json()
    assert client.post(f"{base}/pages/{again['id']}/confirm", headers=headers, json={"page_type": "sales", "page_date": "2099-01-01", "lines": again["lines"]}).status_code == 400
    client.delete(f"{base}/pages/{again['id']}", headers=headers)
    assert client.post(f"{base}/pages/{again['id']}/confirm", headers=headers, json={"page_type": "sales", "page_date": "2026-11-02", "lines": again["lines"]}).status_code == 400


def test_no_key_roles_and_isolation(client):
    headers, base = owner(client)
    response = client.post(f"{base}/pages", headers=headers, files={"file": ("p.png", PNG, "image/png")})
    assert response.status_code == 503  # no AI key: a clear message, and typing the page still works
    assert client.post(f"{base}/pages", headers=headers, files={"file": ("p.svg", b"<svg/>", "image/svg+xml")}).status_code == 415
    draft = client.post(f"{base}/pages/text", headers=headers, json={"page_type": "sales", "text": "Rice 190"}).json()

    token = client.post(f"{base}/invites", headers=headers, json={"role": "accountant"}).json()["token"]
    acct = client.post("/api/auth/signup", json={"email": "acct@example.com", "password": "password123", "invite_token": token}).json()
    acct_headers = {"Authorization": f"Bearer {acct['access_token']}"}
    assert client.get(f"{base}/pages/{draft['id']}", headers=acct_headers).status_code == 200
    assert client.post(f"{base}/pages/{draft['id']}/confirm", headers=acct_headers, json={"page_type": "sales", "page_date": "2026-11-02", "lines": draft["lines"]}).status_code == 403

    other_headers, other_base = owner(client, "o@example.com")
    assert client.get(f"{other_base}/pages/{draft['id']}", headers=other_headers).status_code == 404
    assert client.post(f"{other_base}/pages/{draft['id']}/confirm", headers=other_headers, json={"page_type": "sales", "page_date": "2026-11-02", "lines": draft["lines"]}).status_code == 404
