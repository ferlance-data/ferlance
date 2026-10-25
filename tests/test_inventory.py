from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from pathlib import Path

from backend import config, db, main


def _client(tmp_path, monkeypatch, email="inventory@example.com"):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "inventory.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "password123", "business_name": "Ama Retail"},
    )
    return client, signup.json()["business"]["id"], {
        "Authorization": f"Bearer {signup.json()['access_token']}"
    }


def test_stock_movements_are_audited_and_cannot_overdraw(tmp_path, monkeypatch):
    client, business_id, headers = _client(tmp_path, monkeypatch)
    base = f"/api/businesses/{business_id}/inventory"
    product = client.post(
        f"{base}/products",
        headers=headers,
        json={
            "name": "Rice",
            "sku": "RICE-1",
            "unit": "bag",
            "unit_cost": 2.5,
            "reorder_level": 5,
            "opening_stock": 10,
        },
    )
    assert product.status_code == 200
    product_id = product.json()["id"]
    assert product.json()["quantity_on_hand"] == 10
    assert product.json()["stock_value"] == 25

    sale = client.post(
        f"{base}/products/{product_id}/movements",
        headers=headers,
        json={"movement_type": "sale", "quantity": 3, "note": "Counter sale"},
    )
    purchase = client.post(
        f"{base}/products/{product_id}/movements",
        headers=headers,
        json={"movement_type": "purchase", "quantity": 4},
    )
    adjustment = client.post(
        f"{base}/products/{product_id}/movements",
        headers=headers,
        json={"movement_type": "adjustment", "quantity": -2, "note": "Damaged"},
    )
    overdraw = client.post(
        f"{base}/products/{product_id}/movements",
        headers=headers,
        json={"movement_type": "sale", "quantity": 20},
    )

    assert sale.json()["quantity_on_hand"] == 7
    assert purchase.json()["quantity_on_hand"] == 11
    assert adjustment.json()["quantity_on_hand"] == 9
    assert overdraw.status_code == 400
    snapshot = client.get(base, headers=headers).json()
    assert snapshot["summary"]["low_stock_count"] == 0
    assert snapshot["summary"]["inventory_value"] == 22.5
    movements = client.get(f"{base}/movements", headers=headers).json()
    assert len(movements) == 4
    assert movements[0]["movement_type"] == "adjustment"
    assert movements[0]["recorded_by"] == "inventory@example.com"


def test_stocktake_import_reconciles_counts_and_rolls_back_invalid_batch(tmp_path, monkeypatch):
    client, business_id, headers = _client(tmp_path, monkeypatch)
    base = f"/api/businesses/{business_id}/inventory"
    rice = client.post(
        f"{base}/products",
        headers=headers,
        json={"name": "Rice", "sku": "RICE", "unit": "bag", "opening_stock": 5},
    ).json()
    stocktake = (
        "product,sku,unit,quantity_on_hand,unit_cost,reorder_level\n"
        "Rice,RICE,bag,3,4,2\n"
        "Beans,B-2,bag,7,6,1\n"
    )
    imported = client.post(
        f"{base}/import",
        headers=headers,
        files={"file": ("stocktake.csv", stocktake.encode(), "text/csv")},
    )
    assert imported.status_code == 200
    assert imported.json() == {"created": 1, "updated": 1, "rows_imported": 2}
    items = client.get(base, headers=headers).json()["items"]
    assert {item["name"]: item["quantity_on_hand"] for item in items} == {"Beans": 7, "Rice": 3}
    assert client.get(base, headers=headers).json()["summary"]["inventory_value"] == 54

    invalid_batch = (
        "product,sku,unit,quantity_on_hand\n"
        "New item,NEW,unit,2\n"
        "Wrong name,RICE,bag,3\n"
    )
    failed = client.post(
        f"{base}/import",
        headers=headers,
        files={"file": ("bad-stocktake.csv", invalid_batch.encode(), "text/csv")},
    )
    assert failed.status_code == 400
    final_items = client.get(base, headers=headers).json()["items"]
    assert {item["name"] for item in final_items} == {"Beans", "Rice"}
    movements = client.get(f"{base}/movements", headers=headers).json()
    assert len(movements) == 3
    assert rice["id"] in {movement["product_id"] for movement in movements}


