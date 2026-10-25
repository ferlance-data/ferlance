from collections import defaultdict
from datetime import date
from typing import Any

from .config import DEFAULT_CURRENCY
from .projections import calculate_projections


def _periods(records: list[dict[str, Any]], key, field: str = "amount", output: str = "revenue") -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, float | int]] = defaultdict(lambda: {"revenue": 0.0, "transactions": 0})
    for record in records:
        if not record.get("transaction_date"):
            continue
        period = key(date.fromisoformat(record["transaction_date"]))
        grouped[period]["revenue"] += record.get(field, 0.0)
        grouped[period]["transactions"] += 1
    return [
        {"period": period, output: round(values["revenue"], 2), "transactions": values["transactions"]}
        for period, values in sorted(grouped.items())
    ]


def _product_metrics(records: list[dict[str, Any]], profile: dict[str, Any] | None = None) -> dict[str, Any]:
    products: dict[str, dict[str, Any]] = {}
    product_records = [record for record in records if record.get("product")]
    if not product_records:
        return {"available": False, "reason": "No product field is present in the accepted records."}
    quantity_available = all("quantity" in record for record in product_records)
    cost_available = all("cost" in record for record in product_records)
    cost_mode = bool(profile and profile.get("domain") == "cost")
    profit_available = cost_available and not cost_mode
    for record in product_records:
        name = record["product"]
        item = products.setdefault(name, {"product": name, "revenue": 0.0, "cost": 0.0, "units_sold": 0.0, "transactions": 0})
        item["revenue"] += record["amount"]
        if cost_available:
            item["cost"] += record["cost"]
        item["transactions"] += 1
        if quantity_available:
            item["units_sold"] += record["quantity"]
    items = []
    for item in products.values():
        item["revenue"] = round(item["revenue"], 2)
        if cost_available:
            item["cost"] = round(item["cost"], 2)
        if profit_available:
            item["gross_profit"] = round(item["revenue"] - item["cost"], 2)
            item["margin_pct"] = round(item["gross_profit"] / item["revenue"] * 100, 2) if item["revenue"] else 0.0
            item["roi_pct"] = round(item["gross_profit"] / item["cost"] * 100, 2) if item["cost"] > 0 and item["revenue"] > 0 else None
        else:
            if not cost_available:
                item.pop("cost")
        if quantity_available:
            item["units_sold"] = int(item["units_sold"]) if item["units_sold"].is_integer() else round(item["units_sold"], 2)
        else:
            item.pop("units_sold", None)
        item["metric_label"] = "Cost" if cost_mode else "Revenue"
        item["metric_value"] = item["cost"] if cost_mode and cost_available else item["revenue"]
        items.append(item)
    ranked_desc = sorted(items, key=lambda item: (-item["metric_value"], item["product"]))
    ranked_asc = sorted(items, key=lambda item: (item["metric_value"], item["product"]))
    return {
        "available": True,
        "quantity_available": quantity_available,
        "metric_label": "Cost" if cost_mode else "Revenue",
        "items": ranked_desc,
        "best_sellers": ranked_desc,
        "worst_sellers": ranked_asc,
        "top_5": ranked_desc[:5],
        "worst_5": ranked_asc[:5],
        "all_ranked": ranked_desc,
        "rankings": {
            "revenue": sorted(items, key=lambda item: (-item["revenue"], item["product"])),
            "transactions": sorted(items, key=lambda item: (-item["transactions"], item["product"])),
            "profit": sorted(items, key=lambda item: (-item["gross_profit"], item["product"])) if profit_available else [],
            "loss": sorted([item for item in items if item.get("gross_profit", 0) < 0], key=lambda item: (item["gross_profit"], item["product"])) if profit_available else [],
        },
        "profit_available": profit_available,
    }


def _customer_metrics(records: list[dict[str, Any]], profile: dict[str, Any] | None = None) -> dict[str, Any]:
    customer_records = [record for record in records if record.get("customer")]
    if not customer_records:
        return {"available": False, "reason": "No customer field is present in the accepted records."}
    customers: dict[str, dict[str, Any]] = {}
    for record in customer_records:
        name = record["customer"]
        item = customers.setdefault(name, {"customer": name, "revenue": 0.0, "cost": 0.0, "transactions": 0})
        item["revenue"] += record["amount"]
        item["cost"] += record.get("cost", 0.0)
        item["transactions"] += 1
    items = sorted(
        ({**item, "revenue": round(item["revenue"], 2), "cost": round(item["cost"], 2), "metric_label": "Cost" if profile and profile.get("domain") == "cost" else "Revenue", "metric_value": round(item["cost"] if profile and profile.get("domain") == "cost" else item["revenue"], 2)} for item in customers.values()),
        key=lambda item: (-item["metric_value"], item["customer"]),
    )
    return {
        "available": True,
        "number_of_customers": len(customers),
        "repeat_customers": sum(item["transactions"] >= 2 for item in items),
        "top_customers": items,
    }


def _data_profile(records: list[dict[str, Any]]) -> dict[str, Any]:
    has_revenue = any(record.get("amount", 0) for record in records)
    has_cost = any("cost" in record for record in records)
    if has_cost and not has_revenue:
        return {"domain": "cost", "label": "Costs", "value_key": "cost", "value_label": "Total cost"}
    if has_cost:
        return {"domain": "mixed", "label": "Revenue and costs", "value_key": "amount", "value_label": "Revenue"}
    if has_revenue:
        return {"domain": "sales", "label": "Sales", "value_key": "amount", "value_label": "Revenue"}
    return {"domain": "records", "label": "Records", "value_key": "amount", "value_label": "Recorded value"}


