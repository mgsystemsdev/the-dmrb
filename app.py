"""
The DMRB — Apartment Turn Tracker.
Run from repo root: streamlit run the-dmrb/app.py
Set COCKPIT_DB_PATH for backend mode (default: the-dmrb/data/cockpit.db).
Backend-only: app fails visibly if DB/services fail to load.
"""
import copy
import json
import os
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import streamlit as st

# Backend required
_BACKEND_ERROR = None
try:
    from db.connection import get_connection, ensure_database_ready
    from db import repository as db_repository
    from services import board_query_service
    from services import import_service as import_service_mod
    from services import manual_availability_service as manual_availability_service_mod
    from services import note_service as note_service_mod
    from services import task_service as task_service_mod
    from services import turnover_service as turnover_service_mod
    from services import unit_master_import_service as unit_master_import_service_mod
    _BACKEND_AVAILABLE = True
except Exception as _e:
    _BACKEND_AVAILABLE = False
    _BACKEND_ERROR = _e
    db_repository = import_service_mod = manual_availability_service_mod = note_service_mod = None
    task_service_mod = turnover_service_mod = unit_master_import_service_mod = None

# UI dropdown/label constants (no mock dependency)
STATUS_OPTIONS = ["Vacant ready", "Vacant not ready", "On notice"]
ASSIGNEE_OPTIONS = ["", "Michael", "Brad", "Miguel A", "Roadrunner", "Make Ready Co"]
BLOCK_OPTIONS = ["Not Blocking", "Key Delivery", "Vendor Delay", "Parts on Order", "Permit Required", "Other"]
DEFAULT_TASK_ASSIGNEES = {
    "Insp": {"options": ["Michael", "Miguel A"], "default": "Michael"},
    "CB": {"options": ["Make Ready Co"], "default": ""},
    "MRB": {"options": ["Make Ready Co"], "default": "Make Ready Co"},
    "Paint": {"options": ["Roadrunner"], "default": "Roadrunner"},
    "MR": {"options": ["Make Ready Co"], "default": "Make Ready Co"},
    "HK": {"options": ["Brad"], "default": "Brad"},
    "CC": {"options": ["Brad"], "default": ""},
    "FW": {"options": ["Michael", "Miguel A"], "default": ""},
    "QC": {"options": ["Michael", "Miguel A", "Brad"], "default": "Michael"},
}
DEFAULT_TASK_OFFSETS = {
    "Insp": 1, "CB": 2, "MRB": 3, "Paint": 4,
    "MR": 5, "HK": 6, "CC": 7, "FW": 8, "QC": 9,
}
OFFSET_OPTIONS = list(range(1, 31))
TASK_TYPES_ALL = ["Insp", "CB", "MRB", "Paint", "MR", "HK", "CC", "FW", "QC"]
TASK_DISPLAY_NAMES = {
    "Insp": "Inspection", "CB": "Carpet Bid", "MRB": "Make Ready Bid", "Paint": "Paint",
    "MR": "Make Ready", "HK": "Housekeeping", "CC": "Carpet Clean", "FW": "Final Walk", "QC": "Quality Control",
}
EXEC_LABEL_TO_VALUE = {
    "": None, "Not Started": "NOT_STARTED", "Scheduled": "SCHEDULED", "In Progress": "IN_PROGRESS",
    "Done": "VENDOR_COMPLETED", "N/A": "NA", "Canceled": "CANCELED",
}
EXEC_VALUE_TO_LABEL = {v: k for k, v in EXEC_LABEL_TO_VALUE.items() if v is not None}
EXEC_VALUE_TO_LABEL[None] = ""
CONFIRM_LABEL_TO_VALUE = {"Pending": "PENDING", "Confirmed": "CONFIRMED", "Rejected": "REJECTED", "Waived": "WAIVED"}
CONFIRM_VALUE_TO_LABEL = {v: k for k, v in CONFIRM_LABEL_TO_VALUE.items()}
BRIDGE_MAP = {
    "All": None, "Insp Breach": "inspection_sla_breach", "SLA Breach": "sla_breach",
    "SLA MI Breach": "sla_movein_breach", "Plan Bridge": "plan_breach",
}


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None

def _operational_state_to_badge(operational_state: str) -> str:
    badge_map = {
        "On Notice - Scheduled": "On Notice - Scheduled",
        "On Notice": "On Notice",
        "Scheduled to Move In": "Scheduled to Move In",
        "Move-In Risk": "Move-In Risk",
        "QC Hold": "QC Hold",
        "Work Stalled": "Work Stalled",
        "Needs Attention": "Needs Attention",
        "In Progress": "In Progress",
        "Pending Start": "Pending Start",
        "Apartment Ready": "Apartment Ready",
        "Out of Scope": "Out of Scope",
    }
    return badge_map.get(operational_state or "", operational_state or "")




def _get_attention_badge(row: dict) -> str:
    """Use row's attention_badge if present, else derive from operational_state."""
    if row.get("attention_badge"):
        return row["attention_badge"]
    return _operational_state_to_badge(row.get("operational_state", ""))

def _fmt_date(s, default="—"):
    """Format date string as MM/DD/YYYY."""
    if not s:
        return default
    try:
        d = date.fromisoformat(str(s)[:10])
        return d.strftime("%m/%d/%Y")
    except (ValueError, TypeError):
        return default


def _normalize_label(s: str) -> str:
    """Normalize label for comparison/lookup; avoid KeyError from unicode or whitespace differences."""
    return unicodedata.normalize("NFKC", (s or "").strip())


def _normalize_enum(s) -> str:
    """Normalize DB enum value for mapping lookup; case- and whitespace-safe."""
    if not isinstance(s, str):
        return ""
    return unicodedata.normalize("NFKC", s).strip().upper()


def _safe_index(options: list, value, default: int = 0) -> int:
    """Index of value in options, or default if missing; avoids ValueError from .index()."""
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return default


