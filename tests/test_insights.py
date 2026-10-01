from datetime import date

from backend.insights import answer_question, generate_insights


def records():
    return [
        {"transaction_date": "2026-01-01", "amount": 100.0, "product": "Rice", "customer": "Ama", "quantity": 2},
        {"transaction_date": "2026-01-02", "amount": 40.0, "product": "Beans", "customer": "Kojo", "quantity": 1},
        {"transaction_date": "2025-12-30", "amount": 50.0, "product": "Rice", "customer": "Ama", "quantity": 1},
    ]


def test_insights_are_grounded_in_comparison_metrics():
    result = generate_insights(records(), date(2026, 1, 1), date(2026, 1, 2))

    assert result["revenue_change"] == {"current": 140.0, "previous": 50.0, "percent": 180.0, "direction": "up"}
    assert any(item["type"] == "comparison" for item in result["insights"])
    assert any(item["type"] == "recommendation" for item in result["insights"])


def test_predefined_questions_have_stable_structured_answers():
    result = answer_question("best-products", records(), date(2026, 1, 1), date(2026, 1, 2))

    assert result["label"] == "Best Products"
    assert result["answer"][0]["product"] == "Rice"
    assert result["period"] == {"from": "2026-01-01", "to": "2026-01-02"}


def test_empty_insights_are_honest():
    result = generate_insights([], date(2026, 1, 1), date(2026, 1, 2))

    assert result["insights"] == []
    assert result["revenue_change"]["direction"] == "flat"


def test_insights_identify_grounded_product_decline():
    data = [
        {"transaction_date": "2025-12-31", "amount": 100.0, "product": "Rice"},
        {"transaction_date": "2026-01-01", "amount": 50.0, "product": "Rice"},
    ]

    result = generate_insights(data, date(2026, 1, 1), date(2026, 1, 1))

    anomalies = [item for item in result["insights"] if item["type"] == "anomaly"]
    assert anomalies
    assert anomalies[0]["supporting_metric"]["percent"] == -50.0


def test_insights_identify_product_that_disappears():
    data = [
        {"transaction_date": "2025-12-31", "amount": 100.0, "product": "Rice"},
        {"transaction_date": "2026-01-01", "amount": 40.0, "product": "Beans"},
    ]

    result = generate_insights(data, date(2026, 1, 1), date(2026, 1, 1))

    anomalies = [item for item in result["insights"] if item["type"] == "anomaly"]
    assert anomalies[0]["supporting_metric"]["product"] == "Rice"
    assert anomalies[0]["supporting_metric"]["current"] == 0.0
