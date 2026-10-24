import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
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
ADMIN_EMAILS = {email.strip().lower() for email in os.getenv("FERLANCE_ADMIN_EMAILS", "").split(",") if email.strip()}
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4.1-flash")
OPENROUTER_URL = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://127.0.0.1:8000")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "Ferlance")
OPENROUTER_TIMEOUT_SECONDS = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "45"))
OPENROUTER_MODELS = tuple(model.strip() for model in os.getenv("OPENROUTER_MODELS", "deepseek/deepseek-v4.1-flash,openai/gpt-oss-20b,meta-llama/llama-3.3-70b-instruct,google/gemini-2.0-flash-001,qwen/qwen-2.5-72b-instruct").split(",") if model.strip())
OPENROUTER_MAX_TOKENS = int(os.getenv("OPENROUTER_MAX_TOKENS", "800"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "8"))
AGENTROUTER_API_KEY= os.getenv("AGENTROUTER_API_KEY", "")
AGENTROUTER_URL=os.getenv("AGENTROUTER_URL", "https://agentrouter.org/v1/")
AGENTROUTER_MODELS=tuple(model.strip() for  model in os.getenv("AGENTROUTER_MODELS", ""))
SERPAPI_KEY=os.getenv("SERPAPI_KEY", "")

def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
