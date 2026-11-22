from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from io import BytesIO
import re
import threading

from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from openpyxl import Workbook
import jwt

from backend import config, db, main
from backend.routers import auth, lance


def test_signup_upload_and_history_are_tenant_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)

    signup = client.post("/api/auth/signup", json={"email": "owner@example.com", "password": "password123", "business_name": "Ama Retail"})
    assert signup.status_code == 200
    token = signup.json()["access_token"]
    business_id = signup.json()["business"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    fixture = Path(__file__).parent / "fixtures" / "valid_sales.csv"

    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})
    assert upload.status_code == 200
    assert upload.json()["status"] == "processed"
    assert upload.json()["accepted_rows"] == 3

    records = client.get(f"/api/businesses/{business_id}/datasets/{upload.json()['id']}/records", headers=headers)
    assert records.status_code == 200
    assert records.json()["count"] == 3
    assert len(records.json()["records"]) == 3

    history = client.get(f"/api/businesses/{business_id}/datasets", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 1

    forbidden = client.get("/api/businesses/not-owned/datasets", headers=headers)
    assert forbidden.status_code == 404


def test_folder_import_status_is_scoped_to_business(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(config, "IMPORT_DIR", tmp_path / "incoming")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)

    signup = client.post("/api/auth/signup", json={"email": "folder@example.com", "password": "password123", "business_name": "Folder Shop"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]

    response = client.get(f"/api/businesses/{business_id}/folder-imports", headers=headers)
    forbidden = client.get("/api/businesses/not-owned/folder-imports", headers=headers)

    assert response.status_code == 200
    assert response.json()["folder"] == str((tmp_path / "incoming" / business_id).resolve())
    assert response.json()["imports"] == []
    assert forbidden.status_code == 404


def _frontend_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    return TestClient(main.app)


def test_pages_route_to_the_built_entries_and_fall_back_for_client_routes(tmp_path, monkeypatch):
    client = _frontend_client(tmp_path, monkeypatch)
    dist = tmp_path / "dist"
    (dist / "app").mkdir(parents=True)
    (dist / "index.html").write_text("<title>landing entry</title>")
    (dist / "app" / "index.html").write_text("<title>workspace entry</title>")
    monkeypatch.setattr(config, "FRONTEND_DIST", dist)

    landing = client.get("/")
    workspace = client.get("/app")
    deep_link = client.get("/app/products")

    assert "landing entry" in landing.text
    assert "workspace entry" in workspace.text
    assert "workspace entry" in deep_link.text
    assert landing.headers["cache-control"] == "no-cache"
    assert deep_link.headers["cache-control"] == "no-cache"


def test_pages_explain_how_to_build_when_the_frontend_is_missing(tmp_path, monkeypatch):
    client = _frontend_client(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "FRONTEND_DIST", tmp_path / "missing")

    response = client.get("/app")

    assert response.status_code == 503
    assert "npm --prefix frontend run build" in response.text
    assert client.get("/health").status_code == 200


def test_built_frontend_serves_landing_workspace_and_immutable_assets(tmp_path, monkeypatch):
    built = config.FRONTEND_DIST / "app" / "index.html"
    assert built.is_file(), "Frontend not built: run `npm --prefix frontend ci && npm --prefix frontend run build` before pytest."
    client = _frontend_client(tmp_path, monkeypatch)

    landing = client.get("/")
    workspace = client.get("/app")
    script = re.search(r'src="(/assets/[^"]+\.js)"', workspace.text)
    styles = re.findall(r'href="(/assets/[^"]+\.css)"', workspace.text)

    assert landing.status_code == 200
    assert "Business intelligence for growing businesses" in landing.text
    assert "Ferlance | Workspace" in workspace.text
    assert 'id="root"' in workspace.text
    assert script, "workspace HTML should reference a bundled script"
    bundle = client.get(script.group(1))
    assert bundle.status_code == 200
    assert bundle.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert any("--mint-glow" in client.get(href).text for href in styles)
    assert client.get("/assets/missing-file.js").status_code == 404


def test_upload_rejects_unsupported_type(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "owner2@example.com", "password": "password123", "business_name": "Kojo Shop"})
    headers = {"Authorization": "Bearer " + signup.json()["access_token"]}
    business_id = signup.json()["business"]["id"]
    response = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.pdf", b"data", "application/pdf")})
    assert response.status_code == 415


def test_upload_rejects_files_over_configured_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 4)
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "large@example.com", "password": "password123", "business_name": "Kojo Shop"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]

    response = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", b"12345", "text/csv")})

    assert response.status_code == 413


