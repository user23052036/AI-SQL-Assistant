"""Unit tests for database.py using mocks (no live DB required)."""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, PropertyMock

import database


class TestGetConnection:
    @patch("database.mysql.connector.connect")
    def test_calls_connect_with_config(self, mock_connect):
        mock_connect.return_value = MagicMock()
        database.get_connection()
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        assert "host" in call_kwargs
        assert "database" in call_kwargs

    @patch("database.mysql.connector.connect")
    def test_raises_on_connection_failure(self, mock_connect):
        import mysql.connector
        mock_connect.side_effect = mysql.connector.Error("Connection refused")
        with pytest.raises(mysql.connector.Error):
            database.get_connection()


class TestTestConnection:
    @patch("database.get_connection")
    def test_returns_true_on_success(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("8.0.33",)
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        ok, info = database.test_connection()
        assert ok is True
        assert "8.0.33" in info

    @patch("database.get_connection")
    def test_returns_false_on_failure(self, mock_get_conn):
        import mysql.connector
        mock_get_conn.side_effect = mysql.connector.Error("Access denied")

        ok, info = database.test_connection()
        assert ok is False
        assert "Access denied" in info


class TestGetSchema:
    @patch("database.get_connection")
    def test_returns_schema_dict(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("customers", "customer_id", "int"),
            ("customers", "name", "varchar"),
            ("orders", "order_id", "int"),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        schema = database.get_schema()
        assert "customers" in schema
        assert "orders" in schema
        assert any("customer_id" in c for c in schema["customers"])
        assert any("name" in c for c in schema["customers"])

    @patch("database.get_connection")
    def test_empty_database_returns_empty_dict(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        schema = database.get_schema()
        assert schema == {}


class TestGetRelationships:
    @patch("database.get_connection")
    def test_returns_relationship_strings(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("orders", "customer_id", "customers", "customer_id"),
            ("orders", "product_id", "products", "product_id"),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        rels = database.get_relationships()
        assert len(rels) == 2
        assert "orders.customer_id -> customers.customer_id" in rels
        assert "orders.product_id -> products.product_id" in rels

    @patch("database.get_connection")
    def test_no_relationships_returns_empty_list(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        rels = database.get_relationships()
        assert rels == []


class TestExecuteQuery:
    @patch("database.get_connection")
    def test_returns_dataframe(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.return_value = [(1, "Rahul", "Mumbai")]
        mock_cursor.description = [("customer_id",), ("name",), ("city",)]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        df = database.execute_query("SELECT customer_id, name, city FROM customers")
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["customer_id", "name", "city"]
        assert len(df) == 1

    @patch("database.get_connection")
    def test_empty_result_returns_empty_dataframe(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchmany.return_value = []
        mock_cursor.description = [("customer_id",), ("name",)]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        df = database.execute_query("SELECT * FROM customers WHERE 1=0")
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    @patch("database.get_connection")
    def test_raises_runtime_error_on_db_error(self, mock_get_conn):
        import mysql.connector
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = mysql.connector.Error("Table doesn't exist")
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        with pytest.raises(RuntimeError, match="Table doesn't exist"):
            database.execute_query("SELECT * FROM nonexistent")


class TestSchemaToText:
    def test_formats_correctly(self, sample_schema):
        text = database.schema_to_text(sample_schema)
        assert "TABLE: customers" in text
        assert "customer_id (int)" in text
        assert "TABLE: products" in text

    def test_empty_schema(self):
        text = database.schema_to_text({})
        assert text == ""
