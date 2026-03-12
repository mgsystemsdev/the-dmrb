"""Risk Radar screen: risk-level table."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ui.data.backend import db_repository
from ui.data.cache import (
    cached_get_risk_radar_rows,
    cached_list_phases,
    db_cache_identity,
    db_available,
    get_active_property,
    render_active_property_banner,
)
from ui.helpers.dates import fmt_date


def _get_risk_radar_rows(phase_filter: str, search_unit: str, risk_level: str):
    if not db_available():
        st.error("Database not available")
        return []
    try:
        db_identity = db_cache_identity()
        active_property = get_active_property()
        phase_ids = None
        if db_repository and phase_filter != "All":
            phases = cached_list_phases(
                db_identity,
                active_property["property_id"] if active_property else None,
            )
            phase_id_by_code = {str(p["phase_code"]): p["phase_id"] for p in phases}
            phase_id = phase_id_by_code.get(phase_filter)
            if phase_id is not None:
                phase_ids = (phase_id,)
        return cached_get_risk_radar_rows(
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


def render() -> None:
    st.subheader("Turnover Risk Radar")
    st.caption(
        "Units most likely to miss readiness or move-in deadlines."
    )
    active_property = render_active_property_banner()
    if active_property is None:
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if db_repository:
            try:
                active_property = get_active_property()
                phases = cached_list_phases(
                    db_cache_identity(),
                    active_property["property_id"] if active_property else None,
                )
                phase_opts = ["All"] + sorted(str(p["phase_code"]) for p in phases)
            except Exception:
                phase_opts = ["All", "5", "7", "8"]
        else:
            phase_opts = ["All", "5", "7", "8"]
        phase_filter = st.selectbox(
            "Phase", phase_opts, index=0, key="rr_phase"
        )
    with c2:
        risk_level = st.selectbox(
            "Risk Level",
            ["All", "HIGH", "MEDIUM", "LOW"],
            index=0,
            key="rr_level",
        )
    with c3:
        search_unit = st.text_input(
            "Unit Search",
            value=st.session_state.get("rr_search", ""),
            key="rr_search",
        )

    all_rows = _get_risk_radar_rows(phase_filter, search_unit, "All")
    rows = (
        all_rows
        if risk_level == "All"
        else [r for r in all_rows if (r.get("risk_level") or "LOW") == risk_level]
    )

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
                "Move-in Date": fmt_date(row.get("move_in_date"), default=""),
            }
        )

    st.dataframe(
        pd.DataFrame(radar_table),
        use_container_width=True,
        hide_index=True,
    )
