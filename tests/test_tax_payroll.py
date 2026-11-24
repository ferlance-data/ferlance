from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import config, db, main, payroll, tax


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


def balances(client, headers, base, window="from=2026-01-01&to=2026-12-31"):
    result = client.get(f"{base}/books?{window}", headers=headers).json()
    sheets = result["balance_sheet"]["currencies"]
    if not sheets:
        return result, {}, True
    sheet = sheets[0]
    return result, {item["key"]: item["amount"] for group in ("assets", "liabilities", "equity") for item in sheet[group]}, sheet["balanced"]


def test_rules_are_dated_and_calculations_match_gra_tables():
    assert tax.vat(10000, "2026-11-24").components == [("VAT", 1500), ("NHIL", 250), ("GETFund levy", 250)]
    assert tax.vat(10000, "2025-06-01").total == 2190  # the old compound regime, about 21.9%
    assert tax.paye(tax.to_minor(3000), "2026-11-01") == (40460, "paye-2026-09")  # 0 + 4 + 10 + 390.60
    assert tax.paye(tax.to_minor(60000), "2026-11-01")[0] == 1712110
    assert tax.paye(tax.to_minor(500), "2026-11-01")[0] == 0  # under the GH₵588 free band
    assert tax.paye(tax.to_minor(3000), "2026-06-01")[1] == "paye-2024"  # before September 2026
    assert tax.ssnit(tax.to_minor(100000), "2026-11-01")[:2] == (379500, 897000)  # capped at GH₵69,000
    assert tax.wht(tax.to_minor(1000), "services", "2026-11-01") == (7500, "wht-2026")
    with pytest.raises(tax.TaxError):
        tax.rule_for("vat", "2020-01-01")
    keys = {(r["key"], r["from"]) for r in tax.RULES}
    assert len(keys) == len(tax.RULES)
    for rule in tax.RULES:  # every rule cites a source
        assert rule["sources"] and all(s["url"].startswith("https://") for s in rule["sources"])


def test_vat_invoice_books_tax_to_gra_not_sales(client):
    headers, base = owner(client)
    invoice = client.post(f"{base}/invoices", headers=headers, json={
        "kind": "invoice", "customer_name": "Kofi Stores", "issued_on": "2026-11-10", "charge_vat": True,
        "lines": [{"description": "Cement 50kg", "quantity": 10, "unit_price": 100}],
    }).json()
    doc = client.get(f"{base}/invoices/{invoice['id']}", headers=headers).json()
    assert (doc["net"], doc["tax"], doc["total"], doc["tax_rule"]) == (1000, 200, 1200, "vat-2026")
    assert [t["name"] for t in doc["taxes"]] == ["VAT", "NHIL", "GETFund levy"]
    result, books, balanced = balances(client, headers, base)
    assert balanced and books["receivables"] == 1200 and books["tax_payable"] == 200
    assert result["profit_and_loss"]["currencies"][0]["total_income"] == 1000
    pdf = client.get(f"{base}/invoices/{invoice['id']}/pdf", headers=headers)
    assert pdf.status_code == 200 and len(pdf.content) < 200_000
    summary = client.get(f"{base}/tax/summary?from=2026-11-01&to=2026-11-30", headers=headers).json()
    assert summary["vat_total"] == 200 and summary["unchecked_rules"] == ["vat-2026"]


def test_withholding_on_supplier_payment(client):
    headers, base = owner(client)
    debt = client.post(f"{base}/debts", headers=headers, json={"direction": "we_owe", "party_name": "Kofi Wholesale", "amount": 1000,
                                                              "issued_on": "2026-11-02", "basis": "expense", "description": "Shop repairs"}).json()["id"]
    paid = client.post(f"{base}/debts/{debt}/payments", headers=headers, json={"amount": 1000, "paid_on": "2026-11-05", "method": "bank", "withhold": "services"}).json()
    assert paid["withheld"] == 75 and paid["paid_out"] == 925 and paid["balance"] == 0
    _, books, balanced = balances(client, headers, base)
    assert balanced and books["bank"] == -925 and books["wht_payable"] == 75 and "payables" not in books
    summary = client.get(f"{base}/tax/summary?from=2026-11-01&to=2026-11-30", headers=headers).json()
    assert summary["wht"] == [{"kind": "services", "amount": 75}]
    # Withholding only applies to payments you make, not to customers paying you.
    sale = client.post(f"{base}/debts", headers=headers, json={"direction": "owed_to_us", "party_name": "A", "amount": 100, "issued_on": "2026-11-02", "basis": "new_sale"}).json()["id"]
    assert client.post(f"{base}/debts/{sale}/payments", headers=headers, json={"amount": 100, "paid_on": "2026-11-05", "method": "cash", "withhold": "goods"}).status_code == 400


