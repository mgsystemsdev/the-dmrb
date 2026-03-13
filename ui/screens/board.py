"""DMRB Board screen: filters, metrics, tabbed Unit Info / Unit Tasks."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from application.commands import UpdateTaskStatus, UpdateTurnoverDates, UpdateTurnoverStatus
from application.workflows import (
    update_task_status_workflow,
    update_turnover_dates_workflow,
    update_turnover_status_workflow,
)
from ui.data.backend import db_repository, get_conn, task_service_mod, turnover_service_mod
from ui.data.cache import (
    cached_get_dmrb_board_rows,
    cached_list_phases,
    db_cache_identity,
    db_available,
    get_active_property,
    invalidate_ui_caches,
    render_active_property_banner,
)
from ui.helpers.dates import dates_equal, parse_date, to_date
from ui.helpers.formatting import get_attention_badge
from ui.state import (
    ASSIGNEE_OPTIONS,
    CONFIRM_LABEL_TO_VALUE,
    CONFIRM_VALUE_TO_LABEL,
    DEFAULT_TASK_OFFSETS,
    EXEC_LABEL_TO_VALUE,
    EXEC_VALUE_TO_LABEL,
    STATUS_OPTIONS,
)

EXEC_LABELS = [k for k in EXEC_LABEL_TO_VALUE if k]
CONFIRM_LABELS = list(CONFIRM_LABEL_TO_VALUE.keys())


def _get_dmrb_rows():
    if not db_available():
        st.error("Database not available")
        return []
    try:
        db_identity = db_cache_identity()
        active_property = get_active_property()
        phase_ids = None
        if db_repository and st.session_state.filter_phase != "All":
            if "phase_id_by_code" not in st.session_state:
                phases = cached_list_phases(
                    db_identity, active_property["property_id"] if active_property else None
                )
                st.session_state.phase_id_by_code = {
                    str(p["phase_code"]): p["phase_id"] for p in phases
                }
            phase_id = st.session_state.get("phase_id_by_code", {}).get(
                st.session_state.filter_phase
            )
            if phase_id is not None:
                phase_ids = (phase_id,)
        latest_import_ts = ""
        if db_repository:
            conn = get_conn()
            if conn:
                try:
                    latest_import_ts = db_repository.get_latest_import_batch_timestamp(conn) or ""
                finally:
                    conn.close()
        return cached_get_dmrb_board_rows(
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
            today_iso=date.today().isoformat(),
            latest_import_batch_timestamp=latest_import_ts,
        )
    except Exception as e:
        st.error(str(e))
        return []


def _exec_label(task_dict):
    cur = (task_dict.get("execution_status") or "NOT_STARTED").upper()
    return EXEC_VALUE_TO_LABEL.get(cur, "Not Started")


def _confirm_label(task_dict):
    cur = (task_dict.get("confirmation_status") or "PENDING").upper()
    return CONFIRM_VALUE_TO_LABEL.get(cur, "Pending")


def render() -> None:
    from config.settings import get_settings

    APP_SETTINGS = get_settings()
    active_property = render_active_property_banner()
    if active_property is None:
        return
    rows = _get_dmrb_rows()
    n_active = len(rows)
    n_crit = sum(
        1
        for r in rows
        if r.get("has_violation") or r.get("operational_state") == "Move-In Risk"
    )

    with st.container(border=True):
        c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([2, 1, 1, 1, 1, 1, 1, 1])
        with c0:
            st.session_state.search_unit = st.text_input(
                "Search unit", value=st.session_state.search_unit, key="dmrb_search"
            )
        with c1:
            if db_repository:
                try:
                    active_property = get_active_property()
                    phases = cached_list_phases(
                        db_cache_identity(),
                        active_property["property_id"] if active_property else None,
                    )
                    st.session_state.phase_id_by_code = {
                        str(p["phase_code"]): p["phase_id"] for p in phases
                    }
                    phase_opts = ["All"] + sorted(st.session_state.phase_id_by_code.keys())
                except Exception:
                    phase_opts = ["All", "5", "7", "8"]
            else:
                phase_opts = ["All", "5", "7", "8"]
            idx = (
                phase_opts.index(st.session_state.filter_phase)
                if st.session_state.filter_phase in phase_opts
                else 0
            )
            st.session_state.filter_phase = st.selectbox(
                "Phase", phase_opts, index=idx, key="dmrb_phase"
            )
        with c2:
            status_opts = ["All"] + STATUS_OPTIONS
            idx = (
                status_opts.index(st.session_state.filter_status)
                if st.session_state.filter_status in status_opts
                else 0
            )
            st.session_state.filter_status = st.selectbox(
                "Status", status_opts, index=idx, key="dmrb_status"
            )
        with c3:
            nvm_opts = ["All", "Notice", "Notice + SMI", "Vacant", "SMI", "Move-In"]
            idx = (
                nvm_opts.index(st.session_state.filter_nvm)
                if st.session_state.filter_nvm in nvm_opts
                else 0
            )
            st.session_state.filter_nvm = st.selectbox(
                "N/V/M", nvm_opts, index=idx, key="dmrb_nvm"
            )
        with c4:
            assign_opts = ["All"] + [a for a in ASSIGNEE_OPTIONS if a]
            idx = (
                assign_opts.index(st.session_state.filter_assignee)
                if st.session_state.filter_assignee in assign_opts
                else 0
            )
            st.session_state.filter_assignee = st.selectbox(
                "Assign", assign_opts, index=idx, key="dmrb_assign"
            )
        with c5:
            qc_opts = ["All", "QC Done", "QC Not done"]
            idx = (
                qc_opts.index(st.session_state.filter_qc)
                if st.session_state.filter_qc in qc_opts
                else 0
            )
            st.session_state.filter_qc = st.selectbox(
                "QC", qc_opts, index=idx, key="dmrb_qc"
            )
        with c6:
            st.metric("Active", n_active)
        with c7:
            st.metric("CRIT", n_crit)

    with st.container(border=True):
        n_viol = sum(1 for r in rows if r.get("has_violation"))
        n_plan = sum(1 for r in rows if r.get("plan_breach"))
        n_sla = sum(1 for r in rows if r.get("sla_breach"))
        n_mi_risk = sum(1 for r in rows if r.get("operational_state") == "Move-In Risk")
        n_stalled = sum(1 for r in rows if r.get("is_task_stalled"))
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Active Units", n_active)
        m2.metric("Violations", n_viol)
        m3.metric("Plan Breach", n_plan)
        m4.metric("SLA Breach", n_sla)
        m5.metric("Move-In Risk", n_mi_risk)
        m6.metric("Work Stalled", n_stalled)

    if not rows:
        st.info("No turnovers match filters.")
        return

    tid_map = []
    task_id_map = []
    info_data = []
    task_data = []

    _task_cols = [
        "Inspection",
        "Carpet Bid",
        "Make Ready Bid",
        "Paint",
        "Make Ready",
        "Housekeeping",
        "Carpet Clean",
        "Final Walk",
    ]
    _task_date_cols = [f"{tc} Date" for tc in _task_cols]
    _task_keys = [
        "task_insp",
        "task_cb",
        "task_mrb",
        "task_paint",
        "task_mr",
        "task_hk",
        "task_cc",
        "task_fw",
    ]
    _task_codes = ["Insp", "CB", "MRB", "Paint", "MR", "HK", "CC", "FW"]
    _offsets_cfg = st.session_state.dropdown_config.get(
        "task_offsets", DEFAULT_TASK_OFFSETS
    )

    for row in rows:
        tid = row["turnover_id"]
        tid_map.append(tid)
        tasks = {
            name: (row.get(key) or {})
            for name, key in zip(_task_cols, _task_keys)
        }
        task_qc = row.get("task_qc") or {}

        task_id_map.append(
            {
                **{name: tasks[name].get("task_id") for name in _task_cols},
                "Quality Control": task_qc.get("task_id"),
            }
        )

        nvm_full = row.get("nvm", "—")

        status_display = row.get("availability_status") or row.get("manual_ready_status", "Vacant not ready")

        info_data.append(
            {
                "▶": False,
                "Unit": row.get("unit_code", ""),
                "Status": status_display,
                "Move-Out": parse_date(row.get("move_out_date")),
                "Ready Date": parse_date(row.get("report_ready_date") or row.get("ready_date")),
                "DV": row.get("dv"),
                "Move-In": parse_date(row.get("move_in_date")),
                "DTBR": row.get("dtbr"),
                "N/V/M": nvm_full,
                "W/D": row.get("wd_summary", "—"),
                "Quality Control": _confirm_label(task_qc),
                "Alert": get_attention_badge(row),
                "Notes": (row.get("notes_text") or "")[:50],
            }
        )

        legal_src = row.get("legal_confirmation_source")
        legal_dot = "🟢" if legal_src else "🔴"
        task_row = {
            "▶": False,
            "Unit": row.get("unit_code", ""),
            "⚖": legal_dot,
            "Status": status_display,
            "DV": row.get("dv"),
            "DTBR": row.get("dtbr"),
        }
        move_out_dt = parse_date(row.get("move_out_date"))
        for name, code in zip(_task_cols, _task_codes):
            task_row[name] = _exec_label(tasks[name])
            existing_date = parse_date(tasks[name].get("vendor_due_date"))
            if existing_date:
                task_row[f"{name} Date"] = existing_date
            elif move_out_dt:
                offset = _offsets_cfg.get(code, 1)
                task_row[f"{name} Date"] = move_out_dt + timedelta(days=offset)
            else:
                task_row[f"{name} Date"] = None
        task_data.append(task_row)

    df_info = pd.DataFrame(info_data)
    df_task = pd.DataFrame(task_data)

    _writes_on = st.session_state.enable_db_writes

    _max_notes_len = max(
        (len(r.get("Notes", "")) for r in info_data), default=5
    )
    _notes_width = max(60, min(_max_notes_len * 8 + 16, 300))

    tab_info, tab_tasks = st.tabs(["Unit Info", "Unit Tasks"])

    with tab_info:
        info_col_config = {
            "▶": st.column_config.CheckboxColumn("▶", width=40),
            "Unit": st.column_config.TextColumn("Unit"),
            "Status": st.column_config.SelectboxColumn(
                "Status", options=STATUS_OPTIONS
            ),
            "Move-Out": st.column_config.DateColumn(
                "Move-Out", format="MM/DD/YYYY"
            ),
            "Ready Date": st.column_config.DateColumn(
                "Ready Date", format="MM/DD/YYYY"
            ),
            "DV": st.column_config.NumberColumn("DV", width=50),
            "Move-In": st.column_config.DateColumn(
                "Move-In", format="MM/DD/YYYY"
            ),
            "DTBR": st.column_config.NumberColumn("DTBR", width=60),
            "N/V/M": st.column_config.TextColumn("N/V/M", width=80),
            "W/D": st.column_config.TextColumn("W/D", width=50),
            "Quality Control": st.column_config.SelectboxColumn(
                "Quality Control", options=CONFIRM_LABELS
            ),
            "Alert": st.column_config.TextColumn("Alert"),
            "Notes": st.column_config.TextColumn("Notes", width=_notes_width),
        }
        info_disabled = ["Unit", "DV", "DTBR", "N/V/M", "W/D", "Alert", "Notes"]
        if not _writes_on:
            info_disabled += [
                "Status",
                "Move-Out",
                "Ready Date",
                "Move-In",
                "Quality Control",
            ]
        info_col_order = [
            "▶",
            "Unit",
            "Status",
            "Move-Out",
            "Ready Date",
            "DV",
            "Move-In",
            "DTBR",
            "N/V/M",
            "W/D",
            "Quality Control",
            "Alert",
            "Notes",
        ]
        edited_info = st.data_editor(
            df_info,
            column_config=info_col_config,
            column_order=info_col_order,
            disabled=info_disabled,
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            key="dmrb_info_editor",
        )

    with tab_tasks:
        task_col_config = {
            "▶": st.column_config.CheckboxColumn("▶", width=40),
            "Unit": st.column_config.TextColumn("Unit"),
            "⚖": st.column_config.TextColumn(
                "⚖",
                width=35,
                help="Legal move-out confirmation: 🟢 = confirmed, 🔴 = not confirmed",
            ),
            "Status": st.column_config.TextColumn("Status"),
            "DV": st.column_config.NumberColumn("DV", width=50),
            "DTBR": st.column_config.NumberColumn("DTBR", width=60),
            **{
                tc: st.column_config.SelectboxColumn(tc, options=EXEC_LABELS)
                for tc in _task_cols
            },
            **{
                dc: st.column_config.DateColumn(dc, format="MM/DD/YYYY")
                for dc in _task_date_cols
            },
        }
        task_disabled = ["Unit", "⚖", "Status", "DV", "DTBR"]
        if not _writes_on:
            task_disabled += _task_cols + _task_date_cols
        task_col_order = ["▶", "Unit", "⚖", "Status", "DV", "DTBR"]
        for tc, dc in zip(_task_cols, _task_date_cols):
            task_col_order.extend([tc, dc])
        edited_task = st.data_editor(
            df_task,
            column_config=task_col_config,
            column_order=task_col_order,
            disabled=task_disabled,
            hide_index=True,
            num_rows="fixed",
            use_container_width=True,
            key="dmrb_task_editor",
        )

    nav_tid = None
    status_updates = []
    date_updates = []
    task_exec_updates = []
    task_confirm_updates = []
    task_date_updates = []

    for idx in range(len(tid_map)):
        tid = tid_map[idx]

        if edited_info.iloc[idx]["▶"] or edited_task.iloc[idx]["▶"]:
            nav_tid = tid

        if df_info.iloc[idx]["Status"] != edited_info.iloc[idx]["Status"]:
            status_updates.append((tid, edited_info.iloc[idx]["Status"]))
        date_kwargs = {}
        for col_name, field_name in [
            ("Move-Out", "move_out_date"),
            ("Ready Date", "report_ready_date"),
            ("Move-In", "move_in_date"),
        ]:
            if not dates_equal(
                df_info.iloc[idx][col_name],
                edited_info.iloc[idx][col_name],
            ):
                date_kwargs[field_name] = to_date(
                    edited_info.iloc[idx][col_name]
                )
        if date_kwargs:
            date_updates.append((tid, date_kwargs))
        if df_info.iloc[idx]["Quality Control"] != edited_info.iloc[idx][
            "Quality Control"
        ]:
            qc_task_id = task_id_map[idx].get("Quality Control")
            if qc_task_id:
                new_val = CONFIRM_LABEL_TO_VALUE.get(
                    edited_info.iloc[idx]["Quality Control"]
                )
                if new_val:
                    task_confirm_updates.append((qc_task_id, new_val))

        for task_col in _task_cols:
            if df_task.iloc[idx][task_col] != edited_task.iloc[idx][task_col]:
                task_id = task_id_map[idx].get(task_col)
                if task_id:
                    new_val = EXEC_LABEL_TO_VALUE.get(
                        edited_task.iloc[idx][task_col]
                    )
                    if new_val is not None:
                        task_exec_updates.append((task_id, new_val))
        for task_col, date_col in zip(_task_cols, _task_date_cols):
            if not dates_equal(
                df_task.iloc[idx][date_col],
                edited_task.iloc[idx][date_col],
            ):
                task_id = task_id_map[idx].get(task_col)
                if task_id:
                    task_date_updates.append(
                        (
                            task_id,
                            to_date(edited_task.iloc[idx][date_col]),
                        )
                    )

    if nav_tid is not None:
        st.session_state.selected_turnover_id = nav_tid
        st.session_state.page = "detail"
        st.rerun()
    db_edits = (
        status_updates
        or date_updates
        or task_exec_updates
        or task_confirm_updates
        or task_date_updates
    )
    if (
        st.session_state.enable_db_writes
        and db_edits
        and task_service_mod
        and turnover_service_mod
    ):
        from ui.data.backend import db_write

        conn = get_conn()
        if not conn:
            st.error("Database not available")
        else:
            try:
                today = date.today()
                actor = APP_SETTINGS.default_actor
                for tid, new_status in status_updates:
                    update_turnover_status_workflow(
                        conn,
                        UpdateTurnoverStatus(
                            turnover_id=tid,
                            manual_ready_status=new_status,
                            today=today,
                            actor=actor,
                        ),
                    )
                for tid, kwargs in date_updates:
                    update_turnover_dates_workflow(
                        conn,
                        UpdateTurnoverDates(
                            turnover_id=tid,
                            today=today,
                            actor=actor,
                            move_out_date=kwargs.get("move_out_date"),
                            report_ready_date=kwargs.get("report_ready_date"),
                            move_in_date=kwargs.get("move_in_date"),
                        ),
                    )
                for task_id, new_val in task_exec_updates:
                    update_task_status_workflow(
                        conn,
                        UpdateTaskStatus(
                            task_id=task_id,
                            fields={"execution_status": new_val},
                            today=today,
                            actor=actor,
                        ),
                    )
                for task_id, new_val in task_confirm_updates:
                    update_task_status_workflow(
                        conn,
                        UpdateTaskStatus(
                            task_id=task_id,
                            fields={"confirmation_status": new_val},
                            today=today,
                            actor=actor,
                        ),
                    )
                for task_id, new_date in task_date_updates:
                    update_task_status_workflow(
                        conn,
                        UpdateTaskStatus(
                            task_id=task_id,
                            fields={"vendor_due_date": new_date},
                            today=today,
                            actor=actor,
                        ),
                    )
                conn.commit()
                invalidate_ui_caches()
            except Exception as e:
                conn.rollback()
                st.error(str(e))
            finally:
                conn.close()
        st.rerun()