def _xlsx_bytes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Date", "Revenue", "Product"])
    sheet.append(["2026-01-02", "1250.50", "Rice"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_valid_xlsx_upload_has_readable_records(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "xlsx@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]

    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.xlsx", _xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

    assert upload.status_code == 200
    assert upload.json()["status"] == "processed"
    records = client.get(f"/api/businesses/{business_id}/datasets/{upload.json()['id']}/records", headers=headers)
    assert records.json()["records"][0]["product"] == "Rice"


def test_malformed_xlsx_is_failed_and_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "broken@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]

    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("broken.xlsx", b"not xlsx", "application/octet-stream")})

    assert upload.json()["status"] == "failed"
    assert upload.json()["errors"] == ["The XLSX file is malformed or unreadable."]
    history = client.get(f"/api/businesses/{business_id}/datasets", headers=headers)
    assert history.json()[0]["id"] == upload.json()["id"]
    records = client.get(f"/api/businesses/{business_id}/datasets/{upload.json()['id']}/records", headers=headers)
    assert records.json()["count"] == 0


def test_partial_upload_reports_rejected_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "partial@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]
    fixture = Path(__file__).parent / "fixtures" / "invalid_sales.csv"

    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})

    assert upload.json()["status"] == "partial"
    assert upload.json()["accepted_rows"] == 1
    assert upload.json()["rejected_rows"] == 2
    records = client.get(f"/api/businesses/{business_id}/datasets/{upload.json()['id']}/records", headers=headers)
    assert records.json()["count"] == upload.json()["accepted_rows"]


def test_analytics_returns_filtered_metrics_and_unavailable_states(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "analytics@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]
    fixture = Path(__file__).parent / "fixtures" / "valid_sales.csv"
    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})

    response = client.get(
        f"/api/businesses/{business_id}/analytics",
        headers=headers,
        params={"dataset_id": upload.json()["id"], "from": "2026-01-03", "to": "2026-01-03"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["revenue"] == {"total": 1350.0, "currency": "GHS", "transactions": 2, "average_sale": 675.0}
    assert body["trend"]["daily"] == [{"period": "2026-01-03", "revenue": 1350.0, "transactions": 2}]
    assert body["products"]["items"][0]["product"] == "Rice"
    assert body["customers"]["number_of_customers"] == 2
    assert body["customers"]["repeat_customers"] == 0
    assert body["profit"]["available"] is False
    assert body["inventory"]["available"] is False
    assert body["kpis"]["top_product"] == "Rice"


def test_analytics_rejects_invalid_date_range_and_failed_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "analytics-errors@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]
    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("empty.csv", b"", "text/csv")})

    invalid_range = client.get(f"/api/businesses/{business_id}/analytics", headers=headers, params={"from": "2026-02-01", "to": "2026-01-01"})
    failed = client.get(f"/api/businesses/{business_id}/analytics", headers=headers, params={"dataset_id": upload.json()["id"]})

    assert invalid_range.status_code == 400
    assert failed.status_code == 409


def test_analytics_is_tenant_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    first = client.post("/api/auth/signup", json={"email": "analytics-first@example.com", "password": "password123", "business_name": "First"})
    second = client.post("/api/auth/signup", json={"email": "analytics-second@example.com", "password": "password123", "business_name": "Second"})
    first_headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
    second_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}
    first_business = first.json()["business"]["id"]
    second_business = second.json()["business"]["id"]
    fixture = Path(__file__).parent / "fixtures" / "valid_sales.csv"
    upload = client.post(f"/api/businesses/{first_business}/datasets", headers=first_headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})

    response = client.get(f"/api/businesses/{second_business}/analytics", headers=second_headers, params={"dataset_id": upload.json()["id"]})

    assert response.status_code == 404


