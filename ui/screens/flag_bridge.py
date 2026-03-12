"""Flag Bridge screen: breach-focused table."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ui.data.backend import db_repository
from ui.data.cache import (
    cached_get_flag_bridge_rows,
    db_cache_identity,
    db_available,
    get_active_property,
    render_active_property_banner,
)
from ui.helpers.formatting import get_attention_badge
from ui.helpers.dates import fmt_date
from ui.state import ASSIGNEE_OPTIONS, BRIDGE_MAP, STATUS_OPTIONS


def _get_flag_bridge_rows():
    if not db_available():
        return []
    try:
        db_identity = db_cache_identity()
        active_property = get_active_property()
        phase_ids = None
        if db_repository and st.session_state.filter_phase != "All":
            phase_id = st.session_state.get("phase_id_by_code", {}).get(
                st.session_state.filter_phase
            )
            if phase_id is not None:
                phase_ids = (phase_id,)
        return cached_get_flag_bridge_rows(
            db_identity,
            active_property["property_id"] if active_property else None,
            phase_ids,
            search_unit=st.session_state.search_unit or None,
            filter_phase=None,
            filter_status=st.session_state.filter_status
            if st.session_state.filter_status != "All"
            else None,
            filter_nvm=st.session_state.filter_nvm
            if st.session_state.filter_nvm != "All"
            else None,
            filter_assignee=st.session_state.filter_assignee
            if st.session_state.filter_assignee != "All"
            else None,
            filter_qc=st.session_state.filter_qc
            if st.session_state.filter_qc != "All"
            else None,
            breach_filter=st.session_state.breach_filter
            if st.session_state.breach_filter != "All"
            else None,
            breach_value=st.session_state.breach_value
            if st.session_state.breach_value != "All"
            else None,
            today_iso=date.today().isoformat(),
        )
    except Exception as e:
        st.error(str(e))
        return []


def render() -> None:
    active_property = render_active_property_banner()
    if active_property is None:
        return
    rows = _get_flag_bridge_rows()
    n_viol = sum(1 for r in rows if r.get("has_violation"))
    n_breach = sum(
        1
        for r in rows
        if r.get("inspection_sla_breach")
        or r.get("sla_breach")
        or r.get("sla_movein_breach")
        or r.get("plan_breach")
    )

    with st.container(border=True):
        c0, c1, c2, c3, c4, c5 = st.columns(6)
        with c0:
            phase_opts = (
                ["All"]
                + sorted(st.session_state.get("phase_id_by_code", {}).keys())
                or ["All", "5", "7", "8"]
            )
            idx = (
                phase_opts.index(st.session_state.filter_phase)
                if st.session_state.filter_phase in phase_opts
                else 0
            )
            st.session_state.filter_phase = st.selectbox(
                "Phase", phase_opts, index=idx, key="fb_phase"
            )
        with c1:
            status_opts = ["All"] + STATUS_OPTIONS
            idx = (
                status_opts.index(st.session_state.filter_status)
                if st.session_state.filter_status in status_opts
                else 0
            )
            st.session_state.filter_status = st.selectbox(
                "Status", status_opts, index=idx, key="fb_status"
            )
        with c2:
            nvm_opts = ["All", "Notice", "Notice + SMI", "Vacant", "SMI", "Move-In"]
            idx = (
                nvm_opts.index(st.session_state.filter_nvm)
                if st.session_state.filter_nvm in nvm_opts
                else 0
            )
            st.session_state.filter_nvm = st.selectbox(
                "N/V/M", nvm_opts, index=idx, key="fb_nvm"
            )
        with c3:
            assign_opts = ["All"] + [a for a in ASSIGNEE_OPTIONS if a]
            idx = (
                assign_opts.index(st.session_state.filter_assignee)
                if st.session_state.filter_assignee in assign_opts
                else 0
            )
            st.session_state.filter_assignee = st.selectbox(
                "Assign", assign_opts, index=idx, key="fb_assign"
            )
        with c4:
            bridge_opts = list(BRIDGE_MAP.keys())
            idx = (
                bridge_opts.index(st.session_state.breach_filter)
                if st.session_state.breach_filter in bridge_opts
                else 0
            )
            st.session_state.breach_filter = st.selectbox(
                "Flag Bridge", bridge_opts, index=idx, key="fb_bridge"
            )
        with c5:
            value_opts = ["All", "Yes", "No"]
            idx = (
                value_opts.index(st.session_state.breach_value)
                if st.session_state.breach_value in value_opts
                else 0
            )
            st.session_state.breach_value = st.selectbox(
                "Value", value_opts, index=idx, key="fb_value"
            )

    with st.container(border=True):
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Units", len(rows))
        m2.metric("Violations", n_viol)
        m3.metric("Units w/ Breach", n_breach)

    if not rows:
        st.info("No rows match filters.")
        return

    fb_tid_map = []
    bridge_data = []
    for r in rows:
        fb_tid_map.append(r.get("turnover_id"))
        bridge_data.append(
            {
                "▶": False,
                "Unit": r.get("unit_code", ""),
                "Status": r.get("manual_ready_status", ""),
                "DV": r.get("dv"),
                "Move-In": fmt_date(r.get("move_in_date")),
                "Alert": get_attention_badge(r),
                "Viol": "🔴" if r.get("has_violation") else "—",
                "Insp": "🔴" if r.get("inspection_sla_breach") else "—",
                "SLA": "🔴" if r.get("sla_breach") else "—",
                "MI": "🔴" if r.get("sla_movein_breach") else "—",
                "Plan": "🔴" if r.get("plan_breach") else "—",
            }
        )

    bridge_df = pd.DataFrame(bridge_data)
    edited_bridge = st.data_editor(
        bridge_df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=[
            "Unit",
            "Status",
            "DV",
            "Move-In",
            "Alert",
            "Viol",
            "Insp",
            "SLA",
            "MI",
            "Plan",
        ],
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
        column_order=[
            "▶",
            "Unit",
            "Status",
            "DV",
            "Move-In",
            "Alert",
            "Viol",
            "Insp",
            "SLA",
            "MI",
            "Plan",
        ],
        key="fb_editor",
    )

    for idx in range(len(bridge_df)):
        if edited_bridge.iloc[idx]["▶"]:
            st.session_state.selected_turnover_id = fb_tid_map[idx]
            st.session_state.page = "detail"
            st.rerun()
