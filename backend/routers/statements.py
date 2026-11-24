"""Statements and reconciliation (PRD §9, G5). Reading needs read; importing and booking need manage_books."""

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import config, debts, statements
from ..deps import books_manager, current_user, read_business

router = APIRouter(prefix="/api/businesses/{business_id}/statements", tags=["statements"])
MAX_BYTES = 5 * 1024 * 1024


def _content(file: UploadFile) -> bytes:
    content = file.file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "That statement is over 5 MB. Export a shorter period.")
    return content


def _fail(error: Exception) -> HTTPException:
    return HTTPException(getattr(error, "status", 400), str(error))


@router.get("")
def statements_overview(business: dict = Depends(read_business)) -> dict:
    return statements.overview(config.DB_PATH, business["id"])


@router.post("/preview")
def preview_statement(file: UploadFile = File(...), business: dict = Depends(books_manager)) -> dict:
    """Read the file's columns and suggest which is which. Nothing is saved."""
    try:
        return statements.preview(_content(file), file.filename or "statement.csv")
    except statements.StatementError as error:
        raise _fail(error) from error


@router.post("")
def import_statement(
    file: UploadFile = File(...),
    account: str = Form(...),
    header_row: int = Form(0, ge=0, le=1000),
    mapping: str = Form(...),
    business: dict = Depends(books_manager),
    user: dict = Depends(current_user),
) -> dict:
    try:
        raw = json.loads(mapping)
        clean = {field: (int(raw[field]) if raw.get(field) not in (None, "") else None) for field in statements.FIELDS}
    except (ValueError, TypeError, KeyError) as error:
        raise HTTPException(422, "The column choices could not be read.") from error
    try:
        return statements.import_statement(config.DB_PATH, business["id"], user["id"], account, file.filename or "statement.csv", _content(file), header_row, clean)
    except statements.StatementError as error:
        raise _fail(error) from error


@router.get("/{account}")
def reconcile(account: str, business: dict = Depends(read_business)) -> dict:
    try:
        return statements.view(config.DB_PATH, business["id"], account)
    except statements.StatementError as error:
        raise _fail(error) from error


class MatchRequest(BaseModel):
    candidate_id: str | None = Field(default=None, max_length=200)


@router.put("/lines/{line_id}/match")
def choose_match(line_id: str, payload: MatchRequest, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        statements.choose_match(config.DB_PATH, business["id"], user["id"], line_id, payload.candidate_id)
    except statements.StatementError as error:
        raise _fail(error) from error
    return {"id": line_id, "match": payload.candidate_id}


class BookRequest(BaseModel):
    category: Literal["sale_recorded", "new_sale", "other_income", "payment_recorded", "expense", "owner", "transfer", "debt_payment"]
    detail: dict[str, Any] = Field(default_factory=dict)


@router.post("/lines/{line_id}/book")
def book_line(line_id: str, payload: BookRequest, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        return statements.book(config.DB_PATH, business["id"], user["id"], line_id, payload.category, payload.detail)
    except (statements.StatementError, debts.DebtError) as error:
        raise _fail(error) from error


@router.delete("/lines/{line_id}/book")
def unbook_line(line_id: str, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        statements.unbook(config.DB_PATH, business["id"], user["id"], line_id)
    except (statements.StatementError, debts.DebtError) as error:
        raise _fail(error) from error
    return {"id": line_id, "booking": None}


@router.post("/{account}/fees")
def book_fees(account: str, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    if account not in statements.ACCOUNTS:
        raise HTTPException(404, "Unknown account.")
    return {"booked": statements.book_fees(config.DB_PATH, business["id"], user["id"], account)}
