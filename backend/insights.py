from datetime import date, timedelta
from typing import Any, Callable

from .analytics import analyze

QUESTION_NAMES = {
    "sales-summary": "Sales Summary",
    "best-products": "Best Products",
    "customer-overview": "Customer Overview",
    "revenue-trend": "Revenue Trend",
    "underperforming-products": "Underperforming Products",
    "monthly-comparison": "Monthly Comparison",
}


def _period_bounds(records: list[dict[str, Any]], from_date: date | None, to_date: date | None) -> tuple[date | None, date | None]:
    dates = [date.fromisoformat(record["transaction_date"]) for record in records]
    return from_date or (min(dates) if dates else None), to_date or (max(dates) if dates else None)


def _previous_period(records: list[dict[str, Any]], from_date: date | None, to_date: date | None) -> tuple[date | None, date | None]:
    start, end = _period_bounds(records, from_date, to_date)
    if not start or not end:
        return None, None
    length = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    return previous_end - timedelta(days=length - 1), previous_end


def _change(current: float, previous: float) -> dict[str, Any]:
    if previous == 0:
        return {"current": round(current, 2), "previous": 0.0, "percent": None, "direction": "new" if current else "flat"}
    percent = round((current - previous) / abs(previous) * 100, 2)
    return {"current": round(current, 2), "previous": round(previous, 2), "percent": percent, "direction": "up" if percent > 0 else "down" if percent < 0 else "flat"}


def _change_message(label: str, change: dict[str, Any]) -> str:
    if change["direction"] == "new":
        return f"{label} is new in this period at {change['current']:.2f}; there was no comparable prior-period value."
    if change["direction"] == "flat":
        return f"{label} was unchanged at {change['current']:.2f} compared with the previous period."
    direction = "increased" if change["direction"] == "up" else "declined"
    return f"{label} {direction} by {abs(change['percent']):.2f}% from {change['previous']:.2f} to {change['current']:.2f}."


def generate_insights(records: list[dict[str, Any]], from_date: date | None = None, to_date: date | None = None) -> dict[str, Any]:
    current_start, current_end = _period_bounds(records, from_date, to_date)
    previous_start, previous_end = _previous_period(records, from_date, to_date)
    current = analyze(records, from_date, to_date)
    previous = analyze(records, previous_start, previous_end) if previous_start and previous_end else analyze([])
    revenue_change = _change(current["revenue"]["total"], previous["revenue"]["total"])
    insights: list[dict[str, Any]] = []
    if current["revenue"]["transactions"]:
        insights.append({"type": "summary", "title": "Sales summary", "message": current["summary"], "severity": "info", "supporting_metric": current["revenue"], "limitations": current["warnings"]})
    if previous["revenue"]["transactions"] and revenue_change["percent"] is not None and abs(revenue_change["percent"]) >= 10:
        direction = "increased" if revenue_change["direction"] == "up" else "declined"
        insights.append({"type": "comparison", "title": "Revenue movement", "message": f"Revenue {direction} by {abs(revenue_change['percent']):.2f}% compared with the previous period.", "severity": "positive" if direction == "increased" else "attention", "supporting_metric": revenue_change, "limitations": []})
    if current["products"].get("available") and previous["products"].get("available"):
        current_products = {item["product"]: item for item in current["products"]["items"]}
        previous_products = {item["product"]: item for item in previous["products"]["items"]}
        for product_name, prior in previous_products.items():
            product = current_products.get(product_name, {"product": product_name, "revenue": 0.0})
            if prior["revenue"] > 0:
                product_change = _change(product["revenue"], prior["revenue"])
                if product_change["percent"] is not None and product_change["percent"] <= -20:
                    insights.append({"type": "anomaly", "title": "Product decline", "message": f"{product_name} revenue declined by {abs(product_change['percent']):.2f}% compared with the previous period.", "severity": "attention", "supporting_metric": {**product_change, "product": product_name}, "limitations": ["This is a period comparison, not a causal explanation."]})
    if current["products"].get("available") and current["products"].get("items"):
        top = current["products"]["best_sellers"][0]
        insights.append({"type": "recommendation", "title": "Product focus", "message": f"{top['product']} is the leading product by revenue in this period.", "severity": "info", "supporting_metric": top, "limitations": ["This recommendation uses revenue only; inventory and margin are unavailable."]})
    comparison = {"label": "Revenue", "message": _change_message("Revenue", revenue_change), "current": revenue_change["current"], "previous": revenue_change["previous"], "percent": revenue_change["percent"], "direction": revenue_change["direction"]}
    return {"period": {"from": current_start.isoformat() if current_start else None, "to": current_end.isoformat() if current_end else None}, "comparison_period": {"from": previous_start.isoformat() if previous_start else None, "to": previous_end.isoformat() if previous_end else None}, "comparison": comparison, "revenue_change": revenue_change, "insights": insights, "warnings": current["warnings"]}


def answer_question(question: str, records: list[dict[str, Any]], from_date: date | None = None, to_date: date | None = None) -> dict[str, Any]:
    if question not in QUESTION_NAMES:
        raise KeyError(question)
    result = analyze(records, from_date, to_date)
    if question == "sales-summary":
        answer = result["summary"]
    elif question == "best-products":
        answer = [item for item in result["products"].get("best_sellers", [])[:5]] if result["products"].get("available") else []
    elif question == "customer-overview":
        answer = result["customers"]
    elif question == "revenue-trend":
        answer = result["trend"]
    elif question == "underperforming-products":
        answer = result["products"].get("worst_sellers", []) if result["products"].get("available") else []
    else:
        generated = generate_insights(records, from_date, to_date)
        answer = generated["comparison"]
    return {"question": question, "label": QUESTION_NAMES[question], "answer": answer, "period": result["period"], "warnings": result["warnings"]}
