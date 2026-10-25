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


def test_missing_date_does_not_reject_financial_data(tmp_path):
    path = tmp_path / "missing.csv"
    path.write_text("product,amount\nRice,10\n", encoding="utf-8")
    result = process_file(path, ".csv")
    assert result.errors == []
    assert result.rejected_rows == 0
    assert result.rows[0]["transaction_date"] is None
    assert result.rows[0]["amount"] == 10.0


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
    record = result.rows[0]
    assert record["transaction_date"] == "2026-01-02"
    assert record["amount"] == 0.0
    assert record["cost"] == record["total_cost_usd"] == 125.5
    assert record["transaction_id"] == "PO-1"
    assert record["vendor"] == "Vendor"
    assert record["quantity"] == 2.0
    assert record["_source_domain"] == "costs_cogs_procurement"


def test_mixed_csv_sections_are_normalized_and_keep_domain_labels(tmp_path):
    path = tmp_path / "mixed.csv"
    path.write_text(
        "sale_id,sale_date,product,amount\nS-1,2026-01-02,Rice,100\n\n"
        "expense_date,vendor,total_expense_ghs\n2026-01-03,Power,50\n\n"
        "bl_number,shipping_line_usd,customs_duty_ghs\nBL-1,100,200\n",
        encoding="utf-8",
    )

    result = process_file(path, ".csv")

    assert result.source_rows == 3
    assert result.rejected_rows == 0
    assert result.rows[0]["transaction_date"] == "2026-01-02"
    assert result.rows[0]["_source_domain"] == "transactions_sales"
    assert result.rows[1]["cost"] == 50.0
    assert result.rows[2]["transaction_date"] is None
    assert result.rows[2]["shipping_line_usd"] == 100.0


def test_csv_unit_cost_is_multiplied_by_quantity(tmp_path):
    path = tmp_path / "unit_costs.csv"
    path.write_text(
        "transaction_id,date,amount,product,quantity,unit_cost\n"
        "TX-1,2026-01-02,820,Rice 25kg,2,360\n"
        "TX-2,2026-01-03,185,Frytol oil 5L,1,150\n"
        "TX-3,2026-01-04,50,Sugar 1kg,,12.5\n",
        encoding="utf-8",
    )

    result = process_file(path, ".csv")

    assert [row["cost"] for row in result.rows] == [720.0, 150.0, 12.5]
    metrics = analyze(result.rows)
    assert metrics["profit"]["gross_profit"] == 1055.0 - 882.5
