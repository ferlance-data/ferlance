import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("FERLANCE_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "ferlance.sqlite3"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SECRET_KEY = os.getenv("FERLANCE_SECRET_KEY", "development-only-change-me")


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
