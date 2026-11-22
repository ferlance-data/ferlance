"""Platform-operator console: users, businesses, onboarding progress and an audit log.

Available to users with the platform `admin` role, or listed in FERLANCE_ADMIN_EMAILS.
Admins see accounts and aggregate counts, never a business's records. Every change an admin
makes (role, disable, enable) is written to the append-only `admin_audit` table.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import config, db, exports
from ..deps import admin_user

router = APIRouter(prefix="/api/admin", tags=["admin"])

USER_FIELDS = "id, email, role, full_name, created_at, disabled_at"


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|owner|member)$")


def _audit(actor: dict, action: str, target_user_id: str | None, **detail) -> None:
    db.insert(
        config.DB_PATH,
        "INSERT INTO admin_audit (id, actor_id, action, target_user_id, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), actor["id"], action, target_user_id, json.dumps(detail), db.now()),
    )


def _target(user_id: str) -> dict:
    target = db.one(config.DB_PATH, f"SELECT {USER_FIELDS} FROM users WHERE id = ?", (user_id,))
    if not target:
        raise HTTPException(404, "User not found.")
    return target


def _other_active_admins(excluding: str) -> int:
    rows = db.many(config.DB_PATH, "SELECT email, role FROM users WHERE id != ? AND disabled_at IS NULL", (excluding,))
    return sum(1 for row in rows if row["role"] == "admin" or row["email"].lower() in config.ADMIN_EMAILS)


@router.get("/capabilities")
def admin_capabilities(user: dict = Depends(admin_user)) -> dict:
    return {"role": user["role"], "capabilities": ["view_users", "manage_roles", "disable_users", "view_businesses", "view_onboarding", "view_audit", "view_exports", "run_exports"]}


@router.get("/users")
def admin_users(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(admin_user),
) -> list[dict]:
    like = f"%{q.strip().lower()}%"
    return db.many(
        config.DB_PATH,
        f"SELECT {USER_FIELDS}, (SELECT COUNT(*) FROM business_members m WHERE m.user_id = users.id) AS businesses "
        "FROM users WHERE lower(email) LIKE ? OR lower(full_name) LIKE ? ORDER BY created_at DESC LIMIT ?",
        (like, like, limit),
    )


@router.patch("/users/{user_id}/role")
def admin_update_role(user_id: str, payload: RoleUpdate, user: dict = Depends(admin_user)) -> dict:
    target = _target(user_id)
    if user_id == user["id"] and payload.role != "admin":
        raise HTTPException(400, "You cannot remove your own administrator role.")
    if target["role"] == "admin" and payload.role != "admin" and _other_active_admins(user_id) == 0:
        raise HTTPException(400, "This is the last administrator.")
    db.insert(config.DB_PATH, "UPDATE users SET role = ? WHERE id = ?", (payload.role, user_id))
    _audit(user, "role", user_id, before=target["role"], after=payload.role)
    return _target(user_id)


@router.post("/users/{user_id}/disable")
def admin_disable(user_id: str, user: dict = Depends(admin_user)) -> dict:
    target = _target(user_id)
    if user_id == user["id"]:
        raise HTTPException(400, "You cannot disable your own account.")
    if target["email"].lower() in config.ADMIN_EMAILS:
        raise HTTPException(400, "Administrators named in FERLANCE_ADMIN_EMAILS cannot be disabled here.")
    if target["role"] == "admin" and _other_active_admins(user_id) == 0:
        raise HTTPException(400, "This is the last administrator.")
    if not target["disabled_at"]:
        now = db.now()
        db.insert(config.DB_PATH, "UPDATE users SET disabled_at = ? WHERE id = ?", (now, user_id))
        # End every session at once; access tokens are refused by current_user from now on.
        db.insert(config.DB_PATH, "UPDATE refresh_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (now, user_id))
        _audit(user, "disable", user_id)
    return _target(user_id)


@router.post("/users/{user_id}/enable")
def admin_enable(user_id: str, user: dict = Depends(admin_user)) -> dict:
    target = _target(user_id)
    if target["disabled_at"]:
        db.insert(config.DB_PATH, "UPDATE users SET disabled_at = NULL WHERE id = ?", (user_id,))
        _audit(user, "enable", user_id)
    return _target(user_id)


@router.get("/businesses")
def admin_businesses(
    q: str = Query(default="", max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(admin_user),
) -> list[dict]:
    """Businesses with their owner and setup progress. Counts only, never records."""
    like = f"%{q.strip().lower()}%"
    return db.many(
        config.DB_PATH,
        """
        SELECT b.id, b.name, b.currency, b.created_at, u.email AS owner_email,
          (SELECT COUNT(*) FROM business_members m WHERE m.business_id = b.id) AS members,
          (SELECT COUNT(*) FROM datasets d WHERE d.business_id = b.id AND d.status != 'failed') AS datasets,
          (SELECT COUNT(*) FROM inventory_products p WHERE p.business_id = b.id) AS products,
          (SELECT COUNT(*) FROM financial_position_balances f WHERE f.business_id = b.id) AS balances,
          (SELECT COUNT(*) FROM chat_conversations c WHERE c.business_id = b.id) AS conversations
        FROM businesses b JOIN users u ON u.id = b.user_id
        WHERE lower(b.name) LIKE ? OR lower(u.email) LIKE ?
        ORDER BY b.created_at DESC LIMIT ?
        """,
        (like, like, limit),
    )


@router.get("/onboarding")
def admin_onboarding(user: dict = Depends(admin_user)) -> dict:
    """How far businesses get through setup, as aggregate counts (no business data)."""
    row = db.one(
        config.DB_PATH,
        """
        SELECT COUNT(*) AS businesses,
          SUM(EXISTS(SELECT 1 FROM datasets d WHERE d.business_id = b.id AND d.status != 'failed')) AS imported,
          SUM(EXISTS(SELECT 1 FROM inventory_products p WHERE p.business_id = b.id)) AS stock,
          SUM(EXISTS(SELECT 1 FROM financial_position_balances f WHERE f.business_id = b.id)) AS balances,
          SUM(EXISTS(SELECT 1 FROM chat_conversations c WHERE c.business_id = b.id)) AS asked,
          SUM(EXISTS(SELECT 1 FROM business_members m WHERE m.business_id = b.id AND m.role != 'owner')) AS team
        FROM businesses b
        """,
    ) or {}
    total = row.get("businesses") or 0
    steps = [
        ("imported", "Imported sales records"),
        ("stock", "Added stock"),
        ("balances", "Recorded balances"),
        ("asked", "Asked Lance"),
        ("team", "Invited a teammate"),
    ]
    return {"businesses": total, "steps": [{"key": key, "label": label, "count": row.get(key) or 0} for key, label in steps]}


@router.get("/audit")
def admin_audit(limit: int = Query(default=50, ge=1, le=500), user: dict = Depends(admin_user)) -> list[dict]:
    rows = db.many(
        config.DB_PATH,
        "SELECT a.id, a.action, a.detail, a.created_at, actor.email AS actor_email, target.email AS target_email "
        "FROM admin_audit a LEFT JOIN users actor ON actor.id = a.actor_id LEFT JOIN users target ON target.id = a.target_user_id "
        "ORDER BY a.created_at DESC LIMIT ?",
        (limit,),
    )
    return [{**row, "detail": json.loads(row["detail"])} for row in rows]


@router.get("/exports")
def admin_exports(user: dict = Depends(admin_user)) -> dict:
    """Where daily exports go and each business's latest run. Counts and errors only, never records."""
    return exports.status()


@router.post("/exports/run", status_code=202)
def admin_run_exports(user: dict = Depends(admin_user)) -> dict:
    """Start exporting every business now, replacing today's files. Runs in the background; poll GET /exports."""
    if not exports.enabled():
        raise HTTPException(400, "Data export is not set up. Set FERLANCE_EXPORT_BUCKET (or FERLANCE_EXPORT_DIR) first.")
    if not exports.run_in_background():
        raise HTTPException(409, "An export is already running.")
    _audit(user, "export_run", None)
    return exports.status()
