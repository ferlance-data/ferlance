import sqlite3
import pytest
from backend.external_connectors import ExternalConnectorManager, ConnectorError


def test_sqlite_external_connection_detects_tables(tmp_path):
    ext_db = tmp_path / "pos_external.sqlite3"
    conn = sqlite3.connect(ext_db)
    conn.execute("CREATE TABLE sales (id TEXT, date TEXT, amount REAL, product TEXT);")
    conn.execute("INSERT INTO sales VALUES ('TX1', '2026-03-01', 50.0, 'Bread');")
    conn.commit()
    conn.close()

    result = ExternalConnectorManager.test_connection("sqlite_external", {"path": str(ext_db)})
    assert result["success"] is True
    assert "sales" in result["tables"]

    records = ExternalConnectorManager.fetch_records("sqlite_external", {"path": str(ext_db)})
    assert len(records) == 1
    assert records[0]["amount"] == 50.0


def test_sqlite_external_rejects_internal_database(tmp_path):
    app_db = tmp_path / "ferlance.sqlite3"
    app_db.touch()
    with pytest.raises(ConnectorError, match="cannot be the application's internal database"):
        ExternalConnectorManager.test_connection("sqlite_external", {"path": str(app_db)}, app_db_path=app_db)


def test_pos_connection_validation():
    result = ExternalConnectorManager.test_connection(
        "pos", {"endpoint_url": "https://api.mypos.example.com/v1/sales", "api_key": "token123"}
    )
    assert result["success"] is True


def test_postgres_and_mongo_validation():
    pg = ExternalConnectorManager.test_connection(
        "postgres", {"host": "localhost", "database": "retail_db", "user": "admin"}
    )
    assert pg["success"] is True

    mongo = ExternalConnectorManager.test_connection(
        "mongodb", {"uri": "mongodb://localhost:27017", "database": "orders_db"}
    )
    assert mongo["success"] is True
