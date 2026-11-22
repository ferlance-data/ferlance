from pathlib import Path

import pytest

from backend import db
from backend.rag import DataAvailabilityError, all_records, index_dataset, retrieve


def test_rag_index_is_tenant_scoped_and_retrieves_relevant_rows(tmp_path: Path):
    database = tmp_path / "rag.sqlite3"
    db.initialize(database)
    index_dataset(database, "business-a", "dataset-a", [{"transaction_date": "2026-01-01", "product": "Rice", "amount": 100}])
    index_dataset(database, "business-b", "dataset-b", [{"transaction_date": "2026-01-01", "product": "Rice", "amount": 900}])

    results = retrieve(database, "business-a", "Rice", [{"id": "dataset-a", "filename": "sales.csv", "accepted_rows": 1}])

    assert len(results) == 1
    assert results[0]["dataset"] == "sales.csv"
    assert "Rice" in results[0]["evidence"]


def test_all_records_reports_corrupt_processed_data_instead_of_omitting_it(tmp_path: Path):
    path = tmp_path / "broken.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(DataAvailabilityError, match="[Pp]rocessed records"):
        all_records([{"id": "broken", "filename": "sales.csv", "processed_path": str(path)}])

def test_v2_retrieval_ignores_field_names_and_question_words_and_applies_dates(tmp_path: Path):
    from datetime import date

    from backend import db, rag

    path = tmp_path / "rag.sqlite3"
    db.initialize(path)
    records = [
        {"transaction_date": "2026-09-03", "product": "Sardines", "customer": "Kofi", "amount": 14},
        {"transaction_date": "2026-10-05", "product": "Sardines", "customer": "Ama", "amount": 28},
        {"transaction_date": "2026-10-06", "product": "Rice", "customer": "Kwame Darko", "amount": 95},
        {"transaction_date": "2026-10-07", "channel": "MTN MoMo", "reference": "Payment received", "amount": 50},
    ]
    rag.index_dataset(path, "b1", "d1", records)
    dataset = [{"id": "d1", "filename": "shop.csv"}]

    def found(question, **window):
        return [row["record"] for row in rag.retrieve(path, "b1", question, dataset, **window)]

    # "product"/"customer"/"sales" no longer match every row.
    assert [r["product"] for r in found("Which customers bought sardines? show product sales")] == ["Sardines", "Sardines"]
    assert [r["customer"] for r in found("sardines", from_date=date(2026, 9, 1), to_date=date(2026, 9, 30))] == ["Kofi"]
    assert found("Mobile money payments")[0]["channel"] == "MTN MoMo"  # stemmed: payments -> payment
    assert rag.query_terms("How much did my business sell this month?") == ["business"]
    # Other businesses never leak in.
    assert rag.retrieve(path, "other", "sardines", dataset) == []