def test_jwt_session_refresh_logout_and_me_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)

    signup = client.post("/api/auth/signup", json={"email": " Owner@Example.com ", "password": "password123", "business_name": "Ama Retail"})
    token = signup.json()["access_token"]
    assert jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])["type"] == "access"
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != token
    assert client.post("/api/auth/logout").json() == {"status": "signed_out"}
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_token_is_single_use_under_concurrent_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post(
        "/api/auth/signup",
        json={"email": "refresh-race@example.com", "password": "password123", "business_name": "Ama Retail"},
    )
    refresh_token = signup.cookies.get("ferlance_refresh")
    barrier = threading.Barrier(2)

    def rotate():
        barrier.wait()
        try:
            auth.refresh(Response(), refresh_token=refresh_token)
            return 200
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rotate(), range(2)))

    # One request rotates the token; the other is served once by the reuse grace window.
    assert sorted(results) == [200, 200]
    # The grace is one-shot: a third use of the same token is refused.
    assert _refresh_status(refresh_token) == 401


def _refresh_status(token):
    try:
        auth.refresh(Response(), refresh_token=token)
        return 200
    except HTTPException as error:
        return error.status_code


def test_rotated_refresh_token_grace_window(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "grace@example.com", "password": "password123", "business_name": "G"})
    old = signup.cookies.get("ferlance_refresh")
    first = Response()
    auth.refresh(first, refresh_token=old)  # rotates; pretend this response was lost
    assert _refresh_status(old) == 200  # retried within the grace window
    assert _refresh_status(old) == 401  # only once

    # Outside the window, or after sign-out, a rotated token is refused.
    signup2 = client.post("/api/auth/signup", json={"email": "grace2@example.com", "password": "password123", "business_name": "G"})
    old2 = signup2.cookies.get("ferlance_refresh")
    auth.refresh(Response(), refresh_token=old2)
    monkeypatch.setattr(config, "REFRESH_REUSE_GRACE_SECONDS", -1)
    assert _refresh_status(old2) == 401


def test_profile_update_and_admin_capabilities(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "admin@example.com", "password": "password123", "business_name": "Old Name"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    profile = client.patch("/api/auth/profile", headers=headers, json={"full_name": "Admin User"})
    assert profile.status_code == 200
    assert profile.json()["user"]["full_name"] == "Admin User"
    renamed = client.patch(f"/api/businesses/{signup.json()['business']['id']}", headers=headers, json={"name": "New Name"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "New Name"
    assert client.get("/api/admin/capabilities", headers=headers).status_code == 403

    db.insert(config.DB_PATH, "UPDATE users SET role = 'admin' WHERE email = ?", ("admin@example.com",))
    capabilities = client.get("/api/admin/capabilities", headers=headers)
    assert capabilities.status_code == 200
    assert "manage_roles" in capabilities.json()["capabilities"]
    users = client.get("/api/admin/users", headers=headers)
    assert users.status_code == 200
    admin_id = users.json()[0]["id"]
    self_demotion = client.patch(f"/api/admin/users/{admin_id}/role", headers=headers, json={"role": "member"})
    assert self_demotion.status_code == 400

    client.post("/api/auth/signup", json={"email": "staff@example.com", "password": "password123", "business_name": "Staff Shop"})
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "password123"})
    staff_id = next(item["id"] for item in client.get("/api/admin/users", headers=headers).json() if item["email"] == "staff@example.com")
    changed = client.patch(f"/api/admin/users/{staff_id}/role", headers=headers, json={"role": "member"})
    assert changed.status_code == 200
    assert changed.json()["role"] == "member"


def test_ask_lance_saves_two_way_conversation_history(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    monkeypatch.setattr(lance, "ask_lance", lambda question, snapshot, history: f"Answer to: {question}")
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "chat@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]
    fixture = Path(__file__).parent / "fixtures" / "valid_sales.csv"
    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})
    dataset_id = upload.json()["id"]

    first = client.post(f"/api/businesses/{business_id}/ask-lance", headers=headers, params={"dataset_id": dataset_id}, json={"question": "Which product leads?"})
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]
    second = client.post(f"/api/businesses/{business_id}/ask-lance", headers=headers, params={"dataset_id": dataset_id}, json={"conversation_id": conversation_id, "question": "Why does it lead?"})
    assert second.status_code == 200

    conversations = client.get(f"/api/businesses/{business_id}/ask-lance/conversations", headers=headers)
    assert conversations.status_code == 200
    assert conversations.json()[0]["id"] == conversation_id
    saved = client.get(f"/api/businesses/{business_id}/ask-lance/conversations/{conversation_id}", headers=headers)
    assert [message["role"] for message in saved.json()["messages"]] == ["user", "assistant", "user", "assistant"]
    assert saved.json()["messages"][-1]["content"] == "Answer to: Why does it lead?"

    other = client.post("/api/auth/signup", json={"email": "other-chat@example.com", "password": "password123", "business_name": "Other"})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    forbidden = client.get(f"/api/businesses/{other.json()['business']['id']}/ask-lance/conversations/{conversation_id}", headers=other_headers)
    assert forbidden.status_code == 404


