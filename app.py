"""
The DMRB — Apartment Turn Tracker.
Run from repo root: streamlit run the-dmrb/app.py
Set COCKPIT_DB_PATH for backend mode (default: the-dmrb/data/cockpit.db).
Backend-only: app fails visibly if DB/services fail to load.
"""
import os
import unicodedata
from datetime import date, datetime, timedelta, timezone
import json
from typing import Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

import pandas as pd
import streamlit as st
from application.commands import (
    ApplyImportRow,
    ClearManualOverride,
    CreateTurnover,
    UpdateTaskStatus,
    UpdateTurnoverDates,
    UpdateTurnoverStatus,
)
from application.workflows import (
    apply_import_row_workflow,
    clear_manual_override_workflow,
    create_turnover_workflow,
    update_task_status_workflow,
    update_turnover_dates_workflow,
    update_turnover_status_workflow,
)
from config.settings import get_settings
from ui.actions.db import db_write as ui_db_write, get_conn as ui_get_conn, get_db_path as ui_get_db_path
from ui.components.sidebar import render_navigation
from ui.screens.admin import render_admin as render_admin_screen
from ui.screens.ai_agent import render_ai_agent as render_ai_agent_screen
from ui.screens.board import render_board as render_board_screen
from ui.screens.flag_bridge import render_flag_bridge as render_flag_bridge_screen
from ui.screens.risk_radar import render_risk_radar as render_risk_radar_screen
from ui.screens.turnover_detail import render_turnover_detail as render_turnover_detail_screen
from ui.state import (
    ASSIGNEE_OPTIONS,
    BLOCK_OPTIONS,
    BRIDGE_MAP,
    CONFIRM_LABEL_TO_VALUE,
    CONFIRM_VALUE_TO_LABEL,
    DEFAULT_TASK_ASSIGNEES,
    DEFAULT_TASK_OFFSETS,
    EXEC_LABEL_TO_VALUE,
    EXEC_VALUE_TO_LABEL,
    OFFSET_OPTIONS,
    STATUS_OPTIONS,
    TASK_DISPLAY_NAMES,
    TASK_TYPES_ALL,
    init_session_state,
    save_dropdown_config,
)

# Backend required
_BACKEND_ERROR = None
try:
    from db.connection import get_connection, ensure_database_ready
    from db import repository as db_repository
    from services import board_query_service
    from services import export_service as export_service_mod
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
    db_repository = export_service_mod = import_service_mod = manual_availability_service_mod = note_service_mod = None
    task_service_mod = turnover_service_mod = unit_master_import_service_mod = None

APP_SETTINGS = get_settings()

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
    return st.session_state.get("dropdown_config", {})


def _save_dropdown_config():
    save_dropdown_config(st.session_state.dropdown_config)


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
def _init_session_state():
    init_session_state()

_init_session_state()


def _get_db_path():
    return ui_get_db_path()


# Ensure DB is schema-initialized and migrated before any read path.
# Allow deployments to opt out of bootstrap when the Postgres schema
# has already been created and migrated, to avoid long-running
# initialization on managed services with strict statement timeouts.
_skip_bootstrap_flag = os.getenv("SKIP_DB_BOOTSTRAP", "")
if _skip_bootstrap_flag.strip().lower() not in {"1", "true", "yes", "on", "y"}:
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
    return ui_get_conn(_BACKEND_AVAILABLE)


def _db_available() -> bool:
    conn = _get_conn()
    if not conn:
        return False
    conn.close()
    return True


def _invalidate_ui_caches():
    st.cache_data.clear()


def _db_write(do_write):
    return ui_db_write(do_write, backend_available=_BACKEND_AVAILABLE and turnover_service_mod is not None)


def _db_cache_identity() -> str:
    return f"postgres:{APP_SETTINGS.database_url or ''}"


def _iso_to_date(value: str) -> date:
    return date.fromisoformat(value)


@st.cache_data(ttl=10, show_spinner=False)
def _cached_list_properties(db_identity: str) -> list[dict]:
    if not db_repository:
        return []
    conn = _get_conn()
    if not conn:
        return []
    try:
        return [dict(row) for row in db_repository.list_properties(conn)]
    finally:
        conn.close()


def _sync_active_property(properties: list[dict]) -> dict | None:
    if not properties:
        st.session_state.selected_property_id = None
        st.session_state.selected_property_name = ""
        return None
    selected_id = st.session_state.get("selected_property_id")
    active = next((p for p in properties if p["property_id"] == selected_id), None)
    if active is None:
        active = properties[0]
    _set_active_property(active["property_id"], active.get("name") or f"Property {active['property_id']}")
    return active


def _get_active_property() -> dict | None:
    return _sync_active_property(_cached_list_properties(_db_cache_identity()))


def _set_active_property(property_id: int, property_name: str) -> None:
    if st.session_state.get("selected_property_id") != property_id:
        st.session_state.filter_phase = "All"
        st.session_state.selected_turnover_id = None
    st.session_state.selected_property_id = property_id
    st.session_state.selected_property_name = property_name


def _render_active_property_banner() -> dict | None:
    active_property = _get_active_property()
    if active_property is None:
        st.info("Create a property in the Admin tab to begin.")
        return None
    st.caption(f"Active Property: {st.session_state.selected_property_name}")
    return active_property


@st.cache_data(ttl=10, show_spinner=False)
def _cached_list_phases(db_identity: str, property_id: int | None = None) -> list[dict]:
    if not db_repository:
        return []
    conn = _get_conn()
    if not conn:
        return []
    try:
        return [dict(row) for row in db_repository.list_phases(conn, property_id=property_id)]
    finally:
        conn.close()


@st.cache_data(ttl=10, show_spinner=False)
def _cached_list_buildings(db_identity: str, phase_id: int) -> list[dict]:
    if not db_repository:
        return []
    conn = _get_conn()
    if not conn:
        return []
    try:
        return [dict(row) for row in db_repository.list_buildings(conn, phase_id=phase_id)]
    finally:
        conn.close()


