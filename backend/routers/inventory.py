"""Inventory catalogue and auditable stock ledger (kept separate from sales imports)."""

import csv
import io
import json
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field

from .. import config, db, inventory, ocr, sync
from ..deps import current_user, data_writer, read_business, refund_ai_call, spend_ai_call

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
def inventory_list(include_archived: bool = False, business: dict = Depends(read_business)) -> dict:
    return inventory.list_products(config.DB_PATH, business["id"], include_archived)


@router.post("/products")
def create_product(payload: InventoryProductCreate, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
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
def update_product(product_id: str, payload: InventoryProductUpdate, business: dict = Depends(data_writer)) -> dict:
    try:
        return inventory.update_product(config.DB_PATH, business["id"], product_id, payload.model_dump(exclude_unset=True))
    except inventory.InventoryError as error:
        raise _error(error)


@router.post("/products/{product_id}/movements")
def record_movement(
    product_id: str,
    payload: InventoryMovementRequest,
    business: dict = Depends(data_writer),
    user: dict = Depends(current_user),
) -> dict:
    try:
        return inventory.record_movement(
            config.DB_PATH, business["id"], product_id, user["id"], payload.movement_type, payload.quantity, payload.note
        )
    except inventory.InventoryError as error:
        raise _error(error)


@router.get("/movements")
def movement_history(limit: int = Query(default=100, ge=1, le=500), business: dict = Depends(read_business)) -> list[dict]:
    return inventory.list_movements(config.DB_PATH, business["id"], limit)


@router.post("/import")
def import_stocktake(file: UploadFile = File(...), business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
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
def import_template(business: dict = Depends(read_business)) -> Response:
    return Response(
        STOCKTAKE_HEADERS,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="inventory-stocktake-template.csv"'},
    )


# ---------- Scan an invoice (OCR) -> draft -> review -> confirm ----------

class CaptureText(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class CaptureDecision(BaseModel):
    action: str = Field(pattern="^(add|create|skip)$")
    product_id: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=40)
    quantity: float | None = None
    unit_cost: float | None = None
    reason: str | None = Field(default=None, max_length=200)


class CaptureConfirm(BaseModel):
    lines: list[CaptureDecision] = Field(max_length=ocr.MAX_LINES)


def _save_capture(business: dict, user: dict, source: str, filename: str, lines: list[dict]) -> dict:
    if not lines:
        raise HTTPException(422, "No product lines were found. Try a clearer photo, or type the lines in.")
    # Archived products are matched too: their names are taken, so "create" would be refused.
    products = inventory.list_products(config.DB_PATH, business["id"], include_archived=True)["items"]
    lines = ocr.match_products(lines, products)
    capture_id = str(uuid.uuid4())
    # Drafts nobody confirmed within 30 days are dropped (they hold supplier prices).
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    db.insert(config.DB_PATH, "DELETE FROM stock_captures WHERE business_id = ? AND status != 'confirmed' AND created_at < ?", (business["id"], cutoff))
    db.insert(
        config.DB_PATH,
        "INSERT INTO stock_captures (id, business_id, created_by, source, filename, status, lines, created_at) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)",
        (capture_id, business["id"], user["id"], source, filename[:120], json.dumps(lines), db.now()),
    )
    return {"id": capture_id, "status": "draft", "source": source, "filename": filename[:120], "lines": lines}


@router.post("/captures")
def create_capture(file: UploadFile = File(...), business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    """Read a photo or PDF into a draft. The file itself is not stored."""
    content = file.file.read(ocr.MAX_BYTES + 1)
    try:
        ocr.sniff(content)
    except ocr.OcrError as error:
        raise HTTPException(error.status, str(error))
    spend_ai_call(business["id"])
    try:
        lines = ocr.read_document(content, file.filename or "document")
    except ocr.OcrError as error:
        refund_ai_call(business["id"])
        raise HTTPException(error.status, str(error))
    return _save_capture(business, user, "vision", file.filename or "Photo", lines)


@router.post("/captures/text")
def create_text_capture(payload: CaptureText, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    """Free path: pasted lines such as "Rice 5kg, 10, 70" become a draft without any AI."""
    return _save_capture(business, user, "text", "Typed list", ocr.parse_text(payload.text))


@router.get("/captures/{capture_id}")
def get_capture(capture_id: str, business: dict = Depends(read_business)) -> dict:
    row = db.one(config.DB_PATH, "SELECT * FROM stock_captures WHERE id = ? AND business_id = ?", (capture_id, business["id"]))
    if not row:
        raise HTTPException(404, "Scan not found.")
    return {**{k: row[k] for k in ("id", "status", "source", "filename", "created_at", "confirmed_at")}, "lines": json.loads(row["lines"]), "outcome": json.loads(row["outcome"] or "null")}


@router.post("/captures/{capture_id}/confirm")
def confirm_capture(capture_id: str, payload: CaptureConfirm, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    try:
        return inventory.confirm_capture(config.DB_PATH, business["id"], user["id"], capture_id, [line.model_dump() for line in payload.lines])
    except inventory.CaptureConflict as error:
        raise HTTPException(409, str(error))
    except inventory.InventoryError as error:
        raise HTTPException(404 if str(error) in ("Scan not found.", "Product not found.") else 400, str(error))


@router.delete("/captures/{capture_id}")
def discard_capture(capture_id: str, business: dict = Depends(data_writer)) -> dict:
    db.insert(
        config.DB_PATH,
        "UPDATE stock_captures SET status = 'discarded' WHERE id = ? AND business_id = ? AND status = 'draft'",
        (capture_id, business["id"]),
    )
    return {"status": "discarded"}


# ---------- Sync with sales: links, posting a file's sales to stock, reconciliation ----------

class LinkRequest(BaseModel):
    sales_name: str = Field(min_length=1, max_length=200)
    product_id: str | None = Field(default=None, max_length=64)
    ignore: bool = False


@router.get("/links")
def sales_links(business: dict = Depends(read_business)) -> dict:
    rows = sync.sales_names(config.DB_PATH, business["id"])
    return {"names": rows, "unlinked": sum(1 for row in rows if row["status"] == "unlinked")}


@router.put("/links")
def save_link(payload: LinkRequest, business: dict = Depends(data_writer)) -> dict:
    try:
        if payload.ignore or payload.product_id:
            sync.set_link(config.DB_PATH, business["id"], payload.sales_name, None if payload.ignore else payload.product_id)
        else:
            sync.clear_link(config.DB_PATH, business["id"], payload.sales_name)
    except inventory.InventoryError as error:
        raise _error(error)
    return {"status": "saved"}


@router.get("/posts")
def stock_posts(business: dict = Depends(read_business)) -> dict:
    return sync.post_states(config.DB_PATH, business["id"])


@router.post("/posts/{dataset_id}")
def post_sales(dataset_id: str, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    try:
        return sync.post_dataset(config.DB_PATH, business["id"], dataset_id, user["id"])
    except sync.StockConflict as error:
        raise HTTPException(409, {"message": str(error), "conflicts": error.conflicts})
    except sync.AlreadyPosted as error:
        raise HTTPException(409, {"message": str(error), "conflicts": []})
    except inventory.InventoryError as error:
        raise HTTPException(404 if str(error) == "Dataset not found." else 400, str(error))


@router.get("/reconciliation")
def reconciliation(business: dict = Depends(read_business)) -> list[dict]:
    return sync.reconciliation(config.DB_PATH, business["id"])
