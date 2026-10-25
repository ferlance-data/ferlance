"""Deterministic reporting: metrics, period comparison, insights, fixed questions, and web research."""

from fastapi import APIRouter, Depends, HTTPException

from .. import config, market_research
from ..analytics import analyze, compare
from ..deps import DateRange, Scope, date_range, owned_business, resolve_scope, scope
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


@router.get("/insights")
def business_insights(dates: DateRange = Depends(date_range), data: Scope = Depends(scope)) -> dict:
    result = generate_insights(data.records, dates.start, dates.end)
    result["dataset"] = data.descriptor
    return result


@router.get("/questions")
def list_questions(business: dict = Depends(owned_business)) -> list[dict]:
    return [{"id": key, "label": label} for key, label in QUESTION_NAMES.items()]


@router.get("/questions/{question}")
def business_question(
    question: str,
    dataset_id: str | None = None,
    dates: DateRange = Depends(date_range),
    business: dict = Depends(owned_business),
) -> dict:
    if question not in QUESTION_NAMES:
        raise HTTPException(404, "That business question is not available.")
    data = resolve_scope(business["id"], dataset_id)
    return answer_question(question, data.records, dates.start, dates.end)


@router.post("/performance-research")
def performance_research(
    dates: DateRange = Depends(date_range),
    data: Scope = Depends(scope),
    business: dict = Depends(owned_business),
) -> dict:
    try:
        return market_research.research_performance(config.DB_PATH, business["id"], data.records, dates.start, dates.end)
    except market_research.MarketResearchError as error:
        raise HTTPException(503, str(error))
