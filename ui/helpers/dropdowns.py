"""Dropdown config helpers: session state and persist. Uses Streamlit for session."""
from __future__ import annotations

import os

import streamlit as st

from ui.state.session import save_dropdown_config as persist_dropdown_config


def dropdown_config_path() -> str:
    """Path to dropdown_config.json next to app (legacy app.py location)."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "dropdown_config.json")


def load_dropdown_config() -> dict:
    """Return current dropdown config from session."""
    return st.session_state.get("dropdown_config", {})


def save_dropdown_config() -> None:
    """Persist session dropdown_config to file."""
    persist_dropdown_config(st.session_state.dropdown_config)
