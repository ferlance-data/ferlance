from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import advisor, config, db, ghana_calendar, llm, main, news_context

START = date(2026, 9, 1)  # previous window: Sep 1–30, current: Oct 1–30
CUR = (date(2026, 10, 1), date(2026, 10, 30))


def sale(day: date, product: str, amount: float, *, cost: float | None = None, quantity: float | None = None, customer: str | None = None) -> dict:
    record = {"transaction_date": day.isoformat(), "product": product, "amount": amount}
    if cost is not None:
        record["cost"] = cost
    if quantity is not None:
        record["quantity"] = quantity
    if customer:
        record["customer"] = customer
    return record


def daily(product: str, start: date, days: int, every: int = 1, **kwargs) -> list[dict]:
    return [sale(start + timedelta(days=offset), product, **kwargs) for offset in range(0, days, every)]


def kinds(result: dict) -> dict[str, dict]:
    return {f"{item['kind']}:{item.get('product') or ''}": item for item in result["items"]}


def test_decline_explains_price_vs_volume_and_lapsed_regulars():
    records = (
        daily("Rice", START, 30, amount=100, quantity=2, cost=140, customer="Kofi")
        + daily("Rice", CUR[0], 30, every=3, amount=110, quantity=2, cost=140, customer="Ama")
    )
    result = advisor.build(records, *CUR)
    item = kinds(result)["decline:Rice"]
    assert item["severity"] == "attention"
    texts = " ".join(reason["text"] for reason in item["reasons"])
    assert "higher" in texts and "fewer units" in texts
    customers = next(reason for reason in item["reasons"] if reason["basis"] == "customers")
    assert customers["people"] == ["Kofi"]
    assert "Kofi" not in customers["text"]
    assert any("regular buyer" in action for action in item["actions"])


def test_small_numbers_are_not_called_a_decline():
    records = [sale(START, "Gari", 50), sale(START + timedelta(days=3), "Gari", 50), sale(CUR[0], "Gari", 50)]
    assert "decline:Gari" not in kinds(advisor.build(records, *CUR))


def test_loss_and_margin_squeeze_need_costs_and_say_what_price_restores_margin():
    records = (
        daily("Oil", START, 30, amount=50, quantity=1, cost=40)
        + daily("Oil", CUR[0], 30, amount=50, quantity=1, cost=55)
        + daily("Milo", START, 30, amount=100, quantity=1, cost=60)
        + daily("Milo", CUR[0], 30, amount=100, quantity=1, cost=75)
    )
    found = kinds(advisor.build(records, *CUR))
    assert found["loss:Oil"]["severity"] == "risk"
    assert any("above GH₵55.00" in action for action in found["loss:Oil"]["actions"])
    margin = found["margin:Milo"]
    assert "40% → 25%" in margin["summary"]
    assert any("GH₵125 " in action for action in margin["actions"])  # 75 / (1 - 0.40)

    no_costs = [{key: value for key, value in record.items() if key != "cost"} for record in records]
    result = advisor.build(no_costs, *CUR)
    assert not any(item["kind"] in {"loss", "margin"} for item in result["items"])
    assert any("item costs" in note for note in result["missing"])


def test_restock_and_slow_stock_match_inventory_by_name_only():
    records = daily("Sugar", START, 60, amount=18, quantity=3)
    stock = [
        {"name": "  sugar ", "quantity_on_hand": 10, "stock_value": 120, "active": True},
        {"name": "Sardines", "quantity_on_hand": 50, "stock_value": 500, "active": True},
        {"name": "Sugar 1kg", "quantity_on_hand": 0, "stock_value": 0, "active": True},  # different name: not matched
    ]
    found = kinds(advisor.build(records, *CUR, stock))
    restock = found["restock:Sugar"]
    assert "About 3 days" in restock["summary"]
    assert any("matched by name" in entry["label"] for entry in restock["evidence"])
    assert "slow_stock:Sardines" in found
    assert not any(key.endswith("Sugar 1kg") for key in found)


def test_star_concentration_and_busiest_day_are_normalised():
    records = []
    for offset in range(30):
        day = CUR[0] + timedelta(days=offset)
        records.append(sale(day, "Rice", 300 if day.weekday() == 5 else 100, cost=60))
        records.append(sale(day, "Beans", 20, cost=15))
        records.append(sale(day, "Oil", 10, cost=8))
    found = kinds(advisor.build(records, *CUR))
    assert found["star:Rice"]["title"] == "Sell more Rice"
    assert "concentration:Rice" in found
    assert found["best_day:"]["title"] == "Saturday is your busiest day"


