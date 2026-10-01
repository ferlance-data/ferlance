import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from .config import ACCESS_TOKEN_SECONDS, REFRESH_TOKEN_SECONDS, SECRET_KEY


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_text, digest_text = stored.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
    except (ValueError, base64.binascii.Error):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return hmac.compare_digest(actual, expected)


def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + timedelta(seconds=ACCESS_TOKEN_SECONDS), "jti": str(uuid.uuid4()), "type": "access"}, SECRET_KEY, algorithm="HS256")


def read_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "access" or not payload.get("sub"):
            return None
        return str(payload["sub"])
    except (jwt.InvalidTokenError, TypeError):
        return None


def create_refresh_token() -> tuple[str, datetime]:
    return secrets.token_urlsafe(48), datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TOKEN_SECONDS)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
