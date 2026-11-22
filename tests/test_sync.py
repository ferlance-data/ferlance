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


def setup(client):
    signup = client.post("/api/auth/signup", json={"email": "yaw@example.com", "password": "password123", "business_name": "Yaw Shops"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    base = f"/api/businesses/{signup.json()['business']['id']}"
    rice = client.post(f"{base}/inventory/products", headers=headers, json={"name": "Rice 5kg", "unit": "bag", "unit_cost": 70, "opening_stock": 20}).json()
    oil = client.post(f"{base}/inventory/products", headers=headers, json={"name": "Cooking oil 1L", "unit": "bottle", "unit_cost": 40, "opening_stock": 3}).json()
    csv = (
        "transaction_date,product,quantity,amount\n"
        "2026-10-01,Rice 5kg,4,380\n"          # exact name
        "2026-10-02,RICE (5KG BAG),2,190\n"     # shop's own spelling -> needs a link
        "2026-10-03,Frytol oil 1L,2,96\n"       # linked to Cooking oil
        "2026-10-04,Plastic bags,10,5\n"        # not stock -> ignored
        "2026-10-05,Sardines,,28\n"             # no quantity
    )
    dataset = client.post(f"{base}/datasets", headers=headers, files={"file": ("shop1.csv", csv.encode(), "text/csv")}).json()
    return headers, base, rice, oil, dataset


def stock(client, headers, base):
    return {item["name"]: item["quantity_on_hand"] for item in client.get(f"{base}/inventory?include_archived=true", headers=headers).json()["items"]}


def test_link_post_conflict_idempotency_and_reversal(client):
    headers, base, rice, oil, dataset = setup(client)
    names = {row["sales_name"]: row for row in client.get(f"{base}/inventory/links", headers=headers).json()["names"]}
    assert names["Rice 5kg"]["status"] == "matched"
    assert names["RICE (5KG BAG)"]["status"] == "unlinked"
    assert names["Sardines"]["missing_quantity"] == 1

    client.put(f"{base}/inventory/links", headers=headers, json={"sales_name": "RICE (5KG BAG)", "product_id": rice["id"]})
    client.put(f"{base}/inventory/links", headers=headers, json={"sales_name": "Frytol oil 1L", "product_id": oil["id"]})
    client.put(f"{base}/inventory/links", headers=headers, json={"sales_name": "Plastic bags", "ignore": True})
    statuses = {row["sales_name"]: row["status"] for row in client.get(f"{base}/inventory/links", headers=headers).json()["names"]}
    assert statuses["RICE (5KG BAG)"] == "linked" and statuses["Plastic bags"] == "ignored"

    # Oil: 2 sold, 3 on hand -> fine. Make it short first to see the conflict.
    client.post(f"{base}/inventory/products/{oil['id']}/movements", headers=headers, json={"movement_type": "sale", "quantity": 2})
    conflict = client.post(f"{base}/inventory/posts/{dataset['id']}", headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["conflicts"] == [{"product_id": oil["id"], "name": "Cooking oil 1L", "on_hand": 1.0, "sold": 2.0, "short": 1.0}]
    assert stock(client, headers, base) == {"Rice 5kg": 20, "Cooking oil 1L": 1}  # nothing posted

    client.post(f"{base}/inventory/products/{oil['id']}/movements", headers=headers, json={"movement_type": "purchase", "quantity": 5})
    posted = client.post(f"{base}/inventory/posts/{dataset['id']}", headers=headers).json()
    assert posted["units"] == 8  # 4 + 2 rice (exact name + linked spelling), 2 oil (linked)
    assert posted["skipped"] == {"unlinked": 1, "ignored": 1, "no_quantity": 0, "not_sales": 0}  # Sardines; Plastic bags
    assert stock(client, headers, base) == {"Rice 5kg": 14, "Cooking oil 1L": 4}
    assert client.post(f"{base}/inventory/posts/{dataset['id']}", headers=headers).status_code == 409  # never twice
    assert client.get(f"{base}/inventory/posts", headers=headers).json()[dataset["id"]]["status"] == "posted"

    # Leaving the file out of analysis reverses its stock movements.
    excluded = client.patch(f"{base}/datasets/{dataset['id']}", headers=headers, json={"included": False}).json()
    assert excluded["stock_reversed"] is True
    assert stock(client, headers, base) == {"Rice 5kg": 20, "Cooking oil 1L": 6}
    # Once reversed it can be posted again.
    client.patch(f"{base}/datasets/{dataset['id']}", headers=headers, json={"included": True})
    assert client.post(f"{base}/inventory/posts/{dataset['id']}", headers=headers).status_code == 200
    assert stock(client, headers, base)["Rice 5kg"] == 14


def test_links_feed_advice_and_reconciliation(client):
    headers, base, rice, oil, dataset = setup(client)
    window = "from=2026-10-01&to=2026-10-30"

    def slow(name):
        advice = client.get(f"{base}/insights?{window}", headers=headers).json()["advice"]
        return any(item["kind"] == "slow_stock" and item["product"] == name for item in advice["items"])

    # Unlinked, the oil looks unsold (its sales use another name) and is flagged as slow stock.
    assert slow("Cooking oil 1L")
    client.put(f"{base}/inventory/links", headers=headers, json={"sales_name": "Frytol oil 1L", "product_id": oil["id"]})
    assert not slow("Cooking oil 1L")  # linked sales count, once

    # A stocktake difference shows up in reconciliation.
    stocktake = "product,quantity_on_hand\nRice 5kg,17\n"
    client.post(f"{base}/inventory/import", headers=headers, files={"file": ("count.csv", stocktake.encode(), "text/csv")})
    rows = client.get(f"{base}/inventory/reconciliation", headers=headers).json()
    assert rows[0]["name"] == "Rice 5kg" and rows[0]["variance"] == -3 and rows[0]["value"] == -210


def test_sync_permissions_and_isolation(client):
    headers, base, rice, _, dataset = setup(client)
    invite = client.post(f"{base}/invites", headers=headers, json={"role": "accountant"}).json()["token"]
    acct = client.post("/api/auth/signup", json={"email": "acct@example.com", "password": "password123", "invite_token": invite}).json()
    acct_headers = {"Authorization": f"Bearer {acct['access_token']}"}
    assert client.get(f"{base}/inventory/links", headers=acct_headers).status_code == 200
    assert client.put(f"{base}/inventory/links", headers=acct_headers, json={"sales_name": "x", "ignore": True}).status_code == 403
    assert client.post(f"{base}/inventory/posts/{dataset['id']}", headers=acct_headers).status_code == 403

    other = client.post("/api/auth/signup", json={"email": "o@example.com", "password": "password123", "business_name": "O"}).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    other_base = f"/api/businesses/{other['business']['id']}"
    # Another business can't link to this business's product or post this business's file.
    assert client.put(f"{other_base}/inventory/links", headers=other_headers, json={"sales_name": "Rice", "product_id": rice["id"]}).status_code == 404
    assert client.post(f"{other_base}/inventory/posts/{dataset['id']}", headers=other_headers).status_code == 404
