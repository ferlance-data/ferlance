"""Platform-operator endpoints, available to admins or FERLANCE_ADMIN_EMAILS only."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config, db
from ..deps import admin_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(admin|owner|member)$")


@router.get("/capabilities")
def admin_capabilities(user: dict = Depends(admin_user)) -> dict:
    return {"role": user["role"], "capabilities": ["view_users", "manage_roles", "manage_profiles", "view_all_businesses"]}


@router.get("/users")
def admin_users(user: dict = Depends(admin_user)) -> list[dict]:
    return db.many(config.DB_PATH, "SELECT id, email, role, full_name, created_at FROM users ORDER BY created_at")


@router.patch("/users/{user_id}/role")
def admin_update_role(user_id: str, payload: RoleUpdate, user: dict = Depends(admin_user)) -> dict:
    if not db.one(config.DB_PATH, "SELECT id FROM users WHERE id = ?", (user_id,)):
        raise HTTPException(404, "User not found.")
    if user_id == user["id"] and payload.role != "admin":
        raise HTTPException(400, "You cannot remove your own administrator role.")
    db.insert(config.DB_PATH, "UPDATE users SET role = ? WHERE id = ?", (payload.role, user_id))
    return db.one(config.DB_PATH, "SELECT id, email, role, full_name, created_at FROM users WHERE id = ?", (user_id,)) or {}
