"""A small payroll for 1–20 staff (PRD §9, G6): SSNIT, PAYE, net pay, payslips, into the books.

Each month's run is a draft until posted. Posting books wages and employer SSNIT as costs, pays the
net out of the chosen account, and leaves PAYE and both SSNIT shares as amounts owed to GRA and
SSNIT (``ledger._catch_up_payroll``). Every line keeps the rule ids it used. A posted run can be
voided (its entries are reversed) and the month run again.

PAYE here is for resident employees on basic salary plus cash allowances. Other benefits, reliefs
and bonuses are not handled; an accountant should review the first runs.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from . import db, ledger, tax

PAY_FROM = ("cash", "bank", "momo_mtn", "momo_telecel", "momo_at", "momo_other")


class PayrollError(ValueError):
    status = 400


class NotFound(PayrollError):
    status = 404


def employees(path: Path, business_id: str) -> list[dict[str, Any]]:
    rows = db.many(path, "SELECT * FROM employees WHERE business_id = ? ORDER BY active DESC, name COLLATE NOCASE", (business_id,))
    return [{"id": r["id"], "name": r["name"], "ssnit_number": r["ssnit_number"], "tin": r["tin"], "basic": ledger.from_minor(r["basic_minor"]),
             "allowances": ledger.from_minor(r["allowances_minor"]), "active": bool(r["active"])} for r in rows]


def save_employee(path: Path, business_id: str, employee_id: str | None, *, name: str, ssnit_number: str, tin: str, basic: float, allowances: float, active: bool) -> dict[str, Any]:
    name = " ".join(name.split())
    if not name:
        raise PayrollError("Enter the employee's name.")
    values = (name[:120], ssnit_number.strip()[:30], tin.strip()[:30], tax.to_minor(basic), tax.to_minor(allowances), int(active))
    if employee_id:
        if not db.one(path, "SELECT 1 FROM employees WHERE id = ? AND business_id = ?", (employee_id, business_id)):
            raise NotFound("Employee not found.")
        db.insert(path, "UPDATE employees SET name = ?, ssnit_number = ?, tin = ?, basic_minor = ?, allowances_minor = ?, active = ? WHERE id = ? AND business_id = ?", (*values, employee_id, business_id))
        return {"id": employee_id}
    employee_id = str(uuid.uuid4())
    db.insert(path, "INSERT INTO employees (id, business_id, name, ssnit_number, tin, basic_minor, allowances_minor, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (employee_id, business_id, *values, db.now()))
    return {"id": employee_id}


def calculate(basic_minor: int, allowances_minor: int, day: date) -> dict[str, Any]:
    """One employee's month: SSNIT on basic, PAYE on (gross - employee SSNIT), net pay."""
    gross = basic_minor + allowances_minor
    employee_ssnit, employer_ssnit, ssnit_rule = tax.ssnit(basic_minor, day)
    chargeable = gross - employee_ssnit
    paye, paye_rule = tax.paye(chargeable, day)
    return {"basic": basic_minor, "allowances": allowances_minor, "gross": gross, "ssnit_employee": employee_ssnit, "ssnit_employer": employer_ssnit,
            "chargeable": chargeable, "paye": paye, "net": gross - employee_ssnit - paye, "rules": [ssnit_rule, paye_rule]}


def _month_day(month: str) -> date:
    try:
        return date.fromisoformat(f"{month}-01")
    except ValueError as error:
        raise PayrollError("Choose a month like 2026-11.") from error


def create_run(path: Path, business_id: str, user_id: str, month: str) -> dict[str, Any]:
    day = _month_day(month)
    staff = db.many(path, "SELECT * FROM employees WHERE business_id = ? AND active = 1 ORDER BY name COLLATE NOCASE", (business_id,))
    if not staff:
        raise PayrollError("Add at least one employee first.")
    run_id = str(uuid.uuid4())
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM payroll_runs WHERE business_id = ? AND month = ? AND status != 'void'", (business_id, month)).fetchone():
            raise PayrollError("This month already has a payroll. Void it first to run it again.")
        conn.execute("INSERT INTO payroll_runs (id, business_id, month, status, created_by, created_at) VALUES (?, ?, ?, 'draft', ?, ?)", (run_id, business_id, month, user_id, db.now()))
        for person in staff:
            line = calculate(person["basic_minor"], person["allowances_minor"], day)
            conn.execute(
                "INSERT INTO payroll_lines (id, run_id, employee_id, name, basic_minor, allowances_minor, gross_minor, ssnit_employee_minor, ssnit_employer_minor, chargeable_minor, paye_minor, net_minor, rules) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), run_id, person["id"], person["name"], line["basic"], line["allowances"], line["gross"], line["ssnit_employee"],
                 line["ssnit_employer"], line["chargeable"], line["paye"], line["net"], json.dumps(line["rules"])),
            )
    return {"id": run_id, "month": month}


