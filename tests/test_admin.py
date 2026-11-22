import pytest
from fastapi.testclient import TestClient

from backend import config, db, main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(config, "ADMIN_EMAILS", {"root@example.com"})
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    return TestClient(main.app)


def signup(client, email, business="Shop"):
    response = client.post("/api/auth/signup", json={"email": email, "password": "password123", "business_name": business})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, response


def test_admin_console_disable_audit_and_counts(client):
    root, _ = signup(client, "root@example.com", "Root Co")
    owner, owner_signup = signup(client, "ama@example.com", "Ama Retail")
    base = f"/api/businesses/{owner_signup.json()['business']['id']}"
    client.post(f"{base}/datasets", headers=owner, files={"file": ("s.csv", b"transaction_date,product,amount\n2026-01-01,Rice,10\n", "text/csv")})

    # Non-admins are refused everywhere.
    for path in ("/api/admin/users", "/api/admin/businesses", "/api/admin/onboarding", "/api/admin/audit"):
        assert client.get(path, headers=owner).status_code == 403

    users = client.get("/api/admin/users?q=ama", headers=root).json()
    assert [u["email"] for u in users] == ["ama@example.com"] and users[0]["businesses"] == 1
    target = users[0]["id"]

    businesses = client.get("/api/admin/businesses?q=ama", headers=root).json()
    assert businesses[0]["datasets"] == 1 and businesses[0]["owner_email"] == "ama@example.com"
    assert "records" not in businesses[0]
    funnel = client.get("/api/admin/onboarding", headers=root).json()
    assert funnel["businesses"] == 2 and funnel["steps"][0] == {"key": "imported", "label": "Imported sales records", "count": 1}

    # Disabling ends sessions immediately: the access token, refresh and login all stop working.
    assert client.post(f"/api/admin/users/{target}/disable", headers=root).json()["disabled_at"]
    assert client.get(f"{base}/datasets", headers=owner).status_code == 401
    assert client.post("/api/auth/refresh", cookies={"ferlance_refresh": owner_signup.cookies.get("ferlance_refresh")}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ama@example.com", "password": "password123"}).status_code == 403
    assert client.post(f"/api/admin/users/{target}/enable", headers=root).json()["disabled_at"] is None
    assert client.post("/api/auth/login", json={"email": "ama@example.com", "password": "password123"}).status_code == 200

    # Guards: not yourself, not env-listed admins, not the last admin.
    me = client.get("/api/admin/users?q=root", headers=root).json()[0]["id"]
    assert client.post(f"/api/admin/users/{me}/disable", headers=root).status_code == 400
    client.patch(f"/api/admin/users/{target}/role", headers=root, json={"role": "admin"})
    second_admin, _ = (owner, None)
    relogin = client.post("/api/auth/login", json={"email": "ama@example.com", "password": "password123"}).json()
    ama_admin = {"Authorization": f"Bearer {relogin['access_token']}"}
    assert client.post(f"/api/admin/users/{me}/disable", headers=ama_admin).status_code == 400  # env-listed
    _ = second_admin

    actions = [entry["action"] for entry in client.get("/api/admin/audit", headers=root).json()]
    assert actions == ["role", "enable", "disable"]
    entry = client.get("/api/admin/audit", headers=root).json()[0]
    assert entry["detail"] == {"before": "owner", "after": "admin"} and entry["actor_email"] == "root@example.com"


def test_last_admin_cannot_be_demoted_by_another_path(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_EMAILS", set())
    a, _ = signup(client, "a@example.com")
    b, _ = signup(client, "b@example.com")
    ids = {row["email"]: row["id"] for row in db.many(config.DB_PATH, "SELECT id, email FROM users", ())}
    db.insert(config.DB_PATH, "UPDATE users SET role = 'admin' WHERE email IN ('a@example.com', 'b@example.com')", ())
    # Two admins: a can demote b, but then b (no longer admin) cannot act, and a is the last admin.
    assert client.patch(f"/api/admin/users/{ids['b@example.com']}/role", headers=a, json={"role": "owner"}).status_code == 200
    assert client.patch(f"/api/admin/users/{ids['a@example.com']}/role", headers=a, json={"role": "owner"}).status_code == 400
    assert client.get("/api/admin/users", headers=b).status_code == 403
