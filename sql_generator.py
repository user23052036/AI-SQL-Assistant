"""Groq-based SQL generation and SQL explanation."""

import re
from groq import Groq

import config
from sql_validator import normalize_sql


def _get_client() -> Groq:
    if not config.GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file and restart the application."
        )
    return Groq(api_key=config.GROQ_API_KEY)


def _clean_sql_output(text: str) -> str:
    """Strip markdown fences and surrounding whitespace from LLM output."""
    return normalize_sql(text)


def generate_sql(
    question: str,
    schema: dict[str, list[str]],
    relationships: list[str],
) -> str:
    """
    Convert a natural-language question into a MySQL SELECT query using Groq.

    Args:
        question: The user's natural-language question.
        schema: Dict of table -> [column (type), ...] from database.get_schema().
        relationships: List of FK strings from database.get_relationships().

    Returns:
        A SQL string (not yet validated or executed).

    Raises:
        RuntimeError: If the Groq API key is missing or the request fails.
    """
    client = _get_client()

    schema_text = ""
    for table, columns in schema.items():
        schema_text += f"\nTABLE: {table}\n"
        for col in columns:
            schema_text += f"  - {col}\n"

    relationship_text = (
        "\n".join(relationships) if relationships else "No explicit FK relationships found."
    )

    prompt = f"""You are an expert {config.SQL_DIALECT} developer.

Convert the user's natural-language question into a valid {config.SQL_DIALECT} SELECT query.

DATABASE SCHEMA:
{schema_text}

FOREIGN KEY RELATIONSHIPS:
{relationship_text}

USER QUESTION:
{question}

RULES:
1. Generate ONLY a SELECT query — never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, or REVOKE.
2. Use ONLY tables and columns that appear in the schema above.
3. Use correct JOIN conditions based on the relationships listed.
4. Use valid {config.SQL_DIALECT} syntax.
5. Return ONLY the SQL query — no explanation, no markdown, no code fences.
6. Use table aliases for readability.
7. Do not include a trailing semicolon.
"""

    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": f"You are an expert {config.SQL_DIALECT} SELECT query generator. You output only raw SQL.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=512,
    )

    raw = response.choices[0].message.content or ""
    return _clean_sql_output(raw)


def correct_sql(
    original_question: str,
    bad_sql: str,
    db_error: str,
    schema: dict[str, list[str]],
    relationships: list[str],
) -> str:
    """
    Ask Groq to fix a SQL query that MySQL rejected.

    The db_error is sanitised so that no credentials or connection strings
    are forwarded to the LLM.

    Returns:
        Corrected SQL string (not yet validated).
    """
    client = _get_client()

    # Sanitise: keep only the MySQL error text, strip anything after ':'
    # that might include host/user fragments. Real MySQL errors look like
    # "Table 'ai_sales.foo' doesn't exist" — safe to forward.
    safe_error = re.sub(r"(password|host|user|port)=[^\s,)]*", "[REDACTED]", db_error, flags=re.IGNORECASE)

    schema_text = ""
    for table, columns in schema.items():
        schema_text += f"\nTABLE: {table}\n"
        for col in columns:
            schema_text += f"  - {col}\n"

    prompt = f"""The following {config.SQL_DIALECT} SELECT query was rejected by the database.

ORIGINAL QUESTION:
{original_question}

FAILED SQL:
{bad_sql}

DATABASE ERROR:
{safe_error}

DATABASE SCHEMA:
{schema_text}

Please produce a corrected {config.SQL_DIALECT} SELECT query that answers the original question.
Return ONLY the corrected SQL — no explanation, no markdown, no code fences.
Do not include a trailing semicolon.
"""

    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": f"You are an expert {config.SQL_DIALECT} query debugger."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=512,
    )

    raw = response.choices[0].message.content or ""
    return _clean_sql_output(raw)


def explain_sql(sql: str) -> str:
    """
    Return a plain-English explanation of a MySQL query, suitable for beginners.

    Raises:
        RuntimeError: If the Groq API key is missing or the request fails.
    """
    client = _get_client()

    prompt = f"""Explain this {config.SQL_DIALECT} query in simple language for a beginner software engineer.

SQL:
{sql}

Cover:
1. Which tables are used
2. Joins (if any) and why
3. Filtering (WHERE clause)
4. Grouping (GROUP BY)
5. Sorting (ORDER BY)
6. Aggregation (SUM, COUNT, AVG, etc.)
7. What the final result represents

Be concise and avoid jargon. Do not claim the explanation proves the query is correct.
"""

    response = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": "You explain SQL queries clearly and simply."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=600,
    )

    return response.choices[0].message.content or "No explanation generated."