def _to_date(v) -> Optional[date]:
    """Coerce value (date, Timestamp, str, None, NaT) to plain date or None."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    # Timestamp / datetime → extract date first (before isinstance check,
    # because pd.Timestamp is a date subclass but != plain date)
    if hasattr(v, "date") and callable(v.date) and type(v) is not date:
        result = v.date()
        try:
            if pd.isna(result):
                return None
        except (TypeError, ValueError):
            pass
        return result
    if isinstance(v, date):
        return v
    return _parse_date(str(v))

def _dates_equal(a, b) -> bool:
    """Compare two date-like values for equality (handles None, NaT, date, Timestamp)."""
    da = _to_date(a)
    db = _to_date(b)
    return da == db

st.set_page_config(layout="wide", page_title="The DMRB — Apartment Turn Tracker")

if not _BACKEND_AVAILABLE:
    st.error(f"Backend failed to load: {_BACKEND_ERROR}")
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

# ---------------------------------------------------------------------------
# Dropdown config persistence (JSON file next to DB)
# ---------------------------------------------------------------------------
def _dropdown_config_path():
    return os.path.join(os.path.dirname(__file__) or ".", "data", "dropdown_config.json")


def _load_dropdown_config():
    """Load dropdown config from JSON file, falling back to hardcoded defaults on first run."""
    path = _dropdown_config_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"task_assignees": copy.deepcopy(DEFAULT_TASK_ASSIGNEES), "task_offsets": copy.deepcopy(DEFAULT_TASK_OFFSETS)}


def _save_dropdown_config():
    """Persist current dropdown_config to JSON file."""
    path = _dropdown_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(st.session_state.dropdown_config, f, indent=2)


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
def _init_session_state():
    if "page" not in st.session_state:
        st.session_state.page = "dmrb_board"
    if st.session_state.page in ("add_availability", "import", "dropdown_mgr", "unit_master_import"):
        st.session_state.page = "admin"
    if "selected_turnover_id" not in st.session_state:
        st.session_state.selected_turnover_id = None
    if "search_unit" not in st.session_state:
        st.session_state.search_unit = ""
    if "filter_phase" not in st.session_state:
        st.session_state.filter_phase = "All"
    if "filter_status" not in st.session_state:
        st.session_state.filter_status = "All"
    if "filter_nvm" not in st.session_state:
        st.session_state.filter_nvm = "All"
    if "filter_assignee" not in st.session_state:
        st.session_state.filter_assignee = "All"
    if "filter_qc" not in st.session_state:
        st.session_state.filter_qc = "All"
    if "breach_filter" not in st.session_state:
        st.session_state.breach_filter = "All"
    if "breach_value" not in st.session_state:
        st.session_state.breach_value = "All"
    if "dropdown_config" not in st.session_state:
        st.session_state.dropdown_config = _load_dropdown_config()
    if "task_offsets" not in st.session_state.dropdown_config:
        st.session_state.dropdown_config["task_offsets"] = copy.deepcopy(DEFAULT_TASK_OFFSETS)
    if "enable_db_writes" not in st.session_state:
        st.session_state.enable_db_writes = False

_init_session_state()


def _get_db_path():
    return os.environ.get("COCKPIT_DB_PATH", os.path.join(os.path.dirname(__file__) or ".", "data", "cockpit.db"))


# Ensure DB is schema-initialized and migrated before any read path
try:
    ensure_database_ready(_get_db_path())
except Exception as e:
    st.error(f"Database initialization failed: {e}")
    st.stop()

# Backfill tasks for any open turnovers that have none (one-time reconciliation)
if _BACKEND_AVAILABLE and turnover_service_mod:
    try:
        _rc = get_connection(_get_db_path())
        _backfilled = turnover_service_mod.reconcile_missing_tasks(_rc)
        if _backfilled:
            _rc.commit()
        _rc.close()
        del _rc, _backfilled
    except Exception:
        pass

def _get_conn():
    if not _BACKEND_AVAILABLE:
        return None
    db_path = _get_db_path()
    try:
        return get_connection(db_path)
    except Exception:
        return None


def _db_write(do_write):
    """When enable_db_writes, run do_write(conn); commit or rollback; close. Returns True if committed, False otherwise."""
    if not st.session_state.get("enable_db_writes"):
        return False
    if not _BACKEND_AVAILABLE or not turnover_service_mod:
        return False
    conn = _get_conn()
    if not conn:
        st.error("Database not available")
        return False
    try:
        do_write(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(str(e))
        return False
    finally:
        conn.close()

EXEC_LABELS = [k for k in EXEC_LABEL_TO_VALUE if k]
CONFIRM_LABELS = list(CONFIRM_LABEL_TO_VALUE.keys())

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("The DMRB")
st.sidebar.caption("Apartment Turn Tracker")
enable_writes = st.sidebar.checkbox(
    "Enable DB Writes (⚠ irreversible)",
    value=st.session_state.enable_db_writes,
    key="enable_db_writes_cb",
)
if enable_writes != st.session_state.enable_db_writes:
    st.session_state.enable_db_writes = enable_writes
    st.rerun()
# Navigation
_nav_labels = [
    "DMRB Board",
    "Flag Bridge",
    "Turnover Detail",
    "Admin",
]
_nav_to_page = {
    "DMRB Board": "dmrb_board",
    "Flag Bridge": "flag_bridge",
    "Turnover Detail": "detail",
    "Admin": "admin",
}
_page_to_nav_index = {v: i for i, v in enumerate(_nav_to_page.values())}
_page_to_nav_label = {v: k for k, v in _nav_to_page.items()}

# Sync radio value when page was set programmatically (▶, Open, sidebar flags).
# Use assignment (not del) so Streamlit's internal widget state stays consistent.
_expected_nav = _page_to_nav_label.get(st.session_state.page, "DMRB Board")
if "sidebar_nav" in st.session_state and st.session_state.sidebar_nav != _expected_nav:
    st.session_state["sidebar_nav"] = _expected_nav

def _on_nav_change():
    st.session_state.page = _nav_to_page.get(st.session_state.sidebar_nav, st.session_state.page)

st.sidebar.radio(
    "Navigate",
    _nav_labels,
    index=_nav_labels.index(_expected_nav),
    key="sidebar_nav",
    on_change=_on_nav_change,
)

# Sidebar: Top flags by category
st.sidebar.divider()
st.sidebar.markdown("**Top Flags**")
conn = _get_conn()
if not conn:
    _all_rows = []
    st.sidebar.error("Database not available")
else:
    try:
        _all_rows = board_query_service.get_flag_bridge_rows(
            conn,
            property_ids=None,
            search_unit=st.session_state.search_unit or None,
            filter_phase=st.session_state.filter_phase if st.session_state.filter_phase != "All" else None,
            filter_status=st.session_state.filter_status if st.session_state.filter_status != "All" else None,
            filter_nvm=st.session_state.filter_nvm if st.session_state.filter_nvm != "All" else None,
            filter_assignee=st.session_state.filter_assignee if st.session_state.filter_assignee != "All" else None,
            filter_qc=st.session_state.filter_qc if st.session_state.filter_qc != "All" else None,
            breach_filter=None,
            breach_value=None,
            today=date.today(),
        )
    except sqlite3.OperationalError as e:
        _all_rows = []
        st.sidebar.error(str(e))
    finally:
        conn.close()
_all_rows.sort(key=lambda r: -(r.get("dv") or 0))

def _sort_insp(r):
    """Closest inspection due date (not done) first."""
    t = r.get("task_insp") or {}
    if (t.get("execution_status") or "").upper() == "VENDOR_COMPLETED":
        return date.max
    d = _parse_date(t.get("vendor_due_date"))
    return d if d else date.max

def _sort_dv_desc(r):
    """Highest days vacant first."""
    return -(r.get("dv") or 0)

def _sort_mi_closest(r):
    """Closest move-in date (not ready) first."""
    d = _parse_date(r.get("move_in_date"))
    return d if d else date.max

def _sort_ready_date(r):
    """Ready date (not ready) first."""
    d = _parse_date(r.get("report_ready_date"))
    return d if d else date.max

_FLAG_CATEGORIES = [
    ("📋 Insp Breach", "inspection_sla_breach", lambda r: r.get("inspection_sla_breach"), _sort_insp),
    ("⚠ SLA Breach", "sla_breach", lambda r: r.get("sla_breach"), _sort_dv_desc),
    ("🔴 SLA MI Breach", "sla_movein_breach", lambda r: r.get("sla_movein_breach"), _sort_mi_closest),
    ("📅 Plan Breach", "plan_breach", lambda r: r.get("plan_breach"), _sort_ready_date),
]

def _sidebar_unit_btn(row, prefix):
    uc = row.get("unit_code", "")
    dv_val = row.get("dv")
    label = f"{uc} · DV {dv_val}" if dv_val is not None else uc
    if st.sidebar.button(label, key=f"sb_{prefix}_{row.get('turnover_id')}"):
        st.session_state.selected_turnover_id = row.get("turnover_id")
        st.session_state.page = "detail"
        st.rerun()

_any_flags = False
for _cat_label, _cat_key, _cat_fn, _cat_sort in _FLAG_CATEGORIES:
    _cat_units = sorted([r for r in _all_rows if _cat_fn(r)], key=_cat_sort)
    if _cat_units:
        _any_flags = True
        with st.sidebar.expander(f"{_cat_label} ({len(_cat_units)})"):
            for _u in _cat_units[:5]:
                uc = _u.get("unit_code", "")
                dv_val = _u.get("dv")
                label = f"{uc} · DV {dv_val}" if dv_val is not None else uc
                if st.button(label, key=f"sb_{_cat_key}_{_u.get('turnover_id')}"):
                    st.session_state.selected_turnover_id = _u.get("turnover_id")
                    st.session_state.page = "detail"
                    st.rerun()
if not _any_flags:
    st.sidebar.caption("No flagged units")

# ---------------------------------------------------------------------------
# DMRB Board
# ---------------------------------------------------------------------------
def _get_dmrb_rows():
    conn = _get_conn()
    if not conn:
        st.error("Database not available")
        return []
    try:
        phase_ids = None
        if db_repository and st.session_state.filter_phase != "All":
            if "phase_id_by_code" not in st.session_state:
                phases = db_repository.list_phases(conn)
                st.session_state.phase_id_by_code = {str(p["phase_code"]): p["phase_id"] for p in phases}
            phase_id = st.session_state.get("phase_id_by_code", {}).get(st.session_state.filter_phase)
            if phase_id is not None:
                phase_ids = [phase_id]
        return board_query_service.get_dmrb_board_rows(
            conn,
            property_ids=None,
            phase_ids=phase_ids,
            search_unit=st.session_state.search_unit or None,
            filter_phase=st.session_state.filter_phase if phase_ids is None and st.session_state.filter_phase != "All" else None,
            filter_status=st.session_state.filter_status if st.session_state.filter_status != "All" else None,
            filter_nvm=st.session_state.filter_nvm if st.session_state.filter_nvm != "All" else None,
            filter_assignee=st.session_state.filter_assignee if st.session_state.filter_assignee != "All" else None,
            filter_qc=st.session_state.filter_qc if st.session_state.filter_qc != "All" else None,
            today=date.today(),
        )
    except sqlite3.OperationalError as e:
        st.error(str(e))
        return []
    finally:
        conn.close()

def _exec_label(task_dict):
    """Get display label for a task's execution status."""
    cur = (task_dict.get("execution_status") or "NOT_STARTED").upper()
    return EXEC_VALUE_TO_LABEL.get(cur, "Not Started")

def _confirm_label(task_dict):
    """Get display label for a task's confirmation status."""
    cur = (task_dict.get("confirmation_status") or "PENDING").upper()
    return CONFIRM_VALUE_TO_LABEL.get(cur, "Pending")

