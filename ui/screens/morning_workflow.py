"""Morning Workflow: single-page control panel — import status, repair queue, risk summary, today's critical units."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from ui.data.backend import db_repository, db_write, get_conn
from ui.data.cache import (
    cached_get_dmrb_board_rows,
    db_available,
    db_cache_identity,
    get_active_property,
    render_active_property_banner,
)

# Report type -> display name for Import Status block
IMPORT_LABELS = {
    "MOVE_OUTS": "Move-Out",
    "PENDING_MOVE_INS": "Move-In",
    "AVAILABLE_UNITS": "Available",
    "PENDING_FAS": "FAS",
}


def _format_import_time(imported_at: str | None, today: date) -> str:
    if not imported_at:
        return "—"
    try:
        s = str(imported_at).strip()
        if "T" in s:
            dt = datetime.fromisoformat(s[:19].replace("Z", ""))
        else:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        d = dt.date() if hasattr(dt, "date") else date(dt.year, dt.month, dt.day)
        if d == today and "T" in s and len(s) >= 16:
            hour, minute = int(s[11:13]), int(s[14:16])
            ampm = "AM" if hour < 12 else "PM"
            h12 = hour % 12 or 12
            return f"Today {h12}:{minute:02d} {ampm}"
        if d == today:
            return "Today"
        return d.isoformat()
    except Exception:
        return str(imported_at)[:16] if imported_at else "—"


def _get_last_import_timestamps() -> dict[str, str]:
    if not db_available() or not db_repository:
        return {}
    conn = get_conn()
    if not conn:
        return {}
    try:
        return db_repository.get_last_import_timestamps(conn)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _get_missing_move_out_queue() -> list[dict]:
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


def _render_import_status(today: date) -> None:
    st.subheader("1. Import Status")
    st.caption("Confirm reports are fresh before starting the day.")
    timestamps = _get_last_import_timestamps()
    for report_type, label in IMPORT_LABELS.items():
        ts = timestamps.get(report_type)
        fmt = _format_import_time(ts, today)
        if not ts:
            st.warning(f"⚠ {label} report not imported today")
        else:
            try:
                s = str(ts).strip()[:10]
                imp_date = date.fromisoformat(s) if len(s) >= 10 else None
                if imp_date != today:
                    st.warning(f"⚠ {label} report not imported today (last: {fmt})")
                else:
                    st.text(f"{label:20} {fmt}")
            except Exception:
                st.text(f"{label:20} {fmt}")
    if not timestamps and db_available():
        st.info("No imports recorded yet. Run imports from Admin or your import process.")


def _render_repair_queue(active_property: dict) -> None:
    from services import report_operations_service

    st.subheader("2. Units missing move-out date")
    st.caption("Repair queue: add move-out date and create turnover so the unit appears on the board.")
    rows = _get_missing_move_out_queue()
    if not rows:
        st.success("No units in the repair queue.")
        return

    df = pd.DataFrame([
        {
            "Unit": r.get("unit_code"),
            "Move-In Date": r.get("move_in_date") or "—",
            "Report": r.get("report_type") or "—",
        }
        for r in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("**Resolve: create turnover with move-out date**")
    options = [f"{r.get('unit_code')} ({r.get('conflict_reason')})" for r in rows]
    option_to_row = {opt: r for opt, r in zip(options, rows)}
    selected_label = st.selectbox(
        "Select unit to resolve",
        options=options,
        key="morning_workflow_missing_move_out_unit",
    )
    if not selected_label:
        return
    selected = option_to_row.get(selected_label)
    if not selected:
        return
    move_out_date = st.date_input(
        "Move-out date",
        value=date.today(),
        key="morning_workflow_move_out_date",
    )
    if st.button("Create turnover", key="morning_workflow_create_turnover"):
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


def _render_turnover_risk_summary(rows: list[dict], today: date) -> None:
    st.subheader("3. Turnover risk summary")
    st.caption("Quick counts; open the board or Flag Bridge to act.")
    vacant_over_7 = sum(1 for r in rows if (r.get("dv") or 0) > 7)
    sla_breach_count = sum(1 for r in rows if r.get("sla_breach") is True)
    days_to_move_in = []
    for r in rows:
        d = r.get("days_to_move_in")
        if d is not None and 0 <= d <= 3:
            days_to_move_in.append(r)
    move_in_soon_count = len(days_to_move_in)

    col1, col2, col3 = st.columns(3)
    with col1:
        if vacant_over_7 > 0:
            st.metric("Units vacant > 7 days", vacant_over_7, help="Link to board")
        else:
            st.metric("Units vacant > 7 days", 0)
    with col2:
        if sla_breach_count > 0:
            st.metric("Units with SLA breach", sla_breach_count, help="Link to Flag Bridge")
        else:
            st.metric("Units with SLA breach", 0)
    with col3:
        if move_in_soon_count > 0:
            st.metric("Move-ins within 3 days", move_in_soon_count, help="Link to board")
        else:
            st.metric("Move-ins within 3 days", 0)

    if sla_breach_count > 0:
        if st.button("Open Flag Bridge (SLA breach filter)", key="morning_workflow_flag_bridge"):
            st.session_state.breach_filter = "SLA Breach"
            st.session_state.breach_value = "Yes"
            st.session_state.page = "flag_bridge"
            st.rerun()
    if st.button("Open DMRB Board", key="morning_workflow_board"):
        st.session_state.page = "dmrb_board"
        st.rerun()


def _render_todays_critical(rows: list[dict], today: date) -> None:
    st.subheader("4. Today's critical units")
    st.caption("Move-ins, move-outs, and ready dates today. Click a row to open Turnover Detail.")
    today_iso = today.isoformat()
    critical = []
    for r in rows:
        unit_code = r.get("unit_code") or ""
        tid = r.get("turnover_id")
        mo = (r.get("move_out_date") or "")[:10]
        mi = (r.get("move_in_date") or "")[:10]
        rr = (r.get("report_ready_date") or "")[:10]
        if mo == today_iso:
            critical.append({"Unit": unit_code, "Event": "Move-Out", "Date": "Today", "turnover_id": tid})
        if mi == today_iso:
            critical.append({"Unit": unit_code, "Event": "Move-In", "Date": "Today", "turnover_id": tid})
        if rr == today_iso:
            critical.append({"Unit": unit_code, "Event": "Ready Date", "Date": "Today", "turnover_id": tid})

    if not critical:
        st.info("No move-ins, move-outs, or ready dates today.")
        return

    df = pd.DataFrame([{"Unit": x["Unit"], "Event": x["Event"], "Date": x["Date"]} for x in critical])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption("Open a unit in Turnover Detail:")
    options = [f"{x['Unit']} — {x['Event']}" for x in critical]
    choice = st.selectbox("Select unit", options=options, key="morning_workflow_critical_unit")
    if choice and st.button("Open Turnover Detail", key="morning_workflow_open_detail"):
        idx = options.index(choice)
        tid = critical[idx].get("turnover_id")
        if tid is not None:
            st.session_state.selected_turnover_id = tid
            st.session_state.page = "detail"
            st.rerun()


def render() -> None:
    st.title("Morning Workflow")
    st.caption("What do I need to fix right now before the day starts?")
    active_property = render_active_property_banner()
    if active_property is None:
        return

    today = date.today()

    _render_import_status(today)

    st.markdown("---")
    _render_repair_queue(active_property)

    st.markdown("---")
    rows = []
    if db_available():
        try:
            rows = cached_get_dmrb_board_rows(
                db_cache_identity(),
                active_property.get("property_id"),
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                today.isoformat(),
            )
        except Exception as e:
            st.error(str(e))
    _render_turnover_risk_summary(rows, today)

    st.markdown("---")
    _render_todays_critical(rows, today)