def test_ask_lance_retrieves_across_all_business_datasets(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    captured = {}

    def fake_lance(question, snapshot, history):
        captured["snapshot"] = snapshot
        return "Cross-dataset answer"

    monkeypatch.setattr(lance, "ask_lance", fake_lance)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "rag@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]
    first = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", b"date,amount,product\n2026-01-01,100,Rice\n", "text/csv")})
    second = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("cost.csv", b"date,total_cost_usd,project_name\n2026-01-02,40,Store renovation\n", "text/csv")})
    assert first.json()["status"] == "processed"
    assert second.json()["status"] == "processed"

    response = client.post(f"/api/businesses/{business_id}/ask-lance", headers=headers, params={"dataset_id": first.json()["id"]}, json={"question": "What do we know about renovation and rice?"})

    assert response.status_code == 200
    assert response.json()["datasets_considered"] == 2
    assert captured["snapshot"]["scope"] == "all accepted records across this business"
    analytics = captured["snapshot"]["analytics"]
    assert analytics["currency"] == "MIXED"
    assert analytics["monetary_aggregation_available"] is False
    assert analytics["by_currency"]["GHS"]["revenue"]["total"] == 100.0
    assert analytics["by_currency"]["USD"]["kpis"]["total_cost"] == 40.0
    assert "revenue" not in analytics
    evidence = " ".join(item["evidence"] for item in captured["snapshot"]["retrieved_evidence"])
    assert "renovation" in evidence.lower()
    assert "rice" in evidence.lower()


def test_ask_lance_does_not_create_empty_conversation_when_provider_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)

    def unavailable(*args, **kwargs):
        raise RuntimeError("Model provider unavailable.")

    monkeypatch.setattr(lance, "ask_lance", unavailable)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "failed-chat@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": "Bearer " + signup.json()["access" + "_token"]}
    business_id = signup.json()["business"]["id"]
    fixture = Path(__file__).parent / "fixtures" / "valid_sales.csv"
    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})

    response = client.post(
        f"/api/businesses/{business_id}/ask-lance",
        headers=headers,
        params={"dataset_id": upload.json()["id"]},
        json={"question": "Which product leads?"},
    )

    assert response.status_code == 503
    assert client.get(f"/api/businesses/{business_id}/ask-lance/conversations", headers=headers).json() == []


def test_ask_lance_reports_unavailable_processed_records(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    monkeypatch.setattr(lance, "ask_lance", lambda *args, **kwargs: "Should not run.")
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "missing-records@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": "Bearer " + signup.json()["access" + "_token"]}
    business_id = signup.json()["business"]["id"]
    fixture = Path(__file__).parent / "fixtures" / "valid_sales.csv"
    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})
    dataset = db.one(config.DB_PATH, "SELECT processed_path FROM datasets WHERE id = ?", (upload.json()["id"],))
    Path(dataset["processed_path"]).write_text("{not-json}\n", encoding="utf-8")

    response = client.post(
        f"/api/businesses/{business_id}/ask-lance",
        headers=headers,
        params={"dataset_id": upload.json()["id"]},
        json={"question": "What were the sales?"},
    )

    assert response.status_code == 503
    assert "Processed records" in response.json()["detail"]
    assert client.get(f"/api/businesses/{business_id}/ask-lance/conversations", headers=headers).json() == []


