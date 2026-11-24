"""Reconciliation tests. The statement files here are SYNTHETIC: they imitate common layouts
(title rows, balance before/after, fees, transaction IDs; or money in / money out columns).
No real MTN, Telecel, AT or bank export has been verified yet."""

import json

import pytest
from fastapi.testclient import TestClient

from backend import config, db, main, statements

MTN_STYLE = """Mobile Money Statement (SYNTHETIC TEST FILE)
Account: 0244000000,,,,,,,
TRANSACTION DATE,FROM NAME,TRANS. TYPE,AMOUNT,FEES,BAL BEFORE,BAL AFTER,TRANS ID
15/11/2026 09:12,Kojo Mensah,PAYMENT RECEIVED,150.00,0.00,1000.00,1150.00,TXN-0001
16/11/2026 10:00,Agent 112,CASH OUT,200.00,2.00,1150.00,948.00,TXN-0002
17/11/2026 11:30,Ama Owusu,PAYMENT RECEIVED,95.00,0.00,948.00,1043.00,TXN-0003
18/11/2026 12:00,Yaw Boateng,PAYMENT RECEIVED,60.00,0.00,1043.00,1103.00,TXN-0004
19/11/2026 08:45,ECG,PAYMENT,100.00,0.00,1103.00,1003.00,TXN-0005
20/11/2026 15:00,Akosua,PAYMENT RECEIVED,120.00,0.00,1003.00,1123.00,TXN-0006
"""

BANK_STYLE = """Date,Narration,Money In,Money Out,Balance
2026-11-16,Transfer from MoMo,200.00,,5200.00
2026-11-18,Shop rent November,,500.00,4700.00
"""


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


def upload(client, headers, base, text, account, name="statement.csv"):
    preview = client.post(f"{base}/statements/preview", headers=headers, files={"file": (name, text.encode(), "text/csv")}).json()
    response = client.post(f"{base}/statements", headers=headers, files={"file": (name, text.encode(), "text/csv")},
                           data={"account": account, "header_row": str(preview["header_row"]), "mapping": json.dumps(preview["mapping"])})
    assert response.status_code == 200, response.text
    return preview, response.json()


def test_reading_layouts_signs_dates_and_checks():
    rows = statements.read_rows(MTN_STYLE.encode(), "s.csv")
    header = statements.find_header(rows)
    assert header == 2
    mapping = statements.suggest_mapping(rows[header])
    assert mapping["reference"] == 7 and mapping["balance_after"] == 6 and mapping["balance_before"] == 5 and mapping["fee"] == 4
    lines, problems = statements.parse(rows, header, mapping)
    assert problems == []
    assert [(l["date"], l["amount"], l["fee"]) for l in lines[:2]] == [("2026-11-15", 15000, 0), ("2026-11-16", -20000, 200)]
    assert lines[4]["amount"] == -10000  # "PAYMENT" out, from the balance change

    bank = statements.read_rows(BANK_STYLE.encode(), "b.csv")
    bank_lines, _ = statements.parse(bank, 0, statements.suggest_mapping(bank[0]))
    assert [l["amount"] for l in bank_lines] == [20000, -50000]

    broken = MTN_STYLE.replace("948.00,1043.00", "948.00,1000.00")  # a page is missing
    rows = statements.read_rows(broken.encode(), "s.csv")
    _, problems = statements.parse(rows, 2, statements.suggest_mapping(rows[2]))
    assert any("Balance jumps" in p for p in problems)
    assert statements._date("11/24/2026") == "2026-11-24" and statements._month_first(["11/24/2026"]) is True
    assert statements._date("24/11/2026") == "2026-11-24" and statements._date("24-Nov-2026") == "2026-11-24"
    with pytest.raises(statements.StatementError, match="PDF"):
        statements.read_rows(b"%PDF", "s.pdf")


