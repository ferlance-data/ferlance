"""Business settings and team access: members, roles and invite links.

Ferlance cannot send email, so an invite is a single-use link the owner copies and shares
(WhatsApp, SMS). Only a hash of the token is stored; the link expires after
``config.INVITE_DAYS`` days, and the owner can revoke it at any time.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config, db
from ..deps import business_manager, current_user, team_manager
from ..security import token_hash

router = APIRouter(prefix="/api/businesses/{business_id}", tags=["team"])
public = APIRouter(prefix="/api/invites", tags=["team"])

INVITE_ROLES = "^(manager|accountant)$"
CURRENCY = "^[A-Z]{3}$"


class BusinessUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    currency: str | None = Field(default=None, pattern=CURRENCY)


class InviteRequest(BaseModel):
    role: str = Field(pattern=INVITE_ROLES)


class MemberUpdate(BaseModel):
    role: str = Field(pattern=INVITE_ROLES)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.patch("")
def update_business(payload: BusinessUpdate, business: dict = Depends(business_manager)) -> dict:
    currency = payload.currency or business["currency"]
    db.insert(config.DB_PATH, "UPDATE businesses SET name = ?, currency = ? WHERE id = ?", (payload.name.strip(), currency, business["id"]))
    return {"id": business["id"], "name": payload.name.strip(), "currency": currency, "role": business["member_role"]}


@router.get("/team")
def team(business: dict = Depends(team_manager)) -> dict:
    members = db.many(
        config.DB_PATH,
        "SELECT u.id AS user_id, u.email, u.full_name, m.role, m.created_at FROM business_members m "
        "JOIN users u ON u.id = m.user_id WHERE m.business_id = ? "
        "ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END, m.created_at",
        (business["id"],),
    )
    invites = db.many(
        config.DB_PATH,
        "SELECT id, role, created_at, expires_at FROM business_invites WHERE business_id = ? "
        "AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > ? ORDER BY created_at DESC",
        (business["id"], _now().isoformat()),
    )
    return {"members": members, "invites": invites}


@router.post("/invites")
def create_invite(payload: InviteRequest, business: dict = Depends(team_manager), user: dict = Depends(current_user)) -> dict:
    token = secrets.token_urlsafe(32)
    invite_id = str(uuid.uuid4())
    expires = _now() + timedelta(days=config.INVITE_DAYS)
    db.insert(
        config.DB_PATH,
        "INSERT INTO business_invites (id, business_id, role, token_hash, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (invite_id, business["id"], payload.role, token_hash(token), user["id"], db.now(), expires.isoformat()),
    )
    # The token is returned once, here; only its hash is stored.
    return {"id": invite_id, "role": payload.role, "token": token, "path": f"/?invite={token}", "expires_at": expires.isoformat()}


@router.delete("/invites/{invite_id}")
def revoke_invite(invite_id: str, business: dict = Depends(team_manager)) -> dict:
    db.insert(
        config.DB_PATH,
        "UPDATE business_invites SET revoked_at = ? WHERE id = ? AND business_id = ? AND accepted_at IS NULL AND revoked_at IS NULL",
        (db.now(), invite_id, business["id"]),
    )
    return {"status": "revoked"}


def _member(business_id: str, user_id: str) -> dict:
    row = db.one(config.DB_PATH, "SELECT role FROM business_members WHERE business_id = ? AND user_id = ?", (business_id, user_id))
    if not row:
        raise HTTPException(404, "That person is not a member of this business.")
    if row["role"] == "owner":
        raise HTTPException(400, "The owner's access cannot be changed.")
    return row


@router.patch("/members/{user_id}")
def update_member(user_id: str, payload: MemberUpdate, business: dict = Depends(team_manager)) -> dict:
    _member(business["id"], user_id)
    db.insert(config.DB_PATH, "UPDATE business_members SET role = ? WHERE business_id = ? AND user_id = ?", (payload.role, business["id"], user_id))
    return {"user_id": user_id, "role": payload.role}


@router.delete("/members/{user_id}")
def remove_member(user_id: str, business: dict = Depends(team_manager)) -> dict:
    _member(business["id"], user_id)
    db.insert(config.DB_PATH, "DELETE FROM business_members WHERE business_id = ? AND user_id = ?", (business["id"], user_id))
    return {"status": "removed"}


def find_invite(token: str) -> dict:
    """The live invite for a token, or 404 for unknown, used, revoked and expired links alike."""
    invite = db.one(
        config.DB_PATH,
        "SELECT i.*, b.name AS business_name FROM business_invites i JOIN businesses b ON b.id = i.business_id "
        "WHERE i.token_hash = ? AND i.accepted_at IS NULL AND i.revoked_at IS NULL AND i.expires_at > ?",
        (token_hash(token), _now().isoformat()),
    )
    if not invite:
        raise HTTPException(404, "This invite link is not valid. It may have expired or already been used; ask for a new one.")
    return invite


def accept_invite(token: str, user_id: str) -> dict:
    """Atomically consume the invite and add the membership. Returns the joined business."""
    with db.connection(config.DB_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE")
        invite = conn.execute(
            "SELECT * FROM business_invites WHERE token_hash = ? AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at > ?",
            (token_hash(token), _now().isoformat()),
        ).fetchone()
        if not invite:
            raise HTTPException(404, "This invite link is not valid. It may have expired or already been used; ask for a new one.")
        existing = conn.execute(
            "SELECT role FROM business_members WHERE business_id = ? AND user_id = ?", (invite["business_id"], user_id)
        ).fetchone()
        if existing:
            raise HTTPException(409, "You are already a member of this business.")
        conn.execute(
            "INSERT INTO business_members (business_id, user_id, role, created_at) VALUES (?, ?, ?, ?)",
            (invite["business_id"], user_id, invite["role"], db.now()),
        )
        conn.execute("UPDATE business_invites SET accepted_by = ?, accepted_at = ? WHERE id = ?", (user_id, db.now(), invite["id"]))
        business = conn.execute("SELECT id, name, currency FROM businesses WHERE id = ?", (invite["business_id"],)).fetchone()
    return {**dict(business), "role": invite["role"]}


@public.get("/{token}")
def invite_details(token: str) -> dict:
    invite = find_invite(token)
    return {"business_name": invite["business_name"], "role": invite["role"], "expires_at": invite["expires_at"]}


@public.post("/{token}/accept")
def accept(token: str, user: dict = Depends(current_user)) -> dict:
    return {"business": accept_invite(token, user["id"])}
