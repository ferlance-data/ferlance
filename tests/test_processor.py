from pathlib import Path

from backend.processor import process_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_valid_file_is_normalized_and_deduplicated():
    result = process_file(FIXTURES / "valid_sales.csv", ".csv")
    assert result.source_rows == 3
    assert result.rejected_rows == 0
    assert result.rows[0]["transaction_date"] == "2026-01-02"
    assert result.rows[0]["amount"] == 1250.5


def test_invalid_rows_are_reported_without_stopping_valid_rows():
    result = process_file(FIXTURES / "invalid_sales.csv", ".csv")
    assert result.source_rows == 3
    assert result.rejected_rows == 2
    assert len(result.rows) == 1
    assert len(result.warnings) == 2


def test_missing_required_column_is_an_error(tmp_path):
    path = tmp_path / "missing.csv"
    path.write_text("product,amount\nRice,10\n", encoding="utf-8")
    result = process_file(path, ".csv")
    assert result.errors == ["Missing required column: transaction_date."]
    assert result.rows == []


def test_empty_file_is_an_error(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    result = process_file(path, ".csv")
    assert result.errors == ["The file is empty or has no data rows."]