def test_missing_data_is_reported_instead_of_guessed():
    result = advisor.build([sale(CUR[0], "", 10)], *CUR)
    assert result["items"] == []
    joined = " ".join(result["missing"])
    for phrase in ("product column", "period before", "year of history"):
        assert phrase in joined


def test_seasonal_reason_needs_a_year_of_history():
    last_year = (CUR[0] - timedelta(days=365), CUR[1] - timedelta(days=365))
    ly_prev = (START - timedelta(days=365), START - timedelta(days=336))
    records = (
        daily("Yam", ly_prev[0], 30, amount=100)
        + daily("Yam", last_year[0], 30, every=2, amount=100)
        + daily("Yam", START, 30, amount=100)
        + daily("Yam", CUR[0], 30, every=2, amount=100)
    )
    item = kinds(advisor.build(records, *CUR))["decline:Yam"]
    assert any(reason["basis"] == "seasonal" for reason in item["reasons"])
    short = advisor.build([r for r in records if r["transaction_date"] >= START.isoformat()], *CUR)
    assert not any(reason["basis"] == "seasonal" for reason in kinds(short)["decline:Yam"]["reasons"])


def test_calendar():
    assert ghana_calendar.easter(2026) == date(2026, 4, 5)
    names = [event.name for event in ghana_calendar.events_between(date(2026, 12, 20), date(2026, 12, 31))]
    assert "Christmas Day" in names and "Christmas and New Year season" in names
    diff = ghana_calendar.notable_difference((date(2027, 1, 10), date(2027, 2, 8)), (date(2026, 12, 11), date(2027, 1, 9)))
    assert ("previous", "Christmas and New Year season") in [(side, event.name) for side, event in diff]


def test_explain_prompt_keeps_customer_names_out_and_marks_file_text_as_data():
    records = daily("Rice <b>", START, 30, amount=100, customer="Kofi Mensah") + daily("Rice <b>", CUR[0], 30, every=3, amount=100, customer="Ama")
    result = advisor.build(records, *CUR)
    item = kinds(result)["decline:Rice <b>"]
    prompt = advisor.explain_prompt(item, result, [{"title": "Rice prices rise", "source": "example.com", "date": "20261010", "url": "https://example.com"}])
    assert "Kofi" not in prompt and "Ama" not in prompt
    assert "<b>" not in prompt and "<data>" in prompt
    assert "Rice prices rise (example.com" in prompt


class _Response:
    def __init__(self, payload=None, text=False):
        self.payload, self.text = payload, text
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        if self.text:
            raise ValueError("not json")
        return self.payload


def test_news_search_is_best_effort_and_cached(monkeypatch):
    monkeypatch.setattr(news_context, "MIN_SPACING_SECONDS", 0)
    news_context._cache.clear()
    calls = []

    class Client:
        @staticmethod
        def get(url, params, timeout):
            calls.append(params)
            return _Response({"articles": [{"title": "Rice shortage", "url": "https://news.test/a", "domain": "news.test", "seendate": "20261010T100000Z"}, {"title": "bad", "url": "javascript:x"}]})

    first = news_context.search("Rice 5kg!", date(2026, 10, 1), date(2026, 10, 30), client=Client)
    again = news_context.search("rice 5kg", date(2026, 10, 1), date(2026, 10, 30), client=Client)
    assert first == again == [{"title": "Rice shortage", "url": "https://news.test/a", "source": "news.test", "date": "20261010"}]
    assert len(calls) == 1 and calls[0]["query"] == "Rice sourcecountry:GH"

    class Limited:
        @staticmethod
        def get(url, params, timeout):
            return _Response(text=True)  # GDELT's rate-limit notice is plain text

    assert news_context.search("cooking oil", client=Limited) == []
    assert news_context.search("5 !!") == []


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    config.RAW_DIR.mkdir()
    config.PROCESSED_DIR.mkdir()
    db.initialize(config.DB_PATH)
    return TestClient(main.app)


