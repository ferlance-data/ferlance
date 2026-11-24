"""Tax rules, tax summaries and payroll (PRD §9, G6).

Salaries are private: every payroll route, reads included, needs manage_books (owner and accountant).
Tax rules can be read by any member; confirming one needs manage_books.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import config, payroll, tax
from ..deps import books_manager, current_user, read_business

router = APIRouter(prefix="/api/businesses/{business_id}", tags=["tax and payroll"])


def _fail(error: Exception) -> HTTPException:
    return HTTPException(getattr(error, "status", 400), str(error))


@router.get("/tax/rules")
def tax_rules(business: dict = Depends(read_business)) -> list[dict]:
    return tax.rules_for_business(config.DB_PATH, business["id"])


class CheckRequest(BaseModel):
    checked: bool


@router.put("/tax/rules/{rule_id}/check")
def check_rule(rule_id: str, payload: CheckRequest, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        tax.check_rule(config.DB_PATH, business["id"], user["id"], rule_id, payload.checked)
    except tax.TaxError as error:
        raise _fail(error) from error
    return {"id": rule_id, "checked": payload.checked}


@router.get("/tax/summary")
def tax_summary(start: date = Query(alias="from"), end: date = Query(alias="to"), business: dict = Depends(books_manager)) -> dict:
    if start > end:
        raise HTTPException(400, "The from date must be on or before the to date.")
    return payroll.summary(config.DB_PATH, business["id"], start, end)


@router.get("/payroll/employees")
def list_employees(business: dict = Depends(books_manager)) -> list[dict]:
    return payroll.employees(config.DB_PATH, business["id"])


class EmployeeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ssnit_number: str = Field(default="", max_length=30)
    tin: str = Field(default="", max_length=30)
    basic: float = Field(ge=0, le=1e8)
    allowances: float = Field(default=0, ge=0, le=1e8)
    active: bool = True


@router.post("/payroll/employees")
def add_employee(payload: EmployeeRequest, business: dict = Depends(books_manager)) -> dict:
    try:
        return payroll.save_employee(config.DB_PATH, business["id"], None, **payload.model_dump())
    except payroll.PayrollError as error:
        raise _fail(error) from error


@router.put("/payroll/employees/{employee_id}")
def update_employee(employee_id: str, payload: EmployeeRequest, business: dict = Depends(books_manager)) -> dict:
    try:
        return payroll.save_employee(config.DB_PATH, business["id"], employee_id, **payload.model_dump())
    except payroll.PayrollError as error:
        raise _fail(error) from error


@router.get("/payroll/runs")
def list_runs(business: dict = Depends(books_manager)) -> list[dict]:
    return payroll.runs(config.DB_PATH, business["id"])


class RunRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


@router.post("/payroll/runs")
def create_run(payload: RunRequest, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        return payroll.create_run(config.DB_PATH, business["id"], user["id"], payload.month)
    except (payroll.PayrollError, tax.TaxError) as error:
        raise _fail(error) from error


@router.get("/payroll/runs/{run_id}")
def get_run(run_id: str, business: dict = Depends(books_manager)) -> dict:
    try:
        return payroll.run_detail(config.DB_PATH, business["id"], run_id)
    except payroll.PayrollError as error:
        raise _fail(error) from error


class PostRequest(BaseModel):
    paid_from: Literal["cash", "bank", "momo_mtn", "momo_telecel", "momo_at", "momo_other"]
    paid_on: date


@router.post("/payroll/runs/{run_id}/post")
def post_run(run_id: str, payload: PostRequest, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    if payload.paid_on > date.today():
        raise HTTPException(400, "The pay date cannot be in the future.")
    try:
        payroll.post_run(config.DB_PATH, business["id"], user["id"], run_id, payload.paid_from, payload.paid_on)
    except payroll.PayrollError as error:
        raise _fail(error) from error
    return {"id": run_id, "status": "posted"}


@router.post("/payroll/runs/{run_id}/void")
def void_run(run_id: str, business: dict = Depends(books_manager), user: dict = Depends(current_user)) -> dict:
    try:
        payroll.void_run(config.DB_PATH, business["id"], user["id"], run_id)
    except payroll.PayrollError as error:
        raise _fail(error) from error
    return {"id": run_id, "status": "void"}


@router.get("/payroll/runs/{run_id}/payslips/{line_id}")
def payslip(run_id: str, line_id: str, business: dict = Depends(books_manager)) -> Response:
    try:
        body, filename = payroll.payslip_pdf(config.DB_PATH, business["id"], run_id, line_id)
    except payroll.PayrollError as error:
        raise _fail(error) from error
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "no-store"})
