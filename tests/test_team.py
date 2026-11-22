from datetime import datetime, timedelta, timezone

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend import config, db, deps, main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    return TestClient(main.app)


def signup(client, email, business="Shop", invite=None):
    body = {"email": email, "password": "password123"}
    if invite:
        body["invite_token"] = invite
    else:
        body["business_name"] = business
    response = client.post("/api/auth/signup", json=body)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, response.json()["business"]


def invite(client, headers, business_id, role):
    response = client.post(f"/api/businesses/{business_id}/invites", headers=headers, json={"role": role})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _api_routes():
    """Every API route with path, methods and dependant, including those inside included routers."""
    for route in main.app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if contexts is not None:
            yield from contexts()
        elif isinstance(route, APIRoute):
            yield route


def _permission_of(route) -> set[str]:
    found = set()

    def walk(dependant):
        for sub in dependant.dependencies:
            permission = getattr(sub.call, "permission", None)
            if permission:
                found.add(permission)
            walk(sub)

    walk(route.dependant)
    return found


READ_ONLY_POSTS = {
    ("POST", "/api/businesses/{business_id}/ask-lance"),
    ("POST", "/api/businesses/{business_id}/insights/{insight_id}/explain"),
}


def test_every_business_route_declares_a_permission():
    """Guards against a future route under /api/businesses forgetting tenancy or role checks."""
    checked = 0
    for route in _api_routes():
        if not route.path.startswith("/api/businesses/{business_id}"):
            continue
        permissions = _permission_of(route)
        assert permissions, f"{route.methods} {route.path} has no business_access() dependency"
        for method in set(route.methods) - {"GET", "HEAD"}:
            if (method, route.path) in READ_ONLY_POSTS:
                assert permissions <= {"use_ai", "read"}, route.path
            else:
                assert "read" not in permissions or len(permissions) > 1, f"{method} {route.path} only requires read"
        checked += 1
    assert checked > 20


def test_roles_matrix_and_cross_tenant_denial(client):
    owner, business = signup(client, "owner@example.com", "Ama Retail")
    bid = business["id"]
    base = f"/api/businesses/{bid}"
    manager, _ = signup(client, "manager@example.com", invite=invite(client, owner, bid, "manager"))
    accountant, joined = signup(client, "acct@example.com", invite=invite(client, owner, bid, "accountant"))
    assert joined == {"id": bid, "name": "Ama Retail", "currency": "GHS", "role": "accountant"}
    stranger, _ = signup(client, "stranger@example.com", "Other Shop")

    csv = ("s.csv", b"transaction_date,product,amount\n2026-01-01,Rice,10\n", "text/csv")
    product = {"name": "Rice", "unit": "bag", "reorder_level": 1, "opening_stock": 5}
    balance = {"as_of_date": "2026-01-31", "category": "cash", "account_name": "Till", "amount": 100}

    def status(headers, method, path, **kwargs):
        return client.request(method, f"{base}{path}", headers=headers, **kwargs).status_code

    # Everyone in the business can read.
    for headers in (owner, manager, accountant):
        assert status(headers, "GET", "/datasets") == 200
        assert status(headers, "GET", "/inventory") == 200
    # Data writes: owner and manager only.
    assert status(owner, "POST", "/datasets", files={"file": csv}) == 200
    assert status(manager, "POST", "/inventory/products", json=product) == 200
    assert status(accountant, "POST", "/datasets", files={"file": csv}) == 403
    assert status(accountant, "POST", "/inventory/products", json={**product, "name": "Beans"}) == 403
    # Balances: accountants may record them.
    assert status(accountant, "POST", "/financial-position/balances", json=balance) == 200
    # Team and business settings: owner only.
    for headers in (manager, accountant):
        assert status(headers, "GET", "/team") == 403
        assert status(headers, "POST", "/invites", json={"role": "manager"}) == 403
        assert status(headers, "PATCH", "", json={"name": "Hijacked"}) == 403
    # Outsiders cannot even learn the business exists.
    for method, path in (("GET", "/datasets"), ("GET", "/team"), ("POST", "/invites")):
        assert status(stranger, method, path, json={"role": "manager"}) == 404

    # /me lists memberships; a member sees the business they joined.
    me = client.get("/api/auth/me", headers=accountant).json()
    assert [b["role"] for b in me["businesses"]] == ["accountant"]

    # Owner can change and remove members, but never the owner.
    team = client.get(f"{base}/team", headers=owner).json()
    acct_id = next(m["user_id"] for m in team["members"] if m["role"] == "accountant")
    owner_id = next(m["user_id"] for m in team["members"] if m["role"] == "owner")
    assert client.patch(f"{base}/members/{acct_id}", headers=owner, json={"role": "manager"}).status_code == 200
    assert client.patch(f"{base}/members/{owner_id}", headers=owner, json={"role": "manager"}).status_code == 400
    assert client.delete(f"{base}/members/{acct_id}", headers=owner).status_code == 200
    # Removal takes effect on the next request (roles are not cached in tokens).
    assert status(accountant, "GET", "/datasets") == 404


