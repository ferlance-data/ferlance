"""The books: reports from the double-entry ledger, and the accountant's tools (PRD §9, G1).

Every read first brings the ledger up to date (``ledger.catch_up``), so reports never lag an import
or a stock movement. Reading is open to every member; manual journals, opening balances, the
period lock and the chart of accounts need ``manage_books`` (owner and accountant).
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import config, db, ledger
from ..deps import books_manager, current_user, read_business

router = APIRouter(prefix="/api/businesses/{business_id}/books", tags=["books"])


def _range(start: date | None, end: date | None) -> tuple[date, date]:
    end = end or date.today()
    start = start or date(end.year, 1, 1)
    if start > end:
        raise HTTPException(400, "The from date must be on or before the to date.")
    return start, end


@router.get("")
def books_summary(
    start: date | None = Query(default=None, alias="from"),
    end: date | None = Query(default=None, alias="to"),
    business: dict = Depends(read_business),
) -> dict:
    """Profit and loss, balance sheet, cash flow, the differences check and open issues, for one period."""
    start, end = _range(start, end)
    ledger.catch_up(config.DB_PATH, business["id"])
    with db.connection(config.DB_PATH) as conn:
        books_settings = ledger.settings(conn, business["id"])
    return {
        "settings": books_settings,
        "currency": business.get("currency") or "GHS",
        "lock_history": ledger.lock_history(config.DB_PATH, business["id"]),
        "profit_and_loss": ledger.profit_and_loss(config.DB_PATH, business["id"], start, end),
        "balance_sheet": ledger.balance_sheet(config.DB_PATH, business["id"], end),
        "cash_flow": ledger.cash_flow(config.DB_PATH, business["id"], start, end),
        "differences": ledger.differences(config.DB_PATH, business["id"], start, end),
        "issues": ledger.issues(config.DB_PATH, business["id"]),
    }


@router.get("/trial-balance")
def trial_balance(as_of: date | None = None, business: dict = Depends(read_business)) -> dict:
    ledger.catch_up(config.DB_PATH, business["id"])
    return ledger.trial_balance(config.DB_PATH, business["id"], as_of or date.today())


@router.get("/journal")
def journal(limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0), business: dict = Depends(read_business)) -> list[dict]:
    ledger.catch_up(config.DB_PATH, business["id"])
    return ledger.journal(config.DB_PATH, business["id"], limit, offset)


@router.get("/journal.csv")
def journal_csv(business: dict = Depends(read_business)) -> Response:
    ledger.catch_up(config.DB_PATH, business["id"])
    return Response(
        ledger.journal_csv(config.DB_PATH, business["id"]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ferlance-journal.csv"'},
    )


class JournalLine(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    debit: float = Field(default=0, ge=0, le=1e12)
    credit: float = Field(default=0, ge=0, le=1e12)
    description: str = Field(default="", max_length=300)


class JournalRequest(BaseModel):
    entry_date: date
    memo: str = Field(min_length=1, max_length=300)
    lines: list[JournalLine] = Field(min_length=2, max_length=50)


@router.post("/journal")
def add_journal(payload: JournalRequest, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        entry_id = ledger.manual_journal(config.DB_PATH, business["id"], payload.entry_date, payload.memo, [line.model_dump() for line in payload.lines], user["id"])
    except ledger.LedgerError as error:
        raise HTTPException(400, str(error)) from error
    return {"id": entry_id}


@router.get("/accounts")
def accounts(business: dict = Depends(read_business)) -> list[dict]:
    return ledger.accounts(config.DB_PATH, business["id"])


class AccountRequest(BaseModel):
    code: str = Field(min_length=1, max_length=12, pattern=r"^[0-9A-Za-z-]+$")
    name: str = Field(min_length=1, max_length=120)
    type: Literal["asset", "liability", "equity", "income", "expense"]


@router.post("/accounts")
def add_account(payload: AccountRequest, business: dict = Depends(books_manager)) -> dict:
    try:
        return ledger.add_account(config.DB_PATH, business["id"], payload.code, payload.name.strip(), payload.type)
    except ledger.LedgerError as error:
        raise HTTPException(400, str(error)) from error


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.patch("/accounts/{account_id}")
def rename_account(account_id: str, payload: RenameRequest, business: dict = Depends(books_manager)) -> dict:
    try:
        ledger.rename_account(config.DB_PATH, business["id"], account_id, payload.name.strip())
    except ledger.LedgerError as error:
        raise HTTPException(404, str(error)) from error
    return {"id": account_id, "name": payload.name.strip()}


@router.get("/opening")
def proposed_opening(start: date, business: dict = Depends(read_business)) -> dict:
    """Opening balances suggested from the financial-position balances, to confirm or edit."""
    return ledger.proposed_opening(config.DB_PATH, business["id"], start)


class OpeningLine(BaseModel):
    account: str = Field(min_length=1, max_length=40)
    account_name: str = Field(default="", max_length=120)
    amount: float = Field(ge=-1e12, le=1e12)


class OpeningRequest(BaseModel):
    start_date: date
    lines: list[OpeningLine] = Field(max_length=200)


@router.post("/opening")
def confirm_opening(payload: OpeningRequest, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        return ledger.confirm_opening(config.DB_PATH, business["id"], payload.start_date, [line.model_dump() for line in payload.lines], user["id"])
    except ledger.LedgerError as error:
        raise HTTPException(400, str(error)) from error


class LockRequest(BaseModel):
    lock_date: date | None


@router.put("/lock")
def set_lock(payload: LockRequest, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        ledger.set_lock(config.DB_PATH, business["id"], payload.lock_date, user["id"])
    except ledger.LedgerError as error:
        raise HTTPException(400, str(error)) from error
    return {"lock_date": payload.lock_date.isoformat() if payload.lock_date else None}
