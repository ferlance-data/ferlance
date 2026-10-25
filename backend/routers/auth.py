"""Accounts, sessions, and profile.

Access tokens are short-lived JWTs held in memory by the client; refresh
sessions are opaque, hashed, single-use tokens in an HttpOnly cookie.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from .. import config, db
from ..deps import BUSINESS_FIELDS, current_user, primary_business
from ..security import create_access_token, create_refresh_token, hash_password, token_hash, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
REFRESH_COOKIE = "ferlance_refresh"


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8)
    business_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    full_name: str = Field(default="", max_length=120)
    business_name: str = Field(min_length=1, max_length=120)


def _set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        max_age=int((expires_at - datetime.now(timezone.utc)).total_seconds()),
        path="/api/auth",
    )


def _issue_session(user_id: str, business: dict | None, response: Response) -> dict:
    refresh_token, expires_at = create_refresh_token()
    db.insert(
        config.DB_PATH,
        "INSERT INTO refresh_sessions VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, token_hash(refresh_token), expires_at.isoformat(), None, db.now()),
    )
    _set_refresh_cookie(response, refresh_token, expires_at)
    return {"access_token": create_access_token(user_id), "token_type": "bearer", "business": business}


@router.post("/signup")
def signup(payload: SignupRequest, response: Response) -> dict:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email address.")
    if db.one(config.DB_PATH, "SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "An account with that email already exists.")
    user_id, business_id = str(uuid.uuid4()), str(uuid.uuid4())
    name = payload.business_name.strip()
    db.insert(
        config.DB_PATH,
        "INSERT INTO users (id, email, password_hash, created_at, role, full_name) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, email, hash_password(payload.password), db.now(), "owner", ""),
    )
    db.insert(
        config.DB_PATH,
        "INSERT INTO businesses (id, user_id, name, created_at, currency) VALUES (?, ?, ?, ?, ?)",
        (business_id, user_id, name, db.now(), config.DEFAULT_CURRENCY),
    )
    return _issue_session(user_id, {"id": business_id, "name": name, "currency": config.DEFAULT_CURRENCY}, response)


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict:
    user = db.one(config.DB_PATH, "SELECT * FROM users WHERE email = ?", (payload.email.strip().lower(),))
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password.")
    return _issue_session(user["id"], primary_business(user["id"]), response)


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": user, "business": primary_business(user["id"])}


@router.patch("/profile")
def update_profile(payload: ProfileUpdate, user: dict = Depends(current_user)) -> dict:
    db.insert(config.DB_PATH, "UPDATE users SET full_name = ? WHERE id = ?", (payload.full_name.strip(), user["id"]))
    db.insert(config.DB_PATH, "UPDATE businesses SET name = ? WHERE user_id = ?", (payload.business_name.strip(), user["id"]))
    updated = db.one(config.DB_PATH, "SELECT id, email, role, full_name FROM users WHERE id = ?", (user["id"],))
    return {"user": updated, "business": primary_business(user["id"])}


@router.post("/refresh")
def refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)) -> dict:
    if not refresh_token:
        raise HTTPException(401, "Refresh session is required.")
    with db.connection(config.DB_PATH) as connection:
        connection.execute("BEGIN IMMEDIATE")
        session = connection.execute(
            "SELECT * FROM refresh_sessions WHERE token_hash = ? AND revoked_at IS NULL",
            (token_hash(refresh_token),),
        ).fetchone()
        if not session or datetime.fromisoformat(session["expires_at"]) <= datetime.now(timezone.utc):
            raise HTTPException(401, "Refresh session is invalid or expired.")
        revoked = connection.execute(
            "UPDATE refresh_sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (db.now(), session["id"]),
        )
        if revoked.rowcount != 1:
            raise HTTPException(401, "Refresh session is invalid or expired.")
        replacement, expires_at = create_refresh_token()
        connection.execute(
            "INSERT INTO refresh_sessions VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session["user_id"], token_hash(replacement), expires_at.isoformat(), None, db.now()),
        )
        business_row = connection.execute(
            f"SELECT {BUSINESS_FIELDS} FROM businesses WHERE user_id = ? ORDER BY created_at LIMIT 1",
            (session["user_id"],),
        ).fetchone()
    _set_refresh_cookie(response, replacement, expires_at)
    return {
        "access_token": create_access_token(session["user_id"]),
        "token_type": "bearer",
        "business": dict(business_row) if business_row else None,
    }


@router.post("/logout")
def logout(response: Response, refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)) -> dict[str, str]:
    if refresh_token:
        db.insert(
            config.DB_PATH,
            "UPDATE refresh_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (db.now(), token_hash(refresh_token)),
        )
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return {"status": "signed_out"}
