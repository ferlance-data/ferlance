import pytest

from backend import llm


@pytest.fixture(autouse=True)
def _no_real_ai_providers(monkeypatch):
    """A developer's .env may hold real AI keys; tests must never call a paid provider. Tests opt in with fakes."""
    for name in ("OPENROUTER_KEY", "GROQ_API_KEY", "AGENTROUTER_API_KEY"):
        monkeypatch.setattr(llm, name, "")
