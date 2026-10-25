"""Macroeconomic intelligence and grounded projection models for Ghanaian SMEs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Benchmark Macroeconomic Rates (Ghana Statistical Service / Bank of Ghana 2026 baselines)
MACRO_BENCHMARKS = {
    "ghana_inflation_cpi": 21.5,  # Annual percentage
    "fx_rates": {
        "USD": 15.80,
        "EUR": 17.15,
        "GBP": 20.40,
    },
    "seasonal_calendar": {
        1: {"season": "Post-Holiday & Academic Intake", "impact": "Household spend constrained by school fees; staple demand remains steady."},
        2: {"season": "Dry Season / Harmattan Peak", "impact": "High beverage & cold storage demand; dust/heat impacts transport."},
        3: {"season": "Pre-Planting Preparation", "impact": "Agricultural input procurement rises in rural and peri-urban hubs."},
        4: {"season": "Easter Festive Period", "impact": "Spike in hospitality, events, poultry, meat, and travel services."},
        5: {"season": "Major Rainy Season Onset", "impact": "Logistics delays, open-market trade slowdown; delivery services surge."},
        6: {"season": "Heavy Rains & Mid-Year", "impact": "Construction materials and outdoor projects slow; food preservation vital."},
        7: {"season": "Mid-Year Harvest (Minor)", "impact": "Local maize and vegetable prices soften; trading volume rebounds."},
        8: {"season": "Pre-School Reopening Prep", "impact": "Consumer spending diverts to uniforms, books, stationery, and boarding provisions."},
        9: {"season": "Major Academic Term Reopening", "impact": "Retail spending dip on luxuries; education and transport revenues peak."},
        10: {"season": "Main Cocoa Harvest Opening", "impact": "Rural purchasing power surges across Ashanti, Western, Eastern, and Central regions."},
        11: {"season": "Early Festive Stocking", "impact": "Wholesale stocking ahead of Christmas; currency volatility often increases."},
        12: {"season": "Festive Holiday Peak", "impact": "Annual high for retail, food services, events, entertainment, and gift items."},
    },
}


def calculate_projections(
    trend_items: list[dict[str, Any]],
    kpis: dict[str, Any],
    as_of: date | None = None,
) -> dict[str, Any]:
    """Calculate grounded forward-looking business projections factoring in inflation and seasonality."""
    today = as_of or date.today()
    current_month = today.month
    season_info = MACRO_BENCHMARKS["seasonal_calendar"].get(current_month, {
        "season": "Standard Business Period",
        "impact": "Stable operating conditions across urban markets.",
    })

    total_revenue = float(kpis.get("total_revenue") or 0.0)
    total_cost = float(kpis.get("total_cost") or 0.0)
    gross_profit = float(kpis.get("gross_profit") or (total_revenue - total_cost))
    net_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else 0.0
    transactions = int(kpis.get("transactions") or 0)

    # Compute period growth velocity if trend data is present
    growth_velocity = 0.0
    if len(trend_items) >= 2:
        prev_rev = float(trend_items[-2].get("revenue") or trend_items[-2].get("cost") or 0.0)
        curr_rev = float(trend_items[-1].get("revenue") or trend_items[-1].get("cost") or 0.0)
        if prev_rev > 0:
            growth_velocity = round(((curr_rev - prev_rev) / prev_rev) * 100, 2)

    # Real growth vs inflation
    inflation_rate = MACRO_BENCHMARKS["ghana_inflation_cpi"]
    real_growth = round(growth_velocity - (inflation_rate / 12), 2)  # monthly-adjusted inflation comparison

    # Determine status classification
    if total_revenue <= 0 and total_cost > 0:
        status = "Business in Danger"
        status_code = "danger"
        summary = "Operating with zero recorded revenue against ongoing costs. Immediate restructuring required."
    elif gross_profit < 0 or (growth_velocity < -15 and net_margin < 5):
        status = "Business in Danger"
        status_code = "danger"
        summary = "Expenses outpace earnings, or steep revenue contraction is eroding capital reserves."
    elif growth_velocity < 0 or real_growth < -2 or (net_margin < 10 and growth_velocity < 5):
        status = "Possible Decline"
        status_code = "warning"
        summary = "Revenue growth is negative or trailing headline inflation (~21.5%), reducing real purchasing power."
    elif real_growth > 8 and net_margin > 20:
        status = "Strong Growth"
        status_code = "success"
        summary = "Strong volume expansion and healthy profit margins comfortably beating inflationary pressure."
    else:
        status = "Steady Growth"
        status_code = "positive"
        summary = "Stable transaction cadence and healthy cash retention across the active period."

    # Actionable suggestions
    suggestions: list[str] = []
    if status_code in ("danger", "warning"):
        suggestions.append(f"Review supplier terms: local inflation ({inflation_rate}%) is compressing gross margins.")
        suggestions.append("Prioritize high-margin inventory or core services; discontinue negative-ROI offerings.")
    else:
        suggestions.append("Reinvest operating cash into fast-moving inventory before seasonal price adjustments.")

    # Seasonal suggestion
    suggestions.append(f"Seasonal Focus ({season_info['season']}): {season_info['impact']}")

    return {
        "status": status,
        "status_code": status_code,
        "summary": summary,
        "growth_velocity_pct": growth_velocity,
        "real_growth_pct": real_growth,
        "net_margin_pct": round(net_margin, 2),
        "macro_context": {
            "ghana_inflation_cpi_pct": inflation_rate,
            "exchange_rates": MACRO_BENCHMARKS["fx_rates"],
            "current_season": season_info["season"],
            "seasonal_impact": season_info["impact"],
        },
        "actionable_suggestions": suggestions,
    }
