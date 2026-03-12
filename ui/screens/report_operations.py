"""Report Operations: Missing Move-Out queue and FAS Tracker tabs."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ui.data.backend import db_write, get_conn
from ui.data.cache import (
    db_available,
    get_active_property,
    render_active_property_banner,
)


def _get_missing_move_out_queue():
    if not db_available():
        return []
    conn = get_conn()
    if not conn:
        return []
    try:
        from services import report_operations_service
        active = get_active_property()
        if not active:
            return []
        return report_operations_service.get_missing_move_out_queue(
            conn, property_id=active["property_id"]
        )
    except Exception as e:
        st.error(str(e))
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _get_fas_tracker_rows():
    if not db_available():
        return []
    conn = get_conn()
    if not conn:
        return []
    try:
        from services import report_operations_service
        active = get_active_property()
        if not active:
            return []
        return report_operations_service.get_fas_tracker_rows(
            conn, property_id=active["property_id"]
        )
    except Exception as e:
        st.error(str(e))
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _get_import_diagnostics_queue():
    if not db_available():
        return []
    conn = get_conn()
    if not conn:
        return []
    try:
        from services import report_operations_service
        active = get_active_property()
        if not active:
            return []
        return report_operations_service.get_import_diagnostics_queue(
            conn, property_id=active["property_id"]
        )
    except Exception as e:
        st.error(str(e))
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _render_missing_move_out_tab(active_property: dict) -> None:
    from services import report_operations_service

    st.subheader("Missing Move-Out Queue")
    st.caption(
        "Units from reports with MOVE_IN_WITHOUT_OPEN_TURNOVER or MOVE_OUT_DATE_MISSING. "
        "Enter a move-out date to create a turnover (unit will appear on the board)."
    )
    rows = _get_missing_move_out_queue()
    if not rows:
        st.info("No missing move-out exceptions for the active property.")
        return

    df = pd.DataFrame([
        {
            "Unit": r.get("unit_code"),
            "Report type": r.get("report_type"),
            "Move-in date": r.get("move_in_date") or "—",
            "Conflict reason": r.get("conflict_reason"),
            "Import timestamp": r.get("imported_at") or "—",
        }
        for r in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**Resolve: create turnover with move-out date**")
    options = [f"{r.get('unit_code')} ({r.get('conflict_reason')})" for r in rows]
    option_to_row = {opt: r for opt, r in zip(options, rows)}
    selected_label = st.selectbox(
        "Select unit to resolve",
        options=options,
        key="report_ops_missing_move_out_unit",
    )
    if not selected_label:
        return
    selected = option_to_row.get(selected_label)
    if not selected:
        return
    move_out_date = st.date_input(
        "Move-out date",
        value=date.today(),
        key="report_ops_move_out_date",
    )
    if st.button("Create turnover", key="report_ops_create_turnover"):
        if not move_out_date:
            st.error("Please select a move-out date.")
            return
        phase_code = selected.get("phase_code") or ""
        building_code = selected.get("building_code") or ""
        unit_number = selected.get("unit_number") or ""
        if not unit_number:
            st.error("Unit identity missing.")
            return

        def _do_resolve(conn):
            return report_operations_service.resolve_missing_move_out(
                conn,
                property_id=active_property["property_id"],
                phase_code=phase_code,
                building_code=building_code,
                unit_number=unit_number,
                move_out_date=move_out_date,
            )

        if db_write(_do_resolve):
            st.success("Turnover created. The unit will appear on the board.")
            st.rerun()


def _render_fas_tracker_tab(active_property: dict) -> None:
    from services import report_operations_service

    st.subheader("Final Account Statement Tracker")
    st.caption(
        "Units from Pending FAS imports. Add or edit notes (e.g. Done, Checked, Keys returned); "
        "notes persist across imports."
    )
    rows = _get_fas_tracker_rows()
    if not rows:
        st.info("No PENDING_FAS import rows for the active property.")
        return

    df = pd.DataFrame([
        {
            "Unit": r.get("unit_code"),
            "FAS date": r.get("fas_date") or "—",
            "Import timestamp": r.get("imported_at") or "—",
            "Note": r.get("note_text") or "",
        }
        for r in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**Edit note**")
    options = [f"{r.get('unit_code')} | {r.get('fas_date') or '—'}" for r in rows]
    option_to_row = {opt: r for opt, r in zip(options, rows)}
    selected_label = st.selectbox(
        "Select row",
        options=options,
        key="report_ops_fas_row",
    )
    if not selected_label:
        return
    selected = option_to_row.get(selected_label)
    if not selected:
        return
    current_note = selected.get("note_text") or ""
    new_note = st.text_input(
        "Note",
        value=current_note,
        key="report_ops_fas_note_input",
        placeholder="e.g. Done, Checked, Keys returned",
    )
    if st.button("Save note", key="report_ops_fas_save"):
        def _do_upsert(conn):
            report_operations_service.upsert_fas_note(
                conn,
                unit_id=selected["unit_id"],
                fas_date=selected.get("fas_date") or "",
                note_text=new_note or "",
            )

        if db_write(_do_upsert):
            st.success("Note saved.")
            st.rerun()


def _render_import_diagnostics_tab(active_property: dict) -> None:
    st.subheader("Import Diagnostics")
    st.caption(
        "Non-OK import outcomes (ignored, conflict, invalid, skipped override). "
        "Observational only; no state changes from this tab."
    )
    rows = _get_import_diagnostics_queue()
    if not rows:
        st.info("No diagnostic rows for the active property.")
        return
    df = pd.DataFrame([
        {
            "Unit": r.get("unit_code"),
            "Report type": r.get("report_type"),
            "Status": r.get("validation_status"),
            "Conflict reason": r.get("conflict_reason") or "—",
            "Import time": r.get("imported_at") or "—",
            "Source file": r.get("source_file_name") or "—",
        }
        for r in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)


def render() -> None:
    st.title("Report Operations")
    active_property = render_active_property_banner()
    if active_property is None:
        return

    tab1, tab2, tab3 = st.tabs(["Missing Move-Out", "FAS Tracker", "Import Diagnostics"])
    with tab1:
        _render_missing_move_out_tab(active_property)
    with tab2:
        _render_fas_tracker_tab(active_property)
    with tab3:
        _render_import_diagnostics_tab(active_property)