def test_inventory_is_business_scoped_archivable_and_sales_uploads_do_not_adjust_stock(
    tmp_path, monkeypatch
):
    client, first_business, first_headers = _client(tmp_path, monkeypatch, "first@example.com")
    signup = client.post(
        "/api/auth/signup",
        json={
            "email": "second@example.com",
            "password": "password123",
            "business_name": "Other Business",
        },
    )
    second_business = signup.json()["business"]["id"]
    second_headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    base = f"/api/businesses/{first_business}/inventory"
    product = client.post(
        f"{base}/products",
        headers=first_headers,
        json={"name": "Flour", "opening_stock": 8},
    ).json()
    forbidden = client.patch(
        f"/api/businesses/{second_business}/inventory/products/{product['id']}",
        headers=second_headers,
        json={"active": False},
    )
    assert forbidden.status_code == 404

    archive = client.patch(
        f"{base}/products/{product['id']}",
        headers=first_headers,
        json={"active": False},
    )
    assert archive.status_code == 200
    active_inventory = client.get(base, headers=first_headers).json()
    assert active_inventory["items"] == []
    assert active_inventory["summary"]["product_count"] == 0
    assert active_inventory["summary"]["units_on_hand"] == 8
    archived = client.get(f"{base}?include_archived=true", headers=first_headers).json()
    assert archived["items"][0]["active"] is False
    restore = client.patch(
        f"{base}/products/{product['id']}",
        headers=first_headers,
        json={"active": True},
    )
    assert restore.status_code == 200
    assert restore.json()["quantity_on_hand"] == 8

    fixture = Path(__file__).parent / "fixtures" / "valid_sales.csv"
    upload = client.post(
        f"/api/businesses/{first_business}/datasets",
        headers=first_headers,
        files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")},
    )
    assert upload.status_code == 200
    snapshot = client.get(base, headers=first_headers).json()
    assert snapshot["items"][0]["quantity_on_hand"] == 8
    assert len(client.get(f"{base}/movements", headers=first_headers).json()) == 1


def test_inventory_import_requires_stocktake_headers_and_csv(tmp_path, monkeypatch):
    client, business_id, headers = _client(tmp_path, monkeypatch)
    base = f"/api/businesses/{business_id}/inventory"
    missing_columns = client.post(
        f"{base}/import",
        headers=headers,
        files={"file": ("inventory.csv", b"name,quantity\nRice,3\n", "text/csv")},
    )
    unsupported = client.post(
        f"{base}/import",
        headers=headers,
        files={"file": ("inventory.xlsx", b"not an xlsx", "application/octet-stream")},
    )
    assert missing_columns.status_code == 400
    assert unsupported.status_code == 415
    template = client.get(f"{base}/import-template", headers=headers)
    assert template.status_code == 200
    assert template.text.startswith("product,sku,unit,quantity_on_hand")


def test_inventory_stocktake_rejects_misgrouped_thousands_separators(tmp_path, monkeypatch):
    client, business_id, headers = _client(tmp_path, monkeypatch)
    base = f"/api/businesses/{business_id}/inventory"
    response = client.post(
        f"{base}/import",
        headers=headers,
        files={
            "file": (
                "bad-count.csv",
                b"product,quantity_on_hand\nRice,\"1,2\"\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 400
    assert "invalid quantity_on_hand" in response.json()["detail"]


def test_concurrent_sales_cannot_overdraw_inventory(tmp_path, monkeypatch):
    client, business_id, headers = _client(tmp_path, monkeypatch)
    base = f"/api/businesses/{business_id}/inventory"
    product = client.post(
        f"{base}/products",
        headers=headers,
        json={"name": "Limited stock", "opening_stock": 1},
    ).json()

    def sell_once(_):
        return client.post(
            f"{base}/products/{product['id']}/movements",
            headers=headers,
            json={"movement_type": "sale", "quantity": 1},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(sell_once, range(2)))

    assert sorted(response.status_code for response in responses) == [200, 400]
    snapshot = client.get(base, headers=headers).json()
    assert snapshot["items"][0]["quantity_on_hand"] == 0
    assert len(client.get(f"{base}/movements", headers=headers).json()) == 2
