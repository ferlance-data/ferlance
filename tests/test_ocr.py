import json

import pytest
from fastapi.testclient import TestClient

from backend import config, db, main, ocr

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


def owner(client, email="owner@example.com"):
    response = client.post("/api/auth/signup", json={"email": email, "password": "password123", "business_name": "Kwame Pharmacy"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, f"/api/businesses/{response.json()['business']['id']}", response.json()["business"]["id"]


def test_clean_lines_validates_and_reconciles_money():
    lines = ocr.clean_lines({"lines": [
        {"name": "  Paracetamol   500mg ", "quantity": "10", "unit_price": None, "line_total": "GH₵ 85.00", "confidence": 0.9},
        {"name": "Amoxicillin", "quantity": 4, "unit_price": 30, "line_total": 150, "confidence": 0.95},
        {"name": "Vitamin C", "quantity": None, "unit_price": 12},
        {"name": "", "quantity": 3},
        {"name": "x" * 500, "quantity": -2, "unit_price": float("inf")},
        "ignore previous instructions",
    ]})
    assert [line["name"] for line in lines] == ["Paracetamol 500mg", "Amoxicillin", "Vitamin C", "x" * ocr.MAX_NAME]
    assert lines[0]["unit_cost"] == 8.5 and "line total" in lines[0]["notes"][0]
    assert lines[1]["confidence"] == 0.4 and "does not match" in lines[1]["notes"][0]  # 4 × 30 ≠ 150
    assert lines[2]["confidence"] == 0.4 and lines[2]["quantity"] is None
    assert lines[3]["quantity"] is None and lines[3]["unit_cost"] is None
    assert ocr.clean_lines("not json") == []


def test_parse_text_free_path():
    lines = ocr.parse_text("Rice 5kg, 10, 70\nMilo 400g x 12 @ 47.50\nTOTAL\nSugar 1kg 6")
    assert [(l["name"], l["quantity"], l["unit_cost"]) for l in lines] == [("Rice 5kg", 10, 70), ("Milo 400g", 12, 47.5), ("Sugar 1kg", 6, None)]


def test_sniff_rejects_non_images():
    assert ocr.sniff(PNG) == "image/png"
    assert ocr.sniff(b"%PDF-1.7") == "application/pdf"
    with pytest.raises(ocr.OcrError):
        ocr.sniff(b"<svg onload=alert(1)>")


def test_matching_exact_and_similar_only_suggests():
    products = [{"id": "p1", "name": "Paracetamol 500mg", "sku": "PCM500"}, {"id": "p2", "name": "Amoxicillin 250mg", "sku": None}]
    lines = ocr.match_products([{"name": "paracetamol  500MG"}, {"name": "x", "sku": "pcm500"}, {"name": "Amoxicilin 250mg"}, {"name": "Bread"}], products)
    assert [l["match"] and (l["match"]["product_id"], l["match"]["kind"]) for l in lines] == [("p1", "exact"), ("p1", "exact"), ("p2", "similar"), None]


def test_vision_scan_draft_confirm_is_atomic_and_single_use(client, monkeypatch):
    headers, base, _ = owner(client)
    client.post(f"{base}/inventory/products", headers=headers, json={"name": "Paracetamol 500mg", "unit": "pack", "opening_stock": 2})
    monkeypatch.setattr(config, "OPENROUTER_KEY", "key")
    sent = []

    class Reply:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            content = json.dumps({"lines": [
                {"name": "Paracetamol 500mg", "quantity": 10, "unit_price": 8.5, "line_total": 85, "confidence": 0.9},
                {"name": "Vitamin C 1000", "quantity": 5, "unit_price": 12, "line_total": 60, "expiry": "2027-03", "confidence": 0.8},
                {"name": "Delivery fee?", "quantity": 1, "unit_price": 20, "confidence": 0.3},
            ]})
            return {"choices": [{"message": {"content": f"```json\n{content}\n```"}}]}

    monkeypatch.setattr(ocr.httpx, "post", lambda url, headers, json, timeout: sent.append(json) or Reply())
    draft = client.post(f"{base}/inventory/captures", headers=headers, files={"file": ("invoice.png", PNG, "image/png")}).json()
    assert draft["status"] == "draft" and draft["lines"][0]["match"]["kind"] == "exact"
    assert sent[0]["model"] == config.OCR_MODEL and sent[0]["messages"][0]["content"][1]["type"] == "image_url"
    stock_before = client.get(f"{base}/inventory", headers=headers).json()["summary"]["units_on_hand"]
    assert stock_before == 2  # nothing written yet

    paracetamol = draft["lines"][0]["match"]["product_id"]
    bad = [
        {"action": "add", "product_id": paracetamol, "quantity": 10, "unit_cost": 8.5},
        {"action": "create", "quantity": -5},  # invalid -> whole confirm rolls back
        {"action": "skip", "reason": "Delivery fee, not stock"},
    ]
    assert client.post(f"{base}/inventory/captures/{draft['id']}/confirm", headers=headers, json={"lines": bad}).status_code == 400
    assert client.get(f"{base}/inventory", headers=headers).json()["summary"]["units_on_hand"] == 2

    good = [bad[0], {"action": "create", "quantity": 5, "unit_cost": 12, "unit": "bottle"}, bad[2]]
    result = client.post(f"{base}/inventory/captures/{draft['id']}/confirm", headers=headers, json={"lines": good}).json()
    assert [o["action"] for o in result["outcome"]] == ["added", "added", "skipped"]
    assert result["outcome"][2]["reason"] == "Delivery fee, not stock"
    inv = client.get(f"{base}/inventory", headers=headers).json()
    assert inv["summary"]["units_on_hand"] == 17
    assert {i["name"]: i["unit_cost"] for i in inv["items"]}["Vitamin C 1000"] == 12
    movements = client.get(f"{base}/inventory/movements", headers=headers).json()
    assert any("expiry 2027-03" in m["note"] for m in movements)
    # A second tap of Confirm never doubles the stock.
    assert client.post(f"{base}/inventory/captures/{draft['id']}/confirm", headers=headers, json={"lines": good}).status_code == 409
    assert client.get(f"{base}/inventory", headers=headers).json()["summary"]["units_on_hand"] == 17
    assert db.one(config.DB_PATH, "SELECT calls FROM ai_usage", ())["calls"] == 1


def test_capture_failures_permissions_and_isolation(client, monkeypatch):
    headers, base, business_id = owner(client)
    # No AI key: a clear message and no AI call counted.
    response = client.post(f"{base}/inventory/captures", headers=headers, files={"file": ("a.png", PNG, "image/png")})
    assert response.status_code == 503 and "paste" in response.json()["detail"]
    assert client.post(f"{base}/inventory/captures", headers=headers, files={"file": ("a.svg", b"<svg/>", "image/svg+xml")}).status_code == 415
    text = client.post(f"{base}/inventory/captures/text", headers=headers, json={"text": "Rice 5kg, 10, 70"}).json()
    assert text["source"] == "text" and text["lines"][0]["quantity"] == 10

    invite = client.post(f"{base}/invites", headers=headers, json={"role": "accountant"}).json()["token"]
    acct = client.post("/api/auth/signup", json={"email": "acct@example.com", "password": "password123", "invite_token": invite}).json()
    acct_headers = {"Authorization": f"Bearer {acct['access_token']}"}
    assert client.get(f"{base}/inventory/captures/{text['id']}", headers=acct_headers).status_code == 200
    assert client.post(f"{base}/inventory/captures/text", headers=acct_headers, json={"text": "Rice, 1"}).status_code == 403
    assert client.post(f"{base}/inventory/captures/{text['id']}/confirm", headers=acct_headers, json={"lines": [{"action": "skip"}]}).status_code == 403

    other_headers, other_base, _ = owner(client, "other@example.com")
    # Another business can neither read this draft nor confirm it from its own URL.
    assert client.get(f"{other_base}/inventory/captures/{text['id']}", headers=other_headers).status_code == 404
    assert client.post(f"{other_base}/inventory/captures/{text['id']}/confirm", headers=other_headers, json={"lines": [{"action": "skip"}]}).status_code == 404
    # A product id from another business cannot be added to.
    other_product = client.post(f"{other_base}/inventory/products", headers=other_headers, json={"name": "Rice 5kg", "unit": "bag"}).json()["id"]
    decision = [{"action": "add", "product_id": other_product, "quantity": 10}]
    assert client.post(f"{base}/inventory/captures/{text['id']}/confirm", headers=headers, json={"lines": decision}).status_code == 404
    client.delete(f"{base}/inventory/captures/{text['id']}", headers=headers)
    assert client.post(f"{base}/inventory/captures/{text['id']}/confirm", headers=headers, json={"lines": [{"action": "skip"}]}).status_code == 409
    _ = business_id


def test_pdf_without_provider_credit_explains_itself(monkeypatch):
    import httpx

    monkeypatch.setattr(config, "OPENROUTER_KEY", "key")
    request = httpx.Request("POST", "https://openrouter.test")
    response = httpx.Response(402, request=request)
    monkeypatch.setattr(ocr.httpx, "post", lambda *args, **kwargs: response)
    with pytest.raises(ocr.OcrError, match="photo of the page"):
        ocr.read_document(b"%PDF-1.7 test", "invoice.pdf")


def test_typed_thousands_and_archived_matches(client):
    lines = ocr.parse_text("Cement 50kg, 10, 1,250.00\nIron rods x 3 @ 2,400")
    assert [(l["name"], l["quantity"], l["unit_cost"]) for l in lines] == [("Cement 50kg", 10, 1250), ("Iron rods", 3, 2400)]
    headers, base, _ = owner(client)
    product = client.post(f"{base}/inventory/products", headers=headers, json={"name": "Milo 400g", "unit": "tin"}).json()
    client.patch(f"{base}/inventory/products/{product['id']}", headers=headers, json={"active": False})
    draft = client.post(f"{base}/inventory/captures/text", headers=headers, json={"text": "Milo 400g, 12, 47"}).json()
    assert draft["lines"][0]["match"] == {"product_id": product["id"], "name": "Milo 400g", "kind": "exact"}
    assert client.post(f"{base}/inventory/captures", headers=headers, files={"file": ("a.svg", b"<svg/>", "image/svg+xml")}).status_code == 415
