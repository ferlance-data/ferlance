from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import config, db, debts, main


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


def debt(client, headers, base, **fields):
    body = {"direction": "owed_to_us", "party_name": "Akosua", "amount": 200, "issued_on": "2026-10-02", "basis": "new_sale", **fields}
    response = client.post(f"{base}/debts", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def ledger_lines(client, headers, base, window="from=2026-01-01&to=2026-12-31"):
    result = client.get(f"{base}/books?{window}", headers=headers).json()
    sheet = result["balance_sheet"]["currencies"][0] if result["balance_sheet"]["currencies"] else {"assets": [], "liabilities": [], "equity": [], "balanced": True}
    by_key = {item["key"]: item["amount"] for group in ("assets", "liabilities", "equity") for item in sheet[group]}
    return result, by_key, sheet["balanced"]


def test_credit_sale_part_payment_ageing_and_ledger_match(client):
    headers, base = owner(client)
    first = debt(client, headers, base, party_name="Akosua", phone="024 412 3456", description="2 bags rice", due_on="2026-10-09")
    debt(client, headers, base, party_name="akosua", amount=50, issued_on="2026-11-01", basis="recorded_sale")  # same person, other spelling
    debt(client, headers, base, direction="we_owe", party_name="Kofi Wholesale", amount=700, basis="recorded_purchase", issued_on="2026-10-05")
    assert client.post(f"{base}/debts/{first}/payments", headers=headers, json={"amount": 80, "paid_on": "2026-10-10", "method": "cash"}).status_code == 200
    # Paying more than is owed is refused.
    over = client.post(f"{base}/debts/{first}/payments", headers=headers, json={"amount": 500, "paid_on": "2026-10-11", "method": "cash"})
    assert over.status_code == 400 and "120.00" in over.json()["detail"]

    book = debts.book(config.DB_PATH, client.get("/api/auth/me", headers=headers).json()["businesses"][0]["id"], date(2026, 11, 22))
    assert len(book["parties"]) == 2  # Akosua once, Kofi once
    assert book["totals"]["owed_to_us"]["total"] == 170.0 and book["totals"]["owed_to_us"]["open"] == 2
    assert book["totals"]["owed_to_us"]["buckets"]["31_60"] == 120.0  # due 9 Oct, 44 days late
    assert book["totals"]["owed_to_us"]["buckets"]["1_30"] == 50.0
    assert book["totals"]["we_owe"]["total"] == 700.0

    result, balances, balanced = ledger_lines(client, headers, base)
    assert balanced
    assert balances["receivables"] == 170.0 and balances["payables"] == 700.0  # the debt book equals the ledger
    assert balances["cash"] == 80.0
    assert balances["receipts_clearing"] == -50.0  # the recorded sale clears an imported line's "to allocate"
    pnl = result["profit_and_loss"]["currencies"][0]
    assert pnl["total_income"] == 200.0  # only the new credit sale is new revenue
    assert any("debt book" in item["reason"] for item in result["differences"]["explained"]) and result["differences"]["unexplained"] == 0


def test_voids_reverse_and_keep_history(client):
    headers, base = owner(client)
    debt_id = debt(client, headers, base)
    payment = client.post(f"{base}/debts/{debt_id}/payments", headers=headers, json={"amount": 50, "paid_on": "2026-10-03", "method": "momo_mtn"}).json()
    assert client.post(f"{base}/debts/payments/{payment['id']}/void", headers=headers).status_code == 200
    _, balances, _ = ledger_lines(client, headers, base)
    assert balances["receivables"] == 200.0 and "momo_mtn" not in balances
    assert client.post(f"{base}/debts/{debt_id}/void", headers=headers).status_code == 200
    _, balances, _ = ledger_lines(client, headers, base)
    assert "receivables" not in balances
    book = client.get(f"{base}/debts", headers=headers).json()
    assert book["debts"][0]["status"] == "voided" and book["debts"][0]["payments"][0]["voided"] is True
    assert client.post(f"{base}/debts/{debt_id}/payments", headers=headers, json={"amount": 5, "paid_on": "2026-10-04", "method": "cash"}).status_code == 400


def test_momo_message_settles_a_debt_without_counting_a_second_sale(client):
    headers, base = owner(client)
    debt_id = debt(client, headers, base, party_name="Kojo Mensah", phone="0244123456", amount=300, issued_on="2026-10-01")
    sms = (
        "Payment received for GHS 150.00 from Kojo Mensah (0244123456). Current Balance: GHS 2,450.00. "
        "Reference: rice. Financial Transaction Id: 18293048591. Date: 2026-10-15\n\n"
        "You have received GHS 85.50 from 233201234567 - KWAME ASANTE. Trans ID: 0092837482. Balance: GHS 1,120.00. Date: 2026-10-16"
    )
    assert client.post(f"{base}/sources/momo", headers=headers, json={"sms_text": sms}).status_code == 200
    before, _, _ = ledger_lines(client, headers, base)
    assert before["profit_and_loss"]["currencies"][0]["total_income"] == 535.5  # 300 credit sale + both messages as sales

    found = client.get(f"{base}/debts/suggestions", headers=headers).json()
    assert len(found) == 1 and found[0]["reason"] == "same phone number" and found[0]["amount"] == 150.0
    paid = client.post(f"{base}/debts/{debt_id}/payments", headers=headers, json={"momo_ref": found[0]["momo_ref"]})
    assert paid.status_code == 200 and paid.json()["balance"] == 150.0
    # The same message cannot settle twice, and is no longer suggested.
    assert client.post(f"{base}/debts/{debt_id}/payments", headers=headers, json={"momo_ref": found[0]["momo_ref"]}).status_code == 400
    assert client.get(f"{base}/debts/suggestions", headers=headers).json() == []

    after, balances, balanced = ledger_lines(client, headers, base)
    assert balanced and balances["receivables"] == 150.0
    assert after["profit_and_loss"]["currencies"][0]["total_income"] == 385.5  # the 150 is a debt payment, not a new sale
    assert balances["momo_mtn"] == 150.0
    diff = after["differences"]
    assert diff["unexplained"] == 0 and any("customer debts" in item["reason"] for item in diff["explained"])


def test_opening_balances_come_from_the_debt_book(client):
    headers, base = owner(client)
    client.post(f"{base}/financial-position/balances", headers=headers, json={"as_of_date": "2026-10-31", "category": "receivables", "account_name": "Notebook", "amount": 999})
    client.post(f"{base}/financial-position/balances", headers=headers, json={"as_of_date": "2026-10-31", "category": "cash", "account_name": "Till", "amount": 500})
    old = debt(client, headers, base, amount=300, issued_on="2026-10-01")
    client.post(f"{base}/debts/{old}/payments", headers=headers, json={"amount": 100, "paid_on": "2026-10-20", "method": "cash"})
    proposal = client.get(f"{base}/books/opening?start=2026-11-01", headers=headers).json()
    assert [line["account"] for line in proposal["lines"]] == ["cash"] and any("debt book" in note for note in proposal["notes"])
    client.post(f"{base}/books/opening", headers=headers, json={"start_date": "2026-11-01", "lines": proposal["lines"]})
    client.post(f"{base}/debts/{old}/payments", headers=headers, json={"amount": 50, "paid_on": "2026-11-05", "method": "cash"})
    result, balances, balanced = ledger_lines(client, headers, base)
    assert balanced
    assert balances["receivables"] == 150.0  # 300 - 100 before the start - 50 after
    assert balances["cash"] == 550.0  # 500 opening (already includes the October 100) + 50 in November
    assert result["profit_and_loss"]["currencies"] == []  # an old debt is not new revenue


def test_roles_validation_and_isolation(client):
    headers, base = owner(client)
    debt_id = debt(client, headers, base)
    for role, expected in (("manager", 200), ("accountant", 403)):
        token = client.post(f"{base}/invites", headers=headers, json={"role": role}).json()["token"]
        member = client.post("/api/auth/signup", json={"email": f"{role}@example.com", "password": "password123", "invite_token": token}).json()
        member_headers = {"Authorization": f"Bearer {member['access_token']}"}
        assert client.get(f"{base}/debts", headers=member_headers).status_code == 200
        assert client.post(f"{base}/debts/{debt_id}/payments", headers=member_headers, json={"amount": 1, "paid_on": "2026-10-05", "method": "cash"}).status_code == expected
        assert client.put(f"{base}/debts/settings", headers=member_headers, json={"pay_to": "MTN 0244 000 000 (Ama)"}).status_code == expected

    other_headers, other_base = owner(client, "other@example.com")
    assert client.get(f"{base}/debts", headers=other_headers).status_code == 404
    assert client.post(f"{other_base}/debts/{debt_id}/payments", headers=other_headers, json={"amount": 1, "paid_on": "2026-10-05", "method": "cash"}).status_code == 404
    assert client.post(f"{other_base}/debts/{debt_id}/void", headers=other_headers).status_code == 404
    assert client.post(f"{other_base}/debts/{debt_id}/payments", headers=other_headers, json={"momo_ref": "x:y"}).status_code == 404

    bad = (
        {"direction": "owed_to_us", "basis": "expense"},
        {"due_on": "2026-09-01"},
        {"phone": "<script>"},
        {"amount": 0},
    )
    for fields in bad:
        body = {"direction": "owed_to_us", "party_name": "X", "amount": 10, "issued_on": "2026-10-02", "basis": "new_sale", **fields}
        assert client.post(f"{base}/debts", headers=headers, json=body).status_code in (400, 422), fields
    early = client.post(f"{base}/debts/{debt_id}/payments", headers=headers, json={"amount": 1, "paid_on": "2026-01-01", "method": "cash"})
    assert early.status_code == 400
    assert client.get(f"{base}/debts", headers=headers).json()["pay_to"] == "MTN 0244 000 000 (Ama)"


def test_helpers():
    assert debts.phone_digits("024 412 3456") == "233244123456"
    assert debts.phone_digits("+233 20 123 4567") == "233201234567"
    assert debts.phone_digits("Mobile Money Customer") == ""
    today = date(2026, 11, 22)
    assert [debts.bucket(d, today) for d in ("2026-11-30", "2026-11-22", "2026-11-01", "2026-10-01", "2026-09-01", "2026-01-01")] == ["not_due", "not_due", "1_30", "31_60", "61_90", "over_90"]