def _signup(client):
    signup = client.post("/api/auth/signup", json={"email": "advice@example.com", "password": "password123", "business_name": "Advice Shop"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    base = f"/api/businesses/{signup.json()['business']['id']}"
    rows = ["transaction_date,product,customer,quantity,amount,cost"]
    rows += [f"{(START + timedelta(days=d)).isoformat()},Rice,Kofi,2,200,150" for d in range(30)]
    rows += [f"{(CUR[0] + timedelta(days=d)).isoformat()},Rice,Ama,2,200,150" for d in range(0, 30, 3)]
    client.post(f"{base}/datasets", headers=headers, files={"file": ("s.csv", "\n".join(rows) + "\n", "text/csv")})
    return headers, base


def test_insights_include_advice_and_explain_is_server_built_and_cached(client, monkeypatch):
    headers, base = _signup(client)
    window = "from=2026-10-01&to=2026-10-30"
    advice = client.get(f"{base}/insights?{window}", headers=headers).json()["advice"]
    decline = next(item for item in advice["items"] if item["kind"] == "decline")
    assert advice["ai_available"] is False
    assert client.post(f"{base}/insights/{decline['id']}/explain?{window}", headers=headers).status_code == 503

    monkeypatch.setattr(llm, "OPENROUTER_KEY", "key")
    monkeypatch.setattr(llm, "GROQ_API_KEY", "")
    monkeypatch.setattr(llm, "OPENROUTER_MODELS", ("m",))
    monkeypatch.setattr(news_context, "search", lambda *args, **kwargs: [])
    sent = []

    def post(url, headers, json, timeout):
        sent.append(json)
        assert "tools" not in json
        return _Response({"choices": [{"message": {"content": "Rice is down because fewer units sold. <script>x</script>"}}]})

    monkeypatch.setattr(llm.httpx, "post", post)
    first = client.post(f"{base}/insights/{decline['id']}/explain?{window}", headers=headers).json()
    second = client.post(f"{base}/insights/{decline['id']}/explain?{window}", headers=headers).json()
    assert first["explanation"].startswith("Rice is down") and first["cached"] is False
    assert second["cached"] is True and second["explanation"] == first["explanation"]
    assert len(sent) == 1
    assert "Kofi" not in str(sent[0]) and "Ama" not in str(sent[0])

    assert client.post(f"{base}/insights/not-a-real-id/explain?{window}", headers=headers).status_code == 404
    assert client.post(f"{base}/performance-research", headers=headers).status_code in (404, 405)
    assert client.get(f"{base}/integrations/brave-search", headers=headers).status_code == 404


def test_lance_news_tool_replaces_paid_search(monkeypatch):
    monkeypatch.setattr(news_context, "search", lambda query, *args, **kwargs: [{"title": f"News about {query}", "source": "news.test", "date": "20261010", "url": "https://news.test"}])
    assert "News about rice prices" in llm._news("rice prices")
    assert llm.NEWS_TOOL["function"]["name"] == "news_search"
    assert not hasattr(llm, "SERPAPI_KEY")
    _ = httpx  # imported for the fake responses above


def test_placeholder_customers_are_never_regular_buyers():
    records = (
        daily("Bread", START, 30, amount=10, customer="Walk-in")
        + daily("Bread", CUR[0], 30, every=3, amount=10, customer="Kojo")
    )
    item = kinds(advisor.build(records, *CUR))["decline:Bread"]
    assert not any(reason["basis"] == "customers" for reason in item["reasons"])


def test_calendar_reasons_use_the_matching_window(monkeypatch):
    christmas = ghana_calendar.Event("Christmas and New Year season", date(2026, 12, 1), date(2027, 1, 6), "festive")
    others = [("current", ghana_calendar.Event(f"Season {n}", CUR[0], CUR[1], "school")) for n in range(2)]
    monkeypatch.setattr(ghana_calendar, "notable_difference", lambda *args: others + [("previous", christmas)])
    records = daily("Rice", START, 30, amount=100) + daily("Rice", CUR[0], 30, every=3, amount=100)
    reasons = [r["text"] for r in kinds(advisor.build(records, *CUR))["decline:Rice"]["reasons"] if r["basis"] == "calendar"]
    assert reasons == ["The previous period included Christmas and New Year season, which often lifts sales."]


def test_old_explanations_are_pruned(client, monkeypatch):
    headers, base = _signup(client)
    window = "from=2026-10-01&to=2026-10-30"
    decline = next(item for item in client.get(f"{base}/insights?{window}", headers=headers).json()["advice"]["items"] if item["kind"] == "decline")
    business_id = base.rsplit("/", 1)[1]
    db.insert(config.DB_PATH, "INSERT INTO insight_explanations (business_id, cache_key, text, created_at) VALUES (?, 'old', '{}', '2020-01-01T00:00:00+00:00')", (business_id,))
    monkeypatch.setattr(llm, "OPENROUTER_KEY", "key")
    monkeypatch.setattr(llm, "OPENROUTER_MODELS", ("m",))
    monkeypatch.setattr(news_context, "search", lambda *args, **kwargs: [])
    monkeypatch.setattr(llm.httpx, "post", lambda url, headers, json, timeout: _Response({"choices": [{"message": {"content": "ok"}}]}))
    assert client.post(f"{base}/insights/{decline['id']}/explain?{window}", headers=headers).status_code == 200
    keys_left = [row["cache_key"] for row in db.many(config.DB_PATH, "SELECT cache_key FROM insight_explanations", ())]
    assert "old" not in keys_left and len(keys_left) == 1
