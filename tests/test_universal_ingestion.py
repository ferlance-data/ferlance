from io import BytesIO

import pandas as pd
import pytest

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


@pytest.mark.parametrize("value", ["10abc20", "12,34", "invoice123", "1e6"])
def test_engine_rejects_numbers_with_unparsed_characters(value):
    with pytest.raises(ValueError, match="not numeric"):
        UniversalCSVIngestionEngine._number(value)


def test_engine_keeps_cost_center_text_categorical():
    source = BytesIO(
        b"expense_date,cost_center,total_expense_ghs\n"
        b"2026-09-28,ECG Prepaid Meter,3500.00\n"
    )

    result = UniversalCSVIngestionEngine(source).process_file()

    assert result["schema_summary"]["accepted_rows"] == 1
    assert result["clean_df"].iloc[0]["category"] == "ECG Prepaid Meter"
    assert result["clean_df"].iloc[0]["cost"] == 3500.0


def test_engine_keeps_status_text_across_mixed_business_sections():
    source = BytesIO(
        b"tx_id,sale_date,customer_tag,credit_amount_ghs,settled_amount_ghs,days_overdue,phone_number,flag\n"
        b"CRX-101,2026-08-20,Teacher Evans,480.00,200.00,54,0243111222,Follow Up\n\n"
        b"entry_date,member_name,susu_collector,daily_deposit_ghs,month_cumulative_ghs,commission_deducted,emergency_fund_dues\n"
        b"2026-10-01,Auntie Mansah,Brother Joe Susu,50.00,50.00,0.00,10.00\n\n"
        b"order_id,date,social_platform,meta_ad_cost_usd,order_value_ghs,rider_service,delivery_fee_charged,courier_remittance_status\n"
        b"ORD-881,2026-10-02,Instagram DM,4.50,450.00,Swoove Express,35.00,Remitted\n"
    )

    result = UniversalCSVIngestionEngine(source).process_file()
    records = result["clean_df"].to_dict(orient="records")

    assert [section["domain"] for section in result["schema_summary"]["sections"]] == [
        "credit_collections",
        "savings_deposits",
        "ecommerce_orders",
    ]
    assert result["schema_summary"]["accepted_rows"] == 3
    assert records[0]["date"] == "2026-08-20"
    assert records[0]["phone_number"] == "0243111222"
    assert records[2]["courier_remittance_status"] == "Remitted"
    assert records[2]["meta_ad_cost_usd"] == 4.5


def test_engine_normalizes_mixed_business_sections_and_preserves_undated_shipping():
    source = BytesIO(
        b"payment_date,agency_authority,obligation_type,amount_remitted,gross_base_ghs\n"
        b"2026-08-15,SSNIT,Tier 1 Pension,2484.00,18400.00\n\n"
        b"log_date,worker_id,laborer_name,task_done,daily_wage_ghs,lunch_stipend\n"
        b"2026-10-06,CS-01,Enoch Tetteh,Bagging,90.00,20.00\n\n"
        b"bl_number,clearing_agent,container_size,shipping_line_usd,customs_duty_ghs\n"
        b"MSK-TMA-9921,Ocansey Maritime,40ft HC,1850.00,42150.00\n\n"
        b"rental_date,equipment_type,customer_project,operator_fee,diesel_cost,total_collected_ghs\n"
        b"2026-09-25,Concrete Mixer 500L,Dansoman Residential,150.00,210.00,1200.00\n"
    )

    result = UniversalCSVIngestionEngine(source).process_file()
    sections = result["schema_summary"]["sections"]
    records = result["clean_df"].to_dict(orient="records")

    assert [section["domain"] for section in sections] == [
        "statutory_obligations",
        "payroll_compensation",
        "shipping_logistics",
        "equipment_rental",
    ]
    assert result["schema_summary"]["accepted_rows"] == 4
    assert records[0]["cost"] == 2484.0
    assert records[1]["cost"] == 90.0
    assert records[2]["shipping_line_usd"] == 1850.0
    assert records[2]["customs_duty_ghs"] == 42150.0
    assert pd.isna(records[2]["date"])
    assert records[3]["amount"] == 1200.0
