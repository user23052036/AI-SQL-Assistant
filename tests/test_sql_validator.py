"""Comprehensive tests for sql_validator.py — safety and correctness."""

import pytest
from sql_validator import validate_sql, normalize_sql


# ── Helpers ───────────────────────────────────────────────────────────────────

def assert_safe(sql: str):
    ok, msg = validate_sql(sql)
    assert ok, f"Expected SAFE but got UNSAFE for: {sql!r}\nReason: {msg}"


def assert_unsafe(sql: str, contains: str = ""):
    ok, msg = validate_sql(sql)
    assert not ok, f"Expected UNSAFE but got SAFE for: {sql!r}"
    if contains:
        assert contains.lower() in msg.lower(), (
            f"Expected reason to contain {contains!r}, got: {msg!r}"
        )


# ── Safe queries ──────────────────────────────────────────────────────────────

class TestSafeQueries:
    def test_simple_select(self):
        assert_safe("SELECT * FROM customers")

    def test_select_with_where(self):
        assert_safe("SELECT * FROM customers WHERE city = 'Pune'")

    def test_select_with_join(self):
        assert_safe(
            "SELECT c.name, SUM(o.amount) AS total "
            "FROM customers c JOIN orders o ON c.customer_id = o.customer_id "
            "GROUP BY c.customer_id ORDER BY total DESC LIMIT 5"
        )

    def test_select_aggregate(self):
        assert_safe("SELECT SUM(amount) AS total_sales FROM orders")

    def test_select_uppercase(self):
        assert_safe("SELECT product_name FROM products ORDER BY price DESC LIMIT 1")

    def test_select_lowercase(self):
        assert_safe("select * from customers")

    def test_select_mixed_case(self):
        assert_safe("Select * From Customers Where City = 'Mumbai'")

    def test_select_with_trailing_whitespace(self):
        assert_safe("SELECT * FROM products   ")

    def test_select_with_leading_whitespace(self):
        assert_safe("   SELECT * FROM products")

    def test_select_with_subquery(self):
        assert_safe(
            "SELECT * FROM customers WHERE customer_id IN "
            "(SELECT customer_id FROM orders WHERE amount > 50000)"
        )

    def test_select_with_cte(self):
        assert_safe(
            "WITH ranked AS (SELECT customer_id, SUM(amount) AS total "
            "FROM orders GROUP BY customer_id) "
            "SELECT * FROM ranked ORDER BY total DESC"
        )

    def test_select_from_information_schema(self):
        # Reading INFORMATION_SCHEMA is acceptable (schema discovery)
        assert_safe("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'ai_sales'")

    def test_select_with_markdown_fence_backtick(self):
        sql = "```sql\nSELECT * FROM customers\n```"
        assert_safe(sql)

    def test_select_with_markdown_fence_no_lang(self):
        sql = "```\nSELECT * FROM customers\n```"
        assert_safe(sql)

    def test_select_word_delete_inside_string_literal(self):
        # The word DELETE appears inside a string value — should still be safe
        # because the query itself is SELECT and no DELETE keyword appears as a statement
        assert_safe("SELECT * FROM customers WHERE name = 'Delete Me'")


# ── Dangerous DML / DDL ───────────────────────────────────────────────────────

class TestForbiddenStatements:
    def test_insert_uppercase(self):
        assert_unsafe("INSERT INTO customers VALUES (1, 'x', 'x@x.com', 'X', '2025-01-01')", "INSERT")

    def test_insert_lowercase(self):
        assert_unsafe("insert into customers values (1,'a','a@a.com','A','2025-01-01')")

    def test_update_uppercase(self):
        assert_unsafe("UPDATE customers SET city = 'Chennai' WHERE customer_id = 1", "UPDATE")

    def test_update_lowercase(self):
        assert_unsafe("update customers set city='Chennai' where customer_id=1")

    def test_delete_uppercase(self):
        assert_unsafe("DELETE FROM orders WHERE order_id = 5", "DELETE")

    def test_delete_lowercase(self):
        assert_unsafe("delete from orders where order_id=5")

    def test_drop_table(self):
        assert_unsafe("DROP TABLE orders", "DROP")

    def test_drop_database(self):
        assert_unsafe("DROP DATABASE ai_sales", "DROP")

    def test_alter_table(self):
        assert_unsafe("ALTER TABLE customers ADD COLUMN phone VARCHAR(20)", "ALTER")

    def test_truncate(self):
        assert_unsafe("TRUNCATE TABLE orders", "TRUNCATE")

    def test_create_table(self):
        assert_unsafe("CREATE TABLE tmp (id INT)", "CREATE")

    def test_grant(self):
        assert_unsafe("GRANT SELECT ON ai_sales.* TO 'user'@'localhost'", "GRANT")

    def test_revoke(self):
        assert_unsafe("REVOKE SELECT ON ai_sales.* FROM 'user'@'localhost'", "REVOKE")

    def test_rename(self):
        assert_unsafe("RENAME TABLE orders TO old_orders", "RENAME")

    def test_replace(self):
        assert_unsafe("REPLACE INTO customers VALUES (1,'x','x@x.com','X','2025-01-01')", "REPLACE")


