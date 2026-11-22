import sqlite3
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend import config, db, ledger, main


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


def upload(client, headers, base, text, name="sales.csv"):
    response = client.post(f"{base}/datasets", headers=headers, files={"file": (name, text.encode(), "text/csv")})
    assert response.status_code == 200, response.text
    return response.json()


def books(client, headers, base, window="from=2026-10-01&to=2026-11-30"):
    response = client.get(f"{base}/books?{window}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def lines_of(block, group):
    return {item["key"] or item["name"]: item["amount"] for item in block[group]}


SALES = (
    "transaction_date,product,quantity,amount,cost,payment_method\n"
    "2026-10-01,Rice 5kg,2,190,140,cash\n"
    "2026-10-02,Rice 5kg,1,95,70,MTN MoMo\n"
    "2026-10-03,Oil 1L,3,96,60,bank transfer\n"
    "2026-10-04,Milo,1,50,30,\n"
    "2026-10-05,Rice 5kg,-1,-95,-70,cash\n"  # a refund
)


# ---------------------------------------------------------------- the database enforces double entry


def test_database_refuses_unbalanced_or_changed_entries(client):
    _, _, business_id = owner(client)
    with db.connection(config.DB_PATH) as conn:
        accounts = ledger.ensure_accounts(conn, business_id)

    def draft(conn, amounts):
        entry = str(uuid.uuid4())
        conn.execute("INSERT INTO journal_entries (id, business_id, entry_date, memo, source_key, kind, created_at) VALUES (?, ?, '2026-10-01', 't', 't', 'manual', 'now')", (entry, business_id))
        for account, amount in amounts:
            conn.execute("INSERT INTO journal_lines (id, entry_id, business_id, account_id, currency, amount_minor) VALUES (?, ?, ?, ?, 'GHS', ?)", (str(uuid.uuid4()), entry, business_id, accounts[account], amount))
        return entry

    for amounts in ([("cash", 100), ("sales", -90)], [("cash", 100)]):
        with pytest.raises(sqlite3.IntegrityError, match="does not balance"):
            with db.connection(config.DB_PATH) as conn:
                entry = draft(conn, amounts)
                conn.execute("UPDATE journal_entries SET status = 'posted' WHERE id = ?", (entry,))
    with db.connection(config.DB_PATH) as conn:
        entry = draft(conn, [("cash", 100), ("sales", -100)])
        conn.execute("UPDATE journal_entries SET status = 'posted' WHERE id = ?", (entry,))
    for statement, params in (
        ("UPDATE journal_entries SET memo = 'x' WHERE id = ?", (entry,)),
        ("DELETE FROM journal_entries WHERE id = ?", (entry,)),
        ("UPDATE journal_lines SET amount_minor = 5 WHERE entry_id = ?", (entry,)),
        ("DELETE FROM journal_lines WHERE entry_id = ?", (entry,)),
        ("INSERT INTO journal_lines (id, entry_id, business_id, account_id, currency, amount_minor) VALUES ('x', ?, 'b', 'a', 'GHS', 1)", (entry,)),
    ):
        with pytest.raises(sqlite3.IntegrityError):
            with db.connection(config.DB_PATH) as conn:
                conn.execute(statement, params)
    assert ledger.to_minor(0.1 + 0.2) == 30 and ledger.to_minor("1,0".replace(",", ".")) == 100 and ledger.to_minor(2.675) == 268


# ---------------------------------------------------------------- posting rules


def test_sales_channels_refunds_and_costs(client):
    headers, base, _ = owner(client)
    upload(client, headers, base, SALES)
    result = books(client, headers, base)
    pnl = result["profit_and_loss"]["currencies"][0]
    assert pnl["total_income"] == 336.0  # 190 + 95 + 96 + 50 - 95
    assert lines_of(pnl, "expenses") == {"cogs": 230.0}
    assert pnl["gross_profit"] == 106.0 and pnl["net_profit"] == 106.0
    sheet = result["balance_sheet"]["currencies"][0]
    assert sheet["balanced"] is True
    assets = lines_of(sheet, "assets")
    assert assets == {"cash": 95.0, "momo_mtn": 95.0, "bank": 96.0, "receipts_clearing": 50.0}  # Milo: no payment method
    assert lines_of(sheet, "liabilities") == {"payments_clearing": 230.0}
    flow = result["cash_flow"]["currencies"][0]
    assert flow["lines"]["sales"] == 286.0 and flow["net"] == 286.0  # the unallocated 50 is not cash yet
    assert result["differences"]["unexplained"] == 0
    # Catch-up is idempotent: nothing reposted on a second read.
    count = db.one(config.DB_PATH, "SELECT COUNT(*) AS n FROM journal_entries", ())["n"]
    books(client, headers, base)
    assert db.one(config.DB_PATH, "SELECT COUNT(*) AS n FROM journal_entries", ())["n"] == count


def test_momo_payments_are_spending_and_the_difference_is_named(client):
    headers, base, _ = owner(client)
    sms = (
        "Payment received for GHS 150.00 from Kojo Mensah (0244123456). Current Balance: GHS 2,450.00. "
        "Reference: 5 bags maize. Financial Transaction Id: 18293048591. Date: 2026-10-15\n\n"
        "You have received GHS 85.50 from 233201234567 - KWAME ASANTE. Trans ID: 0092837482. Balance: GHS 1,120.00. Date: 2026-10-16\n\n"
        "Payment made for GHS 40.00 to ECG Prepaid. Current Balance: GHS 1,080.00. Financial Transaction Id: 777001. Date: 2026-10-17"
    )
    assert client.post(f"{base}/sources/momo", headers=headers, json={"sms_text": sms}).status_code == 200
    result = books(client, headers, base)
    pnl = result["profit_and_loss"]["currencies"][0]
    assert pnl["total_income"] == 235.5 and lines_of(pnl, "expenses") == {"uncategorised": 40.0}
    assets = lines_of(result["balance_sheet"]["currencies"][0], "assets")
    assert assets == {"momo_mtn": 110.0, "momo_telecel": 85.5}
    diff = result["differences"]
    assert diff["analytics_revenue"] == 275.5 and diff["ledger_sales"] == 235.5
    assert diff["explained"][0]["amount"] == 40.0 and "MoMo payments made" in diff["explained"][0]["reason"]
    assert diff["unexplained"] == 0


def test_excluding_a_file_reverses_without_deleting(client):
    headers, base, _ = owner(client)
    dataset = upload(client, headers, base, SALES)
    books(client, headers, base)
    before = db.one(config.DB_PATH, "SELECT COUNT(*) AS n FROM journal_entries", ())["n"]
    client.patch(f"{base}/datasets/{dataset['id']}", headers=headers, json={"included": False})
    result = books(client, headers, base)
    assert result["profit_and_loss"]["currencies"] == []
    assert db.one(config.DB_PATH, "SELECT COUNT(*) AS n FROM journal_entries", ())["n"] > before  # reversals added, nothing deleted
    client.patch(f"{base}/datasets/{dataset['id']}", headers=headers, json={"included": True})
    assert books(client, headers, base)["profit_and_loss"]["currencies"][0]["total_income"] == 336.0


def test_stock_movements_and_no_double_counted_cost(client):
    headers, base, _ = owner(client)
    rice = client.post(f"{base}/inventory/products", headers=headers, json={"name": "Rice 5kg", "unit": "bag", "unit_cost": 70, "opening_stock": 10}).json()
    client.post(f"{base}/inventory/products/{rice['id']}/movements", headers=headers, json={"movement_type": "purchase", "quantity": 5, "unit_cost": 70})
    bare = client.post(f"{base}/inventory/products", headers=headers, json={"name": "Sugar", "unit": "bag", "opening_stock": 4}).json()
    result = books(client, headers, base, "from=2026-01-01&to=2099-12-31")
    assets = lines_of(result["balance_sheet"]["currencies"][0], "assets")
    assert assets == {"inventory": 1050.0}  # 15 bags × 70; Sugar has no cost yet
    assert any("Sugar" in issue and "no unit cost" in issue for issue in result["issues"])
    equity = lines_of(result["balance_sheet"]["currencies"][0], "equity")
    assert equity["opening_equity"] == 700.0
    # Once Sugar has a cost, its opening stock is booked.
    client.patch(f"{base}/inventory/products/{bare['id']}", headers=headers, json={"unit_cost": 20})
    result = books(client, headers, base, "from=2026-01-01&to=2099-12-31")
    assert lines_of(result["balance_sheet"]["currencies"][0], "assets")["inventory"] == 1130.0
    assert not any("Sugar" in issue for issue in result["issues"])

    # A sales file posted to stock: cost of goods sold comes from the stock movement only.
    dataset = upload(client, headers, base, "transaction_date,product,quantity,amount,cost\n2026-10-01,Rice 5kg,2,190,140\n")
    assert client.post(f"{base}/inventory/posts/{dataset['id']}", headers=headers).status_code == 200
    result = books(client, headers, base, "from=2026-01-01&to=2099-12-31")
    pnl = result["profit_and_loss"]["currencies"][0]
    assert lines_of(pnl, "expenses") == {"cogs": 140.0}  # not 280
    assert any("come from stock" in issue for issue in result["issues"])
    assert result["balance_sheet"]["currencies"][0]["balanced"] is True


# ---------------------------------------------------------------- opening balances and the books start


def test_opening_balances_do_not_double_count_history(client):
    headers, base, _ = owner(client)
    for category, name, amount in (("cash", "Till", 1000), ("cash", "MTN MoMo wallet", 300), ("inventory", "Stock", 999), ("loans", "Susu loan", 500), ("owner_capital", "Capital", 400)):
        client.post(f"{base}/financial-position/balances", headers=headers, json={"as_of_date": "2026-10-31", "category": category, "account_name": name, "amount": amount})
    client.post(f"{base}/inventory/products", headers=headers, json={"name": "Rice 5kg", "unit": "bag", "unit_cost": 70, "opening_stock": 10})
    upload(client, headers, base, SALES)  # October sales: already inside the 1 Nov cash figure
    upload(client, headers, base, "transaction_date,product,amount,payment_method\n2026-11-03,Rice 5kg,95,cash\n", "nov.csv")

    proposal = client.get(f"{base}/books/opening?start=2026-11-01", headers=headers).json()
    assert {line["account"] for line in proposal["lines"]} == {"cash", "momo_mtn", "loans", "owner_capital"}  # stock comes from the stock ledger
    assert proposal["notes"]
    assert client.post(f"{base}/books/opening", headers=headers, json={"start_date": "2026-11-01", "lines": proposal["lines"]}).status_code == 200

    result = books(client, headers, base, "from=2026-11-01&to=2026-11-30")
    sheet = result["balance_sheet"]["currencies"][0]
    assert sheet["balanced"] is True
    assets = lines_of(sheet, "assets")
    assert assets["cash"] == 1095.0  # 1,000 opening + 95 in November, not + October
    assert assets["inventory"] == 700.0
    assert result["profit_and_loss"]["currencies"][0]["total_income"] == 95.0
    assert any("before your books start" in issue for issue in result["issues"])
    window = books(client, headers, base, "from=2026-10-01&to=2026-11-30")["differences"]
    assert window["unexplained"] == 0 and any("before your books start" in item["reason"] for item in window["explained"])


# ---------------------------------------------------------------- the accountant's tools


def test_manual_journal_lock_roles_and_isolation(client):
    headers, base, business_id = owner(client)
    dataset = upload(client, headers, base, SALES)
    books(client, headers, base)
    accounts = {a["system_key"]: a["id"] for a in client.get(f"{base}/books/accounts", headers=headers).json()}
    entry = {"entry_date": "2026-10-20", "memo": "Owner took cash", "lines": [{"account_id": accounts["drawings"], "debit": 50}, {"account_id": accounts["cash"], "credit": 50}]}
    unbalanced = {**entry, "lines": [{"account_id": accounts["drawings"], "debit": 50}, {"account_id": accounts["cash"], "credit": 40}]}
    assert client.post(f"{base}/books/journal", headers=headers, json=unbalanced).status_code == 400
    assert client.post(f"{base}/books/journal", headers=headers, json=entry).status_code == 200

    # Roles: accountant may post journals; a manager may read the books but not post.
    for role, expected in (("accountant", 200), ("manager", 403)):
        token = client.post(f"{base}/invites", headers=headers, json={"role": role}).json()["token"]
        member = client.post("/api/auth/signup", json={"email": f"{role}@example.com", "password": "password123", "invite_token": token}).json()
        member_headers = {"Authorization": f"Bearer {member['access_token']}"}
        assert client.get(f"{base}/books", headers=member_headers).status_code == 200
        assert client.post(f"{base}/books/journal", headers=member_headers, json=entry).status_code == expected
        assert client.put(f"{base}/books/lock", headers=member_headers, json={"lock_date": None}).status_code == expected

    # Another business can neither read these books nor post to their accounts.
    other_headers, other_base, _ = owner(client, "other@example.com")
    assert client.get(f"{base}/books", headers=other_headers).status_code == 404
    assert client.post(f"{other_base}/books/journal", headers=other_headers, json=entry).status_code == 400

    # Lock October: no journals inside it, and excluding an October file reverses on 1 November.
    assert client.put(f"{base}/books/lock", headers=headers, json={"lock_date": "2026-10-31"}).status_code == 200
    assert client.post(f"{base}/books/journal", headers=headers, json=entry).status_code == 400
    october = books(client, headers, base, "from=2026-10-01&to=2026-10-31")["profit_and_loss"]["currencies"][0]["total_income"]
    client.patch(f"{base}/datasets/{dataset['id']}", headers=headers, json={"included": False})
    assert books(client, headers, base, "from=2026-10-01&to=2026-10-31")["profit_and_loss"]["currencies"][0]["total_income"] == october
    november = books(client, headers, base, "from=2026-11-01&to=2026-11-30")["profit_and_loss"]["currencies"][0]
    assert november["total_income"] == -336.0
    assert client.put(f"{base}/books/lock", headers=headers, json={"lock_date": "2999-01-01"}).status_code == 400

    trial = client.get(f"{base}/books/trial-balance?as_of=2026-12-31", headers=headers).json()
    assert all(block["balanced"] for block in trial["currencies"])
    _ = business_id


def test_journal_export_and_accounts(client):
    headers, base, _ = owner(client)
    upload(client, headers, base, "transaction_date,product,amount,payment_method\n2026-10-01,=HYPERLINK(\"x\"),10,cash\n")
    csv = client.get(f"{base}/books/journal.csv", headers=headers)
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert csv.text.splitlines()[0].startswith("Date,Entry,Account code")
    assert "'=HYPERLINK" in csv.text and ",=HYPERLINK" not in csv.text
    added = client.post(f"{base}/books/accounts", headers=headers, json={"code": "6100", "name": "Generator fuel", "type": "expense"})
    assert added.status_code == 200
    assert client.post(f"{base}/books/accounts", headers=headers, json={"code": "6100", "name": "Again", "type": "expense"}).status_code == 400
    assert client.patch(f"{base}/books/accounts/{added.json()['id']}", headers=headers, json={"name": "Generator diesel"}).status_code == 200
    upload(client, headers, base, "transaction_date,category,cost\n2026-10-02,Shop rent,500\n2026-10-03,Fuel,60\n", "expenses.csv")
    pnl = books(client, headers, base)["profit_and_loss"]["currencies"][0]
    assert lines_of(pnl, "expenses") == {"rent": 500.0, "transport": 60.0} and pnl["net_profit"] == -550.0
    journal = client.get(f"{base}/books/journal", headers=headers).json()
    assert journal and all(sum(l["debit"] for l in e["lines"]) == sum(l["credit"] for l in e["lines"]) for e in journal)


def test_expense_files_and_rules():
    assert ledger.expense_account({"category": "ECG prepaid"}) == "utilities"
    assert ledger.expense_account({"product": "Shop rent October"}) == "rent"
    assert ledger.expense_account({"product": "Paint"}) == "uncategorised"
    assert ledger.receipt_account({"payment_method": "Telecel Cash"}) == "momo_telecel"
    assert ledger.receipt_account({"payment_method": "cashier"}) == "receipts_clearing"
    assert ledger.receipt_account({"payment_method": "Cash"}) == "cash"
    assert ledger.receipt_account({"category": "momo_sale_received", "channel": "Mobile Money"}) == "momo_other"
    _ = date
