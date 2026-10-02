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
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