def analyze(records: list[dict[str, Any]], from_date: date | None = None, to_date: date | None = None) -> dict[str, Any]:
    if from_date and to_date and from_date > to_date:
        raise ValueError("The from date must be on or before the to date.")
    available_dates = [date.fromisoformat(record["transaction_date"]) for record in records if record.get("transaction_date")]
    profile = _data_profile(records)
    start = from_date or (min(available_dates) if available_dates else None)
    end = to_date or (max(available_dates) if available_dates else None)
    filtered = [
        record for record in records
        if (start is None or (record.get("transaction_date") and record["transaction_date"] >= start.isoformat()))
        and (end is None or (record.get("transaction_date") and record["transaction_date"] <= end.isoformat()))
    ]
    currencies = {record.get("currency") for record in filtered if record.get("currency")}
    currency = currencies.pop() if len(currencies) == 1 else DEFAULT_CURRENCY
    total = sum(record["amount"] for record in filtered)
    costs = sum(record.get("cost", 0.0) for record in filtered)
    transactions = len(filtered)
    costs_complete = bool(filtered) and all("cost" in record for record in filtered)
    products = _product_metrics(filtered, profile)
    top_product = products["items"][0]["product"] if products["available"] and products["items"] else None
    warnings = []
    if filtered and any(not record.get("product") for record in filtered):
        warnings.append("Some accepted records have no product field and are excluded from product metrics.")
    if filtered and any(not record.get("customer") for record in filtered):
        warnings.append("Some accepted records have no customer field and are excluded from customer metrics.")
    if products.get("available") and not products.get("quantity_available"):
        warnings.append("Units sold are unavailable because quantity is missing from some product records.")
    if products.get("available") and not products.get("profit_available") and profile["domain"] != "cost":
        warnings.append("Item profit and return on investment are unavailable because cost is missing from some product records.")
    if any("cost" in record for record in filtered) and not costs_complete:
        warnings.append("Total profit is unavailable because cost is missing from some accepted records.")
        warnings.append("Cost trends are unavailable because cost is missing from some accepted records.")
    if len(currencies) > 1:
        warnings.append("Multiple currencies are present in this period; totals have not been converted to a common currency.")
    trend_dict = {
        "daily": _periods(filtered, lambda value: value.isoformat()),
        "weekly": _periods(filtered, lambda value: f"{value.isocalendar().year}-W{value.isocalendar().week:02d}"),
        "monthly": _periods(filtered, lambda value: value.strftime("%Y-%m")),
        "quarterly": _periods(filtered, lambda value: f"{value.year}-Q{(value.month - 1) // 3 + 1}"),
        "cost_daily": _periods(filtered, lambda value: value.isoformat(), "cost", "cost") if costs_complete else [],
        "yearly": _periods(filtered, lambda value: value.strftime("%Y")),
        "cost_quarterly": _periods(filtered, lambda value: f"{value.year}-Q{(value.month - 1) // 3 + 1}", "cost", "cost") if costs_complete else [],
        "cost_weekly": _periods(filtered, lambda value: f"{value.isocalendar().year}-W{value.isocalendar().week:02d}", "cost", "cost") if costs_complete else [],
        "cost_monthly": _periods(filtered, lambda value: value.strftime("%Y-%m"), "cost", "cost") if costs_complete else [],
        "cost_yearly": _periods(filtered, lambda value: value.strftime("%Y"), "cost", "cost") if costs_complete else [],
    }
    kpi_dict = {"total_revenue": round(total, 2), "total_cost": round(costs, 2), "primary_value": round(costs if profile["domain"] == "cost" else total, 2), "primary_label": profile["value_label"], "transactions": transactions, "average_sale": round(total / transactions, 2) if transactions else 0.0, "top_product": top_product}
    projections = calculate_projections(trend_dict["monthly"] or trend_dict["weekly"] or trend_dict["daily"], kpi_dict, end)
    return {
        "period": {"from": start.isoformat() if start else None, "to": end.isoformat() if end else None},
        "summary": (f"Revenue was {currency} {total:.2f} across {transactions} transaction{'s' if transactions != 1 else ''}." if profile["domain"] == "sales" else f"{profile['label']} recorded {currency} {costs if profile['domain'] == 'cost' else total:.2f} across {transactions} records.") if transactions else f"No accepted {profile['label'].lower()} records fall within this period.",
        "profile": profile,
        "currency": currency,
        "available_period": {"from": min(available_dates).isoformat() if available_dates else None, "to": max(available_dates).isoformat() if available_dates else None},
        "revenue": {"total": round(total, 2), "currency": currency, "transactions": transactions, "average_sale": round(total / transactions, 2) if transactions else 0.0},
        "trend": trend_dict,
        "products": products,
        "customers": _customer_metrics(filtered, profile),
        "profit": {"available": True, "revenue": round(total, 2), "cost": round(costs, 2), "gross_profit": round(total - costs, 2)} if costs_complete and profile["domain"] != "cost" else {"available": False, "reason": "Profit requires revenue and cost data for every accepted record in this period." if any("cost" in record for record in filtered) else "Accepted records contain revenue but no cost or expense fields."},
        "inventory": {"available": False, "reason": "No inventory snapshot or stock movement data is present."},
        "kpis": kpi_dict,
        "projections": projections,
        "warnings": warnings,
    }