@st.cache_data(ttl=10, show_spinner=False)
def _cached_list_units(db_identity: str, building_id: int) -> list[dict]:
    if not db_repository:
        return []
    conn = _get_conn()
    if not conn:
        return []
    try:
        return [dict(row) for row in db_repository.list_units(conn, building_id=building_id)]
    finally:
        conn.close()


@st.cache_data(ttl=10, show_spinner=False)
def _cached_list_unit_master_import_units(db_identity: str) -> list[dict]:
    if not db_repository:
        return []
    conn = _get_conn()
    if not conn:
        return []
    try:
        return db_repository.list_unit_master_import_units(conn)
    finally:
        conn.close()


@st.cache_data(ttl=5, show_spinner=False)
def _cached_get_flag_bridge_rows(
    db_identity: str,
    property_id: int | None,
    phase_ids: tuple[int, ...] | None,
    search_unit: str | None,
    filter_phase: str | None,
    filter_status: str | None,
    filter_nvm: str | None,
    filter_assignee: str | None,
    filter_qc: str | None,
    breach_filter: str | None,
    breach_value: str | None,
    today_iso: str,
) -> list[dict]:
    if not board_query_service:
        return []
    conn = _get_conn()
    if not conn:
        return []
    try:
        return board_query_service.get_flag_bridge_rows(
            conn,
            property_ids=[property_id] if property_id is not None else None,
            phase_ids=list(phase_ids) if phase_ids else None,
            search_unit=search_unit,
            filter_phase=filter_phase,
            filter_status=filter_status,
            filter_nvm=filter_nvm,
            filter_assignee=filter_assignee,
            filter_qc=filter_qc,
            breach_filter=breach_filter,
            breach_value=breach_value,
            today=_iso_to_date(today_iso),
        )
    finally:
        conn.close()


@st.cache_data(ttl=5, show_spinner=False)
def _cached_get_dmrb_board_rows(
    db_identity: str,
    property_id: int | None,
    phase_ids: tuple[int, ...] | None,
    search_unit: str | None,
    filter_phase: str | None,
    filter_status: str | None,
    filter_nvm: str | None,
    filter_assignee: str | None,
    filter_qc: str | None,
    today_iso: str,
) -> list[dict]:
    if not board_query_service:
        return []
    conn = _get_conn()
    if not conn:
        return []
    try:
        return board_query_service.get_dmrb_board_rows(
            conn,
            property_ids=[property_id] if property_id is not None else None,
            phase_ids=list(phase_ids) if phase_ids else None,
            search_unit=search_unit,
            filter_phase=filter_phase,
            filter_status=filter_status,
            filter_nvm=filter_nvm,
            filter_assignee=filter_assignee,
            filter_qc=filter_qc,
            today=_iso_to_date(today_iso),
        )
    finally:
        conn.close()


@st.cache_data(ttl=5, show_spinner=False)
def _cached_get_risk_radar_rows(
    db_identity: str,
    property_id: int | None,
    phase_ids: tuple[int, ...] | None,
    search_unit: str | None,
    filter_phase: str | None,
    risk_level: str | None,
    today_iso: str,
) -> list[dict]:
    if not board_query_service:
        return []
    conn = _get_conn()
    if not conn:
        return []
    try:
        return board_query_service.get_risk_radar_rows(
            conn,
            property_ids=[property_id] if property_id is not None else None,
            phase_ids=list(phase_ids) if phase_ids else None,
            search_unit=search_unit,
            filter_phase=filter_phase,
            risk_level=risk_level,
            today=_iso_to_date(today_iso),
        )
    finally:
        conn.close()


@st.cache_data(ttl=5, show_spinner=False)
def _cached_get_turnover_detail(db_identity: str, turnover_id: int, today_iso: str) -> dict:
    if not board_query_service:
        return {}
    conn = _get_conn()
    if not conn:
        return {}
    try:
        return board_query_service.get_turnover_detail(conn, turnover_id, today=_iso_to_date(today_iso))
    finally:
        conn.close()

EXEC_LABELS = [k for k in EXEC_LABEL_TO_VALUE if k]
CONFIRM_LABELS = list(CONFIRM_LABEL_TO_VALUE.keys())

render_navigation(st.session_state.page)

# Sidebar: Top flags by category
st.sidebar.divider()
st.sidebar.markdown("**Top Flags**")
if not _db_available():
    _all_rows = []
    st.sidebar.error("Database not available")
