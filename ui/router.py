"""Page router: resolve current page, lazy-import screen module, call render()."""
from __future__ import annotations

import importlib

import streamlit as st

_PAGE_TO_MODULE = {
    "dmrb_board": "board",
    "flag_bridge": "flag_bridge",
    "risk_radar": "risk_radar",
    "detail": "turnover_detail",
    "dmrb_ai_agent": "ai_agent",
    "admin": "admin",
}


def render_current_page() -> None:
    page = st.session_state.get("page", "dmrb_board")
    module_name = _PAGE_TO_MODULE.get(page, "board")
    module = importlib.import_module(f"ui.screens.{module_name}")
    module.render()
