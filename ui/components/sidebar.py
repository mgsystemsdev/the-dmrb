from __future__ import annotations

import streamlit as st


def render_navigation(current_page: str) -> str:
    st.sidebar.title("The DMRB")
    st.sidebar.caption("Apartment Turn Tracker")

    nav_labels = ["Morning Workflow", "DMRB Board", "Flag Bridge", "Risk Radar", "Report Operations", "Turnover Detail", "DMRB AI Agent", "Admin"]
    nav_to_page = {
        "Morning Workflow": "morning_workflow",
        "DMRB Board": "dmrb_board",
        "Flag Bridge": "flag_bridge",
        "Risk Radar": "risk_radar",
        "Report Operations": "report_operations",
        "Turnover Detail": "detail",
        "DMRB AI Agent": "dmrb_ai_agent",
        "Admin": "admin",
    }
    page_to_nav_label = {v: k for k, v in nav_to_page.items()}
    expected_nav = page_to_nav_label.get(current_page, "DMRB Board")
    if "sidebar_nav" in st.session_state and st.session_state.sidebar_nav != expected_nav:
        st.session_state["sidebar_nav"] = expected_nav

    def _on_nav_change():
        nav = st.session_state.get("sidebar_nav", expected_nav)
        current_page = st.session_state.get("page", "dmrb_board")
        st.session_state.page = nav_to_page.get(nav, current_page)

    st.sidebar.radio(
        "Navigate",
        nav_labels,
        index=nav_labels.index(expected_nav),
        key="sidebar_nav",
        on_change=_on_nav_change,
    )
    return st.session_state.get("page", "dmrb_board")
