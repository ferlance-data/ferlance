"""Phone-app sessions (/api/auth/mobile/*): the refresh token travels in the body, in its own scope."""

from fastapi.testclient import TestClient

from backend import config, db, main
from test_admin import admin_login, client, signup  # noqa: F401  (client is a fixture)

CREDENTIALS = {"email": "ama@example.com", "password": "password123"}


def mobile_login(client, credentials=CREDENTIALS):
    return client.post("/api/auth/mobile/login", json=credentials)


def test_mobile_login_refresh_rotation_and_logout(client):
    _, created = signup(client, "ama@example.com", "Ama Retail")
    business_id = created.json()["business"]["id"]
    phone = TestClient(main.app)  # a fresh client: no cookie jar shared with the web sign-up

    first = mobile_login(phone)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["business"]["id"] == business_id and body["refresh_token"]
    assert "set-cookie" not in first.headers  # nothing for a browser to keep
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert phone.get(f"/api/businesses/{business_id}/debts", headers=headers).status_code == 200

    rotated = phone.post("/api/auth/mobile/refresh", json={"refresh_token": body["refresh_token"]})
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    assert second != body["refresh_token"] and rotated.json()["business"]["id"] == business_id
    # The old token is served once more inside the grace window (a lost response), then never.
    assert phone.post("/api/auth/mobile/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 200
    assert phone.post("/api/auth/mobile/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401

    latest = mobile_login(phone).json()["refresh_token"]
    assert phone.post("/api/auth/mobile/logout", json={"refresh_token": latest}).json() == {"status": "signed_out"}
    assert phone.post("/api/auth/mobile/refresh", json={"refresh_token": latest}).status_code == 401


def test_web_and_mobile_tokens_do_not_cross(client):
    _, created = signup(client, "ama@example.com", "Ama Retail")
    web_token = created.cookies.get("ferlance_refresh")
    assert web_token
    phone = TestClient(main.app)
    assert phone.post("/api/auth/mobile/refresh", json={"refresh_token": web_token}).status_code == 401
    # Mobile logout can't revoke a web session either.
    phone.post("/api/auth/mobile/logout", json={"refresh_token": web_token})
    assert client.post("/api/auth/refresh").status_code == 200

    mobile_token = mobile_login(phone).json()["refresh_token"]
    browser = TestClient(main.app)
    browser.cookies.set("ferlance_refresh", mobile_token, path="/api/auth")
    assert browser.post("/api/auth/refresh").status_code == 401


def test_mobile_refused_for_bad_password_disabled_and_admin_only_accounts(client):
    signup(client, "root@example.com", "Root Co")
    root = admin_login(client, "root@example.com")
    signup(client, "ama@example.com", "Ama Retail")
    phone = TestClient(main.app)

    assert mobile_login(phone, {**CREDENTIALS, "password": "wrong-password"}).status_code == 401
    token = mobile_login(phone).json()["refresh_token"]
    target = client.get("/api/admin/users?q=ama", headers=root).json()[0]["id"]
    assert client.post(f"/api/admin/users/{target}/disable", headers=root).status_code == 200
    assert mobile_login(phone).status_code == 403
    assert phone.post("/api/auth/mobile/refresh", json={"refresh_token": token}).status_code == 401

    # An administrator with no business signs in at /admin, never in the app.
    db.insert(config.DB_PATH, "INSERT INTO users (id, email, password_hash, created_at, role, full_name) SELECT 'adm', 'ops@example.com', password_hash, created_at, 'admin', '' FROM users WHERE email = ?", ("root@example.com",))
    assert mobile_login(phone, {"email": "ops@example.com", "password": "password123"}).status_code == 403
