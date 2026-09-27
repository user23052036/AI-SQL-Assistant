"""AI SQL Query Generator & Database Assistant — Streamlit front-end."""

import io
import streamlit as st
import pandas as pd
import altair as alt

from database import (
    get_schema,
    get_relationships,
    execute_query,
    test_connection,
    schema_to_text,
)
from sql_generator import generate_sql, explain_sql, correct_sql
from sql_validator import validate_sql
import config

# ── Page configuration ────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AI SQL Assistant",
    page_icon="🤖",
    layout="wide",
)

# ── Session-state initialisation ──────────────────────────────────────────────
# All state lives here so Streamlit reruns don't reset mid-workflow values.

_DEFAULTS = {
    "sql": None,          # Last generated SQL string
    "sql_valid": None,    # (bool, message) from validator
    "df": None,           # pd.DataFrame from last successful query
    "explanation": None,  # AI explanation string
    "last_question": "",  # Question that produced current sql
    "db_error": None,     # Last DB error string (for auto-correction)
}

for key, default in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Helper: smart visualisation ───────────────────────────────────────────────

def _build_chart(df: pd.DataFrame) -> alt.Chart | None:
    """
    Return an Altair bar chart when the DataFrame has a useful categorical +
    numeric relationship. Returns None if no sensible chart can be built.
    """
    if df is None or df.empty:
        return None

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    string_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    if not numeric_cols:
        return None

    y_col = numeric_cols[0]

    if string_cols:
        x_col = string_cols[0]
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X(x_col, sort="-y", title=x_col),
                y=alt.Y(y_col, title=y_col),
                tooltip=df.columns.tolist(),
            )
            .properties(height=350)
            .interactive()
        )
        return chart

    # All numeric — use a simple row-index bar chart for single-column results
    if len(df) <= 50 and len(numeric_cols) >= 1:
        df_plot = df[numeric_cols].reset_index().rename(columns={"index": "Row"})
        chart = (
            alt.Chart(df_plot)
            .mark_bar()
            .encode(
                x=alt.X("Row:O", title="Row"),
                y=alt.Y(y_col, title=y_col),
                tooltip=["Row:O"] + [alt.Tooltip(c) for c in numeric_cols],
            )
            .properties(height=350)
            .interactive()
        )
        return chart

    return None


# ── Load database metadata once per session ───────────────────────────────────

@st.cache_data(ttl=120, show_spinner=False)
def _load_db_meta():
    """Cache schema & relationships; re-fetches every 2 minutes."""
    schema = get_schema()
    relationships = get_relationships()
    return schema, relationships


# ── Title & description ───────────────────────────────────────────────────────

st.title("🤖 AI SQL Query Generator & Database Assistant")
st.write(
    "Ask questions about your MySQL database in plain English. "
    "The AI converts your question into a validated SQL query and executes it safely."
)

# ── Database connection status ────────────────────────────────────────────────

db_ok, db_info = test_connection()

if not db_ok:
    st.error(
        f"**Database connection failed:** {db_info}\n\n"
        "Please check your `.env` file (`DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`) "
        "and ensure MySQL is running."
    )
    st.info(
        "The application requires a MySQL connection. "
        "See README.md for setup instructions."
    )
    # Show schema viewer / UI elements but disable execution buttons
    _db_available = False
    schema: dict = {}
    relationships: list = []
else:
    _db_available = True
    try:
        schema, relationships = _load_db_meta()
    except Exception as exc:
        st.error(f"Failed to load database schema: {exc}")
        schema = {}
        relationships = []

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Database")

    if _db_available:
        st.success(f"Connected  \n`{db_info}`")
    else:
        st.error("Not connected")

    st.divider()

    if schema:
        st.subheader("Available Tables")
        for table in schema:
            st.write(f"• `{table}`")

        st.divider()

        if relationships:
            st.subheader("Relationships")
            for rel in relationships:
                st.caption(rel)
    else:
        st.info("Schema unavailable — connect to MySQL first.")

    st.divider()
    st.caption(f"Model: `{config.GROQ_MODEL}`")
    st.caption(f"Max rows returned: `{config.MAX_ROWS}`")

# ── Schema viewer ─────────────────────────────────────────────────────────────

if schema:
    with st.expander("View Database Schema", expanded=False):
        for table, columns in schema.items():
            st.subheader(table)
            for col in columns:
                st.write(f"  - `{col}`")

# ── Question input ────────────────────────────────────────────────────────────

st.header("Ask Your Database")

question = st.text_area(
    "Enter your question in plain English",
    placeholder="Example: Show the top 5 customers by total purchase amount.",
    height=100,
)

# Sample question buttons
st.subheader("Sample Questions")
col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    st.markdown("• Show all customers from Pune.")
    st.markdown("• Show all products.")
with col_s2:
    st.markdown("• Show top 5 customers by sales.")
    st.markdown("• What is the total sales?")
with col_s3:
    st.markdown("• Show sales by city.")
    st.markdown("• Which product generated the most revenue?")

st.divider()

# ── Generate SQL button ───────────────────────────────────────────────────────

gen_disabled = not config.GROQ_API_KEY
if gen_disabled:
    st.warning(
        "**GROQ_API_KEY is not set.** "
        "Add it to `.env` and restart to enable SQL generation."
    )