def runs(path: Path, business_id: str) -> list[dict[str, Any]]:
    rows = db.many(
        path,
        "SELECT r.*, SUM(l.gross_minor) AS gross, SUM(l.net_minor) AS net, SUM(l.paye_minor) AS paye, SUM(l.ssnit_employee_minor + l.ssnit_employer_minor) AS ssnit, COUNT(l.id) AS staff "
        "FROM payroll_runs r LEFT JOIN payroll_lines l ON l.run_id = r.id WHERE r.business_id = ? GROUP BY r.id ORDER BY r.month DESC, r.created_at DESC",
        (business_id,),
    )
    return [{"id": r["id"], "month": r["month"], "status": r["status"], "paid_from": r["paid_from"], "paid_on": r["paid_on"], "staff": r["staff"],
             **{k: ledger.from_minor(r[k] or 0) for k in ("gross", "net", "paye", "ssnit")}} for r in rows]


def run_detail(path: Path, business_id: str, run_id: str) -> dict[str, Any]:
    run = db.one(path, "SELECT * FROM payroll_runs WHERE id = ? AND business_id = ?", (run_id, business_id))
    if not run:
        raise NotFound("Payroll not found.")
    lines = db.many(path, "SELECT * FROM payroll_lines WHERE run_id = ? ORDER BY name COLLATE NOCASE", (run_id,))
    keys = ("basic", "allowances", "gross", "ssnit_employee", "ssnit_employer", "chargeable", "paye", "net")
    rule_ids = {rule for line in lines for rule in json.loads(line["rules"])}
    return {
        "id": run["id"], "month": run["month"], "status": run["status"], "paid_from": run["paid_from"], "paid_on": run["paid_on"],
        "lines": [{"id": l["id"], "employee_id": l["employee_id"], "name": l["name"], "rules": json.loads(l["rules"]), **{k: ledger.from_minor(l[f"{k}_minor"]) for k in keys}} for l in lines],
        "totals": {k: ledger.from_minor(sum(l[f"{k}_minor"] for l in lines)) for k in keys},
        "unchecked_rules": tax.unchecked(path, business_id, rule_ids),
    }


def post_run(path: Path, business_id: str, user_id: str, run_id: str, paid_from: str, paid_on: date) -> None:
    if paid_from not in PAY_FROM:
        raise PayrollError("Choose where the wages were paid from.")
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("UPDATE payroll_runs SET status = 'posted', paid_from = ?, paid_on = ?, posted_at = ? WHERE id = ? AND business_id = ? AND status = 'draft'",
                            (paid_from, paid_on.isoformat(), db.now(), run_id, business_id)).rowcount:
            if not conn.execute("SELECT 1 FROM payroll_runs WHERE id = ? AND business_id = ?", (run_id, business_id)).fetchone():
                raise NotFound("Payroll not found.")
            raise PayrollError("Only a draft payroll can be posted.")
    ledger.catch_up(path, business_id, user_id)


def void_run(path: Path, business_id: str, user_id: str, run_id: str) -> None:
    with db.connection(path) as conn:
        if not conn.execute("UPDATE payroll_runs SET status = 'void' WHERE id = ? AND business_id = ? AND status != 'void'", (run_id, business_id)).rowcount:
            if not conn.execute("SELECT 1 FROM payroll_runs WHERE id = ? AND business_id = ?", (run_id, business_id)).fetchone():
                raise NotFound("Payroll not found.")
    ledger.catch_up(path, business_id, user_id)


