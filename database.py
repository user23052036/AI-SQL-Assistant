"""Database connection, schema discovery, and query execution (MySQL or SQLite)."""

import os
import sqlite3
import tempfile

import mysql.connector
import pandas as pd
from mysql.connector import Error as MySQLError

import config

SQLITE_SEED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database_sqlite.sql")


def _use_sqlite() -> bool:
    return config.DB_BACKEND == "sqlite"


def _sqlite_path() -> str:
    """Return the SQLite file path, building it from the seed script if missing."""
    path = config.SQLITE_PATH or os.path.join(tempfile.gettempdir(), "ai_sales.sqlite")
    if not os.path.exists(path):
        with open(SQLITE_SEED, encoding="utf-8") as f:
            script = f.read()
        # Build into a temp file and rename, so concurrent sessions never see
        # a half-written database.
        fd, tmp = tempfile.mkstemp(suffix=".sqlite", dir=os.path.dirname(path) or ".")
        os.close(fd)
        conn = sqlite3.connect(tmp)
        try:
            conn.executescript(script)
            conn.commit()
        finally:
            conn.close()
        os.replace(tmp, path)
    return path


def _get_sqlite_connection() -> sqlite3.Connection:
    """Open the SQLite database read-only, so no query can modify it."""
    return sqlite3.connect(
        f"file:{_sqlite_path()}?mode=ro", uri=True, timeout=config.QUERY_TIMEOUT
    )


def get_connection():
    """Return a live connection: read-only SQLite, or MySQL using env-based credentials."""
    if _use_sqlite():
        return _get_sqlite_connection()
    params = dict(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        connection_timeout=config.QUERY_TIMEOUT,
    )
    if config.DB_SSL:
        params["ssl_disabled"] = False
        if config.DB_SSL_CA:
            params["ssl_ca"] = config.DB_SSL_CA
            params["ssl_verify_cert"] = True
    return mysql.connector.connect(**params)


def test_connection() -> tuple[bool, str]:
    """Return (True, version_string) on success or (False, error_message)."""
    if _use_sqlite():
        try:
            get_connection().close()
            return True, f"SQLite {sqlite3.sqlite_version}"
        except (sqlite3.Error, OSError) as exc:
            return False, str(exc)
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
    Reads from INFORMATION_SCHEMA (MySQL) or PRAGMA table_info (SQLite).
    """
    if _use_sqlite():
        conn = get_connection()
        try:
            schema: dict[str, list[str]] = {}
            for table in _sqlite_tables(conn):
                cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
                schema[table] = [f"{c[1]} ({c[2].lower()})" for c in cols]
            return schema
        finally:
            conn.close()

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
    if _use_sqlite():
        conn = get_connection()
        try:
            rels = []
            for table in _sqlite_tables(conn):
                # PRAGMA row: (id, seq, table, from, to, on_update, on_delete, match)
                for fk in conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
                    rels.append((table, fk[3], fk[2], fk[4]))
        finally:
            conn.close()
        return [
            f"{tbl}.{col} -> {ref_tbl}.{ref_col}"
            for tbl, col, ref_tbl, ref_col in sorted(rels)
        ]

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
    if _use_sqlite():
        conn = get_connection()
        try:
            cursor = conn.execute(sql)
            rows = cursor.fetchmany(max_rows)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            return pd.DataFrame(rows, columns=columns)
        except sqlite3.Error as exc:
            raise RuntimeError(str(exc)) from exc
        finally:
            conn.close()

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


def _sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def schema_to_text(schema: dict[str, list[str]]) -> str:
    """Format schema dict as a readable block for LLM prompts."""
    lines = []
    for table, columns in schema.items():
        lines.append(f"\nTABLE: {table}")
        for col in columns:
            lines.append(f"  - {col}")
    return "\n".join(lines)
