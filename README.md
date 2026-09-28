# AI SQL Query Generator & Database Assistant

A Streamlit application that converts natural-language questions into validated MySQL SELECT queries using the Groq LLM API, executes them safely, and presents results with automatic visualization.

---

## Project Overview

**Pipeline:**

```
User Question (natural language)
       ↓
Schema + FK relationships (auto-discovered from MySQL)
       ↓
Groq LLM (llama-3.3-70b-versatile)
       ↓
Generated SQL
       ↓
SQL Validator (sqlparse + regex defence-in-depth)
       ↓
  Safe? ── NO ──→ Reject (shown in UI)
  YES
       ↓
MySQL (read-only query execution)
       ↓
Pandas DataFrame
       ↓
Results table + Altair bar chart + CSV download
       ↓
Groq AI explanation (plain English)
```

If MySQL rejects a query, the error is sent back to Groq (with credentials scrubbed) for automatic correction. Correction is attempted up to `MAX_CORRECTION_ATTEMPTS` times, and each corrected query is re-validated before execution.

---

## Technology Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| LLM | Groq (`llama-3.3-70b-versatile`) |
| Database | MySQL |
| Data manipulation | Pandas |
| Visualization | Altair |
| SQL validation | sqlparse + regex |
| Configuration | python-dotenv |

---

## Project Structure

```
AI_SQL_Assistant/
├── app.py               # Streamlit UI with session-state management
├── database.py          # MySQL connection, schema discovery, query execution
├── sql_generator.py     # Groq SQL generation, correction, and explanation
├── sql_validator.py     # SQL safety validation (multi-layer)
├── config.py            # Environment-variable configuration
├── database.sql         # MySQL schema + sample data
├── database_sqlite.sql  # Same schema + data for the SQLite backend
├── requirements.txt
├── .env.example         # Template — copy to .env and fill in
├── .gitignore
├── README.md
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_sql_validator.py   # 54 validator tests (safe + dangerous cases)
    ├── test_database.py        # mocked MySQL DB tests
    ├── test_database_sqlite.py # SQLite backend tests (real temp DB)
    ├── test_sql_generator.py   # 8 mocked Groq tests
    └── test_integration.py     # 13 live-DB tests (skipped if DB unavailable)
```

---

## Prerequisites

- macOS (tested on macOS 13+)
- Python 3.9+
- MySQL 8.0+ (see MySQL setup below)
- A Groq API key — sign up free at https://console.groq.com

---

## Setup

### 1. Clone / enter the project directory

```bash
cd ~/Documents/AI_SQL_Assistant
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```
GROQ_API_KEY=gsk_your_actual_groq_key
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_root_password
DB_NAME=ai_sales
DB_PORT=3306
```

### 5. Install MySQL (macOS)

```bash
brew install mysql
brew services start mysql
mysql_secure_installation   # set root password
```

### 6. Create the database and load sample data

```bash
mysql -u root -p < database.sql
```

Or open MySQL CLI and run:

```sql
SOURCE /path/to/AI_SQL_Assistant/database.sql;
```

Verify:

```sql
USE ai_sales;
SELECT COUNT(*) FROM customers;   -- expects 8
SELECT COUNT(*) FROM products;    -- expects 8
SELECT COUNT(*) FROM orders;      -- expects 14
SELECT SUM(amount) FROM orders;   -- expects 443900
```

### 7. (Optional) Create a read-only MySQL user

```sql
CREATE USER 'ai_sales_ro'@'localhost' IDENTIFIED BY 'choose_a_strong_password';
GRANT SELECT ON ai_sales.* TO 'ai_sales_ro'@'localhost';
FLUSH PRIVILEGES;
```

Then set `DB_USER=ai_sales_ro` and `DB_PASSWORD=...` in `.env`.

---

## Running the Application

```bash
source venv/bin/activate
streamlit run app.py
```

Open: http://localhost:8501

---

## Deployment (Streamlit Community Cloud)

Vercel/Netlify only serve static sites and short-lived functions, so the app is hosted on **Streamlit Community Cloud**.

### Option A — SQLite (no database server needed; used for the live demo)

Set `DB_BACKEND=sqlite`. On first use the app builds a SQLite copy of the same `ai_sales` data from `database_sqlite.sql` and opens it **read-only**, and the LLM is told to write SQLite syntax.

1. On https://share.streamlit.io → *Create app* → pick this repository, branch `main`, main file `app.py`.
2. In *Advanced settings → Secrets* add:
   ```toml
   GROQ_API_KEY = "gsk_..."
   DB_BACKEND = "sqlite"
   ```
   Root-level secrets are exposed as environment variables, which `config.py` reads.

### Option B — cloud MySQL

1. Create a cloud MySQL instance (e.g. Aiven for MySQL) and load the data:
   ```bash
   mysql -h <host> -P <port> -u <user> -p --ssl-mode=REQUIRED < database.sql
   ```
2. Deploy as above, with these secrets:
   ```toml
   GROQ_API_KEY = "gsk_..."
   DB_HOST = "<host>"
   DB_PORT = "<port>"
   DB_USER = "<user>"
   DB_PASSWORD = "<password>"
   DB_NAME = "ai_sales"
   DB_SSL = "true"
   ```
   `DB_SSL=true` turns on TLS, which most cloud MySQL providers require. Set `DB_SSL_CA` to a CA certificate path if you also want the server certificate verified.

---

## Running Tests

```bash
source venv/bin/activate

