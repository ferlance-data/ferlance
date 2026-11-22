"""Shared request dependencies: authentication, tenancy, and data scope."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from fastapi import Depends, Header, HTTPException, Query

from . import config, dataset_store, db
from .security import read_access_token


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required.")
    user_id = read_access_token(authorization.split(" ", 1)[1])
    # Disabled accounts are refused here, so a 15-minute access token stops working at once.
    user = db.one(config.DB_PATH, "SELECT id, email, role, full_name FROM users WHERE id = ? AND disabled_at IS NULL", (user_id or "",))
    if not user:
        raise HTTPException(401, "Invalid or expired token.")
    return user


def is_admin(user: dict) -> bool:
    return user["role"] == "admin" or user["email"].lower() in config.ADMIN_EMAILS


def admin_user(user: dict = Depends(current_user)) -> dict:
    if not is_admin(user):
        raise HTTPException(403, "Administrator privileges are required.")
    return user


# Business roles (per business, in business_members). Not to be confused with users.role,
# which is the platform role (admin or not). Every business route declares the permission it
# needs through business_access(); tests check that no route under /api/businesses skips it.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset({"read", "write_data", "write_balances", "use_ai", "manage_team", "manage_business", "manage_books"}),
    "manager": frozenset({"read", "write_data", "write_balances", "use_ai"}),
    "accountant": frozenset({"read", "write_balances", "use_ai", "manage_books"}),
}
PERMISSIONS = frozenset().union(*ROLE_PERMISSIONS.values())
ROLE_ORDER = "CASE m.role WHEN 'owner' THEN 0 WHEN 'manager' THEN 1 ELSE 2 END"


def memberships(user_id: str) -> list[dict]:
    """Businesses the user belongs to, with their role: owned first, then oldest."""
    return db.many(
        config.DB_PATH,
        f"SELECT b.id, b.name, b.currency, m.role FROM business_members m JOIN businesses b ON b.id = m.business_id "
        f"WHERE m.user_id = ? ORDER BY {ROLE_ORDER}, m.created_at",
        (user_id,),
    )


def primary_business(user_id: str) -> dict | None:
    found = memberships(user_id)
    return found[0] if found else None


def business_access(permission: str):
    """Dependency factory: the user must be a member of the business in the URL with `permission`.

    Non-members get 404 (the business's existence is not revealed); members without the
    permission get 403. The role is read on every request, so removing someone takes effect at once.
    """
    if permission not in PERMISSIONS:
        raise ValueError(f"Unknown permission {permission!r}")

    def dependency(business_id: str, user: dict = Depends(current_user)) -> dict:
        row = db.one(
            config.DB_PATH,
            "SELECT b.*, m.role AS member_role FROM businesses b JOIN business_members m ON m.business_id = b.id "
            "WHERE b.id = ? AND m.user_id = ?",
            (business_id, user["id"]),
        )
        if not row:
            raise HTTPException(404, "Business not found.")
        if permission not in ROLE_PERMISSIONS.get(row["member_role"], frozenset()):
            raise HTTPException(403, "Your role in this business does not allow that.")
        return row

    dependency.permission = permission  # type: ignore[attr-defined]  # read by the route-coverage test
    return dependency


read_business = business_access("read")
data_writer = business_access("write_data")
balance_writer = business_access("write_balances")
ai_user = business_access("use_ai")
team_manager = business_access("manage_team")
business_manager = business_access("manage_business")
books_manager = business_access("manage_books")  # manual journals, opening balances, period lock, accounts


def spend_ai_call(business_id: str) -> None:
    """Count one uncached AI call against the business's daily cap (429 once it is reached)."""
    day = datetime.now(timezone.utc).date().isoformat()
    with db.connection(config.DB_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT calls FROM ai_usage WHERE business_id = ? AND day = ?", (business_id, day)).fetchone()
        calls = row["calls"] if row else 0
        if calls >= config.AI_DAILY_LIMIT:
            raise HTTPException(429, f"This business has used today's {config.AI_DAILY_LIMIT} AI answers. Calculated insights still work; AI is back tomorrow.")
        conn.execute(
            "INSERT INTO ai_usage (business_id, day, calls) VALUES (?, ?, 1) "
            "ON CONFLICT(business_id, day) DO UPDATE SET calls = calls + 1",
            (business_id, day),
        )


@dataclass
class DateRange:
    start: date | None
    end: date | None


def date_range(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
) -> DateRange:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(400, "The from date must be on or before the to date.")
    return DateRange(from_date, to_date)


@dataclass
class Scope:
    """The records a view is computed from: one file, or every included file."""

    descriptor: dict[str, Any]
    datasets: list[dict[str, Any]]
    records: list[dict[str, Any]]


def resolve_scope(business_id: str, dataset_id: str | None) -> Scope:
    if dataset_id and dataset_id != "all":
        dataset = dataset_store.get(business_id, dataset_id)
        if not dataset:
            raise HTTPException(404, "Dataset not found.")
        if dataset["status"] == "failed":
            raise HTTPException(409, "This dataset failed processing and has no analytics.")
        return Scope(dataset_store.serialize(dataset), [dataset], read_scope_records([dataset]))
    datasets = dataset_store.analysable(business_id)
    if not datasets:
        raise HTTPException(404, "No processed business data yet. Import a file to get started.")
    return Scope(dataset_store.combined_descriptor(datasets), datasets, read_scope_records(datasets))


def read_scope_records(datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        return dataset_store.records_for(datasets)
    except dataset_store.RecordsUnavailableError as error:
        raise HTTPException(503, str(error))


def scope(
    business: dict = Depends(read_business),
    dataset_id: str | None = Query(default=None, description="A dataset id, or 'all' (default) for every included file."),
) -> Scope:
    return resolve_scope(business["id"], dataset_id)


def refund_ai_call(business_id: str) -> None:
    """Give back a call that the provider failed to answer, so outages do not use up the day's cap."""
    day = datetime.now(timezone.utc).date().isoformat()
    db.insert(
        config.DB_PATH,
        "UPDATE ai_usage SET calls = MAX(calls - 1, 0) WHERE business_id = ? AND day = ?",
        (business_id, day),
    )
