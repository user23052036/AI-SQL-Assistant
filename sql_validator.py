"""SQL safety validation — ensures only read-only SELECT queries reach MySQL."""

import re
import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DDL, DML


# Statements that must never reach the database
_FORBIDDEN_STATEMENT_TYPES = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
    "TRUNCATE", "RENAME", "CREATE", "GRANT", "REVOKE",
    "REPLACE", "CALL", "EXECUTE", "EXEC",
    "LOAD", "IMPORT", "COPY", "MERGE",
}

# Pattern to strip markdown SQL fences
_FENCE_PATTERN = re.compile(r"```(?:sql)?", re.IGNORECASE)

# Pattern to detect multiple statements (look for ; not inside strings)
_MULTI_STATEMENT_PATTERN = re.compile(r";(?!\s*$)")


def _strip_fences(sql: str) -> str:
    return _FENCE_PATTERN.sub("", sql).strip()


def _extract_first_keyword(statement: Statement) -> str:
    """Return the first meaningful DML/DDL keyword from a parsed statement."""
    for token in statement.tokens:
        ttype = token.ttype
        if ttype in (DML, DDL, Keyword):
            return token.normalized.upper()
        # Skip whitespace and comments
        if ttype is not None and str(ttype).startswith("Token.Text"):
            continue
    return ""


def normalize_sql(sql: str) -> str:
    """Strip fences and excess whitespace; return cleaned SQL string."""
    return _strip_fences(sql).strip()


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    Validate that sql is a safe, read-only SELECT query.

    Returns (True, "SQL query is safe.") on success.
    Returns (False, reason) on failure.

    Validation layers:
    1. Empty/blank check
    2. Markdown fence stripping
    3. Multiple-statement detection
    4. sqlparse-based statement type check (primary gate)
    5. Regex forbidden-keyword scan (defence-in-depth against comment tricks)
    6. Dangerous-pattern heuristics (stacked comments, batch separators)
    """
    if not sql or not sql.strip():
        return False, "SQL query is empty."

    sql = normalize_sql(sql)

    if not sql:
        return False, "SQL query is empty after normalization."

    # ── Multi-statement check ─────────────────────────────────────────────
    # Strip the trailing semicolon, then look for any remaining semicolons.
    sql_no_trailing = sql.rstrip("; \t\n")
    if ";" in sql_no_trailing:
        return False, "Multiple SQL statements are not allowed."

    # ── sqlparse structural check ─────────────────────────────────────────
    try:
        parsed = sqlparse.parse(sql)
        if not parsed or not parsed[0].tokens:
            return False, "SQL could not be parsed."

        statement = parsed[0]
        first_keyword = _extract_first_keyword(statement)

        if first_keyword != "SELECT":
            if first_keyword:
                return False, f"Only SELECT queries are allowed. Got: {first_keyword}"
            # Fallback: check stripped text starts with SELECT
            if not re.match(r"^SELECT\b", sql, re.IGNORECASE):
                return False, "Only SELECT queries are allowed."
    except Exception:
        # sqlparse failure — fall through to regex checks
        if not re.match(r"^SELECT\b", sql, re.IGNORECASE):
            return False, "Only SELECT queries are allowed."

    # ── Regex defence-in-depth ────────────────────────────────────────────
    # Strip comments, then string-literal content, before keyword scanning.
    # Stripping string literals prevents false positives like:
    #   SELECT * FROM t WHERE name = 'Delete Me'
    # while still catching actual forbidden keywords in the SQL structure.
    sql_no_comments = re.sub(r"--[^\n]*", " ", sql)
    sql_no_comments = re.sub(r"/\*.*?\*/", " ", sql_no_comments, flags=re.DOTALL)
    # Remove the contents of single- and double-quoted string literals.
    sql_no_strings = re.sub(r"'[^']*'", "''", sql_no_comments)
    sql_no_strings = re.sub(r'"[^"]*"', '""', sql_no_strings)
    upper = sql_no_strings.upper()

    for keyword in _FORBIDDEN_STATEMENT_TYPES:
        if re.search(rf"\b{re.escape(keyword)}\b", upper):
            return False, f"Forbidden SQL keyword detected: {keyword}"

    # ── Heuristic: batch separator ────────────────────────────────────────
    if re.search(r"^\s*GO\s*$", upper, re.MULTILINE):
        return False, "Batch separator GO is not allowed."

    # ── Heuristic: INFORMATION_SCHEMA / mysql system schema writes ────────
    # Reading from INFORMATION_SCHEMA is fine; we only block writes above.

    return True, "SQL query is safe."