else:
    try:
        db_identity = _db_cache_identity()
        active_property = _get_active_property()
        phase_ids = None
        if db_repository and st.session_state.filter_phase != "All":
            phase_map = {
                str(p["phase_code"]): p["phase_id"]
                for p in _cached_list_phases(db_identity, active_property["property_id"] if active_property else None)
            }
            phase_id = phase_map.get(st.session_state.filter_phase)
            if phase_id is not None:
                phase_ids = (phase_id,)
                st.session_state.phase_id_by_code = phase_map
        _all_rows = _cached_get_flag_bridge_rows(
            db_identity,
            active_property["property_id"] if active_property else None,
            phase_ids,
            search_unit=st.session_state.search_unit or None,
            filter_phase=None,
            filter_status=st.session_state.filter_status if st.session_state.filter_status != "All" else None,
            filter_nvm=st.session_state.filter_nvm if st.session_state.filter_nvm != "All" else None,
            filter_assignee=st.session_state.filter_assignee if st.session_state.filter_assignee != "All" else None,
            filter_qc=st.session_state.filter_qc if st.session_state.filter_qc != "All" else None,
            breach_filter=None,
            breach_value=None,
            today_iso=date.today().isoformat(),
        )
    except Exception as e:
        _all_rows = []
        st.sidebar.error(str(e))
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
    if not _db_available():
        st.error("Database not available")
        return []
    try:
        db_identity = _db_cache_identity()
        active_property = _get_active_property()
        phase_ids = None
        if db_repository and st.session_state.filter_phase != "All":
            if "phase_id_by_code" not in st.session_state:
                phases = _cached_list_phases(db_identity, active_property["property_id"] if active_property else None)
                st.session_state.phase_id_by_code = {str(p["phase_code"]): p["phase_id"] for p in phases}
            phase_id = st.session_state.get("phase_id_by_code", {}).get(st.session_state.filter_phase)
            if phase_id is not None:
                phase_ids = (phase_id,)
        return _cached_get_dmrb_board_rows(
            db_identity,
            active_property["property_id"] if active_property else None,
            phase_ids,
            search_unit=st.session_state.search_unit or None,
            filter_phase=None,
            filter_status=st.session_state.filter_status if st.session_state.filter_status != "All" else None,
            filter_nvm=st.session_state.filter_nvm if st.session_state.filter_nvm != "All" else None,
            filter_assignee=st.session_state.filter_assignee if st.session_state.filter_assignee != "All" else None,
            filter_qc=st.session_state.filter_qc if st.session_state.filter_qc != "All" else None,
            today_iso=date.today().isoformat(),
        )
    except Exception as e:
        st.error(str(e))
        return []

def _exec_label(task_dict):
    """Get display label for a task's execution status."""
    cur = (task_dict.get("execution_status") or "NOT_STARTED").upper()
    return EXEC_VALUE_TO_LABEL.get(cur, "Not Started")

def _confirm_label(task_dict):
    """Get display label for a task's confirmation status."""
    cur = (task_dict.get("confirmation_status") or "PENDING").upper()
    return CONFIRM_VALUE_TO_LABEL.get(cur, "Pending")

def render_dmrb_board():
    active_property = _render_active_property_banner()
    if active_property is None:
        return
    rows = _get_dmrb_rows()
    n_active = len(rows)
    n_crit = sum(1 for r in rows if r.get("has_violation") or r.get("operational_state") == "Move-In Risk")

    # --- ZONE 1: FILTERS ---
    with st.container(border=True):
        c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1, 1, 1, 1, 1, 1, 1])
        with c0:
            st.session_state.search_unit = st.text_input("Search unit", value=st.session_state.search_unit, key="dmrb_search")
        with c1:
            if db_repository:
                try:
                    active_property = _get_active_property()
                    phases = _cached_list_phases(
                        _db_cache_identity(),
                        active_property["property_id"] if active_property else None,
                    )
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
                actor = APP_SETTINGS.default_actor
                for tid, new_status in status_updates:
                    update_turnover_status_workflow(
                        conn,
                        UpdateTurnoverStatus(
                            turnover_id=tid,
                            manual_ready_status=new_status,
                            today=today,
                            actor=actor,
                        ),
                    )
                for tid, kwargs in date_updates:
                    update_turnover_dates_workflow(
                        conn,
                        UpdateTurnoverDates(
                            turnover_id=tid,
                            today=today,
                            actor=actor,
                            move_out_date=kwargs.get("move_out_date"),
                            report_ready_date=kwargs.get("report_ready_date"),
                            move_in_date=kwargs.get("move_in_date"),
                        ),
                    )
                for task_id, new_val in task_exec_updates:
                    update_task_status_workflow(
                        conn,
                        UpdateTaskStatus(
                            task_id=task_id,
                            fields={"execution_status": new_val},
                            today=today,
                            actor=actor,
                        ),
                    )
                for task_id, new_val in task_confirm_updates:
                    update_task_status_workflow(
                        conn,
                        UpdateTaskStatus(
                            task_id=task_id,
                            fields={"confirmation_status": new_val},
                            today=today,
                            actor=actor,
                        ),
                    )
                for task_id, new_date in task_date_updates:
                    update_task_status_workflow(
                        conn,
                        UpdateTaskStatus(
                            task_id=task_id,
                            fields={"vendor_due_date": new_date},
                            today=today,
                            actor=actor,
                        ),
                    )
                conn.commit()
                _invalidate_ui_caches()
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
    if not _db_available():
        return []
    try:
        db_identity = _db_cache_identity()
        active_property = _get_active_property()
        phase_ids = None
        if db_repository and st.session_state.filter_phase != "All":
            phase_id = st.session_state.get("phase_id_by_code", {}).get(st.session_state.filter_phase)
            if phase_id is not None:
                phase_ids = (phase_id,)
        return _cached_get_flag_bridge_rows(
            db_identity,
            active_property["property_id"] if active_property else None,
            phase_ids,
            search_unit=st.session_state.search_unit or None,
            filter_phase=None,
            filter_status=st.session_state.filter_status if st.session_state.filter_status != "All" else None,
            filter_nvm=st.session_state.filter_nvm if st.session_state.filter_nvm != "All" else None,
            filter_assignee=st.session_state.filter_assignee if st.session_state.filter_assignee != "All" else None,
            filter_qc=st.session_state.filter_qc if st.session_state.filter_qc != "All" else None,
            breach_filter=st.session_state.breach_filter if st.session_state.breach_filter != "All" else None,
            breach_value=st.session_state.breach_value if st.session_state.breach_value != "All" else None,
            today_iso=date.today().isoformat(),
        )
    except Exception as e:
        st.error(str(e))
        return []

def render_flag_bridge():
    active_property = _render_active_property_banner()
    if active_property is None:
        return
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


