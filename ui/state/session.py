from __future__ import annotations

import json
import os

import streamlit as st

from config.settings import get_settings
from ui.state.constants import DEFAULT_TASK_OFFSETS, default_dropdown_config


def dropdown_config_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "..", "data", "dropdown_config.json")


def load_dropdown_config() -> dict:
    path = os.path.abspath(dropdown_config_path())
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            pass
    return default_dropdown_config()


def save_dropdown_config(config: dict) -> None:
    path = os.path.abspath(dropdown_config_path())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)


def init_session_state() -> None:
    settings = get_settings()
    if "page" not in st.session_state:
        st.session_state.page = "dmrb_board"
    if st.session_state.page in ("add_availability", "import", "dropdown_mgr", "unit_master_import"):
        st.session_state.page = "admin"
    if "sidebar_nav" not in st.session_state:
        st.session_state.sidebar_nav = "DMRB Board"
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
        st.session_state.dropdown_config = load_dropdown_config()
    if "task_offsets" not in st.session_state.dropdown_config:
        st.session_state.dropdown_config["task_offsets"] = DEFAULT_TASK_OFFSETS.copy()
    if "enable_db_writes" not in st.session_state:
        st.session_state.enable_db_writes = settings.enable_db_writes_default
    if "selected_property_id" not in st.session_state:
        st.session_state.selected_property_id = None
    if "selected_property_name" not in st.session_state:
        st.session_state.selected_property_name = ""
    if "ai_current_session_id" not in st.session_state:
        st.session_state.ai_current_session_id = None
    if "ai_messages" not in st.session_state:
        st.session_state.ai_messages = []
