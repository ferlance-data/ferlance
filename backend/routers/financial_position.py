"""Dated account balances and point-in-time statements of financial position."""

import math
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import config, financial_position
from ..deps import current_user, owned_business

router = APIRouter(prefix="/api/businesses/{business_id}/financial-position", tags=["financial position"])


class BalanceRequest(BaseModel):
    as_of_date: date
    category: str = Field(min_length=1, max_length=40)
    account_name: str = Field(min_length=1, max_length=120)
    amount: float
    note: str = Field(default="", max_length=500)


@router.post("/balances")
def add_balance(payload: BalanceRequest, business: dict = Depends(owned_business), user: dict = Depends(current_user)) -> dict:
    try:
        if not math.isfinite(payload.amount):
            raise financial_position.FinancialPositionError("Balance must be a finite number.")
        return financial_position.record_balance(
            config.DB_PATH,
            business["id"],
            user["id"],
            payload.category,
            payload.account_name,
            payload.as_of_date,
            payload.amount,
            payload.note,
        )
    except financial_position.FinancialPositionError as error:
        raise HTTPException(400, str(error))


@router.get("")
def position(as_of_date: date = Query(default_factory=date.today, alias="as_of"), business: dict = Depends(owned_business)) -> dict:
    return financial_position.position_as_of(config.DB_PATH, business["id"], as_of_date)


@router.get("/history")
def history(limit: int = Query(default=200, ge=1, le=1000), business: dict = Depends(owned_business)) -> list[dict]:
    return financial_position.balance_history(config.DB_PATH, business["id"], limit)
