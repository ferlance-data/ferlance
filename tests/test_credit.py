import json

import pytest
from fastapi.testclient import TestClient

from backend import config, credit, db, main
from tests.test_statements import MTN_STYLE


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    return TestClient(main.app)


def owner(client, email="ama@example.com", name="Ama Provisions"):
    signup = client.post("/api/auth/signup", json={"email": email, "password": "password123", "business_name": name}).json()
    return {"Authorization": f"Bearer {signup['access_token']}"}, f"/api/businesses/{signup['business']['id']}"


def seed(client, headers, base):
    rows = "transaction_date,product,amount,cost,payment_method\n" + "".join(
        f"2026-{m:02d}-10,Rice 5kg,{1000 + m * 10},700,cash\n" for m in range(1, 12)
    )
    client.post(f"{base}/datasets", headers=headers, files={"file": ("sales.csv", rows.encode(), "text/csv")})
    sms = "Payment received for GHS 150.00 from Kojo Mensah (0244123456). Current Balance: GHS 1,150.00. Financial Transaction Id: TXN-0001. Date: 2026-11-15"
    client.post(f"{base}/sources/momo", headers=headers, json={"sms_text": sms})


def test_report_figures_evidence_and_score(client):
    headers, base = owner(client)
    seed(client, headers, base)
    report = client.get(f"{base}/credit", headers=headers).json()
    facts = report["facts"]
    assert facts["months_with_sales"] == 11 and facts["net_margin_pct"] > 0
    assert facts["evidence"]["statement_matched_pct"] == 0 and facts["evidence"]["momo_sms_pct"] > 0
    assert report["score"] == sum(part["points"] for part in report["parts"]) and 0 < report["score"] < 100
    evidence_before = next(p for p in report["parts"] if p["name"] == "Evidence")
    assert evidence_before["raise"]  # says what would raise it

    # Importing the MoMo statement matches the SMS payment: more evidence, a higher score.
    preview = client.post(f"{base}/statements/preview", headers=headers, files={"file": ("s.csv", MTN_STYLE.encode(), "text/csv")}).json()
    client.post(f"{base}/statements", headers=headers, files={"file": ("s.csv", MTN_STYLE.encode(), "text/csv")},
                data={"account": "momo_mtn", "header_row": str(preview["header_row"]), "mapping": json.dumps(preview["mapping"])})
    after = client.get(f"{base}/credit", headers=headers).json()
    assert after["facts"]["evidence"]["statement_matched_pct"] > 0
    assert after["score"] > report["score"]


def test_score_parts_are_explained():
    _, parts = credit._score({
        "months_with_sales": 12, "net_margin_pct": 25.0, "sales_steadiness": 0.9, "books_start": "2026-01-01", "reconciled_accounts": 2,
        "evidence": {"statement_matched_pct": 95.0, "momo_sms_pct": 0.0}, "receivables": {"owed": 0, "late_share_pct": 0.0},
    })
    assert sum(p["points"] for p in parts) >= 95 and all(p["why"] for p in parts)
    assert all(p["raise"] is None for p in parts if p["points"] == p["out_of"])


def test_sharing_needs_consent_is_frozen_logged_and_revocable(client):
    headers, base = owner(client, name="Ama <script>alert(1)</script>")
    seed(client, headers, base)
    assert client.post(f"{base}/credit/shares", headers=headers, json={"days": 7, "lender": "Fidelity", "consent": False}).status_code == 400
    assert client.post(f"{base}/credit/shares", headers=headers, json={"days": 9, "lender": "", "consent": True}).status_code == 422
    shared = client.post(f"{base}/credit/shares", headers=headers, json={"days": 7, "lender": "Fidelity Bank", "consent": True}).json()
    assert shared["url"].endswith(f"/r/{shared['token']}") and shared["code"].startswith("FER-")

    page = client.get(f"/r/{shared['token']}")
    assert page.status_code == 200 and shared["code"] in page.text and "Fidelity Bank" in page.text
    assert "<script>" not in page.text and "&lt;script&gt;" in page.text  # the business name is escaped
    assert "default-src 'none'" in page.headers["content-security-policy"] and page.headers["x-robots-tag"].startswith("noindex")
    assert "Rice 5kg" not in page.text and "Kojo" not in page.text  # no line items or customer names

    # Frozen: later records do not change what the lender sees.
    client.post(f"{base}/datasets", headers=headers, files={"file": ("more.csv", b"transaction_date,product,amount\n2026-11-20,Big order,99999\n", "text/csv")})
    assert "99,999" not in client.get(f"/r/{shared['token']}").text

    listed = client.get(f"{base}/credit/shares", headers=headers).json()
    assert listed[0]["views"] == 2 and listed[0]["active"] is True
    assert client.post(f"{base}/credit/shares/{listed[0]['id']}/revoke", headers=headers).status_code == 200
    assert client.get(f"/r/{shared['token']}").status_code == 404
    assert client.get("/r/not-a-real-token").status_code == 404


def test_expiry_roles_and_isolation(client):
    headers, base = owner(client)
    shared = client.post(f"{base}/credit/shares", headers=headers, json={"days": 7, "consent": True}).json()
    db.insert(config.DB_PATH, "UPDATE credit_shares SET expires_at = '2000-01-01T00:00:00+00:00'", ())
    assert client.get(f"/r/{shared['token']}").status_code == 404
    token = client.post(f"{base}/invites", headers=headers, json={"role": "accountant"}).json()["token"]
    acct = client.post("/api/auth/signup", json={"email": "acct@example.com", "password": "password123", "invite_token": token}).json()
    acct_headers = {"Authorization": f"Bearer {acct['access_token']}"}
    assert client.get(f"{base}/credit", headers=acct_headers).status_code == 200
    assert client.post(f"{base}/credit/shares", headers=acct_headers, json={"days": 7, "consent": True}).status_code == 403  # only the owner shares
    assert client.get(f"{base}/credit/shares", headers=acct_headers).status_code == 403
    other_headers, other_base = owner(client, "o@example.com")
    share_id = client.get(f"{base}/credit/shares", headers=headers).json()[0]["id"]
    assert client.post(f"{other_base}/credit/shares/{share_id}/revoke", headers=other_headers).status_code == 404
    assert client.get(f"{base}/credit", headers=other_headers).status_code == 404
