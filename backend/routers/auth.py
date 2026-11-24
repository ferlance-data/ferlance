"""Accounts, sessions, and profile.

Access tokens are short-lived JWTs held in memory by the client; refresh
sessions are opaque, hashed, single-use tokens in an HttpOnly cookie.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from .. import config, db
from ..deps import current_user, is_admin, memberships, primary_business
from .team import accept_invite, find_invite
from ..security import WORKSPACE, create_access_token, create_refresh_token, hash_password, token_hash, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
REFRESH_COOKIE = "ferlance_refresh"


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8)
    # Required unless joining someone else's business through an invite link.
    business_name: str | None = Field(default=None, max_length=120)
    invite_token: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    full_name: str = Field(default="", max_length=120)


def set_refresh_cookie(response: Response, token: str, expires_at: datetime, name: str = REFRESH_COOKIE, path: str = "/api/auth") -> None:
    response.set_cookie(
        name,
        token,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="lax",
        max_age=int((expires_at - datetime.now(timezone.utc)).total_seconds()),
        path=path,
    )


def start_session(user_id: str, scope: str) -> tuple[str, datetime]:
    """A new refresh session of the given scope ('workspace' or 'admin')."""
    refresh_token, expires_at = create_refresh_token()
    db.insert(
        config.DB_PATH,
        "INSERT INTO refresh_sessions (id, user_id, token_hash, expires_at, revoked_at, created_at, scope) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, token_hash(refresh_token), expires_at.isoformat(), None, db.now(), scope),
    )
    return refresh_token, expires_at


def _issue_session(user_id: str, business: dict | None, response: Response) -> dict:
    refresh_token, expires_at = start_session(user_id, "workspace")
    set_refresh_cookie(response, refresh_token, expires_at)
    return {"access_token": create_access_token(user_id, WORKSPACE), "token_type": "bearer", "business": business}


@router.post("/signup")
def signup(payload: SignupRequest, response: Response) -> dict:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "Enter a valid email address.")
    if db.one(config.DB_PATH, "SELECT id FROM users WHERE email = ?", (email,)):
        raise HTTPException(409, "An account with that email already exists.")
    name = (payload.business_name or "").strip()
    if payload.invite_token:
        find_invite(payload.invite_token)  # fail before creating the account if the link is dead
    elif not name:
        raise HTTPException(422, "Enter your business name.")
    user_id, business_id = str(uuid.uuid4()), str(uuid.uuid4())
    db.insert(
        config.DB_PATH,
        "INSERT INTO users (id, email, password_hash, created_at, role, full_name) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, email, hash_password(payload.password), db.now(), "owner", ""),
    )
    if payload.invite_token:
        # Joining a team: no business of their own is created. If the link was used up between the
        # check above and now, remove the half-made account so the person can simply try again.
        try:
            joined = accept_invite(payload.invite_token, user_id)
        except HTTPException:
            db.insert(config.DB_PATH, "DELETE FROM users WHERE id = ?", (user_id,))
            raise
        return _issue_session(user_id, joined, response)
    db.insert(
        config.DB_PATH,
        "INSERT INTO businesses (id, user_id, name, created_at, currency) VALUES (?, ?, ?, ?, ?)",
        (business_id, user_id, name, db.now(), config.DEFAULT_CURRENCY),
    )
    db.insert(
        config.DB_PATH,
        "INSERT INTO business_members (business_id, user_id, role, created_at) VALUES (?, ?, 'owner', ?)",
        (business_id, user_id, db.now()),
    )
    return _issue_session(user_id, {"id": business_id, "name": name, "currency": config.DEFAULT_CURRENCY, "role": "owner"}, response)


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict:
    user = db.one(config.DB_PATH, "SELECT * FROM users WHERE email = ?", (payload.email.strip().lower(),))
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password.")
    if user.get("disabled_at"):
        raise HTTPException(403, "This account has been disabled. Contact Ferlance support.")
    business = primary_business(user["id"])
    if business is None and is_admin(user):
        raise HTTPException(403, "This is an administrator account. Sign in at /admin instead.")
    return _issue_session(user["id"], business, response)


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    businesses = memberships(user["id"])
    return {"user": user, "business": businesses[0] if businesses else None, "businesses": businesses}


@router.patch("/profile")
def update_profile(payload: ProfileUpdate, user: dict = Depends(current_user)) -> dict:
    db.insert(config.DB_PATH, "UPDATE users SET full_name = ? WHERE id = ?", (payload.full_name.strip(), user["id"]))
    updated = db.one(config.DB_PATH, "SELECT id, email, role, full_name FROM users WHERE id = ?", (user["id"],))
    return {"user": updated, "business": primary_business(user["id"])}


def rotate_session(refresh_token: str | None, scope: str) -> tuple[str, str, datetime]:
    """Swap a refresh token for a new one of the same scope. Returns (user id, new token, expiry)."""
    if not refresh_token:
        raise HTTPException(401, "Refresh session is required.")
    with db.connection(config.DB_PATH) as connection:
        connection.execute("BEGIN IMMEDIATE")
        session = connection.execute("SELECT * FROM refresh_sessions WHERE token_hash = ? AND scope = ?", (token_hash(refresh_token), scope)).fetchone()
        now = datetime.now(timezone.utc)
        if not session or datetime.fromisoformat(session["expires_at"]) <= now:
            raise HTTPException(401, "Refresh session is invalid or expired.")
        owner = connection.execute("SELECT disabled_at FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not owner or owner["disabled_at"]:
            raise HTTPException(401, "This account is no longer active.")
        if session["revoked_at"] is not None:
            # A rotated token is presented again. Allow it for a short grace period, as long as the
            # session it was replaced by is still live: the earlier response was probably lost on a
            # flaky connection. A token revoked by sign-out (no live replacement) is always refused.
            successor = connection.execute(
                "SELECT revoked_at FROM refresh_sessions WHERE id = ?", (session["replaced_by"] or "",)
            ).fetchone()
            rotated = datetime.fromisoformat(session["revoked_at"])
            if not successor or successor["revoked_at"] is not None or (now - rotated).total_seconds() > config.REFRESH_REUSE_GRACE_SECONDS:
                raise HTTPException(401, "Refresh session is invalid or expired.")
            # Retire the successor (its cookie never arrived) and issue a fresh one below. The grace
            # is one-shot: the old token loses its link to a successor, so a second reuse is refused.
            connection.execute("UPDATE refresh_sessions SET revoked_at = ? WHERE id = ?", (db.now(), session["replaced_by"]))
            grace = True
        else:
            grace = False
            revoked = connection.execute(
                "UPDATE refresh_sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (db.now(), session["id"]),
            )
            if revoked.rowcount != 1:
                raise HTTPException(401, "Refresh session is invalid or expired.")
        replacement, expires_at = create_refresh_token()
        replacement_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO refresh_sessions (id, user_id, token_hash, expires_at, revoked_at, created_at, scope) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (replacement_id, session["user_id"], token_hash(replacement), expires_at.isoformat(), None, db.now(), scope),
        )
        connection.execute("UPDATE refresh_sessions SET replaced_by = ? WHERE id = ?", (None if grace else replacement_id, session["id"]))
    return session["user_id"], replacement, expires_at


def end_session(refresh_token: str | None) -> None:
    if refresh_token:
        db.insert(
            config.DB_PATH,
            "UPDATE refresh_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (db.now(), token_hash(refresh_token)),
        )


@router.post("/refresh")
def refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)) -> dict:
    user_id, replacement, expires_at = rotate_session(refresh_token, "workspace")
    set_refresh_cookie(response, replacement, expires_at)
    return {
        "access_token": create_access_token(user_id, WORKSPACE),
        "token_type": "bearer",
        "business": primary_business(user_id),
    }


@router.post("/logout")
def logout(response: Response, refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)) -> dict[str, str]:
    end_session(refresh_token)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return {"status": "signed_out"}
