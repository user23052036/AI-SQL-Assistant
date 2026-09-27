"""Unit tests for sql_generator.py using mocked Groq client."""

import pytest
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_groq_response(content: str) -> MagicMock:
    """Build a fake Groq ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


# ── generate_sql ──────────────────────────────────────────────────────────────

class TestGenerateSql:
    @patch("sql_generator.config.GROQ_API_KEY", "fake-key")
    @patch("sql_generator.Groq")
    def test_returns_sql_string(self, MockGroq, sample_schema, sample_relationships):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(
            "SELECT * FROM customers WHERE city = 'Pune'"
        )
        MockGroq.return_value = mock_client

        from sql_generator import generate_sql
        result = generate_sql("Show customers from Pune", sample_schema, sample_relationships)
        assert "SELECT" in result.upper()
        assert "customers" in result.lower()

    @patch("sql_generator.config.GROQ_API_KEY", "fake-key")
    @patch("sql_generator.Groq")
    def test_strips_markdown_fences(self, MockGroq, sample_schema, sample_relationships):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(
            "```sql\nSELECT * FROM customers\n```"
        )
        MockGroq.return_value = mock_client

        from sql_generator import generate_sql
        result = generate_sql("Show all customers", sample_schema, sample_relationships)
        assert "```" not in result
        assert "SELECT" in result.upper()

    @patch("sql_generator.config.GROQ_API_KEY", "")
    def test_raises_when_api_key_missing(self, sample_schema, sample_relationships):
        from sql_generator import generate_sql
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            generate_sql("Show customers", sample_schema, sample_relationships)

    @patch("sql_generator.config.GROQ_API_KEY", "fake-key")
    @patch("sql_generator.Groq")
    def test_api_failure_raises_exception(self, MockGroq, sample_schema, sample_relationships):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Rate limit exceeded")
        MockGroq.return_value = mock_client

        from sql_generator import generate_sql
        with pytest.raises(Exception, match="Rate limit exceeded"):
            generate_sql("Show customers", sample_schema, sample_relationships)


# ── explain_sql ───────────────────────────────────────────────────────────────

class TestExplainSql:
    @patch("sql_generator.config.GROQ_API_KEY", "fake-key")
    @patch("sql_generator.Groq")
    def test_returns_explanation_string(self, MockGroq):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(
            "This query selects all customers from the customers table."
        )
        MockGroq.return_value = mock_client

        from sql_generator import explain_sql
        result = explain_sql("SELECT * FROM customers")
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("sql_generator.config.GROQ_API_KEY", "")
    def test_raises_when_api_key_missing(self):
        from sql_generator import explain_sql
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            explain_sql("SELECT * FROM customers")


# ── correct_sql ───────────────────────────────────────────────────────────────

class TestCorrectSql:
    @patch("sql_generator.config.GROQ_API_KEY", "fake-key")
    @patch("sql_generator.Groq")
    def test_returns_corrected_sql(self, MockGroq, sample_schema, sample_relationships):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(
            "SELECT * FROM customers WHERE city = 'Pune'"
        )
        MockGroq.return_value = mock_client

        from sql_generator import correct_sql
        result = correct_sql(
            "Show Pune customers",
            "SELECT * FROM customres WHERE city = 'Pune'",
            "Table 'ai_sales.customres' doesn't exist",
            sample_schema,
            sample_relationships,
        )
        assert "SELECT" in result.upper()

    @patch("sql_generator.config.GROQ_API_KEY", "fake-key")
    @patch("sql_generator.Groq")
    def test_sanitises_credentials_from_error(self, MockGroq, sample_schema, sample_relationships):
        """Ensure password/host info in errors is scrubbed before LLM call."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_groq_response(
            "SELECT * FROM customers"
        )
        MockGroq.return_value = mock_client

        from sql_generator import correct_sql
        correct_sql(
            "Show customers",
            "SELECT * FROM customers",
            "Access denied for user 'root'@'localhost' (using password=YES)",
            sample_schema,
            sample_relationships,
        )

        call_args = mock_client.chat.completions.create.call_args
        prompt_text = str(call_args)
        assert "password=YES" not in prompt_text
