"""
Streamlit caching and cached query helpers. Active property sync.
Uses ui.data.backend for DB and services; do not import app.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from config.settings import get_settings
from ui.data.backend import (
    board_query_service,
    get_conn,
    get_db_path,
    property_service_mod,
    unit_service_mod,
)
from ui.helpers.dates import iso_to_date

APP_SETTINGS = get_settings()


def db_cache_identity() -> str:
    return f"postgres:{APP_SETTINGS.database_url or ''}"


def db_available() -> bool:
    conn = get_conn()
    if not conn:
        return False
    conn.close()
    return True


def invalidate_ui_caches() -> None:
    st.cache_data.clear()


@st.cache_data(ttl=10, show_spinner=False)
def cached_list_properties(db_identity: str) -> list[dict]:
    if not property_service_mod:
        return []
    conn = get_conn()
    if not conn:
        return []
    try:
        return [dict(row) for row in property_service_mod.list_properties(conn)]
    finally:
        conn.close()


def set_active_property(property_id: int, property_name: str) -> None:
    if st.session_state.get("selected_property_id") != property_id:
        st.session_state.filter_phase = "All"
        st.session_state.selected_turnover_id = None
    st.session_state.selected_property_id = property_id
    st.session_state.selected_property_name = property_name


def sync_active_property(properties: list[dict]) -> dict | None:
    if not properties:
        st.session_state.selected_property_id = None
        st.session_state.selected_property_name = ""
        return None
    selected_id = st.session_state.get("selected_property_id")
    active = next((p for p in properties if p["property_id"] == selected_id), None)
    if active is None:
        active = properties[0]
    set_active_property(active["property_id"], active.get("name") or f"Property {active['property_id']}")
    return active


def get_active_property() -> dict | None:
    return sync_active_property(cached_list_properties(db_cache_identity()))


def render_active_property_banner() -> dict | None:
    active_property = get_active_property()
    if active_property is None:
        st.info("Create a property in the Admin tab to begin.")
        return None
    st.caption(f"Active Property: {st.session_state.selected_property_name}")
    return active_property


@st.cache_data(ttl=10, show_spinner=False)
def cached_list_phases(db_identity: str, property_id: int | None = None) -> list[dict]:
    if not property_service_mod:
        return []
    conn = get_conn()
    if not conn:
        return []
    try:
        return [dict(row) for row in property_service_mod.list_phases(conn, property_id=property_id)]
    finally:
        conn.close()


@st.cache_data(ttl=10, show_spinner=False)
def cached_list_buildings(db_identity: str, phase_id: int) -> list[dict]:
    if not property_service_mod:
        return []
    conn = get_conn()
    if not conn:
        return []
    try:
        return [dict(row) for row in property_service_mod.list_buildings(conn, phase_id=phase_id)]
    finally:
        conn.close()


@st.cache_data(ttl=10, show_spinner=False)
def cached_list_units(db_identity: str, building_id: int) -> list[dict]:
    if not unit_service_mod:
        return []
    conn = get_conn()
    if not conn:
        return []
    try:
        return [dict(row) for row in unit_service_mod.list_units(conn, building_id=building_id)]
    finally:
        conn.close()


@st.cache_data(ttl=10, show_spinner=False)
def cached_list_unit_master_import_units(db_identity: str) -> list[dict]:
    if not unit_service_mod:
        return []
    conn = get_conn()
    if not conn:
        return []
    try:
        return unit_service_mod.list_unit_master_import_units(conn)
    finally:
        conn.close()


@st.cache_data(ttl=5, show_spinner=False)
def cached_get_flag_bridge_rows(
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
    conn = get_conn()
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
            today=iso_to_date(today_iso),
        )
    finally:
        conn.close()


@st.cache_data(ttl=5, show_spinner=False)
def cached_get_dmrb_board_rows(
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
    conn = get_conn()
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
            today=iso_to_date(today_iso),
        )
    finally:
        conn.close()


@st.cache_data(ttl=5, show_spinner=False)
def cached_get_risk_radar_rows(
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
    conn = get_conn()
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
            today=iso_to_date(today_iso),
        )
    finally:
        conn.close()


@st.cache_data(ttl=5, show_spinner=False)
def cached_get_turnover_detail(db_identity: str, turnover_id: int, today_iso: str) -> dict:
    if not board_query_service:
        return {}
    conn = get_conn()
    if not conn:
        return {}
    try:
        return board_query_service.get_turnover_detail(conn, turnover_id, today=iso_to_date(today_iso))
    finally:
        conn.close()
