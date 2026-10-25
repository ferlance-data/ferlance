"""Shared request dependencies: authentication, tenancy, and data scope."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import Depends, Header, HTTPException, Query

from . import config, dataset_store, db
from .security import read_access_token

BUSINESS_FIELDS = "id, name, currency"


def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required.")
    user_id = read_access_token(authorization.split(" ", 1)[1])
    user = db.one(config.DB_PATH, "SELECT id, email, role, full_name FROM users WHERE id = ?", (user_id or "",))
    if not user:
        raise HTTPException(401, "Invalid or expired token.")
    return user


def admin_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin" and user["email"].lower() not in config.ADMIN_EMAILS:
        raise HTTPException(403, "Administrator privileges are required.")
    return user


def primary_business(user_id: str) -> dict | None:
    return db.one(
        config.DB_PATH,
        f"SELECT {BUSINESS_FIELDS} FROM businesses WHERE user_id = ? ORDER BY created_at LIMIT 1",
        (user_id,),
    )


def owned_business(business_id: str, user: dict = Depends(current_user)) -> dict:
    """Path dependency: the business in the URL must belong to the signed-in user."""
    business = db.one(config.DB_PATH, "SELECT * FROM businesses WHERE id = ? AND user_id = ?", (business_id, user["id"]))
    if not business:
        raise HTTPException(404, "Business not found.")
    return business


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
    business: dict = Depends(owned_business),
    dataset_id: str | None = Query(default=None, description="A dataset id, or 'all' (default) for every included file."),
) -> Scope:
    return resolve_scope(business["id"], dataset_id)