# ── Mixed-case attempts to bypass ────────────────────────────────────────────

class TestMixedCaseBypass:
    def test_drop_mixed_case(self):
        assert_unsafe("DrOp TaBlE customers")

    def test_delete_mixed_case(self):
        assert_unsafe("DeLeTe FrOm orders WHERE order_id=1")

    def test_update_mixed_case(self):
        assert_unsafe("UpDaTe customers SET city='X'")


# ── Comment-hiding attempts ───────────────────────────────────────────────────

class TestCommentHiding:
    def test_select_with_line_comment_hiding_drop(self):
        # SELECT is first keyword, but DROP in comment should be caught
        # after stripping comments from the forbidden-keyword scan
        sql = "SELECT * FROM customers -- DROP TABLE customers"
        # This is safe — DROP is in a comment, so it's fine for line comments.
        # Our validator strips line comments before scanning, so it's detected.
        # Behaviour: this should be SAFE because the dangerous word is in a comment
        # and the statement is a SELECT. The comment-strip approach prevents
        # `-- DROP TABLE` from bypassing — and also means the SELECT itself runs.
        # We want the query to run (it's just a comment), so accept it as safe.
        ok, _ = validate_sql(sql)
        # DROP in a line comment is informational noise; the actual statement is SELECT.
        # Implementation detail: after stripping comments the upper-scan sees only
        # "SELECT * FROM customers" so it passes. This is correct behaviour.
        assert ok  # safe: DROP is only in a comment

    def test_block_comment_hiding_update(self):
        sql = "SELECT * FROM customers /* UPDATE customers SET city='X' */"
        # After stripping block comments, forbidden keyword scan sees only SELECT clause
        ok, _ = validate_sql(sql)
        assert ok  # safe: UPDATE is inside a block comment

    def test_stacked_comment_drop(self):
        # Attempt: use a block comment to inject a keyword before SELECT
        sql = "/* DROP TABLE orders */ SELECT * FROM customers"
        ok, _ = validate_sql(sql)
        assert ok  # block comment stripped; SELECT remains

    def test_non_select_after_comment(self):
        # First token after stripping should not be SELECT
        sql = "DELETE FROM orders -- this is a comment"
        assert_unsafe(sql)


# ── Multiple statements ───────────────────────────────────────────────────────

class TestMultipleStatements:
    def test_two_selects(self):
        assert_unsafe("SELECT * FROM customers; SELECT * FROM orders", "multiple")

    def test_select_then_drop(self):
        assert_unsafe("SELECT * FROM customers; DROP TABLE customers", "multiple")

    def test_trailing_semicolon_only(self):
        # A trailing semicolon after a single SELECT is acceptable
        ok, _ = validate_sql("SELECT * FROM customers;")
        assert ok


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_string(self):
        assert_unsafe("")

    def test_whitespace_only(self):
        assert_unsafe("   \t\n  ")

    def test_none_value(self):
        assert_unsafe(None)

    def test_markdown_fence_only(self):
        assert_unsafe("```sql\n```")

    def test_gibberish(self):
        assert_unsafe("xyzzy frobble plugh")

    def test_integer_only(self):
        assert_unsafe("42")

    def test_very_long_select(self):
        long_sql = "SELECT " + ", ".join([f"col{i}" for i in range(200)]) + " FROM customers"
        # Should still pass validation (it's a valid SELECT structure)
        ok, _ = validate_sql(long_sql)
        assert ok


# ── normalize_sql ─────────────────────────────────────────────────────────────

class TestNormalizeSql:
    def test_strips_sql_fence(self):
        result = normalize_sql("```sql\nSELECT 1\n```")
        assert "```" not in result
        assert "SELECT 1" in result

    def test_strips_plain_fence(self):
        result = normalize_sql("```\nSELECT 1\n```")
        assert "```" not in result

    def test_strips_whitespace(self):
        result = normalize_sql("  SELECT 1  ")
        assert result == "SELECT 1"

    def test_passthrough_clean_sql(self):
        sql = "SELECT * FROM customers"
        assert normalize_sql(sql) == sql
