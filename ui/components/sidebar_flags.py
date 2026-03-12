"""Sidebar Top Flags: expanders by breach category, unit buttons."""
from __future__ import annotations

from datetime import date

import streamlit as st

from ui.data.backend import db_repository
from ui.data.cache import (
    cached_get_flag_bridge_rows,
    cached_list_phases,
    db_available,
    db_cache_identity,
    get_active_property,
)
from ui.helpers.dates import parse_date


def _sort_insp(r):
    """Closest inspection due date (not done) first."""
    t = r.get("task_insp") or {}
    if (t.get("execution_status") or "").upper() == "VENDOR_COMPLETED":
        return date.max
    d = parse_date(t.get("vendor_due_date"))
    return d if d else date.max


def _sort_dv_desc(r):
    """Highest days vacant first."""
    return -(r.get("dv") or 0)


def _sort_mi_closest(r):
    """Closest move-in date (not ready) first."""
    d = parse_date(r.get("move_in_date"))
    return d if d else date.max


def _sort_ready_date(r):
    """Ready date (not ready) first."""
    d = parse_date(r.get("report_ready_date"))
    return d if d else date.max


_FLAG_CATEGORIES = [
    ("📋 Insp Breach", "inspection_sla_breach", lambda r: r.get("inspection_sla_breach"), _sort_insp),
    ("⚠ SLA Breach", "sla_breach", lambda r: r.get("sla_breach"), _sort_dv_desc),
    ("🔴 SLA MI Breach", "sla_movein_breach", lambda r: r.get("sla_movein_breach"), _sort_mi_closest),
    ("📅 Plan Breach", "plan_breach", lambda r: r.get("plan_breach"), _sort_ready_date),
]


def render_top_flags() -> None:
    st.sidebar.divider()
    st.sidebar.markdown("**Top Flags**")
    if not db_available():
        _all_rows = []
        st.sidebar.error("Database not available")
    else:
        try:
            db_identity = db_cache_identity()
            active_property = get_active_property()
            phase_ids = None
            if db_repository and st.session_state.filter_phase != "All":
                phase_map = {
                    str(p["phase_code"]): p["phase_id"]
                    for p in cached_list_phases(
                        db_identity,
                        active_property["property_id"] if active_property else None,
                    )
                }
                phase_id = phase_map.get(st.session_state.filter_phase)
                if phase_id is not None:
                    phase_ids = (phase_id,)
                    st.session_state.phase_id_by_code = phase_map
            _all_rows = cached_get_flag_bridge_rows(
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

    any_flags = False
    for cat_label, cat_key, cat_fn, cat_sort in _FLAG_CATEGORIES:
        cat_units = sorted([r for r in _all_rows if cat_fn(r)], key=cat_sort)
        if cat_units:
            any_flags = True
            with st.sidebar.expander(f"{cat_label} ({len(cat_units)})"):
                for u in cat_units[:5]:
                    uc = u.get("unit_code", "")
                    dv_val = u.get("dv")
                    label = f"{uc} · DV {dv_val}" if dv_val is not None else uc
                    if st.button(label, key=f"sb_{cat_key}_{u.get('turnover_id')}"):
                        st.session_state.selected_turnover_id = u.get("turnover_id")
                        st.session_state.page = "detail"
                        st.rerun()
    if not any_flags:
        st.sidebar.caption("No flagged units")
