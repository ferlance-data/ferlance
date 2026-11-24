"""Notebook pages (PRD §9, G4): photograph or type an exercise-book page, check it, then add it."""

from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import config, ocr, pages
from ..deps import current_user, data_writer, read_business, refund_ai_call, spend_ai_call

router = APIRouter(prefix="/api/businesses/{business_id}/pages", tags=["notebook pages"])
PageType = Literal["sales", "debts", "expenses"]


@router.get("")
def recent_pages(business: dict = Depends(read_business)) -> list[dict]:
    return pages.recent(config.DB_PATH, business["id"])


@router.post("")
def read_page(file: UploadFile = File(...), business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    """Read a page photo into a draft with the AI reader. The photo itself is not stored."""
    content = file.file.read(ocr.MAX_BYTES + 1)
    try:
        ocr.sniff(content)
    except ocr.OcrError as error:
        raise HTTPException(error.status, str(error))
    spend_ai_call(business["id"])
    try:
        page = pages.clean_page(ocr.ask_vision(content, file.filename or "page", pages.PROMPT))
    except ocr.OcrError as error:
        refund_ai_call(business["id"])
        raise HTTPException(error.status, str(error))
    return pages.save_draft(config.DB_PATH, business["id"], user["id"], "vision", page)


class TypedPage(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    page_type: PageType


@router.post("/text")
def type_page(payload: TypedPage, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    """Free path: the page typed in, read on the server without AI."""
    return pages.save_draft(config.DB_PATH, business["id"], user["id"], "text", pages.parse_typed(payload.text, payload.page_type))


@router.get("/{capture_id}")
def get_page(capture_id: str, business: dict = Depends(read_business)) -> dict:
    try:
        return pages.get(config.DB_PATH, business["id"], capture_id)
    except pages.PageError as error:
        raise HTTPException(error.status, str(error))


class PageLine(BaseModel):
    include: bool = True
    date: Date | None = None
    description: str = Field(default="", max_length=200)
    customer: str | None = Field(default=None, max_length=120)
    quantity: float | None = Field(default=None, gt=0, le=1e7)
    amount: float | None = Field(default=None, ge=0, le=1e9)


class ConfirmPage(BaseModel):
    page_type: PageType
    page_date: Date
    lines: list[PageLine] = Field(min_length=1, max_length=pages.MAX_LINES)


@router.post("/{capture_id}/confirm")
def confirm_page(capture_id: str, payload: ConfirmPage, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    try:
        lines = [{**line.model_dump(), "date": line.date.isoformat() if line.date else None} for line in payload.lines]
        return pages.confirm(config.DB_PATH, business["id"], user["id"], capture_id, payload.page_type, payload.page_date, lines)
    except pages.PageError as error:
        raise HTTPException(error.status, str(error))
    except Exception as error:  # e.g. a debt the debt book refused
        if hasattr(error, "status"):
            raise HTTPException(getattr(error, "status"), str(error))
        raise


@router.delete("/{capture_id}")
def discard_page(capture_id: str, business: dict = Depends(data_writer)) -> dict:
    pages.discard(config.DB_PATH, business["id"], capture_id)
    return {"status": "discarded"}