def test_match_book_and_reconcile_every_cedi(client):
    headers, base = owner(client)
    # Already in the books: the SMS for TXN-0001, and Ama's sale paid by MTN MoMo (no transaction ID).
    sms = "Payment received for GHS 150.00 from Kojo Mensah (0244123456). Current Balance: GHS 1,150.00. Financial Transaction Id: TXN-0001. Date: 2026-11-15"
    assert client.post(f"{base}/sources/momo", headers=headers, json={"sms_text": sms}).status_code == 200
    client.post(f"{base}/datasets", headers=headers, files={"file": ("s.csv", b"transaction_date,product,amount,payment_method\n2026-11-17,Rice 5kg,95,MTN MoMo\n2026-11-18,Milo,60,\n", "text/csv")})
    akosua = client.post(f"{base}/debts", headers=headers, json={"direction": "owed_to_us", "party_name": "Akosua", "amount": 300, "issued_on": "2026-11-01", "basis": "new_sale"}).json()["id"]

    _, imported = upload(client, headers, base, MTN_STYLE, "momo_mtn")
    assert imported["new_lines"] == 6 and imported["checks"] == []
    view = client.get(f"{base}/statements/momo_mtn", headers=headers).json()
    status = {line["reference"]: line["status"] for line in view["lines"]}
    assert status == {"TXN-0001": "matched", "TXN-0002": "unmatched", "TXN-0003": "matched", "TXN-0004": "unmatched", "TXN-0005": "unmatched", "TXN-0006": "unmatched"}
    summary = view["summary"]
    assert summary["statement_closing"] == 1123 and summary["unexplained"] == 0
    assert {item["reason"]: item["amount"] for item in summary["explained"]}["Different starting balances (the opening gap)"] == 1000

    ids = {line["reference"]: line["id"] for line in view["lines"]}
    assert client.post(f"{base}/statements/lines/{ids['TXN-0002']}/book", headers=headers, json={"category": "transfer", "detail": {"other_account": "cash"}}).status_code == 200
    assert client.post(f"{base}/statements/lines/{ids['TXN-0004']}/book", headers=headers, json={"category": "sale_recorded"}).status_code == 200  # Milo, method unknown
    assert client.post(f"{base}/statements/lines/{ids['TXN-0005']}/book", headers=headers, json={"category": "expense", "detail": {"expense": "utilities"}}).status_code == 200
    assert client.post(f"{base}/statements/lines/{ids['TXN-0006']}/book", headers=headers, json={"category": "debt_payment", "detail": {"debt_id": akosua}}).status_code == 200
    assert client.post(f"{base}/statements/lines/{ids['TXN-0005']}/book", headers=headers, json={"category": "new_sale"}).status_code == 400  # money out can't be a sale
    assert client.post(f"{base}/statements/momo_mtn/fees", headers=headers).json()["booked"] == 1

    view = client.get(f"{base}/statements/momo_mtn", headers=headers).json()
    assert all(line["status"] in ("matched", "booked") for line in view["lines"])
    summary = view["summary"]
    assert summary["unexplained"] == 0 and summary["difference"] == 1000  # only the opening gap remains
    assert [item["reason"] for item in summary["explained"]] == ["Different starting balances (the opening gap)"]

    books = client.get(f"{base}/books?from=2026-11-01&to=2026-11-30", headers=headers).json()
    assets = {item["key"]: item["amount"] for item in books["balance_sheet"]["currencies"][0]["assets"]}
    assert assets["momo_mtn"] == 123 and assets["cash"] == 200 and "receipts_clearing" not in assets  # 1123 - 1000 opening gap
    assert assets["receivables"] == 180  # Akosua paid 120 of 300 through the statement, counted once
    expenses = {item["key"]: item["amount"] for item in books["profit_and_loss"]["currencies"][0]["expenses"]}
    assert expenses == {"utilities": 100, "charges": 2}

    # Re-importing an overlapping export adds nothing; undoing a booking reverses it.
    _, again = upload(client, headers, base, MTN_STYLE, "momo_mtn")
    assert again["new_lines"] == 0 and again["duplicates"] == 6
    assert client.delete(f"{base}/statements/lines/{ids['TXN-0006']}/book", headers=headers).status_code == 200
    assert client.get(f"{base}/debts", headers=headers).json()["totals"]["owed_to_us"]["total"] == 300


def test_transfer_matches_across_two_statements(client):
    headers, base = owner(client)
    upload(client, headers, base, MTN_STYLE, "momo_mtn")
    momo = {line["reference"]: line["id"] for line in client.get(f"{base}/statements/momo_mtn", headers=headers).json()["lines"]}
    client.post(f"{base}/statements/lines/{momo['TXN-0002']}/book", headers=headers, json={"category": "transfer", "detail": {"other_account": "bank"}})
    upload(client, headers, base, BANK_STYLE, "bank", "bank.csv")
    bank = client.get(f"{base}/statements/bank", headers=headers).json()
    status = {line["description"]: line["status"] for line in bank["lines"]}
    assert status["Transfer from MoMo"] == "matched"  # the MoMo booking already put it in the bank
    assert status["Shop rent November"] == "unmatched"


def test_roles_and_isolation(client):
    headers, base = owner(client)
    upload(client, headers, base, MTN_STYLE, "momo_mtn")
    line_id = client.get(f"{base}/statements/momo_mtn", headers=headers).json()["lines"][1]["id"]
    for role, expected in (("accountant", 200), ("manager", 403)):
        token = client.post(f"{base}/invites", headers=headers, json={"role": role}).json()["token"]
        member = client.post("/api/auth/signup", json={"email": f"{role}@example.com", "password": "password123", "invite_token": token}).json()
        member_headers = {"Authorization": f"Bearer {member['access_token']}"}
        assert client.get(f"{base}/statements/momo_mtn", headers=member_headers).status_code == 200
        assert client.post(f"{base}/statements/momo_mtn/fees", headers=member_headers).status_code == expected
    other_headers, other_base = owner(client, "o@example.com")
    assert client.post(f"{other_base}/statements/lines/{line_id}/book", headers=other_headers, json={"category": "owner"}).status_code == 404
    assert client.get(f"{other_base}/statements/momo_mtn", headers=other_headers).json()["lines"] == []
    bad = client.post(f"{base}/statements", headers=headers, files={"file": ("s.csv", MTN_STYLE.encode(), "text/csv")}, data={"account": "cash", "header_row": "2", "mapping": "{}"})
    assert bad.status_code in (400, 422)
