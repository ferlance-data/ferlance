"""Invoices, quotes and receipts (PRD §9, G3): WhatsApp-ready PDFs in cedis, with gapless numbers.

How each kind reaches the books:
- **Quote** (QUO-0001): nothing is posted. It can be converted into an invoice later.
- **Invoice** (INV-0001): a debt-book entry for the customer (Receivables / Sales), with the due
  date. Payments are recorded against that debt, so status (part-paid, paid, overdue), ageing,
  reminders and the ledger all come from the debt book.
- **Receipt** (RCT-0001): a sale paid on the spot, recorded as a debt and its full payment in
  one step (Cash, MoMo or Bank / Sales).
Invoice and receipt lines linked to a stock product with a quantity take that stock out ('sale'
movements tagged ``invoice:<id>``); stock can't go below zero. Voiding keeps the number (no gaps),
voids the debt and its payments, and puts the stock back with opposite movements.

Numbers are per business and per kind, taken inside the same write transaction, and documents
are never deleted, so the sequence has no gaps.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import db, debts, ledger, tax
from .inventory import _product, _record_movement, _stock

PREFIX = {"invoice": "INV", "quote": "QUO", "receipt": "RCT"}
TITLE = {"invoice": "Invoice", "quote": "Quote", "receipt": "Receipt"}
FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"


class InvoiceError(ValueError):
    status = 400


class NotFound(InvoiceError):
    status = 404


class StockShort(InvoiceError):
    status = 409

    def __init__(self, shortages: list[dict[str, Any]]):
        super().__init__("Not enough stock for: " + ", ".join(f"{s['name']} (have {s['on_hand']:g}, need {s['needed']:g})" for s in shortages))
        self.shortages = shortages


def _line_total(quantity: float, unit_price: float) -> int:
    return ledger.to_minor(Decimal(str(quantity)) * Decimal(str(unit_price)))


def _clean_lines(conn, business_id: str, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not lines:
        raise InvoiceError("Add at least one line.")
    clean = []
    for index, line in enumerate(lines):
        quantity, price = float(line["quantity"]), float(line["unit_price"])
        if quantity <= 0 or price < 0:
            raise InvoiceError("Each line needs a quantity above zero and a price that is not negative.")
        product_id = line.get("product_id") or None
        description = " ".join(str(line.get("description") or "").split())
        if product_id:
            product = _product(conn, product_id, business_id)  # raises if it is not this business's product
            description = description or product["name"]
        if not description:
            raise InvoiceError("Each line needs a description or a product.")
        clean.append({"position": index, "product_id": product_id, "description": description[:200], "quantity": quantity,
                      "unit_price_minor": ledger.to_minor(price), "line_total_minor": _line_total(quantity, price)})
    return clean


def _next_seq(conn, business_id: str, kind: str) -> int:
    row = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS seq FROM invoices WHERE business_id = ? AND kind = ?", (business_id, kind)).fetchone()
    return int(row["seq"])


def _take_stock(conn, business_id: str, invoice_id: str, number: str, lines: list[dict[str, Any]], user_id: str) -> None:
    needed: dict[str, float] = {}
    for line in lines:
        if line["product_id"]:
            needed[line["product_id"]] = needed.get(line["product_id"], 0) + line["quantity"]
    shortages = []
    for product_id, quantity in needed.items():
        on_hand = _stock(conn, product_id)
        if on_hand - quantity < 0:
            shortages.append({"product_id": product_id, "name": _product(conn, product_id, business_id)["name"], "on_hand": on_hand, "needed": quantity})
    if shortages:
        raise StockShort(shortages)
    for product_id, quantity in needed.items():
        _record_movement(conn, business_id, product_id, user_id, "sale", -quantity, f"Sold on {number}", f"invoice:{invoice_id}")


def create(path: Path, business_id: str, user_id: str, *, kind: str, customer_name: str, phone: str, issued_on: date, due_on: date | None,
           lines: list[dict[str, Any]], notes: str = "", paid_by: str | None = None, converted_from: str | None = None, charge_vat: bool = False) -> dict[str, Any]:
    if kind not in PREFIX:
        raise InvoiceError("Choose invoice, quote or receipt.")
    name = " ".join(customer_name.split())
    if not name:
        raise InvoiceError("Enter the customer's name.")
    if issued_on > date.today() + timedelta(days=1):
        raise InvoiceError("The date cannot be in the future.")
    if due_on and due_on < issued_on:
        raise InvoiceError("The due date cannot be before the issue date.")
    if kind == "receipt" and paid_by not in debts.METHODS:
        raise InvoiceError("Choose how the customer paid.")
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        clean = _clean_lines(conn, business_id, lines)
        net = sum(line["line_total_minor"] for line in clean)
        if net <= 0:
            raise InvoiceError("The total must be more than zero.")
        # VAT and levies by the rule in force on the issue date (backend/tax.py); lines are before tax.
        taxes = tax.vat(net, issued_on) if charge_vat else None
        tax_minor = taxes.total if taxes else 0
        total = net + tax_minor
        currency = ledger._currency(conn, business_id)
        seq = _next_seq(conn, business_id, kind)
        number = f"{PREFIX[kind]}-{seq:04d}"
        invoice_id = str(uuid.uuid4())
        party_id = debts._party(conn, business_id, "customer", name, phone.strip())
        debt_id = None
        if kind in ("invoice", "receipt"):
            debt_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO debts (id, business_id, party_id, direction, basis, description, amount_minor, currency, issued_on, due_on, created_by, created_at, tax_minor) "
                "VALUES (?, ?, ?, 'owed_to_us', 'new_sale', ?, ?, ?, ?, ?, ?, ?, ?)",
                (debt_id, business_id, party_id, number, total, currency, issued_on.isoformat(), due_on.isoformat() if kind == "invoice" and due_on else None, user_id, db.now(), tax_minor),
            )
            if kind == "receipt":
                conn.execute(
                    "INSERT INTO debt_payments (id, debt_id, business_id, amount_minor, paid_on, method, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), debt_id, business_id, total, issued_on.isoformat(), paid_by, user_id, db.now()),
                )
        conn.execute(
            "INSERT INTO invoices (id, business_id, kind, seq, number, party_id, customer_name, phone, issued_on, due_on, currency, total_minor, notes, debt_id, converted_from, created_by, created_at, tax_minor, taxes, tax_rule) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (invoice_id, business_id, kind, seq, number, party_id, name, phone.strip(), issued_on.isoformat(), due_on.isoformat() if due_on else None,
             currency, total, notes.strip()[:500], debt_id, converted_from, user_id, db.now(), tax_minor,
             json.dumps(taxes.components if taxes else []), taxes.rule_id if taxes else None),
        )
        for line in clean:
            conn.execute(
                "INSERT INTO invoice_lines (id, invoice_id, position, product_id, description, quantity, unit_price_minor, line_total_minor) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), invoice_id, line["position"], line["product_id"], line["description"], line["quantity"], line["unit_price_minor"], line["line_total_minor"]),
            )
        if kind != "quote":
            _take_stock(conn, business_id, invoice_id, number, clean, user_id)
    ledger.catch_up(path, business_id, user_id)
    return {"id": invoice_id, "number": number}


def convert(path: Path, business_id: str, user_id: str, quote_id: str, issued_on: date, due_on: date | None) -> dict[str, Any]:
    quote = get(path, business_id, quote_id)
    if quote["kind"] != "quote":
        raise InvoiceError("Only a quote can be turned into an invoice.")
    if quote["voided_at"]:
        raise InvoiceError("This quote was voided.")
    if db.one(path, "SELECT 1 FROM invoices WHERE converted_from = ? AND voided_at IS NULL", (quote_id,)):
        raise InvoiceError("This quote is already an invoice.")
    lines = [{"product_id": l["product_id"], "description": l["description"], "quantity": l["quantity"], "unit_price": l["unit_price"]} for l in quote["lines"]]
    return create(path, business_id, user_id, kind="invoice", customer_name=quote["customer_name"], phone=quote["phone"], issued_on=issued_on,
                  due_on=due_on, lines=lines, notes=quote["notes"], converted_from=quote_id, charge_vat=bool(quote["tax"]))


def void(path: Path, business_id: str, user_id: str, invoice_id: str) -> None:
    now = db.now()
    with db.connection(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM invoices WHERE id = ? AND business_id = ?", (invoice_id, business_id)).fetchone()
        if not row:
            raise NotFound("Not found.")
        if row["voided_at"]:
            return
        conn.execute("UPDATE invoices SET voided_at = ?, voided_by = ? WHERE id = ?", (now, user_id, invoice_id))
        if row["debt_id"]:
            conn.execute("UPDATE debts SET voided_at = ?, voided_by = ? WHERE id = ? AND voided_at IS NULL", (now, user_id, row["debt_id"]))
            conn.execute("UPDATE debt_payments SET voided_at = ?, voided_by = ? WHERE debt_id = ? AND voided_at IS NULL", (now, user_id, row["debt_id"]))
        moved = conn.execute(
            "SELECT product_id, SUM(quantity_delta) AS delta FROM inventory_movements WHERE business_id = ? AND source IN (?, ?) GROUP BY product_id",
            (business_id, f"invoice:{invoice_id}", f"invoice-reversal:{invoice_id}"),
        ).fetchall()
        for item in moved:
            if item["delta"]:
                _record_movement(conn, business_id, item["product_id"], user_id, "adjustment", -item["delta"], f"Returned: {row['number']} voided", f"invoice-reversal:{invoice_id}")
    ledger.catch_up(path, business_id, user_id)


def _status(row: dict[str, Any], paid: int, today: date) -> str:
    if row["voided_at"]:
        return "void"
    if row["kind"] == "quote":
        return "converted" if row.get("converted") else "quote"
    balance = row["total_minor"] - paid
    if balance <= 0:
        return "paid"
    if row["due_on"] and row["due_on"] < today.isoformat():
        return "overdue"
    return "part_paid" if paid else "sent"


_PAID = f"COALESCE((SELECT SUM(x.amount_minor) FROM debt_payments x WHERE x.debt_id = i.debt_id AND {ledger.STANDING_PAYMENT}), 0)"


def listing(path: Path, business_id: str, kind: str | None = None, today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    where, params = "i.business_id = ?", [business_id]
    if kind:
        where += " AND i.kind = ?"
        params.append(kind)
    rows = db.many(
        path,
        f"SELECT i.*, {_PAID} AS paid_minor, EXISTS(SELECT 1 FROM invoices c WHERE c.converted_from = i.id AND c.voided_at IS NULL) AS converted "
        f"FROM invoices i WHERE {where} ORDER BY i.issued_on DESC, i.created_at DESC LIMIT 500",
        tuple(params),
    )
    return [_present(row, today) for row in rows]


def _present(row: dict[str, Any], today: date) -> dict[str, Any]:
    paid = row.get("paid_minor") or 0
    return {
        "id": row["id"], "kind": row["kind"], "number": row["number"], "customer_name": row["customer_name"], "phone": row["phone"],
        "issued_on": row["issued_on"], "due_on": row["due_on"], "currency": row["currency"], "notes": row["notes"],
        "total": ledger.from_minor(row["total_minor"]), "paid": ledger.from_minor(paid),
        "net": ledger.from_minor(row["total_minor"] - (row.get("tax_minor") or 0)), "tax": ledger.from_minor(row.get("tax_minor") or 0),
        "taxes": [{"name": name, "amount": ledger.from_minor(amount)} for name, amount in json.loads(row.get("taxes") or "[]")],
        "tax_rule": row.get("tax_rule"),
        "balance": 0 if row["voided_at"] or row["kind"] == "quote" else ledger.from_minor(row["total_minor"] - paid),
        "status": _status(row, paid, today), "debt_id": row["debt_id"], "voided": bool(row["voided_at"]),
    }


def get(path: Path, business_id: str, invoice_id: str, today: date | None = None) -> dict[str, Any]:
    row = db.one(
        path,
        f"SELECT i.*, {_PAID} AS paid_minor, EXISTS(SELECT 1 FROM invoices c WHERE c.converted_from = i.id AND c.voided_at IS NULL) AS converted "
        "FROM invoices i WHERE i.id = ? AND i.business_id = ?",
        (invoice_id, business_id),
    )
    if not row:
        raise NotFound("Not found.")
    lines = db.many(path, "SELECT product_id, description, quantity, unit_price_minor, line_total_minor FROM invoice_lines WHERE invoice_id = ? ORDER BY position", (invoice_id,))
    return {
        **_present(row, today or date.today()),
        "voided_at": row["voided_at"],
        "lines": [{"product_id": l["product_id"], "description": l["description"], "quantity": l["quantity"],
                   "unit_price": ledger.from_minor(l["unit_price_minor"]), "total": ledger.from_minor(l["line_total_minor"])} for l in lines],
    }


def settings(path: Path, business_id: str) -> dict[str, Any]:
    row = db.one(path, "SELECT tin, address, phone, footer FROM invoice_settings WHERE business_id = ?", (business_id,))
    pay = db.one(path, "SELECT pay_to FROM debt_settings WHERE business_id = ?", (business_id,))
    return {**(row or {"tin": "", "address": "", "phone": "", "footer": ""}), "pay_to": pay["pay_to"] if pay else ""}


def save_settings(path: Path, business_id: str, tin: str, address: str, phone: str, footer: str) -> None:
    db.insert(
        path,
        "INSERT INTO invoice_settings (business_id, tin, address, phone, footer, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(business_id) DO UPDATE SET tin = excluded.tin, address = excluded.address, phone = excluded.phone, footer = excluded.footer, updated_at = excluded.updated_at",
        (business_id, tin.strip(), address.strip(), phone.strip(), footer.strip(), db.now()),
    )


# ---------------------------------------------------------------- PDF


def _money(currency: str, amount: float) -> str:
    symbol = "GH₵" if currency == "GHS" else f"{currency} "
    return f"{symbol}{amount:,.2f}"


def pdf(path: Path, business_id: str, invoice_id: str) -> tuple[bytes, str]:
    """A one-page A4 PDF (more pages if there are many lines), small enough to share on WhatsApp."""
    from fpdf import FPDF  # imported only when a PDF is made

    doc = get(path, business_id, invoice_id)
    business = db.one(path, "SELECT name FROM businesses WHERE id = ?", (business_id,)) or {"name": ""}
    extra = settings(path, business_id)
    page = FPDF(format="A4")
    page.set_auto_page_break(auto=True, margin=18)
    page.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
    page.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    page.set_title(f"{TITLE[doc['kind']]} {doc['number']}")
    page.set_author(business["name"])
    page.set_creator("Ferlance")
    page.add_page()
    width = page.w - page.l_margin - page.r_margin

    page.set_font("DejaVu", "B", 16)
    page.cell(width * 0.6, 8, business["name"])
    page.set_font("DejaVu", "B", 16)
    heading = ("TAX " + TITLE[doc["kind"]].upper()) if doc["tax"] and doc["kind"] == "invoice" else TITLE[doc["kind"]].upper()
    page.cell(width * 0.4, 8, heading, align="R", new_x="LMARGIN", new_y="NEXT")
    page.set_font("DejaVu", "", 9)
    details = [line for line in (extra["address"], extra["phone"], f"TIN: {extra['tin']}" if extra["tin"] else "") if line]
    top = page.get_y()
    page.multi_cell(width * 0.6, 4.5, "\n".join(details) or " ")
    left_end = page.get_y()
    page.set_xy(page.l_margin + width * 0.6, top)
    meta = [f"No. {doc['number']}", f"Date: {doc['issued_on']}"]
    if doc["due_on"] and doc["kind"] == "invoice":
        meta.append(f"Due: {doc['due_on']}")
    if doc["kind"] == "quote" and doc["due_on"]:
        meta.append(f"Valid until: {doc['due_on']}")
    page.multi_cell(width * 0.4, 4.5, "\n".join(meta), align="R")
    page.set_y(max(left_end, page.get_y()) + 6)

    page.set_font("DejaVu", "B", 10)
    page.cell(width, 5, "Bill to" if doc["kind"] != "receipt" else "Received from", new_x="LMARGIN", new_y="NEXT")
    page.set_font("DejaVu", "", 10)
    page.multi_cell(width, 5, doc["customer_name"] + (f"\n{doc['phone']}" if doc["phone"] else ""))
    page.ln(4)

    columns = (("Item", 0.5, "L"), ("Qty", 0.12, "R"), ("Price", 0.18, "R"), ("Amount", 0.2, "R"))
    page.set_font("DejaVu", "B", 9)
    page.set_fill_color(240, 240, 240)
    for label, share, align in columns:
        page.cell(width * share, 7, label, align=align, fill=True)
    page.ln(7)
    page.set_font("DejaVu", "", 9)
    for line in doc["lines"]:
        values = (line["description"], f"{line['quantity']:g}", _money(doc["currency"], line["unit_price"]), _money(doc["currency"], line["total"]))
        y = page.get_y()
        page.multi_cell(width * columns[0][1], 6, values[0], new_x="RIGHT", new_y="TOP")
        row_bottom = max(page.get_y(), y + 6)
        x = page.l_margin + width * columns[0][1]
        for (label, share, align), value in zip(columns[1:], values[1:]):
            page.set_xy(x, y)
            page.cell(width * share, 6, value, align=align)
            x += width * share
        page.set_y(row_bottom + 1)
        page.set_draw_color(225, 225, 225)
        page.line(page.l_margin, page.get_y(), page.l_margin + width, page.get_y())
    page.ln(3)

    def total_row(label: str, value: str, bold: bool = False) -> None:
        page.set_font("DejaVu", "B" if bold else "", 10 if bold else 9)
        page.cell(width * 0.8, 6, label, align="R")
        page.cell(width * 0.2, 6, value, align="R", new_x="LMARGIN", new_y="NEXT")

    if doc["tax"]:
        total_row("Subtotal (before tax)", _money(doc["currency"], doc["net"]))
        for item in doc["taxes"]:
            total_row(item["name"], _money(doc["currency"], item["amount"]))
    total_row("Total", _money(doc["currency"], doc["total"]), bold=True)
    if doc["kind"] == "invoice" and doc["paid"]:
        total_row("Paid", _money(doc["currency"], doc["paid"]))
        total_row("Balance due", _money(doc["currency"], doc["balance"]), bold=True)
    page.ln(4)
    stamp = {"paid": "PAID", "void": "VOID"}.get(doc["status"])
    if stamp:
        page.set_font("DejaVu", "B", 18)
        page.set_text_color(30, 120, 70) if stamp == "PAID" else page.set_text_color(190, 40, 40)
        page.cell(width, 10, stamp, align="C", new_x="LMARGIN", new_y="NEXT")
        page.set_text_color(0, 0, 0)
    page.set_font("DejaVu", "", 9)
    if doc["kind"] != "receipt" and extra["pay_to"]:
        page.multi_cell(width, 5, f"Pay to: {extra['pay_to']}")
    if doc["notes"]:
        page.ln(2)
        page.multi_cell(width, 5, doc["notes"])
    if extra["footer"]:
        page.ln(2)
        page.multi_cell(width, 5, extra["footer"])
    page.ln(4)
    page.set_font("DejaVu", "", 7)
    page.set_text_color(120, 120, 120)
    page.cell(width, 4, "Made with Ferlance", align="C")
    filename = f"{doc['number']}.pdf"
    return bytes(page.output()), filename
