"""Invoices, quotes and receipts (PRD §9, G3). Reading is open to members; writing needs write_data."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import config, invoices
from ..deps import current_user, data_writer, read_business
from ..inventory import InventoryError

router = APIRouter(prefix="/api/businesses/{business_id}/invoices", tags=["invoices"])


def _fail(error: Exception) -> HTTPException:
    if isinstance(error, invoices.StockShort):
        return HTTPException(409, {"message": str(error), "shortages": error.shortages})
    if isinstance(error, InventoryError):
        return HTTPException(404, str(error))
    return HTTPException(getattr(error, "status", 400), str(error))


class Line(BaseModel):
    product_id: str | None = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=200)
    quantity: float = Field(gt=0, le=1e7)
    unit_price: float = Field(ge=0, le=1e9)


class InvoiceRequest(BaseModel):
    kind: Literal["invoice", "quote", "receipt"]
    customer_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(default="", max_length=30, pattern=r"^[0-9+ ()-]*$")
    issued_on: date
    due_on: date | None = None
    lines: list[Line] = Field(min_length=1, max_length=100)
    notes: str = Field(default="", max_length=500)
    paid_by: Literal["cash", "momo_mtn", "momo_telecel", "momo_at", "momo_other", "bank"] | None = None


@router.get("")
def list_invoices(kind: Literal["invoice", "quote", "receipt"] | None = Query(default=None), business: dict = Depends(read_business)) -> list[dict]:
    return invoices.listing(config.DB_PATH, business["id"], kind)


@router.post("")
def create_invoice(payload: InvoiceRequest, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    try:
        body = payload.model_dump()
        body["lines"] = [line for line in body["lines"]]
        return invoices.create(config.DB_PATH, business["id"], user["id"], **body)
    except (invoices.InvoiceError, InventoryError) as error:
        raise _fail(error) from error


class SettingsRequest(BaseModel):
    tin: str = Field(default="", max_length=40)
    address: str = Field(default="", max_length=300)
    phone: str = Field(default="", max_length=60)
    footer: str = Field(default="", max_length=300)


@router.get("/settings")
def invoice_settings(business: dict = Depends(read_business)) -> dict:
    return invoices.settings(config.DB_PATH, business["id"])


@router.put("/settings")
def save_invoice_settings(payload: SettingsRequest, business: dict = Depends(data_writer)) -> dict:
    invoices.save_settings(config.DB_PATH, business["id"], **payload.model_dump())
    return invoices.settings(config.DB_PATH, business["id"])


@router.get("/{invoice_id}")
def get_invoice(invoice_id: str, business: dict = Depends(read_business)) -> dict:
    try:
        return invoices.get(config.DB_PATH, business["id"], invoice_id)
    except invoices.InvoiceError as error:
        raise _fail(error) from error


@router.get("/{invoice_id}/pdf")
def invoice_pdf(invoice_id: str, business: dict = Depends(read_business)) -> Response:
    try:
        body, filename = invoices.pdf(config.DB_PATH, business["id"], invoice_id)
    except invoices.InvoiceError as error:
        raise _fail(error) from error
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "no-store"})


class ConvertRequest(BaseModel):
    issued_on: date
    due_on: date | None = None


@router.post("/{invoice_id}/convert")
def convert_quote(invoice_id: str, payload: ConvertRequest, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    try:
        return invoices.convert(config.DB_PATH, business["id"], user["id"], invoice_id, payload.issued_on, payload.due_on)
    except (invoices.InvoiceError, InventoryError) as error:
        raise _fail(error) from error


@router.post("/{invoice_id}/void")
def void_invoice(invoice_id: str, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    try:
        invoices.void(config.DB_PATH, business["id"], user["id"], invoice_id)
    except invoices.InvoiceError as error:
        raise _fail(error) from error
    return {"id": invoice_id, "status": "void"}
