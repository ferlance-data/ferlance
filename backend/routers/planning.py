"""Recurring expenses, budgets, the year-end pack and "download my data" (PRD §9, G9)."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import config, planning
from ..deps import books_manager, business_manager, current_user, read_business

router = APIRouter(prefix="/api/businesses/{business_id}", tags=["planning"])


def _fail(error: planning.PlanningError) -> HTTPException:
    return HTTPException(error.status, str(error))


@router.get("/recurring")
def recurring(business: dict = Depends(read_business)) -> dict:
    return planning.recurring(config.DB_PATH, business["id"])


class RecurringRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    account: Literal["rent", "transport", "airtime", "utilities", "wages", "charges", "uncategorised"]
    amount: float = Field(gt=0, le=1e9)
    paid_from: Literal["cash", "bank", "momo_mtn", "momo_telecel", "momo_at", "momo_other"]
    day_of_month: int = Field(ge=1, le=28)
    start_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


@router.post("/recurring")
def add_recurring(payload: RecurringRequest, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        return planning.add_recurring(config.DB_PATH, business["id"], user["id"], **payload.model_dump())
    except planning.PlanningError as error:
        raise _fail(error) from error


@router.post("/recurring/{item_id}/stop")
def stop_recurring(item_id: str, business: dict = Depends(books_manager)) -> dict:
    try:
        planning.stop_recurring(config.DB_PATH, business["id"], item_id)
    except planning.PlanningError as error:
        raise _fail(error) from error
    return {"id": item_id, "active": False}


class DecideRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    confirm: bool
    amount: float | None = Field(default=None, gt=0, le=1e9)
    posted_on: date | None = None


@router.post("/recurring/{item_id}/decide")
def decide(item_id: str, payload: DecideRequest, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        planning.decide(config.DB_PATH, business["id"], user["id"], item_id, payload.month, payload.confirm, payload.amount, payload.posted_on)
    except planning.PlanningError as error:
        raise _fail(error) from error
    return {"id": item_id, "month": payload.month, "confirmed": payload.confirm}


@router.delete("/recurring/{item_id}/months/{month}")
def undo(item_id: str, month: str, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        planning.undo(config.DB_PATH, business["id"], user["id"], item_id, month)
    except planning.PlanningError as error:
        raise _fail(error) from error
    return {"id": item_id, "month": month, "undone": True}


@router.get("/budgets")
def budgets(month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), business: dict = Depends(read_business)) -> dict:
    return planning.budget_vs_actual(config.DB_PATH, business["id"], month)


class BudgetRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    account: str = Field(min_length=1, max_length=40)
    amount: float = Field(ge=0, le=1e10)


@router.put("/budgets")
def set_budget(payload: BudgetRequest, business: dict = Depends(books_manager)) -> dict:
    try:
        planning.set_budget(config.DB_PATH, business["id"], payload.month, payload.account, payload.amount)
    except planning.PlanningError as error:
        raise _fail(error) from error
    return {"ok": True}


@router.get("/year-end.zip")
def year_end(year: int = Query(ge=2000, le=2100), business: dict = Depends(books_manager)) -> Response:
    body = planning.year_end_pack(config.DB_PATH, business["id"], year)
    return Response(body, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="ferlance-year-end-{year}.zip"', "Cache-Control": "no-store"})


@router.get("/my-data.zip")
def my_data(business: dict = Depends(business_manager)) -> Response:
    body = planning.my_data(config.DB_PATH, business["id"])
    return Response(body, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="ferlance-my-data.zip"', "Cache-Control": "no-store"})
