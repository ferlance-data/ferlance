"""The admin console's own sign-in (served at /admin; later its own subdomain).

Admin sessions are separate from workspace sessions: a different token type, a different refresh
cookie (``ferlance_admin_refresh`` on ``/api/admin/auth``), and refresh sessions with scope 'admin'.
A workspace token never opens the admin API, and an admin token never opens a business.

Who can be an admin:
- An email listed in FERLANCE_ADMIN_EMAILS (server setting). Such a person can create an admin
  account here, or sign in here with the account they already have.
- A user another admin promoted to the platform 'admin' role.
Nobody else can create an admin account: the server setting is the root of trust.
"""

import json
import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from .. import config, db
from ..deps import admin_user, is_admin
from ..security import ADMIN, create_access_token, hash_password, verify_password
from .auth import end_session, rotate_session, set_refresh_cookie, start_session

router = APIRouter(prefix="/api/admin/auth", tags=["admin auth"])
ADMIN_COOKIE = "ferlance_admin_refresh"
COOKIE_PATH = "/api/admin/auth"


class AdminSignup(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=200)
    full_name: str = Field(default="", max_length=120)


class AdminLogin(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


def _issue(user: dict, response: Response) -> dict:
    token, expires_at = start_session(user["id"], "admin")
    set_refresh_cookie(response, token, expires_at, ADMIN_COOKIE, COOKIE_PATH)
    return {"access_token": create_access_token(user["id"], ADMIN), "token_type": "bearer", "user": {k: user[k] for k in ("id", "email", "role", "full_name")}}


def _audit(actor_id: str, action: str) -> None:
    db.insert(
        config.DB_PATH,
        "INSERT INTO admin_audit (id, actor_id, action, target_user_id, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), actor_id, action, actor_id, json.dumps({}), db.now()),
    )


@router.post("/signup")
def admin_signup(payload: AdminSignup, response: Response) -> dict:
    """Create an administrator account. Only for emails in FERLANCE_ADMIN_EMAILS."""
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email address.")
    if email not in config.ADMIN_EMAILS:
        # The same answer whether or not the address exists, so this can't be used to probe accounts.
        raise HTTPException(403, "This email is not allowed to create an administrator account.")
    if db.one(config.DB_PATH, "SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user_id = str(uuid.uuid4())
    db.insert(
        config.DB_PATH,
        "INSERT INTO users (id, email, password_hash, created_at, role, full_name) VALUES (?, ?, ?, ?, 'admin', ?)",
        (user_id, email, hash_password(payload.password), db.now(), payload.full_name.strip()),
    )
    _audit(user_id, "admin_signup")
    user = db.one(config.DB_PATH, "SELECT id, email, role, full_name FROM users WHERE id = ?", (user_id,))
    return _issue(user, response)


@router.post("/login")
def admin_login(payload: AdminLogin, response: Response) -> dict:
    user = db.one(config.DB_PATH, "SELECT * FROM users WHERE email = ?", (payload.email.strip().lower(),))
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password.")
    if user.get("disabled_at"):
        raise HTTPException(403, "This account has been disabled.")
    if not is_admin(user):
        raise HTTPException(403, "This account is not an administrator. Business owners sign in on the main page.")
    return _issue(user, response)


@router.post("/refresh")
def admin_refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    user_id, replacement, expires_at = rotate_session(refresh_token, "admin")
    user = db.one(config.DB_PATH, "SELECT id, email, role, full_name FROM users WHERE id = ? AND disabled_at IS NULL", (user_id,))
    if not user or not is_admin(user):
        end_session(replacement)
        raise HTTPException(403, "Administrator privileges are required.")
    set_refresh_cookie(response, replacement, expires_at, ADMIN_COOKIE, COOKIE_PATH)
    return {"access_token": create_access_token(user_id, ADMIN), "token_type": "bearer", "user": user}


@router.get("/me")
def admin_me(user: dict = Depends(admin_user)) -> dict:
    return {"user": user}


@router.post("/logout")
def admin_logout(response: Response, refresh_token: str | None = Cookie(default=None, alias=ADMIN_COOKIE)) -> dict:
    end_session(refresh_token)
    response.delete_cookie(ADMIN_COOKIE, path=COOKIE_PATH)
    return {"status": "signed_out"}
