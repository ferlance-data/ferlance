"""Ghana tax and payroll rules (PRD §9, G6): data, not code.

Every rate lives in ``RULES`` with the dates it applies, where it came from, and notes. Every tax
figure Ferlance calculates names the rule it used. Rates were taken from the GRA's and SSNIT's
published pages (and noted secondary sources) in November 2026. **They have not been checked by
an accountant**: each business sees "needs accountant check" until its owner or accountant
confirms each rule in the app (``tax_rule_checks``). When a rate changes, add a new rule with a
new ``effective_from`` and close the old one; never edit a rule that figures were calculated with.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from . import db

GRA_VAT = {"title": "GRA: Value Added Tax", "url": "https://gra.gov.gh/domestic-tax/tax-types/vat/"}
GRA_VAT_NOTICE = {"title": "GRA: Notice to all VAT registered taxpayers (VAT Act 2025, Act 1151)", "url": "https://gra.gov.gh/news/portfolio/notice-to-all-vat-registered-taxpayers/"}
GRA_PAYE = {"title": "GRA: Pay As You Earn (PAYE), Year of Assessment 2026", "url": "https://gra.gov.gh/domestic-tax/tax-types/paye/"}
GRA_WHT = {"title": "GRA: Withholding Tax", "url": "https://gra.gov.gh/domestic-tax/tax-types/withholding-tax/"}
SSNIT = {"title": "SSNIT (rates); 2026 ceiling per Sage and EY payroll notices", "url": "https://www.ssnit.org.gh/"}

RULES: list[dict[str, Any]] = [
    {
        "id": "vat-2023", "key": "vat", "from": "2023-01-01", "to": "2025-12-31",
        "label": "VAT 15% on the price plus NHIL 2.5%, GETFund 2.5% and COVID-19 levy 1% (about 21.9% in total)",
        "data": {"scheme": "compound", "levies": [["NHIL", "0.025"], ["GETFund levy", "0.025"], ["COVID-19 levy", "0.01"]], "vat": "0.15"},
        "sources": [GRA_VAT], "notes": "The regime before the VAT Act 2025. Only used for invoices dated before 2026.",
    },
    {
        "id": "vat-2026", "key": "vat", "from": "2026-01-01", "to": None,
        "label": "VAT 15%, NHIL 2.5% and GETFund levy 2.5%, all on the same price (20% in total); COVID-19 levy repealed",
        "data": {"scheme": "flat", "components": [["VAT", "0.15"], ["NHIL", "0.025"], ["GETFund levy", "0.025"]]},
        "sources": [GRA_VAT, GRA_VAT_NOTICE],
        "notes": "VAT Act 2025 (Act 1151), effective 1 January 2026. Registration threshold for goods: GH₵750,000 a year. The VAT Flat Rate Scheme was abolished.",
    },
    {
        "id": "paye-2024", "key": "paye_monthly", "from": "2024-01-01", "to": "2026-08-31",
        "label": "PAYE for residents, monthly: first GH₵490 free, then 5%, 10%, 17.5%, 25%, 30%, 35%",
        "data": {"bands": [["490", "0"], ["110", "0.05"], ["130", "0.10"], ["3166.67", "0.175"], ["16000", "0.25"], ["30520", "0.30"], [None, "0.35"]]},
        "sources": [GRA_PAYE], "notes": "The bands before the Income Tax (Amendment) Act 2026. Band widths above GH₵730 are from secondary sources: check before relying on them.",
    },
    {
        "id": "paye-2026-09", "key": "paye_monthly", "from": "2026-09-01", "to": None,
        "label": "PAYE for residents, monthly: first GH₵588 free, then 5%, 10%, 17.5%, 25%, 30%, and 35% above GH₵50,000",
        "data": {"bands": [["588", "0"], ["80", "0.05"], ["100", "0.10"], ["2900", "0.175"], ["16000", "0.25"], ["30332", "0.30"], [None, "0.35"]]},
        "sources": [GRA_PAYE], "notes": "Income Tax (Amendment) Act 2026 (Act 1178), from 1 September 2026. Non-residents pay a flat 25% (not handled here).",
    },
    {
        "id": "ssnit-2026", "key": "ssnit", "from": "2026-01-01", "to": None,
        "label": "SSNIT: employee 5.5% and employer 13% of basic salary, on at most GH₵69,000 a month",
        "data": {"employee": "0.055", "employer": "0.13", "ceiling": "69000"},
        "sources": [SSNIT],
        "notes": "The employee's 5.5% is deducted before PAYE. Sources differ on how the employer's 13% splits between Tier 1 and Tier 2, so Ferlance books the total to one 'SSNIT payable' account. Check the split with SSNIT or your accountant.",
    },
    {
        "id": "wht-2026", "key": "wht", "from": "2026-01-01", "to": None,
        "label": "Withholding tax (residents): goods 3%, works 5%, services 7.5%; non-residents 20%",
        "data": {"goods": "0.03", "works": "0.05", "services": "0.075", "non_resident": "0.20", "threshold": "2000"},
        "sources": [GRA_WHT],
        "notes": "For goods, works and services from a business, it applies above GH₵2,000 a year from that supplier. Services from an individual may have no threshold: check. The tax withheld is a credit for the supplier, not an extra tax.",
    },
]


class TaxError(ValueError):
    status = 400


def to_minor(value: Any) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _part(minor: int, rate: str) -> int:
    return int((Decimal(minor) * Decimal(rate)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def rule_for(key: str, day: date | str) -> dict[str, Any]:
    day = day if isinstance(day, str) else day.isoformat()
    for rule in RULES:
        if rule["key"] == key and rule["from"] <= day and (rule["to"] is None or day <= rule["to"]):
            return rule
    raise TaxError(f"No {key.replace('_', ' ')} rule covers {day}.")


@dataclass
class VatResult:
    rule_id: str
    components: list[tuple[str, int]]  # name, pesewas

    @property
    def total(self) -> int:
        return sum(amount for _, amount in self.components)


def vat(net_minor: int, day: date | str) -> VatResult:
    """VAT and levies on a net (tax-exclusive) amount, by the rule in force that day."""
    rule = rule_for("vat", day)
    data = rule["data"]
    if data["scheme"] == "flat":
        return VatResult(rule["id"], [(name, _part(net_minor, rate)) for name, rate in data["components"]])
    levies = [(name, _part(net_minor, rate)) for name, rate in data["levies"]]
    base = net_minor + sum(amount for _, amount in levies)
    return VatResult(rule["id"], levies + [("VAT", _part(base, data["vat"]))])


def paye(chargeable_minor: int, day: date | str) -> tuple[int, str]:
    """Monthly PAYE for a resident on chargeable income (gross less the employee's SSNIT)."""
    rule = rule_for("paye_monthly", day)
    left, tax = max(chargeable_minor, 0), Decimal(0)
    for width, rate in rule["data"]["bands"]:
        band = left if width is None else min(left, to_minor(width))
        tax += Decimal(band) * Decimal(rate)
        left -= band
        if left <= 0:
            break
    return int(tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP)), rule["id"]


