from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from io import BytesIO
import threading

from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from openpyxl import Workbook
import jwt

from backend import main


def test_signup_upload_and_history_are_tenant_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(main, "IMPORT_DIR", tmp_path / "incoming")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(main, "IMPORT_DIR", tmp_path / "incoming")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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


def test_public_and_app_pages_serve_structured_frontend(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)

    landing = client.get("/")
    app_shell = client.get("/app")
    styles = client.get("/assets/styles.css")

    assert "Business clarity from your records" in landing.text
    assert "Ferlance | Workspace" in app_shell.text
    assert styles.status_code == 200
    assert ".app-nav" in styles.text


def test_upload_rejects_unsupported_type(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "owner2@example.com", "password": "password123", "business_name": "Kojo Shop"})
    headers = {"Authorization": "Bearer " + signup.json()["access_token"]}
    business_id = signup.json()["business"]["id"]
    response = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.txt", b"data", "text/plain")})
    assert response.status_code == 415


def test_upload_rejects_files_over_configured_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 4)
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)

    signup = client.post("/api/auth/signup", json={"email": " Owner@Example.com ", "password": "password123", "business_name": "Ama Retail"})
    token = signup.json()["access_token"]
    assert jwt.decode(token, main.SECRET_KEY, algorithms=["HS256"])["type"] == "access"
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != token
    assert client.post("/api/auth/logout").json() == {"status": "signed_out"}
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_token_is_single_use_under_concurrent_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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
            main.refresh(Response(), refresh_token=refresh_token)
            return 200
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rotate(), range(2)))

    assert sorted(results) == [200, 401]


def test_profile_update_and_admin_capabilities(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "admin@example.com", "password": "password123", "business_name": "Old Name"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

    profile = client.patch("/api/auth/profile", headers=headers, json={"full_name": "Admin User", "business_name": "New Name"})
    assert profile.status_code == 200
    assert profile.json()["user"]["full_name"] == "Admin User"
    assert profile.json()["business"]["name"] == "New Name"
    assert client.get("/api/admin/capabilities", headers=headers).status_code == 403

    main.db.insert(main.DB_PATH, "UPDATE users SET role = 'admin' WHERE email = ?", ("admin@example.com",))
    capabilities = client.get("/api/admin/capabilities", headers=headers)
    assert capabilities.status_code == 200
    assert "manage_roles" in capabilities.json()["capabilities"]
    users = client.get("/api/admin/users", headers=headers)
    assert users.status_code == 200
    user_id = users.json()[0]["id"]
    changed = client.patch(f"/api/admin/users/{user_id}/role", headers=headers, json={"role": "member"})
    assert changed.status_code == 200
    assert changed.json()["role"] == "member"


def test_ask_lance_saves_two_way_conversation_history(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    monkeypatch.setattr(main, "ask_lance", lambda question, snapshot, history: f"Answer to: {question}")
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    captured = {}

    def fake_lance(question, snapshot, history):
        captured["snapshot"] = snapshot
        return "Cross-dataset answer"

    monkeypatch.setattr(main, "ask_lance", fake_lance)
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)

    def unavailable(*args, **kwargs):
        raise RuntimeError("Model provider unavailable.")

    monkeypatch.setattr(main, "ask_lance", unavailable)
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    monkeypatch.setattr(main, "ask_lance", lambda *args, **kwargs: "Should not run.")
    client = TestClient(main.app)
    signup = client.post("/api/auth/signup", json={"email": "missing-records@example.com", "password": "password123", "business_name": "Ama Retail"})
    headers = {"Authorization": "Bearer " + signup.json()["access" + "_token"]}
    business_id = signup.json()["business"]["id"]
    fixture = Path(__file__).parent / "fixtures" / "valid_sales.csv"
    upload = client.post(f"/api/businesses/{business_id}/datasets", headers=headers, files={"file": ("sales.csv", fixture.read_bytes(), "text/csv")})
    dataset = main.db.one(main.DB_PATH, "SELECT processed_path FROM datasets WHERE id = ?", (upload.json()["id"],))
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
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
    client = TestClient(main.app)
    forged = jwt.encode({"sub": "missing", "type": "access"}, "wrong", algorithm="HS256")
    expired = jwt.encode({"sub": "missing", "type": "access", "exp": 1}, main.SECRET_KEY, algorithm="HS256")

    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_insights_and_predefined_questions_are_tenant_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(main, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(main, "PROCESSED_DIR", tmp_path / "processed")
    main.RAW_DIR.mkdir()
    main.PROCESSED_DIR.mkdir()
    main.db.initialize(main.DB_PATH)
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