# All unit tests (no DB or Groq key required):
python -m pytest tests/test_config.py tests/test_sql_validator.py \
    tests/test_database.py tests/test_sql_generator.py -v

# Integration tests (require live MySQL):
python -m pytest tests/test_integration.py -v

# Full suite:
python -m pytest tests/ -v
```

---

## Example Queries

| Natural language | Expected SQL pattern |
|---|---|
| Show all customers from Pune | `SELECT * FROM customers WHERE city = 'Pune'` |
| Show top 5 customers by total purchase | `SELECT … SUM(amount) … ORDER BY … DESC LIMIT 5` |
| What is the total sales? | `SELECT SUM(amount) AS total_sales FROM orders` |
| Which product generated the most revenue? | `SELECT … SUM(o.amount) … ORDER BY revenue DESC LIMIT 1` |

---

## Security Model

**What is protected:**

1. **Statement-type gate (sqlparse)** — The first SQL keyword must be `SELECT`. Any other keyword (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, RENAME, REPLACE, …) is rejected before execution.

2. **Multi-statement check** — Semicolons inside the query body are rejected, preventing stacked statements like `SELECT 1; DROP TABLE orders`.

3. **Regex defence-in-depth** — After stripping SQL comments *and* string literal content, the SQL is scanned for any forbidden keyword. This catches edge cases where sqlparse might misparse unusual input.

4. **No credentials in LLM prompts** — When auto-correcting a failed query, the error message is sanitised with a regex that redacts any `key=value` patterns for `password`, `host`, `user`, or `port`.

5. **Result-size limit** — `execute_query` fetches at most `MAX_ROWS` rows (default 1000), preventing accidental full-table dumps.

6. **No raw stack traces** — Exceptions are caught in the UI and shown as user-friendly messages.

**What is not claimed:**

- This is not a production-hardened security boundary. For production use, add: a dedicated read-only MySQL user, query timeouts at the DB level, network-level firewall rules, and authenticated user sessions.

---

## Known Limitations

1. **MySQL by default** — Set `DB_BACKEND=sqlite` to run on the bundled SQLite copy of the sample data instead (see Deployment).
2. **GROQ_API_KEY required for generation** — SQL generation and explanation are disabled without a valid key. The UI displays a clear warning.
3. **LLM accuracy** — The LLM may generate syntactically valid but semantically incorrect SQL. Always verify critical query results.
4. **String literal false-negative** — The regex scan strips string literal content before checking forbidden keywords, so a string like `'DROP TABLE foo'` in a WHERE clause will not trigger the validator. The statement-type gate (layer 1) prevents this from being exploitable.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Database connection failed" | Check MySQL is running and `.env` credentials are correct (cloud MySQL: set `DB_SSL=true`) |
| "GROQ_API_KEY is not set" | Add your key to `.env` and restart Streamlit |
| "Only SELECT queries are allowed" | The LLM generated a non-SELECT query; try rephrasing |
| "Multiple SQL statements are not allowed" | Rephrase your question to ask for a single result |
| ImportError on startup | Run `pip install -r requirements.txt` inside the venv |

---

## Notes on Spec Data

The spec document shows `total_sales = 438900`. The actual sum of the `amount` column in `database.sql` is **443,900**. The integration tests use 443,900 (derived from the data, not the document).

The spec's example ordering for "top 5 customers" lists Rahul Sharma before Neha Singh and Pooja Deshmukh, which does not match descending order. The correct descending order by total purchase is:

| Rank | Customer | Total |
|---|---|---|
| 1 | Rohit Verma | 137,000 |
| 2 | Rahul Sharma | 70,000 |
| 3 | Neha Singh | 60,000 |
| 4 | Pooja Deshmukh | 50,000 |
| 5 | Amit Kumar | 38,400 |
