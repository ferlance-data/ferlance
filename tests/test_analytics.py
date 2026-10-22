from datetime import date

from backend.analytics import analyze
from backend.insights import generate_insights


def test_analyze_groups_revenue_by_day_week_and_month():
    records = [
        {"transaction_date": "2025-12-31", "amount": 100.0, "product": "A", "customer": "C1", "quantity": 1},
        {"transaction_date": "2026-01-01", "amount": 200.0, "product": "B", "customer": "C1", "quantity": 2},
    ]

    result = analyze(records)

    assert result["revenue"]["total"] == 300.0
    assert result["summary"] == "Revenue was GHS 300.00 across 2 transactions."
    assert result["trend"]["weekly"] == [{"period": "2026-W01", "revenue": 300.0, "transactions": 2}]
    assert result["trend"]["monthly"] == [
        {"period": "2025-12", "revenue": 100.0, "transactions": 1},
        {"period": "2026-01", "revenue": 200.0, "transactions": 1},
    ]
    assert result["trend"]["quarterly"] == [
        {"period": "2025-Q4", "revenue": 100.0, "transactions": 1},
        {"period": "2026-Q1", "revenue": 200.0, "transactions": 1},
    ]
    assert result["trend"]["yearly"] == [
        {"period": "2025", "revenue": 100.0, "transactions": 1},
        {"period": "2026", "revenue": 200.0, "transactions": 1},
    ]
    assert result["products"]["quantity_available"] is True
    assert result["products"]["best_sellers"][0]["product"] == "B"
    assert result["products"]["worst_sellers"][0]["product"] == "A"
    assert result["customers"]["repeat_customers"] == 1


def test_analyze_empty_filter_returns_empty_metrics():
    records = [{"transaction_date": "2026-01-01", "amount": 100.0}]

    result = analyze(records, date(2026, 2, 1), date(2026, 2, 28))

    assert result["revenue"]["total"] == 0.0
    assert result["revenue"]["transactions"] == 0
    assert result["summary"] == "No accepted sales records fall within this period."
    assert result["trend"]["daily"] == []
    assert result["products"]["available"] is False
    assert result["customers"]["available"] is False


def test_analyze_warns_when_optional_fields_are_incomplete():
    records = [
        {"transaction_date": "2026-01-01", "amount": 100.0, "product": "A"},
        {"transaction_date": "2026-01-02", "amount": 50.0, "customer": "C1"},
    ]

    result = analyze(records)

    assert len(result["warnings"]) == 4
    assert result["profit"]["available"] is False


def test_product_rankings_compare_transactions_and_profit():
    result = analyze([
        {"transaction_date": "2026-01-01", "amount": 300.0, "cost": 100.0, "product": "A", "quantity": 40},
        {"transaction_date": "2026-01-01", "amount": 100.0, "cost": 75.0, "product": "B", "quantity": 25},
        {"transaction_date": "2026-01-01", "amount": 100.0, "cost": 75.0, "product": "B", "quantity": 25},
    ])

    assert result["products"]["rankings"]["profit"][0]["product"] == "A"
    assert result["products"]["rankings"]["transactions"][0]["product"] == "B"
    assert result["products"]["rankings"]["profit"][0]["gross_profit"] == 200.0
    assert result["products"]["rankings"]["profit"][0]["roi_pct"] == 200.0
    assert result["products"]["rankings"]["profit"][1]["roi_pct"] == 33.33


