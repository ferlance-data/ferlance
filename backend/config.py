"""Runtime settings read from the environment.

Modules read paths and limits through this module (``config.DB_PATH``) at call
time rather than importing the values, so tests and deployments can repoint
storage without reloading the application.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = Path(os.getenv("FERLANCE_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "ferlance.sqlite3"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

SECRET_KEY = os.getenv("FERLANCE_SECRET_KEY", "development-only-change-me")
MAX_UPLOAD_BYTES = int(os.getenv("FERLANCE_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ACCESS_TOKEN_SECONDS = int(os.getenv("FERLANCE_ACCESS_TOKEN_SECONDS", "900"))
REFRESH_TOKEN_SECONDS = int(os.getenv("FERLANCE_REFRESH_TOKEN_SECONDS", "2592000"))
COOKIE_SECURE = os.getenv("FERLANCE_COOKIE_SECURE", "false").lower() == "true"
DEFAULT_CURRENCY = os.getenv("FERLANCE_DEFAULT_CURRENCY", "GHS")
ADMIN_EMAILS = {email.lower() for email in _csv(os.getenv("FERLANCE_ADMIN_EMAILS", ""))}

# Ask Lance providers, tried in order: OpenRouter models, Groq, then AgentRouter.
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
OPENROUTER_URL = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_TIMEOUT_SECONDS = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "45"))
OPENROUTER_MODELS = _csv(
    os.getenv(
        "OPENROUTER_MODELS",
        "deepseek/deepseek-v4.1-flash,openai/gpt-oss-20b,meta-llama/llama-3.3-70b-instruct",
    )
)
OPENROUTER_MAX_TOKENS = int(os.getenv("OPENROUTER_MAX_TOKENS", "800"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "8"))
AGENTROUTER_API_KEY = os.getenv("AGENTROUTER_API_KEY", "")
AGENTROUTER_URL = os.getenv("AGENTROUTER_URL", "https://agentrouter.org/v1/chat/completions")
AGENTROUTER_MODELS = _csv(os.getenv("AGENTROUTER_MODELS", ""))

# Optional web search tool that Lance may call for market prices.
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")


def ensure_storage() -> None:
    for directory in (DATA_DIR, RAW_DIR, PROCESSED_DIR):
        directory.mkdir(parents=True, exist_ok=True)
