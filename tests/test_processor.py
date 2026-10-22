from pathlib import Path

from openpyxl import Workbook

from backend.analytics import analyze
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


def test_valid_xlsx_file_is_normalized(tmp_path):
    path = tmp_path / "sales.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Date", "Revenue", "Product"])
    sheet.append(["2026-01-02", "GHS 1,250.50", "Rice"])
    workbook.save(path)

    result = process_file(path, ".xlsx")

    assert result.source_rows == 1
    assert result.rejected_rows == 0
    assert result.rows == [{"transaction_date": "2026-01-02", "amount": 1250.5, "product": "Rice"}]


def test_malformed_xlsx_is_a_controlled_error(tmp_path):
    path = tmp_path / "malformed.xlsx"
    path.write_bytes(b"not an xlsx file")

    result = process_file(path, ".xlsx")

    assert result.rows == []
    assert result.errors == ["The XLSX file is malformed or unreadable."]


def test_cost_file_aliases_are_accepted_without_becoming_revenue(tmp_path):
    path = tmp_path / "costs.csv"
    path.write_text("po_number,order_date,vendor_name,total_cost_usd,quantity\nPO-1,2026-01-02,Vendor,125.50,2\n", encoding="utf-8")

    result = process_file(path, ".csv")

    assert result.rejected_rows == 0
    assert result.rows == [{"transaction_date": "2026-01-02", "amount": 0.0, "currency": "USD", "cost": 125.5, "transaction_id": "PO-1", "customer": "Vendor", "quantity": 2.0}]


def test_unit_cost_is_extended_by_quantity_for_item_roi(tmp_path):
    path = tmp_path / "unit-costs.csv"
    path.write_text("date,product,revenue,unit_cost,quantity\n2026-01-02,Tea,120,3.50,4\n", encoding="utf-8")

    result = process_file(path, ".csv")

    assert result.rejected_rows == 0
    assert result.rows == [{"transaction_date": "2026-01-02", "amount": 120.0, "product": "Tea", "quantity": 4.0, "cost": 14.0}]
    item = analyze(result.rows)["products"]["items"][0]
    assert item["gross_profit"] == 106.0
    assert item["roi_pct"] == 757.14


def test_financial_parser_rejects_embedded_letters_and_bad_grouping(tmp_path):
    path = tmp_path / "malformed-numbers.csv"
    path.write_text(
        'date,revenue\n2026-01-01,10abc20\n2026-01-02,"12,34"\n',
        encoding="utf-8",
    )

    result = process_file(path, ".csv")

    assert result.rows == []
    assert result.rejected_rows == 2
    assert len(result.warnings) == 2


def test_invalid_utf8_csv_returns_a_controlled_import_error(tmp_path):
    path = tmp_path / "invalid-encoding.csv"
    path.write_bytes(b"date,revenue\n2026-01-01,\xff")

    result = process_file(path, ".csv")

    assert result.rows == []
    assert result.errors == ["The CSV file is not valid UTF-8. Save it as UTF-8 and upload it again."]


def test_zero_financial_values_are_valid_numbers(tmp_path):
    path = tmp_path / "zero.csv"
    path.write_text("date,revenue,cost\n2026-01-01,0,0\n2026-01-02,.50,\n", encoding="utf-8")

    result = process_file(path, ".csv")

    assert result.rejected_rows == 0
    assert result.rows[0]["amount"] == 0
    assert result.rows[0]["cost"] == 0
    assert result.rows[1]["amount"] == 0.5


def test_blank_financial_rows_are_rejected_instead_of_counted_as_zero_sales(tmp_path):
    path = tmp_path / "blank-amount.csv"
    path.write_text("date,revenue\n2026-01-01,\n", encoding="utf-8")

    result = process_file(path, ".csv")

    assert result.rows == []
    assert result.rejected_rows == 1
    assert "financial value is missing" in result.warnings[0]


def test_specific_financial_headers_take_precedence_over_generic_totals(tmp_path):
    path = tmp_path / "specific-headers.csv"
    path.write_text(
        "date,revenue,total,cost,total_cost\n2026-01-01,100,140,30,45\n",
        encoding="utf-8",
    )

    result = process_file(path, ".csv")

    assert result.rows[0]["amount"] == 100
    assert result.rows[0]["cost"] == 45


def test_identical_rows_without_transaction_ids_are_preserved(tmp_path):
    path = tmp_path / "repeat-sales.csv"
    path.write_text(
        "date,revenue,product\n2026-01-01,15,Rice\n2026-01-01,15,Rice\n",
        encoding="utf-8",
    )

    result = process_file(path, ".csv")

    assert result.rejected_rows == 0
    assert len(result.rows) == 2


def test_duplicate_transaction_ids_are_rejected(tmp_path):
    path = tmp_path / "duplicate-ids.csv"
    path.write_text(
        "transaction_id,date,revenue\nsale-1,2026-01-01,15\nsale-1,2026-01-02,20\n",
        encoding="utf-8",
    )

    result = process_file(path, ".csv")

    assert result.rejected_rows == 1
    assert len(result.rows) == 1
    assert "duplicate transaction ID" in result.warnings[0]


def test_duplicate_normalized_headers_fail_import_explicitly(tmp_path):
    path = tmp_path / "duplicate-headers.csv"
    path.write_text(
        "date,Revenue,revenue\n2026-01-01,10,20\n",
        encoding="utf-8",
    )

    result = process_file(path, ".csv")

    assert result.rows == []
    assert result.errors == ["The CSV file contains duplicate column names."]