def test_invite_lifecycle(client):
    owner, business = signup(client, "owner2@example.com", "Kwame Pharmacy")
    base = f"/api/businesses/{business['id']}"
    token = invite(client, owner, business["id"], "accountant")
    assert client.get(f"/api/invites/{token}").json() == {
        "business_name": "Kwame Pharmacy", "role": "accountant", "expires_at": client.get(f"/api/invites/{token}").json()["expires_at"]}

    # An existing user accepts while signed in; the link is then used up.
    existing, own = signup(client, "efua@example.com", "Efua Events")
    assert client.post(f"/api/invites/{token}/accept", headers=existing).json()["business"]["role"] == "accountant"
    assert client.get(f"/api/invites/{token}").status_code == 404
    assert client.post(f"/api/invites/{token}/accept", headers=existing).status_code == 404
    me = client.get("/api/auth/me", headers=existing).json()
    assert [(b["name"], b["role"]) for b in me["businesses"]] == [("Efua Events", "owner"), ("Kwame Pharmacy", "accountant")]

    # Revoked and expired links fail, and signup with a dead link creates no account.
    revoked = invite(client, owner, business["id"], "manager")
    pending = client.get(f"{base}/team", headers=owner).json()["invites"]
    assert len(pending) == 1
    client.delete(f"{base}/invites/{pending[0]['id']}", headers=owner)
    assert client.post("/api/auth/signup", json={"email": "late@example.com", "password": "password123", "invite_token": revoked}).status_code == 404
    assert not db.one(config.DB_PATH, "SELECT id FROM users WHERE email = 'late@example.com'", ())
    expired = invite(client, owner, business["id"], "manager")
    db.insert(config.DB_PATH, "UPDATE business_invites SET expires_at = ? WHERE accepted_at IS NULL AND revoked_at IS NULL",
              ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),))
    assert client.get(f"/api/invites/{expired}").status_code == 404
    # Signup without an invite still needs a business name; the token is stored only as a hash.
    assert client.post("/api/auth/signup", json={"email": "x@example.com", "password": "password123"}).status_code == 422
    assert not db.one(config.DB_PATH, "SELECT id FROM business_invites WHERE token_hash = ?", (token,))
    _ = own


def test_daily_ai_cap(client, monkeypatch):
    owner, business = signup(client, "cap@example.com")
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 2)
    deps.spend_ai_call(business["id"])
    deps.spend_ai_call(business["id"])
    with pytest.raises(Exception) as error:
        deps.spend_ai_call(business["id"])
    assert getattr(error.value, "status_code", None) == 429
    _ = owner


def test_signed_out_token_gets_no_grace(client):
    from fastapi import Response

    from backend.routers import auth

    response = client.post("/api/auth/signup", json={"email": "out@example.com", "password": "password123", "business_name": "S"})
    old = response.cookies.get("ferlance_refresh")
    rotated = Response()
    auth.refresh(rotated, refresh_token=old)
    new_token = rotated.headers["set-cookie"].split("ferlance_refresh=")[1].split(";")[0]
    auth.logout(Response(), refresh_token=new_token)
    with pytest.raises(Exception) as error:
        auth.refresh(Response(), refresh_token=old)
    assert getattr(error.value, "status_code", None) == 401


def test_frontend_role_map_matches_backend():
    """The UI hides what the server would refuse; both must agree on every role's permissions."""
    import re
    from pathlib import Path

    source = (Path(__file__).parent.parent / "frontend/src/app/workspace.tsx").read_text()
    block = source[source.index("ROLE_PERMISSIONS"):source.index("};", source.index("ROLE_PERMISSIONS"))]
    for role, permissions in deps.ROLE_PERMISSIONS.items():
        listed = set(re.findall(r"'([a-z_]+)'", re.search(rf"{role}: \[([^\]]*)\]", block).group(1)))
        assert listed == set(permissions), role


def test_ai_refund_and_already_member_invite(client, monkeypatch):
    owner, business = signup(client, "refund@example.com")
    deps.spend_ai_call(business["id"])
    deps.refund_ai_call(business["id"])
    deps.refund_ai_call(business["id"])  # never below zero
    assert db.one(config.DB_PATH, "SELECT calls FROM ai_usage", ())["calls"] == 0

    member, _ = signup(client, "already@example.com", invite=invite(client, owner, business["id"], "manager"))
    again = client.post(f"/api/invites/{invite(client, owner, business['id'], 'accountant')}/accept", headers=member)
    assert again.status_code == 409 and again.json()["detail"]["business_id"] == business["id"]
