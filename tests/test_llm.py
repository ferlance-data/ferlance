import httpx

from backend import llm


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.request = httpx.Request("POST", "https://example.test")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("provider error", request=self.request, response=self)

    def json(self):
        return self.payload


def test_ask_lance_tries_five_openrouter_models(monkeypatch):
    attempts = []
    monkeypatch.setattr(llm, "OPENROUTER_KEY", "router-key")
    monkeypatch.setattr(llm, "GROQ_API_KEY", "")
    monkeypatch.setattr(llm, "OPENROUTER_MODELS", ("model-1", "model-2", "model-3", "model-4", "model-5"))

    def post(url, **kwargs):
        attempts.append((url, kwargs["json"]["model"]))
        if len(attempts) < 5:
            return FakeResponse({"error": {"message": "temporary failure"}}, 503)
        return FakeResponse({"choices": [{"message": {"content": "fifth model answer"}}]})

    monkeypatch.setattr(llm.httpx, "post", post)

    assert llm.ask_lance("Question", {"total": 10}) == "fifth model answer"
    assert [model for _, model in attempts] == ["model-1", "model-2", "model-3", "model-4", "model-5"]


def test_ask_lance_falls_back_to_groq_after_openrouter_failures(monkeypatch):
    attempts = []
    monkeypatch.setattr(llm, "OPENROUTER_KEY", "router-key")
    monkeypatch.setattr(llm, "GROQ_API_KEY", "groq-key")
    monkeypatch.setattr(llm, "OPENROUTER_MODELS", ("model-1", "model-2", "model-3", "model-4", "model-5"))

    def post(url, **kwargs):
        attempts.append((url, kwargs["json"]["model"]))
        if "openrouter" in url:
            return FakeResponse({"error": {"message": "model unavailable"}}, 404)
        return FakeResponse({"choices": [{"message": {"content": "groq answer"}}]})

    monkeypatch.setattr(llm.httpx, "post", post)

    assert llm.ask_lance("Question", {"total": 10}) == "groq answer"
    assert len(attempts) == 6
    assert attempts[-1][1] == llm.GROQ_MODEL