from datetime import date

from backend.analytics import analyze


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

    assert len(result["warnings"]) == 3


def test_product_rankings_compare_transactions_and_profit():
    result = analyze([
        {"transaction_date": "2026-01-01", "amount": 300.0, "cost": 100.0, "product": "A", "quantity": 40},
        {"transaction_date": "2026-01-01", "amount": 100.0, "cost": 75.0, "product": "B", "quantity": 25},
        {"transaction_date": "2026-01-01", "amount": 100.0, "cost": 75.0, "product": "B", "quantity": 25},
    ])

    assert result["products"]["rankings"]["profit"][0]["product"] == "A"
    assert result["products"]["rankings"]["transactions"][0]["product"] == "B"
    assert result["products"]["rankings"]["profit"][0]["gross_profit"] == 200.0


def test_analyze_exposes_costs_and_gross_profit():
    result = analyze([{"transaction_date": "2026-01-01", "amount": 250.0, "cost": 80.0}])

    assert result["profit"] == {"available": True, "revenue": 250.0, "cost": 80.0, "gross_profit": 170.0}