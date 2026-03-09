from __future__ import annotations

import streamlit as st


def render_navigation(current_page: str, enable_writes: bool) -> str:
    st.sidebar.title("The DMRB")
    st.sidebar.caption("Apartment Turn Tracker")
    sidebar_writes = st.sidebar.checkbox(
        "Enable DB Writes (⚠ irreversible)",
        value=enable_writes,
        key="enable_db_writes_cb",
    )
    if sidebar_writes != st.session_state.enable_db_writes:
        st.session_state.enable_db_writes = sidebar_writes
        st.rerun()

    nav_labels = ["DMRB Board", "Flag Bridge", "Risk Radar", "Turnover Detail", "DMRB AI Agent", "Admin"]
    nav_to_page = {
        "DMRB Board": "dmrb_board",
        "Flag Bridge": "flag_bridge",
        "Risk Radar": "risk_radar",
        "Turnover Detail": "detail",
        "DMRB AI Agent": "dmrb_ai_agent",
        "Admin": "admin",
    }
    page_to_nav_label = {v: k for k, v in nav_to_page.items()}
    expected_nav = page_to_nav_label.get(current_page, "DMRB Board")
    if "sidebar_nav" in st.session_state and st.session_state.sidebar_nav != expected_nav:
        st.session_state["sidebar_nav"] = expected_nav

    def _on_nav_change():
        st.session_state.page = nav_to_page.get(st.session_state.sidebar_nav, st.session_state.page)

    st.sidebar.radio(
        "Navigate",
        nav_labels,
        index=nav_labels.index(expected_nav),
        key="sidebar_nav",
        on_change=_on_nav_change,
    )
    return st.session_state.page
