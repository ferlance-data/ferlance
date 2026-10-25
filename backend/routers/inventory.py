"""Inventory catalogue and auditable stock ledger (kept separate from sales imports)."""

import csv
import io
import math
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from .. import config, inventory
from ..deps import current_user, owned_business

router = APIRouter(prefix="/api/businesses/{business_id}/inventory", tags=["inventory"])
STOCKTAKE_HEADERS = "product,sku,unit,quantity_on_hand,unit_cost,reorder_level\n"


class InventoryProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="unit", min_length=1, max_length=40)
    unit_cost: float | None = Field(default=None, ge=0)
    reorder_level: float = Field(default=0, ge=0)
    opening_stock: float = Field(default=0, ge=0)


class InventoryProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    sku: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=40)
    unit_cost: float | None = Field(default=None, ge=0)
    reorder_level: float | None = Field(default=None, ge=0)
    active: bool | None = None


class InventoryMovementRequest(BaseModel):
    movement_type: str = Field(pattern="^(purchase|sale|adjustment)$")
    quantity: float
    note: str = Field(default="", max_length=500)


def _error(error: inventory.InventoryError) -> HTTPException:
    message = str(error)
    status_code = 404 if message == "Product not found." else 409 if "already exists" in message else 400
    return HTTPException(status_code, message)


def _parse_number(value: str | None, row_number: int, field: str, required: bool = False) -> float | None:
    if value is None or not value.strip():
        if required:
            raise HTTPException(400, f"Row {row_number} is missing {field}.")
        return None
    cleaned = value.strip()
    if not re.fullmatch(r"(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?|\.\d+)", cleaned):
        raise HTTPException(400, f"Row {row_number} has an invalid {field}.")
    number = float(cleaned.replace(",", ""))
    if not math.isfinite(number) or number < 0:
        raise HTTPException(400, f"Row {row_number} {field} must be finite and non-negative.")
    return number


def _cell(row: dict, header_map: dict[str, str], name: str) -> str | None:
    return row.get(header_map[name]) if name in header_map else None


@router.get("")
def inventory_list(include_archived: bool = False, business: dict = Depends(owned_business)) -> dict:
    return inventory.list_products(config.DB_PATH, business["id"], include_archived)


@router.post("/products")
def create_product(payload: InventoryProductCreate, business: dict = Depends(owned_business), user: dict = Depends(current_user)) -> dict:
    try:
        return inventory.create_product(
            config.DB_PATH,
            business["id"],
            user["id"],
            name=payload.name,
            sku=payload.sku,
            unit=payload.unit,
            unit_cost=payload.unit_cost,
            reorder_level=payload.reorder_level,
            opening_stock=payload.opening_stock,
        )
    except inventory.InventoryError as error:
        raise _error(error)


@router.patch("/products/{product_id}")
def update_product(product_id: str, payload: InventoryProductUpdate, business: dict = Depends(owned_business)) -> dict:
    try:
        return inventory.update_product(config.DB_PATH, business["id"], product_id, payload.model_dump(exclude_unset=True))
    except inventory.InventoryError as error:
        raise _error(error)


@router.post("/products/{product_id}/movements")
def record_movement(
    product_id: str,
    payload: InventoryMovementRequest,
    business: dict = Depends(owned_business),
    user: dict = Depends(current_user),
) -> dict:
    try:
        return inventory.record_movement(
            config.DB_PATH, business["id"], product_id, user["id"], payload.movement_type, payload.quantity, payload.note
        )
    except inventory.InventoryError as error:
        raise _error(error)


@router.get("/movements")
def movement_history(limit: int = Query(default=100, ge=1, le=500), business: dict = Depends(owned_business)) -> list[dict]:
    return inventory.list_movements(config.DB_PATH, business["id"], limit)


@router.post("/import")
def import_stocktake(file: UploadFile = File(...), business: dict = Depends(owned_business), user: dict = Depends(current_user)) -> dict:
    if Path(file.filename or "").suffix.lower() != ".csv":
        raise HTTPException(415, "Inventory stocktake imports must be CSV files.")
    content = file.file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Uploaded file is too large.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "Inventory CSV must use UTF-8 encoding.")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        raise HTTPException(400, "Inventory CSV must include a header row.")
    headers = [header.strip().casefold() for header in reader.fieldnames]
    if len(headers) != len(set(headers)):
        raise HTTPException(400, "Inventory CSV contains duplicate column names.")
    if not {"product", "quantity_on_hand"}.issubset(headers):
        raise HTTPException(400, "Inventory CSV must include product and quantity_on_hand columns.")
    header_map = dict(zip(headers, reader.fieldnames))
    rows = []
    for row_number, raw_row in enumerate(reader, start=2):
        if None in raw_row:
            raise HTTPException(400, f"Row {row_number} has extra values beyond its headers.")
        if not any((value or "").strip() for value in raw_row.values()):
            continue
        rows.append(
            {
                "name": _cell(raw_row, header_map, "product") or "",
                "sku": _cell(raw_row, header_map, "sku"),
                "unit": _cell(raw_row, header_map, "unit") or "unit",
                "quantity_on_hand": _parse_number(_cell(raw_row, header_map, "quantity_on_hand"), row_number, "quantity_on_hand", required=True),
                "unit_cost": _parse_number(_cell(raw_row, header_map, "unit_cost"), row_number, "unit_cost"),
                "reorder_level": _parse_number(_cell(raw_row, header_map, "reorder_level"), row_number, "reorder_level"),
            }
        )
    try:
        return inventory.import_stocktake(config.DB_PATH, business["id"], user["id"], rows)
    except inventory.InventoryError as error:
        raise _error(error)


@router.get("/import-template")
def import_template(business: dict = Depends(owned_business)) -> Response:
    return Response(
        STOCKTAKE_HEADERS,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="inventory-stocktake-template.csv"'},
    )