def test_payroll_run_post_payslip_and_void(client):
    headers, base = owner(client)
    for name, basic, allowance in (("Abena Mensah", 3000, 0), ("Ɔkomfo Yaw", 1500, 200)):
        assert client.post(f"{base}/payroll/employees", headers=headers, json={"name": name, "basic": basic, "allowances": allowance, "ssnit_number": "C123"}).status_code == 200
    run = client.post(f"{base}/payroll/runs", headers=headers, json={"month": "2026-11"}).json()
    assert client.post(f"{base}/payroll/runs", headers=headers, json={"month": "2026-11"}).status_code == 400  # one per month
    detail = client.get(f"{base}/payroll/runs/{run['id']}", headers=headers).json()
    abena = next(line for line in detail["lines"] if line["name"] == "Abena Mensah")
    expected = payroll.calculate(300000, 0, date(2026, 11, 1))
    assert abena["ssnit_employee"] == 165 and abena["ssnit_employer"] == 390 and abena["paye"] == expected["paye"] / 100 and abena["net"] == expected["net"] / 100
    assert set(detail["unchecked_rules"]) == {"paye-2026-09", "ssnit-2026"}

    _, before, _ = balances(client, headers, base)
    assert "wages" not in before  # a draft posts nothing
    assert client.post(f"{base}/payroll/runs/{run['id']}/post", headers=headers, json={"paid_from": "bank", "paid_on": "2026-11-23"}).status_code == 200
    result, books, balanced = balances(client, headers, base)
    totals = detail["totals"]
    assert balanced and books["bank"] == -totals["net"] and books["paye_payable"] == totals["paye"]
    assert books["ssnit_payable"] == round(totals["ssnit_employee"] + totals["ssnit_employer"], 2)
    expenses = {item["key"]: item["amount"] for item in result["profit_and_loss"]["currencies"][0]["expenses"]}
    assert expenses == {"wages": totals["gross"], "ssnit_employer": totals["ssnit_employer"]}

    slip = client.get(f"{base}/payroll/runs/{run['id']}/payslips/{detail['lines'][1]['id']}", headers=headers)
    assert slip.status_code == 200 and slip.content.startswith(b"%PDF") and "payslip-2026-11-" in slip.headers["content-disposition"]

    assert client.post(f"{base}/tax/rules/paye-2026-09/check", headers=headers, json={"checked": True}).status_code == 405
    assert client.put(f"{base}/tax/rules/paye-2026-09/check", headers=headers, json={"checked": True}).status_code == 200
    rules = {r["id"]: r for r in client.get(f"{base}/tax/rules", headers=headers).json()}
    assert rules["paye-2026-09"]["checked"]["checked_by"] == "ama@example.com" and rules["ssnit-2026"]["checked"] is None

    assert client.post(f"{base}/payroll/runs/{run['id']}/void", headers=headers).status_code == 200
    _, books, _ = balances(client, headers, base)
    assert "wages" not in books and "paye_payable" not in books
    assert client.post(f"{base}/payroll/runs", headers=headers, json={"month": "2026-11"}).status_code == 200  # can run again


def test_salaries_are_private_and_isolated(client):
    headers, base = owner(client)
    client.post(f"{base}/payroll/employees", headers=headers, json={"name": "Abena", "basic": 3000})
    for role, expected in (("accountant", 200), ("manager", 403)):
        token = client.post(f"{base}/invites", headers=headers, json={"role": role}).json()["token"]
        member = client.post("/api/auth/signup", json={"email": f"{role}@example.com", "password": "password123", "invite_token": token}).json()
        member_headers = {"Authorization": f"Bearer {member['access_token']}"}
        assert client.get(f"{base}/payroll/employees", headers=member_headers).status_code == expected
        assert client.get(f"{base}/tax/rules", headers=member_headers).status_code == 200
    other_headers, other_base = owner(client, "o@example.com")
    employee = client.get(f"{base}/payroll/employees", headers=headers).json()[0]["id"]
    assert client.put(f"{other_base}/payroll/employees/{employee}", headers=other_headers, json={"name": "X", "basic": 1}).status_code == 404
    assert client.get(f"{other_base}/payroll/employees", headers=other_headers).json() == []