def payslip_pdf(path: Path, business_id: str, run_id: str, line_id: str) -> tuple[bytes, str]:
    from fpdf import FPDF

    from .invoices import FONT_DIR

    run = run_detail(path, business_id, run_id)
    line = next((l for l in run["lines"] if l["id"] == line_id), None)
    if not line:
        raise NotFound("Payslip not found.")
    business = db.one(path, "SELECT name FROM businesses WHERE id = ?", (business_id,)) or {"name": ""}
    employee = db.one(path, "SELECT ssnit_number, tin FROM employees WHERE id = ?", (line["employee_id"],)) or {}
    page = FPDF(format="A5")
    page.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
    page.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    page.add_page()
    width = page.w - page.l_margin - page.r_margin
    page.set_font("DejaVu", "B", 13)
    page.cell(width, 7, business["name"], new_x="LMARGIN", new_y="NEXT")
    page.set_font("DejaVu", "", 9)
    page.cell(width, 5, f"Payslip for {run['month']}" + (" (draft)" if run["status"] == "draft" else ""), new_x="LMARGIN", new_y="NEXT")
    page.ln(2)
    page.set_font("DejaVu", "B", 10)
    page.cell(width, 6, line["name"], new_x="LMARGIN", new_y="NEXT")
    page.set_font("DejaVu", "", 8)
    ids = [f"SSNIT no. {employee.get('ssnit_number')}" if employee.get("ssnit_number") else "", f"TIN {employee.get('tin')}" if employee.get("tin") else ""]
    page.cell(width, 5, " · ".join(i for i in ids if i) or " ", new_x="LMARGIN", new_y="NEXT")
    page.ln(3)
    rows = [("Basic salary", line["basic"]), ("Allowances", line["allowances"]), ("Gross pay", line["gross"]), ("SSNIT (5.5%)", -line["ssnit_employee"]),
            ("Taxable income", line["chargeable"]), ("PAYE", -line["paye"]), ("Net pay", line["net"])]
    for label, value in rows:
        bold = label in ("Gross pay", "Net pay")
        page.set_font("DejaVu", "B" if bold else "", 10 if bold else 9)
        page.cell(width * 0.6, 6, label)
        page.cell(width * 0.4, 6, f"GH₵{value:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")
    page.ln(3)
    page.set_font("DejaVu", "", 7)
    page.multi_cell(width, 4, f"Employer SSNIT (13%): GH₵{line['ssnit_employer']:,.2f}, paid by the employer. Calculated with rules: {', '.join(line['rules'])}.")
    safe = re.sub(r"[^A-Za-z0-9-]+", "-", line["name"]).strip("-")[:40] or "employee"
    return bytes(page.output()), f"payslip-{run['month']}-{safe}.pdf"


def summary(path: Path, business_id: str, first: date, last: date) -> dict[str, Any]:
    """What is owed to GRA and SSNIT for a period: VAT and levies on invoices, withholding tax kept back,
    PAYE and SSNIT from posted payrolls. Each section names the rules used and whether they were checked."""
    a, b = first.isoformat(), last.isoformat()
    invoices = db.many(path, "SELECT taxes, tax_rule FROM invoices WHERE business_id = ? AND voided_at IS NULL AND kind IN ('invoice', 'receipt') AND tax_minor > 0 AND issued_on BETWEEN ? AND ?", (business_id, a, b))
    vat: dict[str, int] = {}
    for row in invoices:
        for name, amount in json.loads(row["taxes"]):
            vat[name] = vat.get(name, 0) + amount
    wht_rows = db.many(path, "SELECT p.wht_kind, SUM(p.wht_minor) AS amount, MIN(p.wht_rule) AS rule FROM debt_payments p JOIN debts d ON d.id = p.debt_id "
                             "WHERE p.business_id = ? AND p.voided_at IS NULL AND d.voided_at IS NULL AND p.wht_minor > 0 AND p.paid_on BETWEEN ? AND ? GROUP BY p.wht_kind", (business_id, a, b))
    pay = db.many(path, "SELECT r.month, SUM(l.paye_minor) AS paye, SUM(l.ssnit_employee_minor) AS emp, SUM(l.ssnit_employer_minor) AS er FROM payroll_runs r JOIN payroll_lines l ON l.run_id = r.id "
                        "WHERE r.business_id = ? AND r.status = 'posted' AND r.paid_on BETWEEN ? AND ? GROUP BY r.month ORDER BY r.month", (business_id, a, b))
    rules = {row["tax_rule"] for row in invoices if row["tax_rule"]} | {row["rule"] for row in wht_rows if row["rule"]}
    rules |= {rule for row in db.many(path, "SELECT l.rules FROM payroll_lines l JOIN payroll_runs r ON r.id = l.run_id WHERE r.business_id = ? AND r.status = 'posted' AND r.paid_on BETWEEN ? AND ?", (business_id, a, b)) for rule in json.loads(row["rules"])}
    return {
        "from": a, "to": b,
        "vat": [{"name": name, "amount": ledger.from_minor(amount)} for name, amount in vat.items()],
        "vat_total": ledger.from_minor(sum(vat.values())),
        "wht": [{"kind": row["wht_kind"], "amount": ledger.from_minor(row["amount"])} for row in wht_rows],
        "payroll": [{"month": row["month"], "paye": ledger.from_minor(row["paye"]), "ssnit_employee": ledger.from_minor(row["emp"]), "ssnit_employer": ledger.from_minor(row["er"])} for row in pay],
        "unchecked_rules": tax.unchecked(path, business_id, rules),
        "note": "Output VAT only: input VAT on purchases is not captured yet. Ferlance does not file with GRA or SSNIT; use these figures to file, and have an accountant check them.",
    }
