"""Deterministic reporting: metrics, period comparison, insights and advice, fixed questions, AI explanations."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from .. import advisor, config, db, inventory, llm, news_context
from ..analytics import analyze, compare
from ..deps import ai_user, refund_ai_call, spend_ai_call, date_range, DateRange, read_business, resolve_scope, Scope, scope
from ..insights import QUESTION_NAMES, answer_question, generate_insights

router = APIRouter(prefix="/api/businesses/{business_id}", tags=["analytics"])


@router.get("/analytics")
def business_analytics(dates: DateRange = Depends(date_range), data: Scope = Depends(scope)) -> dict:
    try:
        metrics = analyze(data.records, dates.start, dates.end)
    except ValueError as error:
        raise HTTPException(400, str(error))
    metrics["comparison"] = compare(data.records, dates.start, dates.end)
    metrics["dataset"] = data.descriptor
    return metrics


def _advice(business_id: str, dates: DateRange, data: Scope) -> dict:
    stock = inventory.list_products(config.DB_PATH, business_id)["items"]
    # Sales names linked to a stock product (Inventory → Link sales) count as that product.
    by_id = {item["id"]: item for item in stock}
    rows = db.many(config.DB_PATH, "SELECT sales_name, product_id FROM product_links WHERE business_id = ? AND product_id IS NOT NULL", (business_id,))
    stock += [{**by_id[row["product_id"]], "name": row["sales_name"], "linked": True} for row in rows if row["product_id"] in by_id]
    return advisor.build(data.records, dates.start, dates.end, stock)


@router.get("/insights")
def business_insights(
    dates: DateRange = Depends(date_range),
    data: Scope = Depends(scope),
    business: dict = Depends(read_business),
) -> dict:
    result = generate_insights(data.records, dates.start, dates.end)
    result["dataset"] = data.descriptor
    result["advice"] = {**_advice(business["id"], dates, data), "ai_available": llm.ai_available()}
    return result


# News is only worth a slow outside lookup for items about one product that went wrong.
_NEWS_KINDS = {"decline", "stopped", "loss", "margin"}


# Old explanations are dropped after this long; they are cheap to regenerate if needed.
EXPLANATION_RETENTION_DAYS = 90


@router.post("/insights/{insight_id}/explain")
def explain_insight(
    insight_id: str,
    dates: DateRange = Depends(date_range),
    data: Scope = Depends(scope),
    business: dict = Depends(ai_user),
) -> dict:
    """AI explanation of one advice item. The item is rebuilt on the server from the scope, never taken from the client."""
    advice = _advice(business["id"], dates, data)
    item = next((entry for entry in advice["items"] if entry["id"] == insight_id), None)
    if item is None:
        raise HTTPException(404, "That suggestion no longer applies to this data. Refresh the page.")
    if not llm.ai_available():
        raise HTTPException(503, "AI explanations are not set up on this server. The reasons and actions above are calculated without AI.")
    # Same finding with the same evidence → same explanation, so taps never pay twice.
    fingerprint = json.dumps({key: item[key] for key in ("title", "summary", "evidence", "reasons", "actions")}, sort_keys=True, default=str)
    cache_key = hashlib.sha256(f"{advice['period']}|{advice['comparison_period']}|{fingerprint}".encode()).hexdigest()
    cached = db.one(config.DB_PATH, "SELECT text, created_at FROM insight_explanations WHERE business_id = ? AND cache_key = ?", (business["id"], cache_key))
    if cached:
        stored = json.loads(cached["text"])
        return {"id": insight_id, "explanation": stored["text"], "news": stored["news"], "cached": True, "created_at": cached["created_at"]}

    spend_ai_call(business["id"])
    news = []
    if item["kind"] in _NEWS_KINDS and item.get("product"):
        news = news_context.search(item["product"], dates.start, dates.end)
    try:
        text = llm.explain(advisor.EXPLAIN_SYSTEM, advisor.explain_prompt(item, advice, news))
    except RuntimeError as error:
        refund_ai_call(business["id"])
        raise HTTPException(503, str(error))
    created = db.now()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=EXPLANATION_RETENTION_DAYS)).isoformat()
    db.insert(config.DB_PATH, "DELETE FROM insight_explanations WHERE business_id = ? AND created_at < ?", (business["id"], cutoff))
    db.insert(
        config.DB_PATH,
        "INSERT OR REPLACE INTO insight_explanations (business_id, cache_key, text, created_at) VALUES (?, ?, ?, ?)",
        (business["id"], cache_key, json.dumps({"text": text, "news": news}), created),
    )
    return {"id": insight_id, "explanation": text, "news": news, "cached": False, "created_at": created}


@router.get("/questions")
def list_questions(business: dict = Depends(read_business)) -> list[dict]:
    return [{"id": key, "label": label} for key, label in QUESTION_NAMES.items()]


@router.get("/questions/{question}")
def business_question(
    question: str,
    dataset_id: str | None = None,
    dates: DateRange = Depends(date_range),
    business: dict = Depends(read_business),
) -> dict:
    if question not in QUESTION_NAMES:
        raise HTTPException(404, "That business question is not available.")
    data = resolve_scope(business["id"], dataset_id)
    return answer_question(question, data.records, dates.start, dates.end)