def test_cost_records_use_cost_as_primary_metric_and_filter_dates():
    result = analyze([
        {"transaction_date": "2026-01-01", "amount": 0.0, "cost": 100.0, "product": "Cloud"},
        {"transaction_date": "2026-02-01", "amount": 0.0, "cost": 250.0, "product": "Cloud"},
    ], date(2026, 2, 1), date(2026, 2, 1))

    assert result["profile"]["domain"] == "cost"
    assert result["summary"] == "Costs recorded GHS 250.00 across 1 records."
    assert result["kpis"]["primary_label"] == "Total cost"
    assert result["kpis"]["primary_value"] == 250.0
    assert result["products"]["items"][0]["metric_value"] == 250.0
    assert result["trend"]["cost_weekly"] == [{"period": "2026-W05", "cost": 250.0, "transactions": 1}]
    assert result["trend"]["cost_monthly"] == [{"period": "2026-02", "cost": 250.0, "transactions": 1}]
    assert result["trend"]["cost_yearly"] == [{"period": "2026", "cost": 250.0, "transactions": 1}]
    assert result["trend"]["cost_quarterly"] == [{"period": "2026-Q1", "cost": 250.0, "transactions": 1}]
    assert result["profit"]["available"] is False


def test_analyze_exposes_costs_and_gross_profit():
    result = analyze([{"transaction_date": "2026-01-01", "amount": 250.0, "cost": 80.0}])

    assert result["profit"] == {"available": True, "revenue": 250.0, "cost": 80.0, "gross_profit": 170.0}


def test_missing_costs_never_look_like_zero_cost_or_roi():
    result = analyze([
        {"transaction_date": "2026-01-01", "amount": 100.0, "cost": 40.0, "product": "Known"},
        {"transaction_date": "2026-01-02", "amount": 100.0, "product": "Unknown"},
    ])

    assert result["profit"]["available"] is False
    assert result["products"]["profit_available"] is False
    assert result["products"]["rankings"]["profit"] == []
    assert any("missing from some accepted records" in warning for warning in result["warnings"])


def test_zero_cost_items_have_no_roi_and_loss_insights_are_grounded():
    records = [
        {"transaction_date": "2026-01-01", "amount": 50.0, "cost": 75.0, "product": "Loss maker"},
        {"transaction_date": "2026-01-02", "amount": 100.0, "cost": 0.0, "product": "No cost"},
        {"transaction_date": "2026-01-03", "amount": 200.0, "cost": 50.0, "product": "High return"},
    ]

    result = analyze(records)
    insights = generate_insights(records)["insights"]

    items = {item["product"]: item for item in result["products"]["items"]}
    assert items["Loss maker"]["gross_profit"] == -25.0
    assert items["Loss maker"]["roi_pct"] == -33.33
    assert items["No cost"]["roi_pct"] is None
    assert any(item["title"] == "Item operating at a loss" and "Loss maker" in item["message"] for item in insights)
    assert any(item["title"] == "Highest item return" and "High return" in item["message"] for item in insights)


def test_large_dataset_rollups_preserve_totals():
    records = [
        {"transaction_date": f"2026-{month:02d}-{day:02d}", "amount": 1.0, "cost": 0.25, "product": "Bulk"}
        for month in range(1, 13)
        for day in range(1, 29)
        for _ in range(30)
    ]

    result = analyze(records)

    assert result["revenue"]["total"] == 10080.0
    assert result["profit"]["gross_profit"] == 7560.0
    assert len(result["trend"]["quarterly"]) == 4
    assert result["products"]["items"][0]["roi_pct"] == 300.0


def test_net_zero_revenue_with_recorded_cost_still_reports_operating_loss():
    result = analyze([
        {"transaction_date": "2026-01-01", "amount": 100.0, "cost": 80.0},
        {"transaction_date": "2026-01-02", "amount": -100.0, "cost": 10.0},
    ])

    assert result["profit"]["available"] is True
    assert result["profit"]["gross_profit"] == -90.0


def test_cost_trend_is_withheld_when_some_records_have_no_cost():
    result = analyze([
        {"transaction_date": "2026-01-01", "amount": 100.0, "cost": 80.0},
        {"transaction_date": "2026-01-02", "amount": 50.0},
    ])

    assert result["trend"]["cost_daily"] == []
    assert result["trend"]["cost_weekly"] == []
    assert any("Cost trends are unavailable" in warning for warning in result["warnings"])