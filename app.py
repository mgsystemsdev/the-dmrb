"""
The DMRB — Apartment Turn Tracker.
Run from repo root: streamlit run the-dmrb/app.py
Set COCKPIT_DB_PATH for backend mode (default: the-dmrb/data/cockpit.db).
Backend-only: app fails visibly if DB/services fail to load.
"""
import os

import streamlit as st

from ui.components.sidebar import render_navigation
from ui.data.backend import (
    BACKEND_AVAILABLE,
    BACKEND_ERROR,
    ensure_database_ready,
    get_connection,
    get_db_path,
    turnover_service_mod,
)
from ui.router import render_current_page
from ui.state import init_session_state

try:
    from ui.components.sidebar_flags import render_top_flags
except ImportError:
    render_top_flags = None

st.set_page_config(layout="wide", page_title="The DMRB — Apartment Turn Tracker")

if not BACKEND_AVAILABLE:
    st.error(f"Backend failed to load: {BACKEND_ERROR}")
    st.stop()

# ---------------------------------------------------------------------------
# Global CSS — center text in tables and containers, auto-fit columns
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* Center text in data_editor / dataframe cells (not dropdowns) */
[data-testid="stDataFrame"] td {
    text-align: center !important;
}
[data-testid="stDataFrame"] th {
    text-align: center !important;
}
/* Center metric values and labels */
[data-testid="stMetric"] {
    text-align: center;
}
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
    justify-content: center;
    display: flex;
}
/* Center text in containers (st.write, st.markdown, st.caption) */
[data-testid="stVerticalBlock"] .stMarkdown p,
[data-testid="stVerticalBlock"] .stMarkdown span {
    text-align: center;
}
/* Keep selectbox/input labels left-aligned */
[data-testid="stSelectbox"] label,
[data-testid="stTextInput"] label,
[data-testid="stDateInput"] label,
[data-testid="stTextArea"] label {
    text-align: left !important;
}
/* Auto-fit data_editor columns to content */
[data-testid="stDataFrame"] table {
    table-layout: auto !important;
}
</style>
""", unsafe_allow_html=True)

init_session_state()

# Ensure DB is schema-initialized and migrated before any read path.
_skip_bootstrap = os.getenv("SKIP_DB_BOOTSTRAP", "").strip().lower()
if _skip_bootstrap not in ("1", "true", "yes", "on", "y"):
    try:
        ensure_database_ready(get_db_path())
    except Exception as e:
        st.error(f"Database initialization failed: {e}")
        st.stop()

# Backfill tasks for any open turnovers that have none (one-time reconciliation).
if BACKEND_AVAILABLE and turnover_service_mod:
    try:
        conn = get_connection(get_db_path())
        backfilled = turnover_service_mod.reconcile_missing_tasks(conn)
        if backfilled:
            conn.commit()
        conn.close()
    except Exception:
        pass

render_navigation(st.session_state.page)
if render_top_flags is not None:
    render_top_flags()
render_current_page()