def ssnit(basic_minor: int, day: date | str) -> tuple[int, int, str]:
    rule = rule_for("ssnit", day)
    base = min(max(basic_minor, 0), to_minor(rule["data"]["ceiling"]))
    return _part(base, rule["data"]["employee"]), _part(base, rule["data"]["employer"]), rule["id"]


WHT_KINDS = ("goods", "works", "services", "non_resident")


def wht(amount_minor: int, kind: str, day: date | str) -> tuple[int, str]:
    if kind not in WHT_KINDS:
        raise TaxError("Choose goods, works, services or non-resident.")
    rule = rule_for("wht", day)
    return _part(amount_minor, rule["data"][kind]), rule["id"]


# ---------------------------------------------------------------- per-business checks


def rules_for_business(path: Path, business_id: str) -> list[dict[str, Any]]:
    checks = {row["rule_id"]: row for row in db.many(
        path, "SELECT c.rule_id, c.checked_at, u.email AS checked_by FROM tax_rule_checks c LEFT JOIN users u ON u.id = c.checked_by WHERE c.business_id = ?", (business_id,)
    )}
    return [{**{k: rule[k] for k in ("id", "key", "from", "to", "label", "sources", "notes")}, "checked": checks.get(rule["id"])} for rule in RULES]


def check_rule(path: Path, business_id: str, user_id: str, rule_id: str, checked: bool) -> None:
    if rule_id not in {rule["id"] for rule in RULES}:
        raise TaxError("Unknown rule.")
    if checked:
        db.insert(path, "INSERT OR REPLACE INTO tax_rule_checks (business_id, rule_id, checked_by, checked_at) VALUES (?, ?, ?, ?)", (business_id, rule_id, user_id, db.now()))
    else:
        db.insert(path, "DELETE FROM tax_rule_checks WHERE business_id = ? AND rule_id = ?", (business_id, rule_id))


def unchecked(path: Path, business_id: str, rule_ids: set[str]) -> list[str]:
    done = {row["rule_id"] for row in db.many(path, "SELECT rule_id FROM tax_rule_checks WHERE business_id = ?", (business_id,))}
    return sorted(rule_ids - done)
