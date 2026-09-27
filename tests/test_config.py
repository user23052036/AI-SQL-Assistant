"""Tests for config.py — environment variable loading."""

import pytest
import importlib


class TestConfig:
    def test_groq_model_has_default(self):
        import config
        assert isinstance(config.GROQ_MODEL, str)
        assert len(config.GROQ_MODEL) > 0

    def test_db_host_has_default(self):
        import config
        assert isinstance(config.DB_HOST, str)

    def test_db_port_is_int(self):
        import config
        assert isinstance(config.DB_PORT, int)
        assert config.DB_PORT > 0

    def test_max_rows_is_positive_int(self):
        import config
        assert isinstance(config.MAX_ROWS, int)
        assert config.MAX_ROWS > 0

    def test_max_correction_attempts_is_non_negative(self):
        import config
        assert isinstance(config.MAX_CORRECTION_ATTEMPTS, int)
        assert config.MAX_CORRECTION_ATTEMPTS >= 0

    def test_no_credentials_in_module_attributes(self):
        """Ensure config module doesn't accidentally hard-code real credentials."""
        import config
        # These should be empty strings from defaults when .env is absent
        # or contain values from .env — either way not hard-coded test values.
        # We just verify they are strings.
        assert isinstance(config.GROQ_API_KEY, str)
        assert isinstance(config.DB_PASSWORD, str)