def test_auth_rejects_forged_and_expired_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    forged = jwt.encode({"sub": "missing", "type": "access"}, "wrong", algorithm="HS256")
    expired = jwt.encode({"sub": "missing", "type": "access", "exp": 1}, config.SECRET_KEY, algorithm="HS256")

    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_insights_and_predefined_questions_are_tenant_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "insights@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    business_id = signup.json()["business"]["id"]
    fixture = Path(__file__).parent / "fixtures" / "valid_sales.csv"
    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})
    dataset_id = upload.json()["id"]

    insights = client.get(f"/api/businesses/{business_id}/insights", headers=headers, params={"dataset_id": dataset_id})
    question = client.get(f"/api/businesses/{business_id}/questions/best-products", headers=headers, params={"dataset_id": dataset_id})
    unknown = client.get(f"/api/businesses/{business_id}/questions/unknown", headers=headers)

    assert insights.status_code == 200
    assert insights.json()["dataset"]["id"] == dataset_id
    assert question.status_code == 200
    assert question.json()["answer"][0]["product"] == "Rice"
    assert unknown.status_code == 404


def test_datasets_report_their_record_date_span_and_old_rows_are_backfilled(tmp_path, monkeypatch):
    from backend import dataset_store

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "period@example.com", "password": "password123", "business_name": "Period Shop"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    base = f"/api/businesses/{signup.json()['business']['id']}"
    csv = b"transaction_date,product,amount\n2026-03-04,Rice,10\n2026-01-15,Beans,5\n2026-02-01,Oil,7\n"

    upload = client.post(f"{base}/datasets", headers=headers, files={"file": ("sales.csv", csv, "text/csv")})
    assert upload.json()["period"] == {"from": "2026-01-15", "to": "2026-03-04"}

    # A file imported before the span was stored is filled in once, from its records.
    db.insert(config.DB_PATH, "UPDATE datasets SET period_from = NULL, period_to = NULL", ())
    assert client.get(f"{base}/datasets", headers=headers).json()[0]["period"] == {"from": None, "to": None}
    dataset_store.backfill_periods()
    assert client.get(f"{base}/datasets", headers=headers).json()[0]["period"] == {"from": "2026-01-15", "to": "2026-03-04"}
    analytics = client.get(f"{base}/analytics", headers=headers).json()
    assert analytics["available_period"] == {"from": "2026-01-15", "to": "2026-03-04"}


def test_responses_are_gzipped_except_auth():
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    body = PlainTextResponse("x" * 5000)
    inner = Starlette(routes=[Route("/api/auth/refresh", lambda request: body), Route("/api/businesses/b/analytics", lambda request: body)])
    client = TestClient(main._Compression(inner))
    headers = {"Accept-Encoding": "gzip"}
    assert "content-encoding" not in client.get("/api/auth/refresh", headers=headers).headers
    assert client.get("/api/businesses/b/analytics", headers=headers).headers["content-encoding"] == "gzip"
    # The real app is wrapped too.
    assert any(item.cls is main._Compression for item in main.app.user_middleware)


def test_backfill_retries_files_that_are_unreadable(tmp_path, monkeypatch):
    from backend import dataset_store

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "retry@example.com", "password": "password123", "business_name": "Retry Shop"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    base = f"/api/businesses/{signup.json()['business']['id']}"
    client.post(f"{base}/datasets", headers=headers, files={"file": ("s.csv", b"transaction_date,product,amount\n2026-02-03,Rice,10\n", "text/csv")})
    db.insert(config.DB_PATH, "UPDATE datasets SET period_from = NULL, period_to = NULL", ())
    processed = next(config.PROCESSED_DIR.iterdir())
    hidden = processed.with_suffix(".hidden")
    processed.rename(hidden)
    monkeypatch.setattr(dataset_store, "_resolve", lambda stored, directory: processed)  # file temporarily missing
    dataset_store.backfill_periods()
    assert db.one(config.DB_PATH, "SELECT period_from FROM datasets", ())["period_from"] is None
    hidden.rename(processed)
    dataset_store.backfill_periods()
    assert client.get(f"{base}/datasets", headers=headers).json()[0]["period"] == {"from": "2026-02-03", "to": "2026-02-03"}
