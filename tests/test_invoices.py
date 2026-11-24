import pytest
from fastapi.testclient import TestClient

from backend import config, db, main


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


def doc(client, headers, base, **fields):
    body = {"kind": "invoice", "customer_name": "Akosua Boateng", "phone": "0205551234", "issued_on": "2026-10-02",
            "lines": [{"description": "Delivery", "quantity": 1, "unit_price": 20}], **fields}
    response = client.post(f"{base}/invoices", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def balances(client, headers, base):
    sheet = client.get(f"{base}/books?from=2026-01-01&to=2026-12-31", headers=headers).json()["balance_sheet"]["currencies"]
    return {item["key"]: item["amount"] for group in ("assets", "liabilities", "equity") for item in (sheet[0][group] if sheet else [])}


def test_invoice_numbers_stock_debt_payment_and_void(client):
    headers, base = owner(client)
    rice = client.post(f"{base}/inventory/products", headers=headers, json={"name": "Rice 5kg", "unit": "bag", "unit_cost": 70, "opening_stock": 5}).json()
    first = doc(client, headers, base, due_on="2026-10-16", lines=[
        {"product_id": rice["id"], "quantity": 2, "unit_price": 95},
        {"description": "Delivery", "quantity": 1, "unit_price": 12.5},
    ])
    second = doc(client, headers, base)
    quote = doc(client, headers, base, kind="quote")
    assert (first["number"], second["number"], quote["number"]) == ("INV-0001", "INV-0002", "QUO-0001")

    invoice = client.get(f"{base}/invoices/{first['id']}", headers=headers).json()
    assert invoice["total"] == 202.5 and invoice["lines"][0]["description"] == "Rice 5kg" and invoice["status"] == "overdue"
    stock = {i["name"]: i["quantity_on_hand"] for i in client.get(f"{base}/inventory", headers=headers).json()["items"]}
    assert stock["Rice 5kg"] == 3

    # The invoice is a debt: pay part of it through the debt book.
    assert client.post(f"{base}/debts/{invoice['debt_id']}/payments", headers=headers, json={"amount": 100, "paid_on": "2026-10-05", "method": "momo_mtn"}).status_code == 200
    invoice = client.get(f"{base}/invoices/{first['id']}", headers=headers).json()
    assert invoice["paid"] == 100 and invoice["balance"] == 102.5
    books = balances(client, headers, base)
    assert books["receivables"] == 102.5 + 20 and books["momo_mtn"] == 100 and books["inventory"] == 210  # 3 bags left × 70

    # Too much stock is refused; nothing is written and the number is not used.
    short = client.post(f"{base}/invoices", headers=headers, json={"kind": "invoice", "customer_name": "Kojo", "issued_on": "2026-10-03",
                                                                   "lines": [{"product_id": rice["id"], "quantity": 9, "unit_price": 95}]})
    assert short.status_code == 409 and short.json()["detail"]["shortages"][0]["needed"] == 9
    assert doc(client, headers, base)["number"] == "INV-0003"

    # Voiding keeps the number, reverses the debt and its payment, and returns the stock.
    assert client.post(f"{base}/invoices/{first['id']}/void", headers=headers).status_code == 200
    assert client.get(f"{base}/invoices/{first['id']}", headers=headers).json()["status"] == "void"
    stock = {i["name"]: i["quantity_on_hand"] for i in client.get(f"{base}/inventory", headers=headers).json()["items"]}
    assert stock["Rice 5kg"] == 5
    books = balances(client, headers, base)
    assert books["receivables"] == 40 and "momo_mtn" not in books and books["inventory"] == 350
    result = client.get(f"{base}/books?from=2026-01-01&to=2026-12-31", headers=headers).json()
    expenses = {item["key"] for item in result["profit_and_loss"]["currencies"][0]["expenses"]}
    assert "shrinkage" not in expenses and result["differences"]["unexplained"] == 0


def test_receipts_quotes_and_conversion(client):
    headers, base = owner(client)
    receipt = doc(client, headers, base, kind="receipt", paid_by="cash", lines=[{"description": "Milo 400g", "quantity": 3, "unit_price": 47.5}])
    assert receipt["number"] == "RCT-0001"
    assert client.get(f"{base}/invoices/{receipt['id']}", headers=headers).json()["status"] == "paid"
    assert balances(client, headers, base)["cash"] == 142.5
    assert client.post(f"{base}/invoices", headers=headers, json={"kind": "receipt", "customer_name": "X", "issued_on": "2026-10-02",
                                                                  "lines": [{"description": "a", "quantity": 1, "unit_price": 1}]}).status_code == 400  # how paid?

    quote = doc(client, headers, base, kind="quote", due_on="2026-10-31")
    assert "receivables" not in balances(client, headers, base)  # a quote posts nothing
    converted = client.post(f"{base}/invoices/{quote['id']}/convert", headers=headers, json={"issued_on": "2026-10-05", "due_on": "2026-10-20"})
    assert converted.status_code == 200 and converted.json()["number"] == "INV-0001"
    assert client.post(f"{base}/invoices/{quote['id']}/convert", headers=headers, json={"issued_on": "2026-10-05"}).status_code == 400
    listed = {item["number"]: item["status"] for item in client.get(f"{base}/invoices", headers=headers).json()}
    assert listed["QUO-0001"] == "converted" and listed["INV-0001"] in ("sent", "overdue")
    assert [i["number"] for i in client.get(f"{base}/invoices?kind=quote", headers=headers).json()] == ["QUO-0001"]


def test_pdf_is_small_and_handles_cedi_and_twi_letters(client):
    headers, base = owner(client)
    client.put(f"{base}/invoices/settings", headers=headers, json={"tin": "C0012345678", "address": "Makola Market, Accra", "phone": "024 000 0000", "footer": "Thank you"})
    client.put(f"{base}/debts/settings", headers=headers, json={"pay_to": "MTN MoMo 024 000 0000 (Ama)"})
    lines = [{"description": f"Item {n} ɛɔŋ", "quantity": n, "unit_price": 12.5} for n in range(1, 40)]
    invoice = doc(client, headers, base, customer_name="Ɔkomfo Anɔkye", lines=lines)
    response = client.get(f"{base}/invoices/{invoice['id']}/pdf", headers=headers)
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF") and len(response.content) < 200_000
    assert 'filename="INV-0001.pdf"' in response.headers["content-disposition"]


def test_roles_validation_and_isolation(client):
    headers, base = owner(client)
    invoice = doc(client, headers, base)
    token = client.post(f"{base}/invites", headers=headers, json={"role": "accountant"}).json()["token"]
    acct = client.post("/api/auth/signup", json={"email": "acct@example.com", "password": "password123", "invite_token": token}).json()
    acct_headers = {"Authorization": f"Bearer {acct['access_token']}"}
    assert client.get(f"{base}/invoices/{invoice['id']}/pdf", headers=acct_headers).status_code == 200
    assert client.post(f"{base}/invoices/{invoice['id']}/void", headers=acct_headers).status_code == 403

    other_headers, other_base = owner(client, "o@example.com")
    assert client.get(f"{other_base}/invoices/{invoice['id']}", headers=other_headers).status_code == 404
    assert client.get(f"{other_base}/invoices/{invoice['id']}/pdf", headers=other_headers).status_code == 404
    assert client.post(f"{other_base}/invoices/{invoice['id']}/void", headers=other_headers).status_code == 404
    product = client.post(f"{base}/inventory/products", headers=headers, json={"name": "Rice", "unit": "bag", "opening_stock": 3}).json()
    stolen = client.post(f"{other_base}/invoices", headers=other_headers, json={"kind": "invoice", "customer_name": "X", "issued_on": "2026-10-02",
                                                                                "lines": [{"product_id": product["id"], "quantity": 1, "unit_price": 1}]})
    assert stolen.status_code == 404
    for bad in ({"issued_on": "2099-01-01"}, {"due_on": "2026-01-01"}, {"lines": [{"description": "", "quantity": 1, "unit_price": 1}]}, {"lines": [{"description": "a", "quantity": 1, "unit_price": 0}]}):
        body = {"kind": "invoice", "customer_name": "X", "issued_on": "2026-10-02", "lines": [{"description": "a", "quantity": 1, "unit_price": 1}], **bad}
        assert client.post(f"{base}/invoices", headers=headers, json=body).status_code in (400, 422), bad
