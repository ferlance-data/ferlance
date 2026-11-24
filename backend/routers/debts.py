"""The debt book: who owes the business, whom it owes, payments, reminders and MoMo matches (PRD §9, G2).

Reading is open to every member. Recording debts and payments, voiding, and the pay-to details
need ``write_data`` (owner and manager), like any other business record.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config, debts, tax
from ..deps import current_user, data_writer, read_business

router = APIRouter(prefix="/api/businesses/{business_id}/debts", tags=["debts"])


def _fail(error: debts.DebtError) -> HTTPException:
    return HTTPException(error.status, str(error))


@router.get("")
def debt_book(business: dict = Depends(read_business)) -> dict:
    return debts.book(config.DB_PATH, business["id"])


class DebtRequest(BaseModel):
    direction: Literal["owed_to_us", "we_owe"]
    party_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(default="", max_length=30, pattern=r"^[0-9+ ()-]*$")
    description: str = Field(default="", max_length=300)
    amount: float = Field(gt=0, le=1e10)
    issued_on: date
    due_on: date | None = None
    basis: Literal["new_sale", "recorded_sale", "recorded_purchase", "expense"]


@router.post("")
def add_debt(payload: DebtRequest, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    try:
        return debts.create_debt(config.DB_PATH, business["id"], user["id"], **payload.model_dump())
    except debts.DebtError as error:
        raise _fail(error) from error


class PaymentRequest(BaseModel):
    amount: float | None = Field(default=None, gt=0, le=1e10)
    paid_on: date | None = None
    method: Literal["cash", "momo_mtn", "momo_telecel", "momo_at", "momo_other", "bank"] | None = None
    momo_ref: str | None = Field(default=None, max_length=200)
    withhold: Literal["goods", "works", "services", "non_resident"] | None = None


@router.post("/{debt_id}/payments")
def add_payment(debt_id: str, payload: PaymentRequest, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    try:
        return debts.add_payment(config.DB_PATH, business["id"], user["id"], debt_id, **payload.model_dump())
    except (debts.DebtError, tax.TaxError) as error:
        raise _fail(error) from error


@router.post("/{debt_id}/void")
def void_debt(debt_id: str, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    try:
        debts.void_debt(config.DB_PATH, business["id"], user["id"], debt_id)
    except debts.DebtError as error:
        raise _fail(error) from error
    return {"id": debt_id, "status": "voided"}


@router.post("/payments/{payment_id}/void")
def void_payment(payment_id: str, business: dict = Depends(data_writer), user: dict = Depends(current_user)) -> dict:
    try:
        debts.void_payment(config.DB_PATH, business["id"], user["id"], payment_id)
    except debts.DebtError as error:
        raise _fail(error) from error
    return {"id": payment_id, "status": "voided"}


@router.get("/suggestions")
def momo_suggestions(business: dict = Depends(read_business)) -> list[dict]:
    return debts.suggestions(config.DB_PATH, business["id"])


class PayToRequest(BaseModel):
    pay_to: str = Field(max_length=160)


@router.put("/settings")
def set_pay_to(payload: PayToRequest, business: dict = Depends(data_writer)) -> dict:
    debts.set_pay_to(config.DB_PATH, business["id"], payload.pay_to)
    return {"pay_to": payload.pay_to.strip()}
