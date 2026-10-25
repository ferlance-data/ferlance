import httpx
from fastapi.testclient import TestClient

from backend import config, db, main
from backend import market_research


def _client(tmp_path, monkeypatch, email="research@example.com"):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "research.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(market_research, "SECRET_KEY", "test-secret-key-longer-than-thirty-two-characters")
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


def test_search_key_is_encrypted_tenant_scoped_and_removable(tmp_path, monkeypatch):
    client, business_id, headers = _client(tmp_path, monkeypatch)
    endpoint = f"/api/businesses/{business_id}/integrations/brave-search"
    key = "brave-owner-key-not-for-the-database"
    assert client.get(endpoint, headers=headers).json()["configured"] is False
    saved = client.put(endpoint, headers=headers, json={"api_key": key})
    assert saved.status_code == 200
    assert saved.json()["configured"] is True
    stored = db.one(
        config.DB_PATH,
        "SELECT encrypted_api_key FROM business_integrations WHERE business_id = ?",
        (business_id,),
    )
    assert stored["encrypted_api_key"] != key
    assert market_research._brave_key(config.DB_PATH, business_id) == key
    removed = client.delete(endpoint, headers=headers)
    assert removed.json() == {"configured": False}
    assert client.get(endpoint, headers=headers).json()["configured"] is False


def test_performance_research_uses_search_sources_and_reports_model_state(tmp_path, monkeypatch):
    client, business_id, headers = _client(tmp_path, monkeypatch)
    upload = client.post(
        f"/api/businesses/{business_id}/datasets",
        headers=headers,
        files={
            "file": (
                "sales.csv",
                b"Date,Product,Revenue\n2026-01-09,Rice,100\n2026-01-10,Rice,40\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200
    integration = f"/api/businesses/{business_id}/integrations/brave-search"
    assert client.post(
        f"/api/businesses/{business_id}/performance-research",
        headers=headers,
        params={"dataset_id": upload.json()["id"], "from": "2026-01-10", "to": "2026-01-10"},
    ).status_code == 503
    assert client.put(
        integration, headers=headers, json={"api_key": "brave-owner-key"}
    ).status_code == 200

    queries = []
    assessments = []

    def fake_search(query, api_key):
        queries.append((query, api_key))
        return [{
            "title": "Ghana seasonal demand and rainfall patterns",
            "description": "Public seasonal context for retail food demand.",
            "url": "https://example.test/ghana-seasonality",
            "age": "2026-01-01",
        }]

    def fake_lance(question, evidence, history):
        assessments.append((question, evidence, history))
        return "The source suggests a possible seasonal link [S1], but it does not establish causation."

    monkeypatch.setattr(market_research, "_search", fake_search)
    monkeypatch.setattr(market_research, "ask_lance", fake_lance)
    response = client.post(
        f"/api/businesses/{business_id}/performance-research",
        headers=headers,
        params={"dataset_id": upload.json()["id"], "from": "2026-01-10", "to": "2026-01-10"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["market"] == "Ghana"
    assert result["status"] == "complete"
    assert any(item["product"] == "Rice" for item in result["findings"])
    assert result["sources"][0]["url"] == "https://example.test/ghana-seasonality"
    assert result["analysis"].endswith("not establish causation.")
    assert len(queries) >= 1
    assert all(key == "brave-owner-key" for _, key in queries)
    assert any("Rice" in query for query, _ in queries)
    assert all("Ghana" in query for query, _ in queries)
    assert all("100" not in query and "40" not in query for query, _ in queries)
    assert assessments[0][1]["external_sources"][0]["untrusted_web_content"] is True
    assert result["limitations"]


def test_search_credentials_require_strong_application_secret(tmp_path, monkeypatch):
    client, business_id, headers = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(market_research, "SECRET_KEY", "weak")
    response = client.put(
        f"/api/businesses/{business_id}/integrations/brave-search",
        headers=headers,
        json={"api_key": "brave-owner-key"},
    )
    assert response.status_code == 503
    assert "FERLANCE_SECRET_KEY" in response.json()["detail"]


def test_search_rejects_non_web_urls():
    class FakeClient:
        def get(self, *args, **kwargs):
            return httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {"title": "Unsafe", "url": "javascript:alert(1)"},
                            {"title": "Malformed", "url": "https://[invalid"},
                            {"title": "Safe", "url": "https://example.test/source"},
                        ]
                    }
                },
                request=httpx.Request("GET", market_research.BRAVE_SEARCH_URL),
            )

    sources = market_research._search("Ghana rice demand", "test-key", client=FakeClient())

    assert [source["url"] for source in sources] == ["https://example.test/source"]