def _get_risk_radar_rows(phase_filter: str, search_unit: str, risk_level: str):
    if not _db_available():
        st.error("Database not available")
        return []
    try:
        db_identity = _db_cache_identity()
        active_property = _get_active_property()
        phase_ids = None
        if db_repository and phase_filter != "All":
            phases = _cached_list_phases(db_identity, active_property["property_id"] if active_property else None)
            phase_id_by_code = {str(p["phase_code"]): p["phase_id"] for p in phases}
            phase_id = phase_id_by_code.get(phase_filter)
            if phase_id is not None:
                phase_ids = (phase_id,)
        return _cached_get_risk_radar_rows(
            db_identity,
            active_property["property_id"] if active_property else None,
            phase_ids,
            search_unit=search_unit or None,
            filter_phase=None,
            risk_level=risk_level if risk_level != "All" else None,
            today_iso=date.today().isoformat(),
        )
    except Exception as e:
        st.error(str(e))
        return []


def render_risk_radar():
    st.subheader("Turnover Risk Radar")
    st.caption("Units most likely to miss readiness or move-in deadlines.")
    active_property = _render_active_property_banner()
    if active_property is None:
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if db_repository:
            try:
                active_property = _get_active_property()
                phases = _cached_list_phases(
                    _db_cache_identity(),
                    active_property["property_id"] if active_property else None,
                )
                phase_opts = ["All"] + sorted(str(p["phase_code"]) for p in phases)
            except Exception:
                phase_opts = ["All", "5", "7", "8"]
        else:
            phase_opts = ["All", "5", "7", "8"]
        phase_filter = st.selectbox("Phase", phase_opts, index=0, key="rr_phase")
    with c2:
        risk_level = st.selectbox("Risk Level", ["All", "HIGH", "MEDIUM", "LOW"], index=0, key="rr_level")
    with c3:
        search_unit = st.text_input("Unit Search", value=st.session_state.get("rr_search", ""), key="rr_search")

    all_rows = _get_risk_radar_rows(phase_filter, search_unit, "All")
    rows = all_rows if risk_level == "All" else [r for r in all_rows if (r.get("risk_level") or "LOW") == risk_level]

    high_count = sum(1 for r in all_rows if r.get("risk_level") == "HIGH")
    med_count = sum(1 for r in all_rows if r.get("risk_level") == "MEDIUM")
    low_count = sum(1 for r in all_rows if r.get("risk_level") == "LOW")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Active Turnovers", len(all_rows))
    m2.metric("High Risk", high_count)
    m3.metric("Medium Risk", med_count)
    m4.metric("Low Risk", low_count)

    if not rows:
        st.info("No turnovers match current Risk Radar filters.")
        return

    def _risk_display(level: str) -> str:
        if level == "HIGH":
            return "🔴 HIGH"
        if level == "MEDIUM":
            return "🟠 MEDIUM"
        return "🟢 LOW"

    radar_table = []
    for row in rows:
        radar_table.append(
            {
                "Unit": row.get("unit_code") or "",
                "Phase": row.get("phase_code") or "",
                "Risk Level": _risk_display(row.get("risk_level") or "LOW"),
                "Risk Score": row.get("risk_score") or 0,
                "Risk Reasons": ", ".join(row.get("risk_reasons") or []),
                "Move-in Date": _fmt_date(row.get("move_in_date"), default=""),
            }
        )

    st.dataframe(pd.DataFrame(radar_table), use_container_width=True, hide_index=True)

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
    active_property = _render_active_property_banner()
    if active_property is None:
        return
    if st.session_state.selected_turnover_id is None:
        st.subheader("Turnover Detail")
        unit_search = st.text_input("Unit code", key="detail_unit_search")
        if st.button("Go"):
            if not _db_available():
                st.error("Database not available")
                return
            try:
                rows = _cached_get_dmrb_board_rows(
                    _db_cache_identity(),
                    st.session_state.get("selected_property_id"),
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    date.today().isoformat(),
                )
                norm = (unit_search or "").strip().lower()
                for r in rows:
                    if norm and norm in (r.get("unit_code") or "").lower():
                        st.session_state.selected_turnover_id = r["turnover_id"]
                        st.rerun()
                        return
            except Exception as e:
                st.error(str(e))
                return
            st.warning("Unit not found")
        return

    tid = st.session_state.selected_turnover_id
    if not _db_available():
        st.error("Database not available")
        return
    try:
        detail = _cached_get_turnover_detail(_db_cache_identity(), tid, date.today().isoformat())
    except Exception as e:
        st.error(str(e))
        return
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
    actor = APP_SETTINGS.default_actor
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
                if _db_write(
                    lambda c: update_turnover_status_workflow(
                        c,
                        UpdateTurnoverStatus(
                            turnover_id=tid,
                            manual_ready_status=new_status,
                            today=today,
                            actor=actor,
                        ),
                    )
                ):
                    st.rerun()
        with s2:
            st.write("")
            if st.button("✅ Confirm Quality Control", type="primary", use_container_width=True, key="detail_confirm_qc", disabled=not _detail_writes):
                qc_task = next((task for task in tasks_for_turnover if task.get("task_type") == "QC"), None)
                if qc_task:
                    if _db_write(
                        lambda c: update_task_status_workflow(
                            c,
                            UpdateTaskStatus(
                                task_id=qc_task["task_id"],
                                fields={"confirmation_status": "CONFIRMED"},
                                today=today,
                                actor=actor,
                            ),
                        )
                    ):
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
                if _db_write(
                    lambda c: update_turnover_dates_workflow(
                        c,
                        UpdateTurnoverDates(
                            turnover_id=tid,
                            move_out_date=new_mo,
                            today=today,
                            actor=actor,
                        ),
                    )
                ):
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
                if _db_write(
                    lambda c: update_turnover_dates_workflow(
                        c,
                        UpdateTurnoverDates(
                            turnover_id=tid,
                            report_ready_date=new_rr,
                            today=today,
                            actor=actor,
                        ),
                    )
                ):
                    st.rerun()
        # Move_in + DTBR
        with dt4:
            mi_val = _parse_date(t.get("move_in_date"))
            new_mi = st.date_input(
                "Move-In", value=mi_val, key="detail_mi", format="MM/DD/YYYY",
                disabled=not _detail_writes
            )
            if _detail_writes and new_mi is not None and new_mi != mi_val:
                if _db_write(
                    lambda c: update_turnover_dates_workflow(
                        c,
                        UpdateTurnoverDates(
                            turnover_id=tid,
                            move_in_date=new_mi,
                            today=today,
                            actor=actor,
                        ),
                    )
                ):
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
                        clear_manual_override_workflow(
                            c,
                            ClearManualOverride(
                                turnover_id=tid,
                                override_field=field,
                                actor=actor,
                            ),
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
                        if _db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"assignee": new_assignee or None},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.rerun()
                with tc3:
                    new_due = st.date_input(
                        "Date", value=due_val, key=f"detail_due_{task_id}_{task_type}", label_visibility="collapsed",
                        format="MM/DD/YYYY", disabled=not _detail_writes
                    )
                    if _detail_writes and new_due != due_val:
                        if _db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"vendor_due_date": new_due},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.rerun()
                with tc4:
                    new_exec = st.selectbox(
                        "Exec", exec_options, index=exec_idx, key=f"detail_exec_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    new_exec_val = EXEC_LABEL_TO_VALUE.get(new_exec)
                    if _detail_writes and new_exec_val is not None and _normalize_enum(task.get("execution_status")) != (new_exec_val or "").upper():
                        if _db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"execution_status": new_exec_val},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.toast(f"Execution → {new_exec}", icon="✅")
                            st.rerun()
                with tc5:
                    new_conf = st.selectbox(
                        "Confirm", conf_options, index=conf_idx, key=f"detail_conf_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    new_conf_val = CONFIRM_LABEL_TO_VALUE.get(new_conf)
                    if _detail_writes and new_conf_val and _normalize_enum(task.get("confirmation_status")) != (new_conf_val or "").upper():
                        if _db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"confirmation_status": new_conf_val},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.toast(f"Confirmation → {new_conf}", icon="✅")
                            st.rerun()
                with tc6:
                    req_val = bool(task.get("required"))
                    new_req = st.checkbox(
                        "Req", value=req_val, key=f"detail_req_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    if _detail_writes and new_req != req_val:
                        if _db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"required": new_req},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.rerun()
                with tc7:
                    new_block = st.selectbox(
                        "Block", block_options, index=block_idx, key=f"detail_block_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    if _detail_writes and new_block != cur_block:
                        if _db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"blocking": new_block != "Not Blocking", "blocking_reason": new_block},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
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
    if _render_active_property_banner() is None:
        return

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
    if _render_active_property_banner() is None:
        return
    if not db_repository:
        st.info("Backend not available.")
        return
    if not _db_available():
        st.error("Database not available")
        return
    db_identity = _db_cache_identity()
    properties = _cached_list_properties(db_identity)
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
        pid = prop["property_id"]
        name = prop.get("name") or f"Property {pid}"
        with st.expander(f"**{name}** (id={pid})", expanded=True):
            phases = _cached_list_phases(db_identity, pid)
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
                phase_id = ph["phase_id"]
                phase_code = ph.get("phase_code") or ""
                st.markdown(f"Phase **{phase_code}** (id={phase_id})")
                buildings = _cached_list_buildings(db_identity, phase_id)
                if not buildings:
                    st.caption("  No buildings.")
                    continue
                for b in buildings:
                    building_id = b["building_id"]
                    bcode = b.get("building_code") or ""
                    units = _cached_list_units(db_identity, building_id)
                    unit_list = ", ".join(str(u.get("unit_number") or u.get("unit_id")) for u in units) if units else "—"
                    st.caption(f"  Building {bcode} (id={building_id}): units {unit_list}")


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
    active_property = _render_active_property_banner()
    if active_property is None:
        return
    if not _db_available():
        st.error("Database not available")
        return
    db_identity = _db_cache_identity()
    property_id = active_property["property_id"]
    phases = _cached_list_phases(db_identity, property_id)
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
    phase_opts = sorted(
        [str(p.get("phase_code") or p.get("phase_id") or "") for p in phases if (p.get("phase_code") or p.get("phase_id"))],
        key=lambda x: (int(x) if x.isdigit() else float("inf"), x),
    )
    if not phase_opts:
        phase_opts = [str(p.get("phase_id", "")) for p in phases]
    prev_phase = st.session_state.get("add_avail_phase")
    phase_idx = phase_opts.index(prev_phase) if prev_phase in phase_opts else 0
    phase_code = st.selectbox("Phase", phase_opts, index=phase_idx, key="add_avail_phase")
    if prev_phase is not None and prev_phase != phase_code:
        st.session_state.pop("add_avail_building", None)
    phase_row = next((p for p in phases if str(p.get("phase_code") or p.get("phase_id") or "") == phase_code), phases[0] if phases else None)
    phase_id = int(phase_row["phase_id"]) if phase_row else None
    buildings = _cached_list_buildings(db_identity, phase_id) if phase_id else []
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
                return create_turnover_workflow(
                    conn,
                    CreateTurnover(
                        property_id=property_id,
                        phase_code=phase_code,
                        building_code=building_code,
                        unit_number=unit_number,
                        move_out_date=move_out_date,
                        move_in_date=move_in_date if move_in_date else None,
                        report_ready_date=report_ready_date if report_ready_date else None,
                        today=date.today(),
                        actor=APP_SETTINGS.default_actor,
                    ),
                )
            if _db_write(do_add):
                st.success("Turnover created. You can open it from the board or detail.")
                st.rerun()


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
    active_property = _render_active_property_banner()
    if active_property is None:
        return
    if not _db_available():
        st.error("Database not available")
        return
    db_identity = _db_cache_identity()
    property_id = active_property["property_id"]
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
    st.markdown("### Unit Master Import \u2014 Imported Units")
    imported_units = _cached_list_unit_master_import_units(db_identity)
    if imported_units:
        st.dataframe(pd.DataFrame(imported_units), use_container_width=True, hide_index=True)
    else:
        st.info("No units imported yet.")


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------
def _run_import_for_report(*, report_type: str, uploaded, active_property: dict) -> None:
    """Shared import execution logic for a specific report_type."""
    if uploaded is None:
        st.warning("Upload a file first.")
        return
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
        result = apply_import_row_workflow(
            conn,
            ApplyImportRow(
                report_type=report_type,
                file_path=tmp_path,
                property_id=active_property["property_id"],
                db_path=db_path,
            ),
        )
        conn.commit()
        _invalidate_ui_caches()
        status = result.get("status", "SUCCESS")
        batch_id = result.get("batch_id", "")
        record_count = result.get("record_count", 0)
        applied_count = result.get("applied_count", 0)
        conflict_count = result.get("conflict_count", 0)
        invalid_count = result.get("invalid_count", 0)
        diagnostics = result.get("diagnostics", []) or []
        if status == "NO_OP":
            st.info(f"No-op: file already imported (checksum match). Batch ID: {batch_id} | Records: {record_count} | Applied: 0")
        else:
            st.success(
                f"Batch ID: {batch_id} | Status: {status} | Records: {record_count} | "
                f"Applied: {applied_count} | Conflicts: {conflict_count} | Invalid: {invalid_count}"
            )
        if diagnostics:
            st.warning(f"Row diagnostics: {len(diagnostics)} issue(s)")
            for diag in diagnostics[:50]:
                row_label = f"Row {diag.get('row_index')}" if diag.get("row_index") is not None else "File"
                column = diag.get("column")
                column_text = f" | Column: {column}" if column else ""
                msg = diag.get("error_message") or diag.get("reason") or "Import issue"
                suggestion = diag.get("suggestion")
                line = f"- {row_label}{column_text} | {msg}"
                if suggestion:
                    line += f" | Suggestion: {suggestion}"
                st.write(line)
            if len(diagnostics) > 50:
                st.caption(f"... and {len(diagnostics) - 50} more diagnostics.")

        # Per-report tables, mirroring the raw columns each import brings.
        try:
            rows = db_repository.get_import_rows_by_batch(conn, batch_id)
        except Exception:
            rows = []

        if not rows:
            return

        values: list[dict] = []
        for r in rows:
            try:
                raw = json.loads(r.get("raw_json") or "{}")
            except Exception:
                raw = {}

            base = {
                "validation_status": r.get("validation_status"),
                "conflict_flag": bool(r.get("conflict_flag")),
                "conflict_reason": r.get("conflict_reason"),
            }

            if report_type == "AVAILABLE_UNITS":
                base.update(
                    {
                        "Unit": raw.get("Unit"),
                        "Status": raw.get("Status"),
                        "Available Date": raw.get("Available Date"),
                        "Move-In Ready Date": raw.get("Move-In Ready Date"),
                    }
                )
            elif report_type == "MOVE_OUTS":
                base.update(
                    {
                        "Unit": raw.get("Unit"),
                        "Move-Out Date": raw.get("Move-Out Date"),
                    }
                )
            elif report_type == "PENDING_MOVE_INS":
                base.update(
                    {
                        "Unit": raw.get("Unit"),
                        "Move-In Date": raw.get("Move-In Date"),
                    }
                )
            elif report_type == "PENDING_FAS":
                base.update(
                    {
                        "Unit": raw.get("Unit"),
                        "MO / Cancel Date": raw.get("MO / Cancel Date"),
                    }
                )
            values.append(base)

        if values:
            if report_type == "AVAILABLE_UNITS":
                heading = "Available Units — Imported Rows"
            elif report_type == "MOVE_OUTS":
                heading = "Move Outs — Imported Rows"
            elif report_type == "PENDING_MOVE_INS":
                heading = "Pending Move-Ins — Imported Rows"
            elif report_type == "PENDING_FAS":
                heading = "FAS — Imported Rows"
            else:
                heading = "Imported Rows"
            st.markdown(f"### {heading}")
            st.dataframe(pd.DataFrame(values), use_container_width=True, hide_index=True)
    except Exception as e:
        conn.rollback()
        payload = e.to_dict() if hasattr(e, "to_dict") else None
        if isinstance(payload, dict) and payload.get("error_type") == "IMPORT_VALIDATION_FAILED":
            st.error(payload.get("message", "Import validation failed."))
            errors = payload.get("errors") or []
            if errors:
                st.warning(f"Validation diagnostics: {len(errors)} issue(s)")
                for diag in errors[:50]:
                    row_label = f"Row {diag.get('row_index')}" if diag.get("row_index") is not None else "File"
                    column = diag.get("column")
                    column_text = f" | Column: {column}" if column else ""
                    msg = diag.get("error_message") or "Validation issue"
                    suggestion = diag.get("suggestion")
                    line = f"- {row_label}{column_text} | {msg}"
                    if suggestion:
                        line += f" | Suggestion: {suggestion}"
                    st.write(line)
                if len(errors) > 50:
                    st.caption(f"... and {len(errors) - 50} more diagnostics.")
        else:
            st.error(str(e))
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------
def render_import():
    st.subheader("Import console")
    if not import_service_mod or not db_repository:
        st.warning("Backend or import service not available.")
        if _BACKEND_ERROR is not None:
            with st.expander("Details"):
                st.code(str(_BACKEND_ERROR), language=None)
        return
    if not st.session_state.get("enable_db_writes"):
        st.warning("Enable **Enable DB Writes** in the sidebar to run import.")
        return
    active_property = _render_active_property_banner()
    if active_property is None:
        return
    # Four dedicated tabs: Available Units, Move Outs, Pending Move-Ins, FAS
    tab_available, tab_move_outs, tab_pending_move_ins, tab_fas = st.tabs(
        ["Available Units", "Move Outs", "Pending Move-Ins", "Final Account Statement (FAS)"]
    )

    with tab_available:
        uploaded_au = st.file_uploader(
            "Available Units.csv", key="import_file_available_units", type=["csv"]
        )
        if st.button("Run Available Units import", key="import_run_available_units"):
            _run_import_for_report(
                report_type="AVAILABLE_UNITS",
                uploaded=uploaded_au,
                active_property=active_property,
            )

    with tab_move_outs:
        uploaded_mo = st.file_uploader(
            "Move Outs.csv", key="import_file_move_outs", type=["csv"]
        )
        if st.button("Run Move Outs import", key="import_run_move_outs"):
            _run_import_for_report(
                report_type="MOVE_OUTS",
                uploaded=uploaded_mo,
                active_property=active_property,
            )

    with tab_pending_move_ins:
        uploaded_pmi = st.file_uploader(
            "Pending Move-Ins.csv", key="import_file_pending_move_ins", type=["csv"]
        )
        if st.button("Run Pending Move-Ins import", key="import_run_pending_move_ins"):
            _run_import_for_report(
                report_type="PENDING_MOVE_INS",
                uploaded=uploaded_pmi,
                active_property=active_property,
            )

    with tab_fas:
        uploaded_fas = st.file_uploader(
            "Pending FAS.csv", key="import_file_fas", type=["csv"]
        )
        if st.button("Run FAS import", key="import_run_fas"):
            _run_import_for_report(
                report_type="PENDING_FAS",
                uploaded=uploaded_fas,
                active_property=active_property,
            )

    st.subheader("Conflicts")
    st.caption("Conflict details are recorded in import_row for the batch. List conflicts here when a batch is selected (future).")


