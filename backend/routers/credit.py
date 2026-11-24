"""Credit-readiness report (PRD §9, G7).

Members can read the live report. Sharing it outside the business is the owner's decision
(manage_business): creating, listing and revoking share links. A share link opens a frozen
snapshot on a plain server-rendered page (no scripts, everything escaped), and each view is logged.
"""

import html
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .. import config, credit
from ..deps import business_manager, current_user, read_business

router = APIRouter(prefix="/api/businesses/{business_id}/credit", tags=["credit report"])
public = APIRouter(tags=["credit report"])


@router.get("")
def credit_report(business: dict = Depends(read_business)) -> dict:
    return credit.build(config.DB_PATH, business["id"])


@router.get("/shares")
def list_shares(business: dict = Depends(business_manager)) -> list[dict]:
    return credit.shares(config.DB_PATH, business["id"])


class ShareRequest(BaseModel):
    days: Literal[7, 14, 30]
    lender: str = Field(default="", max_length=120)
    consent: bool


@router.post("/shares")
def create_share(payload: ShareRequest, request: Request, business: dict = Depends(business_manager), user: dict = Depends(current_user)) -> dict:
    try:
        shared = credit.share(config.DB_PATH, business["id"], user["id"], payload.days, payload.lender, payload.consent)
    except credit.CreditError as error:
        raise HTTPException(error.status, str(error)) from error
    base = str(request.base_url).rstrip("/")
    return {**shared, "url": f"{base}/r/{shared['token']}"}


@router.post("/shares/{share_id}/revoke")
def revoke_share(share_id: str, business: dict = Depends(business_manager)) -> dict:
    try:
        credit.revoke(config.DB_PATH, business["id"], share_id)
    except credit.CreditError as error:
        raise HTTPException(error.status, str(error)) from error
    return {"id": share_id, "revoked": True}


_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
    "Cache-Control": "no-store",
}


def _money(currency: str, value: float | None) -> str:
    if value is None:
        return "—"
    return f"{'GH₵' if currency == 'GHS' else currency + ' '}{value:,.2f}"


@public.get("/r/{token}", include_in_schema=False)
def shared_report(token: str, request: Request) -> HTMLResponse:
    """The lender's view: a frozen snapshot. Plain HTML, printable, every value escaped."""
    if len(token) > 100:
        raise HTTPException(404, "Not found.")
    try:
        report = credit.open_shared(config.DB_PATH, token, request.headers.get("user-agent", ""))
    except credit.CreditError as error:
        page = f"<!doctype html><meta charset=utf-8><title>Link not available</title><p style='font-family:sans-serif;padding:24px'>{html.escape(str(error))}</p>"
        return HTMLResponse(page, status_code=404, headers=_HEADERS)
    e = html.escape
    cur = report["currency"]
    facts = report["facts"]
    rows = "".join(
        f"<tr><td>{e(m['month'])}</td><td class=n>{e(_money(cur, m['sales']))}</td><td class=n>{e(_money(cur, m['profit']))}</td></tr>" for m in report["monthly"]
    )
    parts = "".join(
        f"<tr><td>{e(p['name'])}</td><td class=n>{p['points']} / {p['out_of']}</td><td>{e(p['why'])}</td></tr>" for p in report["parts"]
    )
    evidence = facts["evidence"]
    page = f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content="noindex,nofollow"><title>{e(report['business'])}: business summary</title>
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;background:#fff;color:#111;line-height:1.5}}
main{{max-width:760px;margin:0 auto;padding:20px 16px}} h1{{font-size:1.4rem;margin:0 0 4px}} h2{{font-size:1.05rem;margin:24px 0 8px}}
.muted{{color:#555;font-size:.9rem}} table{{width:100%;border-collapse:collapse;font-size:.92rem}} td,th{{padding:6px 4px;border-bottom:1px solid #e5e5e5;text-align:left;vertical-align:top}}
.n{{text-align:right;white-space:nowrap}} .score{{font-size:2rem;font-weight:700}} .box{{border:1px solid #ddd;border-radius:10px;padding:12px 14px;margin:12px 0}}
.code{{font-family:ui-monospace,monospace;font-weight:600}}
@media (prefers-color-scheme: dark){{body{{background:#0f0f11;color:#f1f1f3}} .muted{{color:#babac2}} td,th{{border-color:#2a2a2f}} .box{{border-color:#34343a}}}}
@media print{{body{{background:#fff;color:#000}}}}
</style></head><body><main>
<p class=muted>Business summary shared through Ferlance{(' with ' + e(report['lender'])) if report['lender'] else ''}</p>
<h1>{e(report['business'])}</h1>
<p class=muted>Records from {e(report['from'])} to {e(report['as_of'])}. Verification code <span class=code>{e(report['code'])}</span>. Link valid until {e(report['expires_at'][:10])}.</p>
<div class=box><div class=score>{report['score']} / 100</div><div class=muted>Readiness score: how complete and well-evidenced these records are. Not a credit decision.</div></div>
<h2>Key figures (last 12 months)</h2>
<table>
<tr><td>Sales</td><td class=n>{e(_money(cur, facts['sales']))}</td></tr>
<tr><td>Net profit</td><td class=n>{e(_money(cur, facts['net_profit']))}{(' (' + str(facts['net_margin_pct']) + '%)') if facts['net_margin_pct'] is not None else ''}</td></tr>
<tr><td>Months with sales</td><td class=n>{facts['months_with_sales']} of 12</td></tr>
<tr><td>Sales matched to a MoMo or bank statement</td><td class=n>{evidence['statement_matched_pct']}%</td></tr>
<tr><td>Sales from MoMo messages</td><td class=n>{evidence['momo_sms_pct']}%</td></tr>
<tr><td>Owed by customers / over 60 days late</td><td class=n>{e(_money(cur, facts['receivables']['owed']))} / {facts['receivables']['late_share_pct']}%</td></tr>
<tr><td>Stock turnover</td><td class=n>{facts['stock_turnover'] if facts['stock_turnover'] is not None else '—'}</td></tr>
</table>
<h2>How the score is made</h2><table>{parts}</table>
<h2>Month by month</h2><table><tr><th>Month</th><th class=n>Sales</th><th class=n>Profit</th></tr>{rows}</table>
<p class=muted style="margin-top:24px">{e(report['disclaimer'])} Figures typed in by the business are self-reported. Shared on {e(report['shared_at'][:10])}.</p>
</main></body></html>"""
    return HTMLResponse(page, headers=_HEADERS)
