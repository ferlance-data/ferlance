from io import BytesIO

from backend.universal_ingestion import UniversalCSVIngestionEngine


def test_engine_detects_preamble_semicolon_encoding_and_casts_dirty_values():
    source = BytesIO(
        "Report exported by ERP\n\nDate;Total_Price;Customer;Notes\n2026/01/02;GH₵ 1,250.50; Ama ; urgent reorder\n2026/01/03;not money;Kojo;check supplier\n".encode("utf-8-sig")
    )

    result = UniversalCSVIngestionEngine(source).process_file()

    assert result["schema_summary"]["delimiter"] == ";"
    assert result["schema_summary"]["header_row"] == 3
    assert result["domain"] == "transactions_sales"
    assert result["clean_df"].iloc[0]["date"] == "2026-01-02"
    assert result["clean_df"].iloc[0]["amount"] == 1250.50
    assert result["clean_df"].iloc[0]["_text_payload"] == '{"Notes": "urgent reorder"}'
    assert result["quarantined_rows"][0]["row_number"] == 5
    assert "not numeric" in result["quarantined_rows"][0]["errors"][0]


def test_engine_accepts_pipe_delimiter_and_latin1(tmp_path):
    path = tmp_path / "payroll.csv"
    path.write_bytes("employee_name|salary|department\nAndre|£2,500|Finance\n".encode("latin-1"))

    result = UniversalCSVIngestionEngine(path).process_file()

    assert result["schema_summary"]["delimiter"] == "|"
    assert result["schema_summary"]["encoding"] in {"cp1250", "iso-8859-1", "latin-1", "cp1252"}
    assert result["domain"] == "payroll_compensation"
    assert result["clean_df"].iloc[0]["amount"] == 2500.0


def test_engine_quarantines_ragged_rows_and_reports_checksum():
    result = UniversalCSVIngestionEngine(BytesIO(b"date,amount\n2026-01-01,10,unexpected\n")).process_file()

    assert result["clean_df"].empty
    assert result["quarantined_rows"][0]["errors"] == ["extra columns: 1"]
    assert len(result["schema_summary"]["checksum"]) == 64


def test_engine_maps_budget_cost_columns_without_misclassifying_categories():
    source = BytesIO(b"expense_id,date,expense_category,budgeted_cost_usd,actual_cost_usd,variance_pct\nEXP-1,2026-01-15,Cloud Hosting,100,120,20\n")

    result = UniversalCSVIngestionEngine(source).process_file()

    assert result["domain"] == "budgets_variances"
    assert result["schema_summary"]["column_mapping"]["cost"] == "actual_cost_usd"
    assert result["clean_df"].iloc[0]["category"] == "Cloud Hosting"
    assert result["clean_df"].iloc[0]["cost"] == 120.0