def render_exports():
    st.subheader("Export Reports")
    st.caption("Exports always include all open turnovers (closed/canceled excluded), regardless of current screen filters.")
    if _render_active_property_banner() is None:
        return
    if not export_service_mod:
        st.warning("Export service is not available.")
        return

    if "export_payloads" not in st.session_state:
        st.session_state.export_payloads = None

    conn = _get_conn()
    if not conn:
        st.error("Database not available")
        return
    try:
        if st.button("Prepare Export Files", key="prepare_exports"):
            with st.spinner("Building reports..."):
                st.session_state.export_payloads = export_service_mod.generate_all_export_artifacts(
                    conn, today=date.today()
                )
            st.success("Export files ready.")
    except Exception as e:
        st.error(str(e))
    finally:
        conn.close()

    payloads = st.session_state.export_payloads
    if not payloads:
        st.info("Click 'Prepare Export Files' to generate downloads.")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Download Final Report (XLSX)",
            data=payloads.get("Final_Report.xlsx", b""),
            file_name="Final_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_final_xlsx",
        )
        st.download_button(
            "Download DMRB Report (XLSX)",
            data=payloads.get("DMRB_Report.xlsx", b""),
            file_name="DMRB_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_dmrb_xlsx",
        )
        st.download_button(
            "Download Dashboard Chart (PNG)",
            data=payloads.get("Dashboard_Chart.png", b""),
            file_name="Dashboard_Chart.png",
            mime="image/png",
            key="dl_dashboard_png",
        )
    with c2:
        st.download_button(
            "Download Weekly Summary (TXT)",
            data=payloads.get("Weekly_Summary.txt", b""),
            file_name="Weekly_Summary.txt",
            mime="text/plain",
            key="dl_weekly_txt",
        )
        st.download_button(
            "Download All Reports (ZIP)",
            data=payloads.get("DMRB_Reports.zip", b""),
            file_name="DMRB_Reports.zip",
            mime="application/zip",
            key="dl_all_zip",
        )


