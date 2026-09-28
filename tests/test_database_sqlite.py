"""Tests for the SQLite backend in database.py (uses a real temporary SQLite file)."""

import pytest

import config
import database


@pytest.fixture
def sqlite_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DB_BACKEND", "sqlite")
    monkeypatch.setattr(config, "SQLITE_PATH", str(tmp_path / "ai_sales.sqlite"))
    return tmp_path / "ai_sales.sqlite"


class TestSqliteBackend:
    def test_builds_database_on_first_connection(self, sqlite_backend):
        assert not sqlite_backend.exists()
        ok, info = database.test_connection()
        assert ok
        assert info.startswith("SQLite")
        assert sqlite_backend.exists()

    def test_schema_matches_mysql_tables(self, sqlite_backend):
        schema = database.get_schema()
        assert set(schema) == {"customers", "orders", "products"}
        assert "amount (decimal(10,2))" in schema["orders"]
        assert schema["customers"][0] == "customer_id (integer)"

    def test_relationships(self, sqlite_backend):
        assert database.get_relationships() == [
            "orders.customer_id -> customers.customer_id",
            "orders.product_id -> products.product_id",
        ]

    def test_row_counts(self, sqlite_backend):
        for table, expected in (("customers", 8), ("products", 8), ("orders", 14)):
            df = database.execute_query(f"SELECT COUNT(*) AS n FROM {table}")
            assert df["n"][0] == expected

    def test_total_sales(self, sqlite_backend):
        df = database.execute_query("SELECT SUM(amount) AS total_sales FROM orders")
        assert df["total_sales"][0] == 443900

    def test_top_customer(self, sqlite_backend):
        df = database.execute_query(
            "SELECT c.name, SUM(o.amount) AS total FROM orders o "
            "JOIN customers c ON c.customer_id = o.customer_id "
            "GROUP BY c.name ORDER BY total DESC LIMIT 1"
        )
        assert df["name"][0] == "Rohit Verma"
        assert df["total"][0] == 137000

    def test_respects_max_rows(self, sqlite_backend):
        df = database.execute_query("SELECT * FROM orders", max_rows=3)
        assert len(df) == 3

    def test_connection_is_read_only(self, sqlite_backend):
        with pytest.raises(RuntimeError, match="readonly"):
            database.execute_query("DELETE FROM orders")
        df = database.execute_query("SELECT COUNT(*) AS n FROM orders")
        assert df["n"][0] == 14

    def test_bad_sql_raises_runtime_error(self, sqlite_backend):
        with pytest.raises(RuntimeError, match="no such table"):
            database.execute_query("SELECT * FROM missing_table")