generate_clicked = st.button(
    "Generate SQL",
    type="primary",
    use_container_width=True,
    disabled=gen_disabled,
)

if generate_clicked:
    q = question.strip()
    if not q:
        st.warning("Please enter a question before generating SQL.")
        st.stop()

    if not schema:
        st.error("Cannot generate SQL: database schema is unavailable.")
        st.stop()

    with st.spinner("Generating SQL…"):
        try:
            sql_out = generate_sql(q, schema, relationships)
        except Exception as exc:
            st.error(f"AI error: {exc}")
            st.stop()

    is_safe, msg = validate_sql(sql_out)

    # Store in session state
    st.session_state["sql"] = sql_out
    st.session_state["sql_valid"] = (is_safe, msg)
    st.session_state["last_question"] = q
    # Clear previous results so stale data isn't shown
    st.session_state["df"] = None
    st.session_state["explanation"] = None
    st.session_state["db_error"] = None

# ── Show generated SQL & validation status ────────────────────────────────────

if st.session_state["sql"] is not None:
    st.subheader("Generated SQL")
    st.code(st.session_state["sql"], language="sql")

    is_safe, msg = st.session_state["sql_valid"]
    if is_safe:
        st.success(f"✅ {msg}")
    else:
        st.error(f"❌ {msg}")

# ── Execute Query button ──────────────────────────────────────────────────────

exec_disabled = (
    st.session_state["sql"] is None
    or not st.session_state["sql_valid"][0]  # not safe
    or not _db_available
) if st.session_state["sql_valid"] else True

execute_clicked = st.button(
    "Execute Query",
    type="primary",
    use_container_width=True,
    disabled=exec_disabled if st.session_state["sql"] else True,
)

if execute_clicked and st.session_state["sql"]:
    sql_to_run = st.session_state["sql"]
    question_ctx = st.session_state["last_question"]
    attempts = 0

    with st.spinner("Executing query…"):
        while attempts <= config.MAX_CORRECTION_ATTEMPTS:
            try:
                df_result = execute_query(sql_to_run)
                st.session_state["df"] = df_result
                st.session_state["db_error"] = None
                st.session_state["sql"] = sql_to_run  # update to corrected SQL
                st.session_state["sql_valid"] = (True, "SQL query is safe.")
                break
            except RuntimeError as exc:
                db_err = str(exc)
                st.session_state["db_error"] = db_err

                if attempts >= config.MAX_CORRECTION_ATTEMPTS:
                    st.error(f"Query failed after {attempts} correction attempt(s): {db_err}")
                    st.session_state["df"] = None
                    break

                # Attempt automatic correction via Groq
                if not config.GROQ_API_KEY:
                    st.error(f"Query execution failed: {db_err}")
                    st.session_state["df"] = None
                    break

                attempts += 1
                with st.spinner(f"Auto-correcting SQL (attempt {attempts})…"):
                    try:
                        corrected = correct_sql(
                            question_ctx, sql_to_run, db_err, schema, relationships
                        )
                        is_safe, safety_msg = validate_sql(corrected)
                        if not is_safe:
                            st.error(
                                f"Auto-corrected SQL failed validation: {safety_msg}"
                            )
                            st.session_state["df"] = None
                            break
                        sql_to_run = corrected
                        st.session_state["sql"] = corrected
                        st.session_state["sql_valid"] = (True, "SQL query is safe.")
                        st.info(f"SQL was auto-corrected (attempt {attempts}). Retrying…")
                    except Exception as corr_exc:
                        st.error(f"Auto-correction failed: {corr_exc}")
                        st.session_state["df"] = None
                        break

# ── Results display ───────────────────────────────────────────────────────────

if st.session_state["df"] is not None:
    df: pd.DataFrame = st.session_state["df"]

    st.subheader("Query Results")

    if df.empty:
        st.info("Query executed successfully, but no records were found.")
    else:
        st.dataframe(df, use_container_width=True)

        m_col1, m_col2 = st.columns(2)
        with m_col1:
            st.metric("Rows", len(df))
        with m_col2:
            st.metric("Columns", len(df.columns))

        # ── Visualisation ─────────────────────────────────────────────────
        st.subheader("Visualisation")
        chart = _build_chart(df)
        if chart is not None:
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info(
                "No suitable chart could be generated for this result. "
                "The table above shows all data."
            )

        # ── CSV download ──────────────────────────────────────────────────
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download Results as CSV",
            data=csv_bytes,
            file_name="query_results.csv",
            mime="text/csv",
        )

    # ── SQL explanation ───────────────────────────────────────────────────
    with st.expander("💡 Explain SQL Query", expanded=False):
        if st.session_state["explanation"] is None:
            if config.GROQ_API_KEY:
                with st.spinner("Generating explanation…"):
                    try:
                        st.session_state["explanation"] = explain_sql(
                            st.session_state["sql"]
                        )
                    except Exception as exc:
                        st.session_state["explanation"] = f"Explanation unavailable: {exc}"
            else:
                st.session_state["explanation"] = (
                    "Explanation unavailable: GROQ_API_KEY not set."
                )
        st.write(st.session_state["explanation"])

# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption("AI SQL Assistant | Python · Streamlit · Groq · MySQL")