# ---------------------------------------------------------------------------
# Admin (tabbed page)
# ---------------------------------------------------------------------------
def render_admin():
    st.subheader("Admin")

    admin_col1, admin_col2, admin_col3 = st.columns([1.2, 1.6, 1.6])
    with admin_col1:
        st.checkbox(
            "Enable DB Writes (⚠ irreversible)",
            value=st.session_state.get("enable_db_writes", False),
            key="enable_db_writes",
            on_change=lambda: st.rerun(),
        )
    properties = _cached_list_properties(_db_cache_identity())
    active_property = _sync_active_property(properties)
    with admin_col2:
        if properties:
            property_options = {}
            for p in properties:
                property_name = p.get("name") or f"Property {p['property_id']}"
                property_options[f"{property_name} (id={p['property_id']})"] = p
            active_label = next(
                (label for label, prop in property_options.items() if prop["property_id"] == active_property["property_id"]),
                next(iter(property_options)),
            )
            selected_label = st.selectbox(
                "Active Property",
                list(property_options.keys()),
                index=list(property_options.keys()).index(active_label),
                key="admin_active_property",
            )
            selected_property = property_options[selected_label]
            _set_active_property(
                selected_property["property_id"],
                selected_property.get("name") or f"Property {selected_property['property_id']}",
            )
        else:
            st.caption("Create a property in the Admin tab to begin.")
    with admin_col3:
        new_property_name = st.text_input("New Property", value="", key="admin_new_property_name", placeholder="Property name")
        if st.button("Create Property", key="admin_create_property"):
            if not st.session_state.get("enable_db_writes"):
                st.error("Enable DB Writes in the Admin tab first.")
            elif not (new_property_name or "").strip():
                st.error("Enter a property name.")
            else:
                created = {"property_id": None}

                def do_create(conn):
                    created["property_id"] = db_repository.insert_property(conn, (new_property_name or "").strip())

                if _db_write(do_create):
                    property_id = created["property_id"]
                    property_name = (new_property_name or "").strip()
                    if property_id is None:
                        st.error("Property creation failed: no property_id was returned.")
                    else:
                        _set_active_property(property_id, property_name)
                        st.success(f"Active Property: {property_name}")
                        st.rerun()

    if st.session_state.get("enable_db_writes"):
        st.caption("DB writes are **on**. Edits and status changes will be persisted.")
    else:
        st.caption("DB writes are **off**. You can browse and export; turn this on here to save changes.")
    if st.session_state.get("selected_property_id") is not None:
        st.caption(f"Active Property: {st.session_state.get('selected_property_name')}")
    else:
        st.caption("Create a property in the Admin tab to begin.")

    tab_add, tab_import, tab_unit_master, tab_export, tab_dropdown = st.tabs(
        ["Add Unit", "Import", "Unit Master Import", "Exports", "Dropdown Manager"]
    )
    with tab_add:
        render_add_availability()
    with tab_import:
        render_import()
    with tab_unit_master:
        render_unit_master_import()
    with tab_export:
        render_exports()
    with tab_dropdown:
        render_dropdown_manager()


