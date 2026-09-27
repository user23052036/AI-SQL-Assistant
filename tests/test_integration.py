"""
Integration tests — require a live MySQL database.
Skipped automatically when DB_HOST / credentials are unavailable.

Run with:
    pytest tests/test_integration.py -v

Expected data totals from database.sql:
  - 8 customers
  - 8 products
  - 14 orders
  - total_sales = 443900
  - top customer by purchase = Rohit Verma (137000)
  - customers in Pune = 1 (Priya Patil)
"""

import pytest
import pandas as pd

# Skip every test in this module if the database is not reachable
pytestmark = pytest.mark.skipif(
    True,  # overridden below after import attempt
    reason="Live DB not available",
)


def _check_db() -> bool:
    try:
        from database import test_connection
        ok, _ = test_connection()
        return ok
    except Exception:
        return False


# Re-evaluate the skip condition at collection time
_db_available = _check_db()

pytestmark = pytest.mark.skipif(
    not _db_available,
    reason="Live MySQL database not reachable — skipping integration tests",
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_schema():
    from database import get_schema
    return get_schema()


@pytest.fixture(scope="module")
def db_relationships():
    from database import get_relationships
    return get_relationships()


# ── Schema discovery ──────────────────────────────────────────────────────────

class TestSchemaDiscovery:
    def test_expected_tables_present(self, db_schema):
        assert "customers" in db_schema
        assert "products" in db_schema
        assert "orders" in db_schema

    def test_customer_columns(self, db_schema):
        cols_text = " ".join(db_schema["customers"])
        assert "customer_id" in cols_text
        assert "name" in cols_text
        assert "city" in cols_text

    def test_orders_columns(self, db_schema):
        cols_text = " ".join(db_schema["orders"])
        assert "customer_id" in cols_text
        assert "product_id" in cols_text
        assert "amount" in cols_text


class TestRelationshipDiscovery:
    def test_fk_customers(self, db_relationships):
        assert any("orders.customer_id" in r for r in db_relationships)

    def test_fk_products(self, db_relationships):
        assert any("orders.product_id" in r for r in db_relationships)


# ── Query execution ───────────────────────────────────────────────────────────

class TestQueryExecution:
    def _run(self, sql: str) -> pd.DataFrame:
        from database import execute_query
        return execute_query(sql)

    def test_customers_row_count(self):
        df = self._run("SELECT COUNT(*) AS n FROM customers")
        assert df.iloc[0, 0] == 8

    def test_products_row_count(self):
        df = self._run("SELECT COUNT(*) AS n FROM products")
        assert df.iloc[0, 0] == 8

    def test_orders_row_count(self):
        df = self._run("SELECT COUNT(*) AS n FROM orders")
        assert df.iloc[0, 0] == 14

    def test_total_sales(self):
        """Total of all order amounts = 443900 (calculated from database.sql data)."""
        df = self._run("SELECT SUM(amount) AS total_sales FROM orders")
        assert float(df.iloc[0, 0]) == pytest.approx(443900.0, abs=1.0)

    def test_customers_from_pune(self):
        df = self._run("SELECT * FROM customers WHERE city = 'Pune'")
        assert len(df) == 1
        assert df.iloc[0]["name"] == "Priya Patil"

    def test_top_customer_by_purchase(self):
        """Rohit Verma should have the highest total purchase (137000)."""
        df = self._run(
            "SELECT c.name, SUM(o.amount) AS total_purchase "
            "FROM customers c JOIN orders o ON c.customer_id = o.customer_id "
            "GROUP BY c.customer_id, c.name "
            "ORDER BY total_purchase DESC LIMIT 1"
        )
        assert len(df) == 1
        assert df.iloc[0]["name"] == "Rohit Verma"
        assert float(df.iloc[0]["total_purchase"]) == pytest.approx(137000.0, abs=1.0)

    def test_top_5_customers(self):
        """Top 5 customers by DESC total should include the 5 highest spenders."""
        df = self._run(
            "SELECT c.name, SUM(o.amount) AS total_purchase "
            "FROM customers c JOIN orders o ON c.customer_id = o.customer_id "
            "GROUP BY c.customer_id, c.name "
            "ORDER BY total_purchase DESC LIMIT 5"
        )
        assert len(df) == 5
        names = df["name"].tolist()
        # Rohit must be first (137000)
        assert names[0] == "Rohit Verma"
        # All 5 must appear
        for expected in ["Rohit Verma", "Rahul Sharma", "Neha Singh", "Pooja Deshmukh", "Amit Kumar"]:
            assert expected in names

    def test_most_revenue_product(self):
        """Laptop should be the highest-revenue product (195000 total)."""
        df = self._run(
            "SELECT p.product_name, SUM(o.amount) AS revenue "
            "FROM products p JOIN orders o ON p.product_id = o.product_id "
            "GROUP BY p.product_id, p.product_name "
            "ORDER BY revenue DESC LIMIT 1"
        )
        assert len(df) == 1
        assert df.iloc[0]["product_name"] == "Laptop"

    def test_empty_result(self):
        from database import execute_query
        df = execute_query("SELECT * FROM customers WHERE city = 'Atlantis'")
        assert df.empty

    def test_max_rows_limit(self):
        from database import execute_query
        df = execute_query("SELECT * FROM orders", max_rows=3)
        assert len(df) <= 3


class TestQueryErrors:
    def test_nonexistent_table_raises_runtime_error(self):
        from database import execute_query
        with pytest.raises(RuntimeError):
            execute_query("SELECT * FROM nonexistent_table_xyz")

    def test_nonexistent_column_raises_runtime_error(self):
        from database import execute_query
        with pytest.raises(RuntimeError):
            execute_query("SELECT nonexistent_column FROM customers")
