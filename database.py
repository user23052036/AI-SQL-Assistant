"""MySQL database connection, schema discovery, and query execution."""

import mysql.connector
import pandas as pd
from mysql.connector import Error as MySQLError

import config


def get_connection() -> mysql.connector.MySQLConnection:
    """Return a live MySQL connection using env-based credentials."""
    return mysql.connector.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        connection_timeout=config.QUERY_TIMEOUT,
    )


def test_connection() -> tuple[bool, str]:
    """Return (True, version_string) on success or (False, error_message)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return True, f"MySQL {version}"
    except MySQLError as exc:
        return False, str(exc)


def get_schema() -> dict[str, list[str]]:
    """
    Return a dict mapping table names to lists of 'column (type)' strings.
    Reads from INFORMATION_SCHEMA for the current database.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    schema: dict[str, list[str]] = {}
    for table, column, data_type in rows:
        schema.setdefault(table, []).append(f"{column} ({data_type})")
    return schema


def get_relationships() -> list[str]:
    """
    Return foreign-key relationships as human-readable strings.
    Example: 'orders.customer_id -> customers.customer_id'
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME,
                   REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND REFERENCED_TABLE_NAME IS NOT NULL
            ORDER BY TABLE_NAME, COLUMN_NAME
            """
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return [
        f"{tbl}.{col} -> {ref_tbl}.{ref_col}"
        for tbl, col, ref_tbl, ref_col in rows
    ]


def execute_query(sql: str, max_rows: int = config.MAX_ROWS) -> pd.DataFrame:
    """
    Execute a read-only SQL query and return results as a DataFrame.
    Raises RuntimeError on database errors; limits results to max_rows.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchmany(max_rows)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        # Drain any remaining rows so mysql.connector doesn't raise
        # "Unread result found" when the cursor is closed.
        if cursor.with_rows:
            cursor.fetchall()
        return pd.DataFrame(rows, columns=columns)
    except MySQLError as exc:
        raise RuntimeError(str(exc)) from exc
    finally:
        cursor.close()
        conn.close()


def schema_to_text(schema: dict[str, list[str]]) -> str:
    """Format schema dict as a readable block for LLM prompts."""
    lines = []
    for table, columns in schema.items():
        lines.append(f"\nTABLE: {table}")
        for col in columns:
            lines.append(f"  - {col}")
    return "\n".join(lines)