def _chat_api_base_url() -> str:
    return (os.environ.get("DMRB_CHAT_API_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")


def _chat_api_request(method: str, path: str, payload: Optional[dict] = None):
    url = f"{_chat_api_base_url()}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib_request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib_request.urlopen(req, timeout=90) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"{exc.code} {exc.reason}: {detail}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Could not reach chat API at {_chat_api_base_url()}") from exc


def render_dmrb_ai_agent():
    st.subheader("DMRB AI Agent")
    st.caption("AI can make mistakes. Check important info.")

    if "ai_current_session_id" not in st.session_state:
        st.session_state.ai_current_session_id = None
    if "ai_messages" not in st.session_state:
        st.session_state.ai_messages = []

    fallback_suggestions = [
        "How many units are vacant right now?",
        "Which units are about to breach SLA?",
        "Who has the most open units?",
        "Give me a morning briefing",
    ]

    try:
        sessions = _chat_api_request("GET", "/api/chat/sessions") or []
    except Exception as exc:
        st.error(str(exc))
        sessions = []

    left, right = st.columns([1, 3], gap="small")
    with left:
        if st.button("+ New Chat", use_container_width=True):
            st.session_state.ai_current_session_id = None
            st.session_state.ai_messages = []
            st.rerun()
        st.markdown("#### Sessions")
        if not sessions:
            st.caption("No chat sessions yet.")
        for session in sessions:
            sid = session.get("session_id")
            title = session.get("title") or "New Chat"
            row_a, row_b = st.columns([4, 1], gap="small")
            selected = st.session_state.ai_current_session_id == sid
            if row_a.button(
                f"{'● ' if selected else ''}{title[:40]}",
                key=f"ai_open_{sid}",
                use_container_width=True,
            ):
                st.session_state.ai_current_session_id = sid
                try:
                    st.session_state.ai_messages = _chat_api_request("GET", f"/api/chat/sessions/{sid}/messages") or []
                except Exception as exc:
                    st.error(str(exc))
                st.rerun()
            if row_b.button("🗑", key=f"ai_del_{sid}", use_container_width=True):
                try:
                    _chat_api_request("DELETE", f"/api/chat/sessions/{sid}")
                    if st.session_state.ai_current_session_id == sid:
                        st.session_state.ai_current_session_id = None
                        st.session_state.ai_messages = []
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with right:
        current_session_id = st.session_state.ai_current_session_id
        if current_session_id and not st.session_state.ai_messages:
            try:
                st.session_state.ai_messages = _chat_api_request("GET", f"/api/chat/sessions/{current_session_id}/messages") or []
            except Exception as exc:
                st.error(str(exc))

        if not st.session_state.ai_messages:
            st.markdown("### DMRB AI Agent")
            try:
                suggestions = _chat_api_request("GET", "/api/chat/suggestions") or fallback_suggestions
            except Exception:
                suggestions = fallback_suggestions
            cols = st.columns(2)
            for idx, question in enumerate(suggestions[:10]):
                if cols[idx % 2].button(question, key=f"ai_suggest_{idx}", use_container_width=True):
                    st.session_state.ai_input_prefill = question
                    st.rerun()

        for message in st.session_state.ai_messages:
            role = "assistant" if message.get("role") == "assistant" else "user"
            with st.chat_message(role):
                st.markdown(message.get("content") or "")

        prompt = st.chat_input("Ask anything about turnovers...")
        if prompt is None and st.session_state.get("ai_input_prefill"):
            prompt = st.session_state.pop("ai_input_prefill")
        if prompt:
            with st.chat_message("user"):
                st.markdown(prompt)
            try:
                response = _chat_api_request(
                    "POST",
                    "/api/chat",
                    {"sessionId": current_session_id or "new", "message": prompt},
                )
                new_session_id = response.get("sessionId") if isinstance(response, dict) else None
                if new_session_id:
                    st.session_state.ai_current_session_id = new_session_id
                    st.session_state.ai_messages = (
                        _chat_api_request("GET", f"/api/chat/sessions/{new_session_id}/messages") or []
                    )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
if st.session_state.page == "dmrb_board":
    render_board_screen(render_dmrb_board)
elif st.session_state.page == "flag_bridge":
    render_flag_bridge_screen(render_flag_bridge)
elif st.session_state.page == "risk_radar":
    render_risk_radar_screen(render_risk_radar)
elif st.session_state.page == "detail":
    render_turnover_detail_screen(render_detail)
elif st.session_state.page == "dmrb_ai_agent":
    render_ai_agent_screen(render_dmrb_ai_agent)
elif st.session_state.page == "admin":
    render_admin_screen(render_admin)
else:
    render_board_screen(render_dmrb_board)
