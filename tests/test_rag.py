from pathlib import Path

from backend import db
from backend.rag import index_dataset, retrieve


def test_rag_index_is_tenant_scoped_and_retrieves_relevant_rows(tmp_path: Path):
    database = tmp_path / "rag.sqlite3"
    db.initialize(database)
    index_dataset(database, "business-a", "dataset-a", [{"transaction_date": "2026-01-01", "product": "Rice", "amount": 100}])
    index_dataset(database, "business-b", "dataset-b", [{"transaction_date": "2026-01-01", "product": "Rice", "amount": 900}])

    results = retrieve(database, "business-a", "Rice", [{"id": "dataset-a", "filename": "sales.csv", "accepted_rows": 1}])

    assert len(results) == 1
    assert results[0]["dataset"] == "sales.csv"
    assert "Rice" in results[0]["evidence"]