def render_dmrb_board():
    rows = _get_dmrb_rows()
    n_active = len(rows)
    n_crit = sum(1 for r in rows if r.get("has_violation") or r.get("operational_state") == "Move-In Risk")

    # --- ZONE 1: FILTERS ---
    with st.container(border=True):
        c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1, 1, 1, 1, 1, 1, 1])
        with c0:
            st.session_state.search_unit = st.text_input("Search unit", value=st.session_state.search_unit, key="dmrb_search")
        with c1:
            conn = _get_conn()
            if conn and db_repository:
                try:
                    phases = db_repository.list_phases(conn)
                    st.session_state.phase_id_by_code = {str(p["phase_code"]): p["phase_id"] for p in phases}
                    phase_opts = ["All"] + sorted(st.session_state.phase_id_by_code.keys())
                except Exception:
                    phase_opts = ["All", "5", "7", "8"]
            else:
                phase_opts = ["All", "5", "7", "8"]
            idx = phase_opts.index(st.session_state.filter_phase) if st.session_state.filter_phase in phase_opts else 0
            st.session_state.filter_phase = st.selectbox("Phase", phase_opts, index=idx, key="dmrb_phase")
        with c2:
            status_opts = ["All"] + STATUS_OPTIONS
            idx = status_opts.index(st.session_state.filter_status) if st.session_state.filter_status in status_opts else 0
            st.session_state.filter_status = st.selectbox("Status", status_opts, index=idx, key="dmrb_status")
        with c3:
            nvm_opts = ["All", "Notice", "Notice + SMI", "Vacant", "SMI", "Move-In"]
            idx = nvm_opts.index(st.session_state.filter_nvm) if st.session_state.filter_nvm in nvm_opts else 0
            st.session_state.filter_nvm = st.selectbox("N/V/M", nvm_opts, index=idx, key="dmrb_nvm")
        with c4:
            assign_opts = ["All"] + [a for a in ASSIGNEE_OPTIONS if a]
            idx = assign_opts.index(st.session_state.filter_assignee) if st.session_state.filter_assignee in assign_opts else 0
            st.session_state.filter_assignee = st.selectbox("Assign", assign_opts, index=idx, key="dmrb_assign")
        with c5:
            qc_opts = ["All", "QC Done", "QC Not done"]
            idx = qc_opts.index(st.session_state.filter_qc) if st.session_state.filter_qc in qc_opts else 0
            st.session_state.filter_qc = st.selectbox("QC", qc_opts, index=idx, key="dmrb_qc")
        with c6:
            st.metric("Active", n_active)
        with c7:
            st.metric("CRIT", n_crit)

    # --- ZONE 2: METRICS ---
    with st.container(border=True):
        n_viol = sum(1 for r in rows if r.get("has_violation"))
        n_plan = sum(1 for r in rows if r.get("plan_breach"))
        n_sla = sum(1 for r in rows if r.get("sla_breach"))
        n_mi_risk = sum(1 for r in rows if r.get("operational_state") == "Move-In Risk")
        n_stalled = sum(1 for r in rows if r.get("is_task_stalled"))
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Active Units", n_active)
        m2.metric("Violations", n_viol)
        m3.metric("Plan Breach", n_plan)
        m4.metric("SLA Breach", n_sla)
        m5.metric("Move-In Risk", n_mi_risk)
        m6.metric("Work Stalled", n_stalled)

    # --- ZONE 3: TABBED TABLES ---
    if not rows:
        st.info("No turnovers match filters.")
        return

    # Build shared tracking arrays
    tid_map = []
    task_id_map = []
    info_data = []
    task_data = []

    _task_cols = ["Inspection", "Carpet Bid", "Make Ready Bid", "Paint", "Make Ready", "Housekeeping", "Carpet Clean", "Final Walk"]
    _task_date_cols = [f"{tc} Date" for tc in _task_cols]
    _task_keys = ["task_insp", "task_cb", "task_mrb", "task_paint", "task_mr", "task_hk", "task_cc", "task_fw"]
    _task_codes = ["Insp", "CB", "MRB", "Paint", "MR", "HK", "CC", "FW"]
    _offsets_cfg = st.session_state.dropdown_config.get("task_offsets", DEFAULT_TASK_OFFSETS)

    for row in rows:
        tid = row["turnover_id"]
        tid_map.append(tid)
        tasks = {name: (row.get(key) or {}) for name, key in zip(_task_cols, _task_keys)}
        task_qc = row.get("task_qc") or {}

        task_id_map.append({
            **{name: tasks[name].get("task_id") for name in _task_cols},
            "Quality Control": task_qc.get("task_id"),
        })

        nvm_full = row.get("nvm", "—")

        # --- Tab 1: Unit Info ---
        info_data.append({
            "▶": False,
            "Unit": row.get("unit_code", ""),
            "Status": row.get("manual_ready_status", "Vacant not ready"),
            "Move-Out": _parse_date(row.get("move_out_date")),
            "Ready Date": _parse_date(row.get("report_ready_date")),
            "DV": row.get("dv"),
            "Move-In": _parse_date(row.get("move_in_date")),
            "DTBR": row.get("dtbr"),
            "N/V/M": nvm_full,
            "W/D": row.get("wd_summary", "—"),
            "Quality Control": _confirm_label(task_qc),
            "Alert": _get_attention_badge(row),
            "Notes": (row.get("notes_text") or "")[:50],
        })

        # --- Tab 2: Unit Tasks ---
        legal_src = row.get("legal_confirmation_source")
        legal_dot = "🟢" if legal_src else "🔴"
        task_row = {
            "▶": False,
            "Unit": row.get("unit_code", ""),
            "⚖": legal_dot,
            "Status": row.get("manual_ready_status", "Vacant not ready"),
            "DV": row.get("dv"),
            "DTBR": row.get("dtbr"),
        }
        move_out_dt = _parse_date(row.get("move_out_date"))
        for name, code in zip(_task_cols, _task_codes):
            task_row[name] = _exec_label(tasks[name])
            existing_date = _parse_date(tasks[name].get("vendor_due_date"))
            if existing_date:
                task_row[f"{name} Date"] = existing_date
            elif move_out_dt:
                offset = _offsets_cfg.get(code, 1)
                task_row[f"{name} Date"] = move_out_dt + timedelta(days=offset)
            else:
                task_row[f"{name} Date"] = None
        task_data.append(task_row)

    df_info = pd.DataFrame(info_data)
    df_task = pd.DataFrame(task_data)

    _writes_on = st.session_state.enable_db_writes

    # Compute Notes column width
    _max_notes_len = max((len(r.get("Notes", "")) for r in info_data), default=5)
    _notes_width = max(60, min(_max_notes_len * 8 + 16, 300))

    tab_info, tab_tasks = st.tabs(["Unit Info", "Unit Tasks"])

    # =================== TAB 1: UNIT INFO ===================
    with tab_info:
        info_col_config = {
            "▶": st.column_config.CheckboxColumn("▶", width=40),
            "Unit": st.column_config.TextColumn("Unit"),
            "Status": st.column_config.SelectboxColumn("Status", options=STATUS_OPTIONS),
            "Move-Out": st.column_config.DateColumn("Move-Out", format="MM/DD/YYYY"),
            "Ready Date": st.column_config.DateColumn("Ready Date", format="MM/DD/YYYY"),
            "DV": st.column_config.NumberColumn("DV", width=50),
            "Move-In": st.column_config.DateColumn("Move-In", format="MM/DD/YYYY"),
            "DTBR": st.column_config.NumberColumn("DTBR", width=60),
            "N/V/M": st.column_config.TextColumn("N/V/M", width=80),
            "W/D": st.column_config.TextColumn("W/D", width=50),
            "Quality Control": st.column_config.SelectboxColumn("Quality Control", options=CONFIRM_LABELS),
            "Alert": st.column_config.TextColumn("Alert"),
            "Notes": st.column_config.TextColumn("Notes", width=_notes_width),
        }
        info_disabled = ["Unit", "DV", "DTBR", "N/V/M", "W/D", "Alert", "Notes"]
        if not _writes_on:
            info_disabled += ["Status", "Move-Out", "Ready Date", "Move-In", "Quality Control"]
        info_col_order = [
            "▶", "Unit", "Status", "Move-Out", "Ready Date", "DV", "Move-In", "DTBR",
            "N/V/M", "W/D", "Quality Control", "Alert", "Notes",
        ]
        edited_info = st.data_editor(
            df_info,
            column_config=info_col_config,
            column_order=info_col_order,
            disabled=info_disabled,
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            key="dmrb_info_editor",
        )

    # =================== TAB 2: UNIT TASKS ===================
    with tab_tasks:
        task_col_config = {
            "▶": st.column_config.CheckboxColumn("▶", width=40),
            "Unit": st.column_config.TextColumn("Unit"),
            "⚖": st.column_config.TextColumn("⚖", width=35, help="Legal move-out confirmation: 🟢 = confirmed, 🔴 = not confirmed"),
            "Status": st.column_config.TextColumn("Status"),
            "DV": st.column_config.NumberColumn("DV", width=50),
            "DTBR": st.column_config.NumberColumn("DTBR", width=60),
            **{tc: st.column_config.SelectboxColumn(tc, options=EXEC_LABELS) for tc in _task_cols},
            **{dc: st.column_config.DateColumn(dc, format="MM/DD/YYYY") for dc in _task_date_cols},
        }
        task_disabled = ["Unit", "⚖", "Status", "DV", "DTBR"]
        if not _writes_on:
            task_disabled += _task_cols + _task_date_cols
        # Interleave task exec + date columns
        task_col_order = ["▶", "Unit", "⚖", "Status", "DV", "DTBR"]
        for tc, dc in zip(_task_cols, _task_date_cols):
            task_col_order.extend([tc, dc])
        edited_task = st.data_editor(
            df_task,
            column_config=task_col_config,
            column_order=task_col_order,
            disabled=task_disabled,
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            key="dmrb_task_editor",
        )

    # =================== EDIT DETECTION (both tabs) ===================
    nav_tid = None
    status_updates = []
    date_updates = []
    task_exec_updates = []
    task_confirm_updates = []
    task_date_updates = []

    for idx in range(len(tid_map)):
        tid = tid_map[idx]

        # ▶ from either tab
        if edited_info.iloc[idx]["▶"] or edited_task.iloc[idx]["▶"]:
            nav_tid = tid

        # Tab 1 edits: Status, dates, QC
        if df_info.iloc[idx]["Status"] != edited_info.iloc[idx]["Status"]:
            status_updates.append((tid, edited_info.iloc[idx]["Status"]))
        date_kwargs = {}
        for col_name, field_name in [("Move-Out", "move_out_date"), ("Ready Date", "report_ready_date"), ("Move-In", "move_in_date")]:
            if not _dates_equal(df_info.iloc[idx][col_name], edited_info.iloc[idx][col_name]):
                date_kwargs[field_name] = _to_date(edited_info.iloc[idx][col_name])
        if date_kwargs:
            date_updates.append((tid, date_kwargs))
        if df_info.iloc[idx]["Quality Control"] != edited_info.iloc[idx]["Quality Control"]:
            qc_task_id = task_id_map[idx].get("Quality Control")
            if qc_task_id:
                new_val = CONFIRM_LABEL_TO_VALUE.get(edited_info.iloc[idx]["Quality Control"])
                if new_val:
                    task_confirm_updates.append((qc_task_id, new_val))

        # Tab 2 edits: task exec statuses + task dates
        for task_col in _task_cols:
            if df_task.iloc[idx][task_col] != edited_task.iloc[idx][task_col]:
                task_id = task_id_map[idx].get(task_col)
                if task_id:
                    new_val = EXEC_LABEL_TO_VALUE.get(edited_task.iloc[idx][task_col])
                    if new_val is not None:
                        task_exec_updates.append((task_id, new_val))
        for task_col, date_col in zip(_task_cols, _task_date_cols):
            if not _dates_equal(df_task.iloc[idx][date_col], edited_task.iloc[idx][date_col]):
                task_id = task_id_map[idx].get(task_col)
                if task_id:
                    task_date_updates.append((task_id, _to_date(edited_task.iloc[idx][date_col])))

    # Navigation takes priority
    if nav_tid is not None:
        st.session_state.selected_turnover_id = nav_tid
        st.session_state.page = "detail"
        st.rerun()
    db_edits = status_updates or date_updates or task_exec_updates or task_confirm_updates or task_date_updates
    if (
        st.session_state.enable_db_writes
        and db_edits
        and task_service_mod
        and turnover_service_mod
    ):
        conn = _get_conn()
        if not conn:
            st.error("Database not available")
        else:
            try:
                today = date.today()
                actor = "manager"
                for tid, new_status in status_updates:
                    turnover_service_mod.set_manual_ready_status(
                        conn=conn, turnover_id=tid, manual_ready_status=new_status, today=today, actor=actor
                    )
                for tid, kwargs in date_updates:
                    turnover_service_mod.update_turnover_dates(
                        conn=conn, turnover_id=tid, today=today, actor=actor, **kwargs
                    )
                for task_id, new_val in task_exec_updates:
                    task_service_mod.update_task_fields(
                        conn=conn, task_id=task_id, fields={"execution_status": new_val}, today=today, actor=actor
                    )
                for task_id, new_val in task_confirm_updates:
                    task_service_mod.update_task_fields(
                        conn=conn, task_id=task_id, fields={"confirmation_status": new_val}, today=today, actor=actor
                    )
                for task_id, new_date in task_date_updates:
                    task_service_mod.update_task_fields(
                        conn=conn, task_id=task_id, fields={"vendor_due_date": new_date}, today=today, actor=actor
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                st.error(str(e))
            finally:
                conn.close()
        st.rerun()

# ---------------------------------------------------------------------------
# Flag Bridge
# ---------------------------------------------------------------------------
def _get_flag_bridge_rows():
    conn = _get_conn()
    if not conn:
        return []
    try:
        phase_ids = None
        if db_repository and st.session_state.filter_phase != "All":
            phase_id = st.session_state.get("phase_id_by_code", {}).get(st.session_state.filter_phase)
            if phase_id is not None:
                phase_ids = [phase_id]
        return board_query_service.get_flag_bridge_rows(
            conn,
            property_ids=None,
            phase_ids=phase_ids,
            search_unit=st.session_state.search_unit or None,
            filter_phase=st.session_state.filter_phase if phase_ids is None and st.session_state.filter_phase != "All" else None,
            filter_status=st.session_state.filter_status if st.session_state.filter_status != "All" else None,
            filter_nvm=st.session_state.filter_nvm if st.session_state.filter_nvm != "All" else None,
            filter_assignee=st.session_state.filter_assignee if st.session_state.filter_assignee != "All" else None,
            filter_qc=st.session_state.filter_qc if st.session_state.filter_qc != "All" else None,
            breach_filter=st.session_state.breach_filter if st.session_state.breach_filter != "All" else None,
            breach_value=st.session_state.breach_value if st.session_state.breach_value != "All" else None,
            today=date.today(),
        )
    except sqlite3.OperationalError as e:
        st.error(str(e))
        return []
    finally:
        conn.close()

def render_flag_bridge():
    rows = _get_flag_bridge_rows()
    n_viol = sum(1 for r in rows if r.get("has_violation"))
    n_breach = sum(1 for r in rows if r.get("inspection_sla_breach") or r.get("sla_breach") or r.get("sla_movein_breach") or r.get("plan_breach"))

    # --- ZONE 1: FILTERS ---
    with st.container(border=True):
        c0, c1, c2, c3, c4, c5 = st.columns(6)
        with c0:
            phase_opts = ["All"] + sorted(st.session_state.get("phase_id_by_code", {}).keys()) or ["All", "5", "7", "8"]
            idx = phase_opts.index(st.session_state.filter_phase) if st.session_state.filter_phase in phase_opts else 0
            st.session_state.filter_phase = st.selectbox("Phase", phase_opts, index=idx, key="fb_phase")
        with c1:
            status_opts = ["All"] + STATUS_OPTIONS
            idx = status_opts.index(st.session_state.filter_status) if st.session_state.filter_status in status_opts else 0
            st.session_state.filter_status = st.selectbox("Status", status_opts, index=idx, key="fb_status")
        with c2:
            nvm_opts = ["All", "Notice", "Notice + SMI", "Vacant", "SMI", "Move-In"]
            idx = nvm_opts.index(st.session_state.filter_nvm) if st.session_state.filter_nvm in nvm_opts else 0
            st.session_state.filter_nvm = st.selectbox("N/V/M", nvm_opts, index=idx, key="fb_nvm")
        with c3:
            assign_opts = ["All"] + [a for a in ASSIGNEE_OPTIONS if a]
            idx = assign_opts.index(st.session_state.filter_assignee) if st.session_state.filter_assignee in assign_opts else 0
            st.session_state.filter_assignee = st.selectbox("Assign", assign_opts, index=idx, key="fb_assign")
        with c4:
            bridge_opts = list(BRIDGE_MAP.keys())
            idx = bridge_opts.index(st.session_state.breach_filter) if st.session_state.breach_filter in bridge_opts else 0
            st.session_state.breach_filter = st.selectbox("Flag Bridge", bridge_opts, index=idx, key="fb_bridge")
        with c5:
            value_opts = ["All", "Yes", "No"]
            idx = value_opts.index(st.session_state.breach_value) if st.session_state.breach_value in value_opts else 0
            st.session_state.breach_value = st.selectbox("Value", value_opts, index=idx, key="fb_value")

    # --- ZONE 2: METRICS ---
    with st.container(border=True):
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Units", len(rows))
        m2.metric("Violations", n_viol)
        m3.metric("Units w/ Breach", n_breach)

    # --- ZONE 3: TABLE (st.dataframe — read-only, breach-focused) ---
    if not rows:
        st.info("No rows match filters.")
        return

    fb_tid_map = []
    bridge_data = []
    for r in rows:
        fb_tid_map.append(r.get("turnover_id"))
        bridge_data.append({
            "▶": False,
            "Unit": r.get("unit_code", ""),
            "Status": r.get("manual_ready_status", ""),
            "DV": r.get("dv"),
            "Move-In": _fmt_date(r.get("move_in_date")),
            "Alert": _get_attention_badge(r),
            "Viol": "🔴" if r.get("has_violation") else "—",
            "Insp": "🔴" if r.get("inspection_sla_breach") else "—",
            "SLA": "🔴" if r.get("sla_breach") else "—",
            "MI": "🔴" if r.get("sla_movein_breach") else "—",
            "Plan": "🔴" if r.get("plan_breach") else "—",
        })

    bridge_df = pd.DataFrame(bridge_data)
    edited_bridge = st.data_editor(
        bridge_df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=["Unit", "Status", "DV", "Move-In", "Alert", "Viol", "Insp", "SLA", "MI", "Plan"],
        column_config={
            "▶": st.column_config.CheckboxColumn("▶", width=40),
            "Unit": st.column_config.TextColumn("Unit"),
            "Status": st.column_config.TextColumn("Status"),
            "DV": st.column_config.NumberColumn("DV", width=50),
            "Move-In": st.column_config.TextColumn("Move-In"),
            "Alert": st.column_config.TextColumn("Alert"),
            "Viol": st.column_config.TextColumn("Viol", width=50),
            "Insp": st.column_config.TextColumn("Insp", width=50),
            "SLA": st.column_config.TextColumn("SLA", width=50),
            "MI": st.column_config.TextColumn("MI", width=50),
            "Plan": st.column_config.TextColumn("Plan", width=50),
        },
        column_order=["▶", "Unit", "Status", "DV", "Move-In", "Alert", "Viol", "Insp", "SLA", "MI", "Plan"],
        key="fb_editor",
    )

    # Navigate on ▶ checkbox
    for idx in range(len(bridge_df)):
        if edited_bridge.iloc[idx]["▶"]:
            st.session_state.selected_turnover_id = fb_tid_map[idx]
            st.session_state.page = "detail"
            st.rerun()

# ---------------------------------------------------------------------------
# Turnover Detail
# ---------------------------------------------------------------------------
def _parse_date_for_input(s):
    """Return date or today for st.date_input."""
    if not s:
        return date.today()
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return date.today()

def render_detail():
    if st.session_state.selected_turnover_id is None:
        st.subheader("Turnover Detail")
        unit_search = st.text_input("Unit code", key="detail_unit_search")
        if st.button("Go"):
            conn = _get_conn()
            if not conn:
                st.error("Database not available")
                return
            try:
                rows = board_query_service.get_dmrb_board_rows(conn, property_ids=None, today=date.today())
                norm = (unit_search or "").strip().lower()
                for r in rows:
                    if norm and norm in (r.get("unit_code") or "").lower():
                        st.session_state.selected_turnover_id = r["turnover_id"]
                        st.rerun()
                        return
            except sqlite3.OperationalError as e:
                st.error(str(e))
                return
            finally:
                conn.close()
            st.warning("Unit not found")
        return

    tid = st.session_state.selected_turnover_id
    conn = _get_conn()
    if not conn:
        st.error("Database not available")
        return
    try:
        detail = board_query_service.get_turnover_detail(conn, tid, today=date.today())
    except sqlite3.OperationalError as e:
        st.error(str(e))
        return
    finally:
        conn.close()
    if not detail or not detail.get("turnover"):
        st.warning("Turnover not found")
        st.session_state.selected_turnover_id = None
        st.rerun()
        return
    t = detail["turnover"]
    u = detail.get("unit")
    enriched = detail.get("enriched_fields") or {}
    dv = enriched.get("dv")
    dtbr = enriched.get("dtbr")
    nvm = enriched.get("nvm", "")
    assign_display = enriched.get("assign_display", "")
    tasks_for_turnover = detail.get("tasks") or []
    notes_for_turnover = detail.get("notes") or []
    risks_for_turnover = detail.get("risks") or []

    unit_code = (u.get("unit_code_raw") or u.get("unit_code_norm") or "") if u else ""
    phase_display = (u.get("phase_code") or str(u.get("property_id", ""))) if u else ""
    building = (u.get("building_code") or "") if u else ""
    unit_number = (u.get("unit_number") or "") if u else ""
    if not building and not unit_number and u:
        _uc_parts = (u.get("unit_code_raw") or "").split("-")
        building = _uc_parts[1] if len(_uc_parts) >= 3 else ""
        unit_number = _uc_parts[-1] if len(_uc_parts) >= 2 else (_uc_parts[0] if _uc_parts else "")

    # ===================================================================
    # PANEL A: UNIT INFORMATION
    # ===================================================================
    with st.container(border=True):
        st.markdown("**UNIT INFORMATION**")
        hdr_left, hdr_right = st.columns([4, 1])
        with hdr_left:
            legal_src = t.get("legal_confirmation_source")
            legal_dot_html = (
                '<span title="Legal move-out confirmed" style="color:#28a745;font-size:1.1em;">●</span>'
                if legal_src else
                '<span title="No legal confirmation" style="color:#dc3545;font-size:1.1em;">●</span>'
            )
            unit_label = f"Unit {unit_code}" if unit_code else f"Turnover {tid}"
            st.markdown(f"<h3 style='margin:0;'>{unit_label} {legal_dot_html}</h3>", unsafe_allow_html=True)
        with hdr_right:
            if st.button("← Back"):
                st.session_state.page = "dmrb_board"
                st.rerun()
        id1, id2, id3, id4, id5 = st.columns([0.8, 0.8, 0.8, 0.8, 1.2])
        id1.write(f"**Phase:** {phase_display}")
        id2.write(f"**Building:** {building}" if building else "**Building:** —")
        id3.write(f"**Unit:** {unit_number}")
        id4.write(f"**N/V/M:** {nvm}")
        id5.write(f"**Assignee:** {assign_display}")

    # ===================================================================
    # PANEL B: STATUS & QC ACTION
    # ===================================================================
    today = date.today()
    actor = "manager"
    _detail_writes = st.session_state.enable_db_writes
    with st.container(border=True):
        s1, s2 = st.columns([2, 1])
        with s1:
            cur_status = (t.get("manual_ready_status") or "Vacant not ready").strip()
            idx = _safe_index(STATUS_OPTIONS, cur_status)
            new_status = st.selectbox(
                "Status", STATUS_OPTIONS, index=idx, key="detail_status", disabled=not _detail_writes
            )
            if _detail_writes and new_status != cur_status:
                if _db_write(lambda c: turnover_service_mod.set_manual_ready_status(
                    conn=c, turnover_id=tid, manual_ready_status=new_status, today=today, actor=actor
                )):
                    st.rerun()
        with s2:
            st.write("")
            if st.button("✅ Confirm Quality Control", type="primary", use_container_width=True, key="detail_confirm_qc", disabled=not _detail_writes):
                qc_task = next((task for task in tasks_for_turnover if task.get("task_type") == "QC"), None)
                if qc_task:
                    if _db_write(lambda c: task_service_mod.confirm_task(
                        conn=c, task_id=qc_task["task_id"], today=today, actor=actor
                    )):
                        st.rerun()

    # ===================================================================
    # PANEL C: DATES & METRICS
    # ===================================================================
    with st.container(border=True):
        st.markdown("**DATES**")
        dt1, dt2, dt3, dt4, dt5 = st.columns([1.2, 0.6, 1.2, 1.2, 0.6])
        # Move_out + DV
        with dt1:
            mo_val = _parse_date(t.get("move_out_date"))
            new_mo = st.date_input(
                "Move-Out", value=mo_val or date.today(), key="detail_mo", format="MM/DD/YYYY",
                disabled=not _detail_writes
            )
            if _detail_writes and mo_val is not None and new_mo != mo_val:
                if _db_write(lambda c: turnover_service_mod.update_turnover_dates(
                    conn=c, turnover_id=tid, move_out_date=new_mo, today=today, actor=actor
                )):
                    st.rerun()
        if dv is not None and dv > 10:
            dt2.markdown(f'**DV**<br><span style="color:#dc3545;font-weight:bold">{dv}</span>', unsafe_allow_html=True)
        else:
            dt2.write(f"**DV:** {dv if dv is not None else '—'}")
        # Ready_Date
        with dt3:
            rr_val = _parse_date(t.get("report_ready_date"))
            new_rr = st.date_input(
                "Ready Date", value=rr_val, key="detail_rr", format="MM/DD/YYYY",
                disabled=not _detail_writes
            )
            if _detail_writes and new_rr is not None and new_rr != rr_val:
                if _db_write(lambda c: turnover_service_mod.update_turnover_dates(
                    conn=c, turnover_id=tid, report_ready_date=new_rr, today=today, actor=actor
                )):
                    st.rerun()
        # Move_in + DTBR
        with dt4:
            mi_val = _parse_date(t.get("move_in_date"))
            new_mi = st.date_input(
                "Move-In", value=mi_val, key="detail_mi", format="MM/DD/YYYY",
                disabled=not _detail_writes
            )
            if _detail_writes and new_mi is not None and new_mi != mi_val:
                if _db_write(lambda c: turnover_service_mod.update_turnover_dates(
                    conn=c, turnover_id=tid, move_in_date=new_mi, today=today, actor=actor
                )):
                    st.rerun()
        dt5.write(f"**DTBR:** {dtbr if dtbr is not None else '—'}")

    # ===================================================================
    # PANEL D: W/D STATUS — Present (dropdown) | Notified (button) | Installed (button)
    # ===================================================================
    with st.container(border=True):
        st.markdown("**W/D STATUS**")
        w1, w2, w3 = st.columns(3)
        with w1:
            wd_opts = ["No", "Yes", "Yes stack"]
            cur_wd = "No"
            if t.get("wd_present"):
                cur_wd = (t.get("wd_present_type") or "Yes").strip()
            wd_idx = _safe_index(wd_opts, cur_wd)
            new_wd = st.selectbox(
                "Present", wd_opts, index=wd_idx, key="detail_wd_present", disabled=not _detail_writes
            )
            if _detail_writes and new_wd != cur_wd:
                wd_bool = new_wd != "No"
                if _db_write(lambda c: turnover_service_mod.update_wd_panel(
                    conn=c, turnover_id=tid, today=today, wd_present=wd_bool, wd_present_type=new_wd, actor=actor
                )):
                    st.rerun()
        with w2:
            st.write("")  # spacer to align with selectbox label
            notified = "✅ Yes" if t.get("wd_supervisor_notified") else "No"
            st.markdown(f'<p style="text-align:left;"><strong>Notified:</strong> {notified}</p>', unsafe_allow_html=True)
            if not t.get("wd_supervisor_notified"):
                if st.button("Mark Notified", key="detail_wd_notified", disabled=not _detail_writes):
                    if _db_write(lambda c: turnover_service_mod.update_wd_panel(
                        conn=c, turnover_id=tid, today=today, wd_supervisor_notified=True, actor=actor
                    )):
                        st.rerun()
        with w3:
            st.write("")  # spacer to align with selectbox label
            installed = "✅ Yes" if t.get("wd_installed") else "No"
            st.markdown(f'<p style="text-align:left;"><strong>Installed:</strong> {installed}</p>', unsafe_allow_html=True)
            if not t.get("wd_installed"):
                if st.button("Mark Installed", key="detail_wd_installed", disabled=not _detail_writes):
                    if _db_write(lambda c: turnover_service_mod.update_wd_panel(
                        conn=c, turnover_id=tid, today=today, wd_installed=True, actor=actor
                    )):
                        st.rerun()

    # ===================================================================
    # PANEL D: RISKS (always visible)
    # ===================================================================
    with st.container(border=True):
        st.markdown('<p style="text-align:left;"><strong>RISKS</strong></p>', unsafe_allow_html=True)
        risks = risks_for_turnover
        if risks:
            for r in risks:
                sev = r.get("severity", "")
                icon = "🔴" if sev == "CRITICAL" else "🟡" if sev == "WARNING" else "⚪"
                st.markdown(f'<p style="text-align:left;">{icon} {r.get("risk_type", "")} ({sev}) — {r.get("description", "") or ""}</p>', unsafe_allow_html=True)
        else:
            st.caption("No active risks")

    # ===================================================================
    # PANEL E2: AUTHORITY & IMPORT COMPARISON (collapsible)
    # ===================================================================
    _override_fields = [
        ("Move-Out Date", "move_out_date", "last_import_move_out_date", "move_out_manual_override_at"),
        ("Ready Date", "report_ready_date", "last_import_ready_date", "ready_manual_override_at"),
        ("Move-In Date", "move_in_date", "last_import_move_in_date", "move_in_manual_override_at"),
        ("Status", "manual_ready_status", "last_import_status", "status_manual_override_at"),
    ]
    _any_override = any(t.get(of[3]) for of in _override_fields)
    _any_divergence = any(
        t.get(of[2]) is not None and str(t.get(of[1]) or "") != str(t.get(of[2]) or "")
        for of in _override_fields
    )
    _panel_indicator = " ⚠" if (_any_override or _any_divergence) else ""

    with st.expander(f"▶ Authority & Import Comparison{_panel_indicator}", expanded=False):
        auth_rows = []
        for label, sys_key, import_key, override_key in _override_fields:
            sys_val = t.get(sys_key) or ""
            if sys_key != "manual_ready_status":
                sys_val = _fmt_date(sys_val) if sys_val else "—"
            else:
                sys_val = sys_val or "—"
            import_val = t.get(import_key) or ""
            if import_key != "last_import_status":
                import_val = _fmt_date(import_val) if import_val else "—"
            else:
                import_val = import_val or "—"
            override_at = t.get(override_key)
            override_active = override_at is not None
            # Source
            legal_src = t.get("legal_confirmation_source")
            if sys_key == "move_out_date" and legal_src:
                source = "Legal Confirmed"
            elif override_active:
                source = "Manual"
            else:
                source = "Import"
            override_display = "Active" if override_active else ""
            auth_rows.append({
                "Field": label,
                "Current (System)": sys_val,
                "Last Import": import_val,
                "Source": source,
                "Override": override_display,
                "_override_active": override_active,
                "_divergent": override_active and str(t.get(sys_key) or "") != str(t.get(import_key) or "") and t.get(import_key) is not None,
                "_pending_clear": override_active and str(t.get(sys_key) or "") == str(t.get(import_key) or "") and t.get(import_key) is not None,
                "_override_key": override_key,
            })

        # Render table with row highlighting
        for i, ar in enumerate(auth_rows):
            if ar["_divergent"]:
                bg = "background-color: rgba(255, 193, 7, 0.15);"
            else:
                bg = ""
            cols = st.columns([1.5, 1.5, 1.5, 1, 0.8, 0.8])
            if i == 0:
                cols[0].markdown("**Field**")
                cols[1].markdown("**Current (System)**")
                cols[2].markdown("**Last Import**")
                cols[3].markdown("**Source**")
                cols[4].markdown("**Override**")
                cols[5].markdown("")
                cols = st.columns([1.5, 1.5, 1.5, 1, 0.8, 0.8])
            if ar["_divergent"]:
                cols[0].markdown(f'<span style="background-color:rgba(255,193,7,0.2);padding:2px 4px;border-radius:3px;">{ar["Field"]}</span>', unsafe_allow_html=True)
            else:
                cols[0].write(ar["Field"])
            cols[1].write(ar["Current (System)"])
            cols[2].write(ar["Last Import"])
            cols[3].write(ar["Source"])
            if ar["_pending_clear"]:
                cols[4].caption("Pending Clear")
            else:
                cols[4].write(ar["Override"])
            if ar["_override_active"]:
                if cols[5].button("Clear", key=f"clear_override_{ar['_override_key']}"):
                    override_field = ar["_override_key"]
                    def _do_clear(c, field=override_field):
                        c.execute(
                            f"UPDATE turnover SET {field} = NULL, updated_at = ? WHERE turnover_id = ?",
                            (datetime.now(timezone.utc).isoformat(), tid),
                        )
                        c.execute(
                            "INSERT INTO audit_log (entity_type, entity_id, field_name, old_value, new_value, changed_at, actor, source) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            ("turnover", tid, "manual_override_cleared", field, None,
                             datetime.now(timezone.utc).isoformat(), actor, "manual"),
                        )
                    if _db_write(_do_clear):
                        st.rerun()

    # ===================================================================
    # PANEL F: TASKS — Task | Assignee | Date | Exec | Confirm | Req ☑ | Block ▼
    # ===================================================================
    block_opts = BLOCK_OPTIONS
    with st.container(border=True):
        st.markdown("**TASKS**")
        th1, th2, th3, th4, th5, th6, th7 = st.columns([1.0, 1.2, 1.0, 1.2, 1.0, 0.5, 1.2])
        th1.markdown("**Task**")
        th2.markdown("**Assignee**")
        th3.markdown("**Date**")
        th4.markdown("**Execution**")
        th5.markdown("**Confirm**")
        th6.markdown("**Req**")
        th7.markdown("**Blocking**")
        st.divider()

        task_assignees_cfg = st.session_state.dropdown_config.get("task_assignees", {})
        detail_offsets_cfg = st.session_state.dropdown_config.get("task_offsets", DEFAULT_TASK_OFFSETS)
        detail_move_out = _parse_date(t.get("move_out_date"))
        tasks_sorted = sorted(tasks_for_turnover, key=lambda t: (t.get("task_type", ""), t.get("task_id", 0)))
        for task in tasks_sorted:
                task_type = task.get("task_type", "")
                task_id = task.get("task_id")
                if not task_id:
                    continue
                display_name = TASK_DISPLAY_NAMES.get(task_type, task_type)
                if task.get("vendor_due_date"):
                    due_val = _parse_date_for_input(task.get("vendor_due_date"))
                elif detail_move_out:
                    offset = detail_offsets_cfg.get(task_type, 1)
                    due_val = detail_move_out + timedelta(days=offset)
                else:
                    due_val = date.today()
                exec_cur = _normalize_enum(task.get("execution_status")) or "NOT_STARTED"
                exec_label = EXEC_VALUE_TO_LABEL.get(exec_cur)
                exec_options = list(EXEC_LABELS)
                if exec_label and exec_label not in exec_options:
                    exec_options.append(exec_label)
                exec_idx = _safe_index(exec_options, exec_label)

                conf_cur = _normalize_enum(task.get("confirmation_status")) or "PENDING"
                conf_label = CONFIRM_VALUE_TO_LABEL.get(conf_cur)
                conf_options = list(CONFIRM_LABELS)
                if conf_label and conf_label not in conf_options:
                    conf_options.append(conf_label)
                conf_idx = _safe_index(conf_options, conf_label)

                db_assignee = _normalize_label(task.get("assignee") or "")
                cfg = task_assignees_cfg.get(task_type, {})
                # Stable, deterministic options (sorted so order never shifts between reruns).
                cfg_opts = cfg.get("options") or [o for o in ASSIGNEE_OPTIONS if o]
                assignee_opts = ("",) + tuple(sorted({_normalize_label(x) for x in cfg_opts if _normalize_label(x)}))
                # Ensure DB value is selectable even if not in config
                if db_assignee and db_assignee not in assignee_opts:
                    assignee_opts = assignee_opts + (db_assignee,)
                assignee_key = f"detail_assignee_{task_id}_{task_type}"
                # Drive selection via session_state (not index) so widget + frontend always agree.
                cur_widget = st.session_state.get(assignee_key, "")
                if not isinstance(cur_widget, str) or cur_widget not in assignee_opts:
                    st.session_state[assignee_key] = db_assignee if db_assignee in assignee_opts else ""

                cur_block = task.get("blocking_reason") or ("Not Blocking" if not task.get("blocking") else "Other")
                block_options = list(block_opts)
                if cur_block and cur_block not in block_options:
                    block_options.append(cur_block)
                block_idx = _safe_index(block_options, cur_block)

                tc1, tc2, tc3, tc4, tc5, tc6, tc7 = st.columns([1.0, 1.2, 1.0, 1.2, 1.0, 0.5, 1.2])
                tc1.write(display_name)
                with tc2:
                    new_assignee = st.selectbox(
                        "Assignee",
                        assignee_opts,
                        key=assignee_key,
                        label_visibility="collapsed",
                        disabled=not _detail_writes
                    )
                    if _detail_writes and _normalize_label(new_assignee) != db_assignee:
                        if _db_write(lambda c: task_service_mod.update_task_fields(
                            conn=c, task_id=task_id, fields={"assignee": new_assignee or None}, today=today, actor=actor
                        )):
                            st.rerun()
                with tc3:
                    new_due = st.date_input(
                        "Date", value=due_val, key=f"detail_due_{task_id}_{task_type}", label_visibility="collapsed",
                        format="MM/DD/YYYY", disabled=not _detail_writes
                    )
                    if _detail_writes and new_due != due_val:
                        if _db_write(lambda c: task_service_mod.update_task_fields(
                            conn=c, task_id=task_id, fields={"vendor_due_date": new_due}, today=today, actor=actor
                        )):
                            st.rerun()
                with tc4:
                    new_exec = st.selectbox(
                        "Exec", exec_options, index=exec_idx, key=f"detail_exec_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    new_exec_val = EXEC_LABEL_TO_VALUE.get(new_exec)
                    if _detail_writes and new_exec_val is not None and _normalize_enum(task.get("execution_status")) != (new_exec_val or "").upper():
                        if _db_write(lambda c: task_service_mod.update_task_fields(
                            conn=c, task_id=task_id, fields={"execution_status": new_exec_val}, today=today, actor=actor
                        )):
                            st.toast(f"Execution → {new_exec}", icon="✅")
                            st.rerun()
                with tc5:
                    new_conf = st.selectbox(
                        "Confirm", conf_options, index=conf_idx, key=f"detail_conf_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    new_conf_val = CONFIRM_LABEL_TO_VALUE.get(new_conf)
                    if _detail_writes and new_conf_val and _normalize_enum(task.get("confirmation_status")) != (new_conf_val or "").upper():
                        if _db_write(lambda c: task_service_mod.update_task_fields(
                            conn=c, task_id=task_id, fields={"confirmation_status": new_conf_val}, today=today, actor=actor
                        )):
                            st.toast(f"Confirmation → {new_conf}", icon="✅")
                            st.rerun()
                with tc6:
                    req_val = bool(task.get("required"))
                    new_req = st.checkbox(
                        "Req", value=req_val, key=f"detail_req_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    if _detail_writes and new_req != req_val:
                        if _db_write(lambda c: task_service_mod.update_task_fields(
                            conn=c, task_id=task_id, fields={"required": new_req}, today=today, actor=actor
                        )):
                            st.rerun()
                with tc7:
                    new_block = st.selectbox(
                        "Block", block_options, index=block_idx, key=f"detail_block_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    if _detail_writes and new_block != cur_block:
                        if _db_write(lambda c: task_service_mod.update_task_fields(
                            conn=c, task_id=task_id,
                            fields={"blocking": new_block != "Not Blocking", "blocking_reason": new_block},
                            today=today, actor=actor
                        )):
                            st.rerun()

    # ===================================================================
    # PANEL G: NOTES
    # ===================================================================
    with st.container(border=True):
        st.markdown("**NOTES**")
        notes = notes_for_turnover
        for n in notes:
            col1, col2 = st.columns([4, 1])
            severity = n.get("note_type", "info")
            icon = "⛔" if n.get("blocking") else ""
            with col1:
                st.write(f"- {icon} {(n.get('description') or '')} ({severity})")
            with col2:
                if n.get("resolved_at"):
                    st.caption("Resolved")
                elif st.session_state.get("enable_db_writes") and note_service_mod and st.button("Resolve", key=f"note_resolve_{n.get('note_id')}"):
                    if _db_write(lambda c: note_service_mod.resolve_note(conn=c, note_id=n["note_id"], actor=actor)):
                        st.rerun()
        new_note = st.text_area("Add note (free text)", key="detail_new_note", placeholder="Description...")
        if st.button("Add note") and (new_note or "").strip():
            if st.session_state.get("enable_db_writes") and note_service_mod and _db_write(lambda c: note_service_mod.create_note(
                conn=c, turnover_id=tid, description=(new_note or "").strip(), actor=actor
            )):
                st.rerun()

# ---------------------------------------------------------------------------
# Dropdown Manager
# ---------------------------------------------------------------------------
def render_dropdown_manager():
    st.subheader("Dropdown Manager")
    st.caption("Manage assignees per task type. Execution statuses, confirmation statuses, and blocking reasons are system-controlled and cannot be changed here.")

    cfg = st.session_state.dropdown_config
    task_assignees = cfg.get("task_assignees", {})

    # --- Task Assignees (the only user-configurable dropdown) ---
    with st.container(border=True):
        st.markdown("**TASK ASSIGNEES**")
        st.caption("Add or remove assignees for each task type.")

        for task_code in TASK_TYPES_ALL:
            display_name = TASK_DISPLAY_NAMES.get(task_code, task_code)
            ta_cfg = task_assignees.get(task_code, {"options": [], "default": ""})
            opts = ta_cfg.get("options", [])

            with st.expander(f"{display_name} — {len(opts)} assignee(s)"):
                for i, opt in enumerate(opts):
                    c1, c3 = st.columns([4, 1])
                    c1.write(opt)
                    if c3.button("Remove", key=f"dd_rm_{task_code}_{i}"):
                        opts.pop(i)
                        _save_dropdown_config()
                        st.rerun()

                new_assignee = st.text_input("Add assignee", key=f"dd_add_{task_code}", placeholder="Name...")
                if st.button("Add", key=f"dd_add_btn_{task_code}") and (new_assignee or "").strip():
                    name = new_assignee.strip()
                    if name not in opts:
                        opts.append(name)
                        ta_cfg["options"] = opts
                        task_assignees[task_code] = ta_cfg
                        _save_dropdown_config()
                        st.rerun()

    # --- Task Offsets (days after move-out) ---
    task_offsets = cfg.get("task_offsets", {})
    with st.container(border=True):
        st.markdown("**TASK OFFSET SCHEDULE**")
        st.caption("Days after move-out when each task is scheduled. Select an offset and hit Save.")

        for task_code in TASK_TYPES_ALL:
            display_name = TASK_DISPLAY_NAMES.get(task_code, task_code)
            current_offset = task_offsets.get(task_code, DEFAULT_TASK_OFFSETS.get(task_code, 1))
            c1, c2, c3 = st.columns([2, 1.5, 1])
            c1.write(f"**{display_name}**")
            offset_idx = OFFSET_OPTIONS.index(current_offset) if current_offset in OFFSET_OPTIONS else 0
            new_offset = c2.selectbox(
                "Offset", OFFSET_OPTIONS, index=offset_idx,
                key=f"dd_offset_{task_code}", label_visibility="collapsed",
            )
            if c3.button("Save", key=f"dd_offset_save_{task_code}"):
                task_offsets[task_code] = new_offset
                cfg["task_offsets"] = task_offsets
                _save_dropdown_config()
                st.rerun()

        # Show current schedule summary
        st.divider()
        st.caption("Current schedule (days after move-out):")
        sorted_tasks = sorted(TASK_TYPES_ALL, key=lambda tc: task_offsets.get(tc, 99))
        for tc in sorted_tasks:
            dn = TASK_DISPLAY_NAMES.get(tc, tc)
            off = task_offsets.get(tc, "—")
            st.write(f"Day {off} → {dn}")

    # --- Reference: hard-coded system values (read-only display) ---
    with st.container(border=True):
        st.markdown("**SYSTEM-CONTROLLED VALUES** *(read-only — managed by backend)*")
        r1, r2, r3 = st.columns(3)
        with r1:
            st.caption("Execution Statuses")
            for label in EXEC_LABELS:
                st.write(f"· {label}")
        with r2:
            st.caption("Confirmation Statuses")
            for label in CONFIRM_LABELS:
                st.write(f"· {label}")
        with r3:
            st.caption("Blocking Reasons")
            for label in BLOCK_OPTIONS:
                st.write(f"· {label}")

# ---------------------------------------------------------------------------
# Admin: Property Structure (read-only hierarchy)
# ---------------------------------------------------------------------------
def render_property_structure():
    st.subheader("Property structure")
    st.caption("Read-only view: property → phase → building → unit. Use to validate hierarchy migration.")
    if not db_repository:
        st.info("Backend not available.")
        return
    conn = _get_conn()
    if not conn:
        st.error("Database not available")
        return
    try:
        properties = db_repository.list_properties(conn)
        if not properties:
            st.write("No properties in database. Create one below.")
            if st.session_state.get("enable_db_writes"):
                name = st.text_input("Property name", value="My Property", key="ps_new_property_name")
                if st.button("Create property", key="ps_create_property"):
                    def do_create(conn):
                        db_repository.insert_property(conn, name or "My Property")
                    if _db_write(do_create):
                        st.success("Property created.")
                        st.rerun()
            else:
                st.caption("Enable DB Writes in the sidebar to create a property.")
            return
        for prop in properties:
            prop = dict(prop)
            pid = prop["property_id"]
            name = prop.get("name") or f"Property {pid}"
            with st.expander(f"**{name}** (id={pid})", expanded=True):
                phases = db_repository.list_phases(conn, property_id=pid)
                if st.session_state.get("enable_db_writes"):
                    st.caption("Add another phase to this property:")
                    add_phase_col1, add_phase_col2 = st.columns([1, 3])
                    with add_phase_col1:
                        new_phase_code = st.text_input("Phase code", value="", key=f"ps_phase_code_{pid}", placeholder="e.g. 5, 7, 8")
                    with add_phase_col2:
                        if st.button("Add phase", key=f"ps_add_phase_{pid}") and (new_phase_code or "").strip():
                            def do_add_phase(conn, prop_id=pid, code=new_phase_code.strip()):
                                db_repository.resolve_phase(conn, property_id=prop_id, phase_code=code)
                            if _db_write(lambda c: do_add_phase(c)):
                                st.success(f"Phase {new_phase_code.strip()} added.")
                                st.rerun()
                if not phases:
                    st.caption("No phases yet.")
                    continue
                for ph in phases:
                    ph = dict(ph)
                    phase_id = ph["phase_id"]
                    phase_code = ph.get("phase_code") or ""
                    st.markdown(f"Phase **{phase_code}** (id={phase_id})")
                    buildings = db_repository.list_buildings(conn, phase_id=phase_id)
                    if not buildings:
                        st.caption("  No buildings.")
                        continue
                    for b in buildings:
                        b = dict(b)
                        building_id = b["building_id"]
                        bcode = b.get("building_code") or ""
                        units = db_repository.list_units(conn, building_id=building_id)
                        unit_list = ", ".join(str(dict(u).get("unit_number") or dict(u).get("unit_id")) for u in units) if units else "—"
                        st.caption(f"  Building {bcode} (id={building_id}): units {unit_list}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Operations: Add Unit (add unit to active turnover)
# ---------------------------------------------------------------------------
def render_add_availability():
    st.subheader("Add unit")
    st.caption("Add unit to active turnover. Unit must already exist in the database (e.g. from Unit Master Import); one open turnover per unit. If Phase + Building + Unit does not match a unit in the database, it cannot enter the lifecycle.")
    if not manual_availability_service_mod or not db_repository:
        st.warning("Backend or manual availability service not available.")
        if _BACKEND_ERROR is not None:
            with st.expander("Details"):
                st.code(str(_BACKEND_ERROR), language=None)
                st.caption("Run from repo root: streamlit run the-dmrb/app.py")
        return
    if not st.session_state.get("enable_db_writes"):
        st.caption("Turn on **Enable DB Writes** in the sidebar to submit.")
    conn = _get_conn()
    if not conn:
        st.error("Database not available")
        return
    try:
        properties = db_repository.list_properties(conn)
        if not properties:
            st.error("No properties in database. Add a property first.")
            name = st.text_input("Property name", value="My Property", key="add_avail_new_property_name")
            if st.button("Create property", key="add_avail_create_property"):
                def do_create(conn):
                    db_repository.insert_property(conn, name or "My Property")
                if _db_write(do_create):
                    st.success("Property created. Refreshing.")
                    st.rerun()
            return
        properties = [dict(p) for p in properties]
        property_id = properties[0]["property_id"] if len(properties) == 1 else None
        if property_id is None:
            prop_opts = [f"{p.get('name') or p['property_id']} (id={p['property_id']})" for p in properties]
            sel = st.selectbox("Property", prop_opts, key="add_avail_property")
            property_id = int(sel.split("(id=")[1].rstrip(")"))
        else:
            p0 = dict(properties[0])
            st.caption(f"Property: {p0.get('name') or property_id}")
        phases = db_repository.list_phases(conn, property_id=property_id)
        if not phases:
            st.warning("No phases for this property. Run **Admin → Unit Master Import** with your Units CSV first to populate Phase and Building dropdowns, or create one phase below.")
            if not st.session_state.get("enable_db_writes"):
                st.caption("Turn on **Enable DB Writes** in the sidebar, then use the form below.")
            phase_code_input = st.text_input("Phase code", value="5", key="add_avail_new_phase_code", help="e.g. 5, 7, or 8")
            if st.button("Create phase", key="add_avail_create_phase"):
                if not st.session_state.get("enable_db_writes"):
                    st.error("Enable DB Writes in the sidebar first.")
                else:
                    code = (phase_code_input or "5").strip()
                    if not code:
                        st.error("Enter a phase code.")
                    else:
                        def do_create_phase(conn):
                            db_repository.resolve_phase(conn, property_id=property_id, phase_code=code)
                        if _db_write(do_create_phase):
                            st.success("Phase created. Refreshing.")
                            st.rerun()
            return
        phases = [dict(p) for p in phases]
        phase_opts = sorted(
            [str(p.get("phase_code") or p.get("phase_id") or "") for p in phases if (p.get("phase_code") or p.get("phase_id"))],
            key=lambda x: (int(x) if x.isdigit() else float("inf"), x),
        )
        if not phase_opts:
            phase_opts = [str(p.get("phase_id", "")) for p in phases]
        prev_phase = st.session_state.get("add_avail_phase")
        phase_idx = phase_opts.index(prev_phase) if prev_phase in phase_opts else 0
        phase_code = st.selectbox("Phase", phase_opts, index=phase_idx, key="add_avail_phase")
        # Clear stale building selection when phase changes
        if prev_phase is not None and prev_phase != phase_code:
            st.session_state.pop("add_avail_building", None)
        phase_row = next((p for p in phases if str(p.get("phase_code") or p.get("phase_id") or "") == phase_code), phases[0] if phases else None)
        phase_id = int(phase_row["phase_id"]) if phase_row else None
        buildings = db_repository.list_buildings(conn, phase_id=phase_id) if phase_id else []
        buildings = [dict(b) for b in buildings]
        building_opts = sorted(
            [str(b.get("building_code") or b.get("building_id") or "") for b in buildings if (b.get("building_code") or b.get("building_id"))],
            key=lambda x: (int(x) if x.isdigit() else float("inf"), x),
        )
        if not building_opts:
            building_opts = [str(b.get("building_id", "")) for b in buildings]
        if building_opts:
            prev_bldg = st.session_state.get("add_avail_building")
            building_idx = building_opts.index(prev_bldg) if prev_bldg in building_opts else 0
            building_code = st.selectbox("Building", building_opts, index=building_idx, key="add_avail_building")
        else:
            st.warning(f"No buildings found for Phase {phase_code}. Run **Unit Master Import** or create one below.")
            if not st.session_state.get("enable_db_writes"):
                st.caption("Turn on **Enable DB Writes** in the sidebar, then use the form below.")
            building_code_input = st.text_input("Building code", value="1", key="add_avail_new_building_code", help="e.g. 1, 2, A, B")
            if st.button("Create building", key="add_avail_create_building"):
                if not st.session_state.get("enable_db_writes"):
                    st.error("Enable DB Writes in the sidebar first.")
                else:
                    bcode = (building_code_input or "1").strip()
                    if not bcode:
                        st.error("Enter a building code.")
                    else:
                        def do_create_building(conn):
                            db_repository.resolve_building(conn, phase_id=phase_id, building_code=bcode)
                        if _db_write(do_create_building):
                            st.success(f"Building {bcode} created under Phase {phase_code}. Refreshing.")
                            st.rerun()
            return
        unit_number = st.text_input("Unit", key="add_avail_unit_number").strip()
        move_out_date = st.date_input("Move out", key="add_avail_move_out", format="MM/DD/YYYY")
        report_ready_date = st.date_input("Ready date (optional)", value=None, key="add_avail_report_ready", format="MM/DD/YYYY")
        move_in_date = st.date_input("Move in (optional)", value=None, key="add_avail_move_in", format="MM/DD/YYYY")
        if st.button("Add unit", key="add_avail_submit"):
            if not st.session_state.get("enable_db_writes"):
                st.error("Enable DB Writes in the sidebar to create a turnover.")
            elif not unit_number:
                st.error("Unit is required.")
            else:
                def do_add(conn):
                    return manual_availability_service_mod.add_manual_availability(
                        conn=conn,
                        property_id=property_id,
                        phase_code=phase_code,
                        building_code=building_code,
                        unit_number=unit_number,
                        move_out_date=move_out_date,
                        move_in_date=move_in_date if move_in_date else None,
                        report_ready_date=report_ready_date if report_ready_date else None,
                        today=date.today(),
                        actor="manager",
                    )
                if _db_write(do_add):
                    st.success("Turnover created. You can open it from the board or detail.")
                    st.rerun()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Admin: Unit Master Import
# ---------------------------------------------------------------------------
def render_unit_master_import():
    st.subheader("Unit Master Import")
    st.caption("One-time structural bootstrap from Units.csv. Writes only to unit (and phase/building when creating units). Does not touch turnover, task, risk, or SLA.")
    if not unit_master_import_service_mod or not db_repository:
        st.warning("Backend or unit master import service not available.")
        if _BACKEND_ERROR is not None:
            with st.expander("Details"):
                st.code(str(_BACKEND_ERROR), language=None)
                st.caption("Run from repo root: streamlit run the-dmrb/app.py")
        return
    if not st.session_state.get("enable_db_writes"):
        st.warning("Enable DB Writes in the sidebar to run import.")
        return
    conn = _get_conn()
    if not conn:
        st.error("Database not available")
        return
    try:
        properties = db_repository.list_properties(conn)
        if not properties:
            st.error("No properties in database. Add a property first.")
            name = st.text_input("Property name", value="My Property", key="um_import_new_property_name")
            if st.button("Create property", key="um_import_create_property"):
                def do_create(conn):
                    db_repository.insert_property(conn, name or "My Property")
                if _db_write(do_create):
                    st.success("Property created. Refreshing.")
                    st.rerun()
            return
        properties = [dict(p) for p in properties]
        property_id = properties[0]["property_id"] if len(properties) == 1 else None
        if property_id is None:
            prop_opts = [f"{p.get('name') or p['property_id']} (id={p['property_id']})" for p in properties]
            sel = st.selectbox("Property", prop_opts, key="um_import_property")
            property_id = int(sel.split("(id=")[1].rstrip(")"))
        else:
            st.caption(f"Property: {properties[0].get('name') or property_id}")
        strict_mode = st.checkbox("Strict mode (fail if unit not found; no creates)", value=False, key="um_import_strict")
        uploaded = st.file_uploader("Units.csv", type=["csv"], key="um_import_file")
        if st.button("Run Unit Master Import", key="um_import_run"):
            if uploaded is None:
                st.warning("Upload a CSV file first.")
            else:
                import tempfile
                with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
                    tmp.write(uploaded.getvalue())
                    tmp_path = tmp.name
                try:
                    um_result = [None]

                    def do_import(conn):
                        um_result[0] = unit_master_import_service_mod.run_unit_master_import(
                            conn, tmp_path, property_id=property_id, strict_mode=strict_mode
                        )

                    if _db_write(do_import):
                        result = um_result[0] or {}
                        status_label = result.get("status", "SUCCESS")
                        if status_label == "NO_OP":
                            st.info(f"No-op: this file was already imported (checksum match). Applied: 0")
                        else:
                            st.success(f"Status: {status_label} | Applied: {result.get('applied_count', 0)} | Conflicts: {result.get('conflict_count', 0)} | Errors: {result.get('error_count', 0)}")
                        if result.get("errors"):
                            for err in result["errors"][:20]:
                                st.write(f"- {err}")
                            if len(result["errors"]) > 20:
                                st.caption(f"... and {len(result['errors']) - 20} more.")
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
def render_import():
    st.subheader("Import console")
    uploaded = st.file_uploader("Select file", key="import_file", type=["csv", "xlsx", "xls"])
    report_type = st.selectbox("Report type", ["MOVE_OUTS", "PENDING_MOVE_INS", "AVAILABLE_UNITS", "PENDING_FAS", "DMRB"], key="import_type")

    if not import_service_mod or not db_repository:
        st.warning("Backend or import service not available.")
        if _BACKEND_ERROR is not None:
            with st.expander("Details"):
                st.code(str(_BACKEND_ERROR), language=None)
        return
    if not st.session_state.get("enable_db_writes"):
        st.warning("Enable **Enable DB Writes** in the sidebar to run import.")
        return

    if st.button("Run import", key="import_run"):
        if uploaded is None:
            st.warning("Upload a file first.")
        else:
            import tempfile
            db_path = _get_db_path()
            with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
                tmp.write(uploaded.getvalue())
                tmp_path = tmp.name
            conn = _get_conn()
            if not conn:
                st.error("Database not available")
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                return
            try:
                result = import_service_mod.import_report_file(
                    conn=conn,
                    report_type=report_type,
                    file_path=tmp_path,
                    property_id=1,
                    db_path=db_path,
                )
                conn.commit()
                status = result.get("status", "SUCCESS")
                batch_id = result.get("batch_id", "")
                record_count = result.get("record_count", 0)
                applied_count = result.get("applied_count", 0)
                conflict_count = result.get("conflict_count", 0)
                invalid_count = result.get("invalid_count", 0)
                if status == "NO_OP":
                    st.info(f"No-op: file already imported (checksum match). Batch ID: {batch_id} | Records: {record_count} | Applied: 0")
                else:
                    st.success(
                        f"Batch ID: {batch_id} | Status: {status} | Records: {record_count} | "
                        f"Applied: {applied_count} | Conflicts: {conflict_count} | Invalid: {invalid_count}"
                    )
            except Exception as e:
                conn.rollback()
                st.error(str(e))
            finally:
                conn.close()
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    st.subheader("Conflicts")
    st.caption("Conflict details are recorded in import_row for the batch. List conflicts here when a batch is selected (future).")

# ---------------------------------------------------------------------------
# Admin (tabbed page)
# ---------------------------------------------------------------------------
def render_admin():
    st.subheader("Admin")
    tab_add, tab_import, tab_unit_master, tab_dropdown = st.tabs(
        ["Add Unit", "Import", "Unit Master Import", "Dropdown Manager"]
    )
    with tab_add:
        render_add_availability()
    with tab_import:
        render_import()
    with tab_unit_master:
        render_unit_master_import()
    with tab_dropdown:
        render_dropdown_manager()

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
if st.session_state.page == "dmrb_board":
    render_dmrb_board()
elif st.session_state.page == "flag_bridge":
    render_flag_bridge()
elif st.session_state.page == "detail":
    render_detail()
elif st.session_state.page == "admin":
    render_admin()
else:
    render_dmrb_board()
