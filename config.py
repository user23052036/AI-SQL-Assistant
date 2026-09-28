"""Application configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
DB_USER: str = os.getenv("DB_USER", "root")
DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
DB_NAME: str = os.getenv("DB_NAME", "ai_sales")
# Cloud MySQL providers (Aiven, TiDB Cloud, etc.) require TLS.
DB_SSL: bool = os.getenv("DB_SSL", "false").strip().lower() in ("1", "true", "yes")
DB_SSL_CA: str = os.getenv("DB_SSL_CA", "")

MAX_ROWS: int = int(os.getenv("MAX_ROWS", "1000"))
MAX_CORRECTION_ATTEMPTS: int = 2
QUERY_TIMEOUT: int = 30
