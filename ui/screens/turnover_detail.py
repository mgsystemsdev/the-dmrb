"""Turnover Detail screen: single turnover view, edit status/dates/tasks/notes."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from application.commands import (
    ClearManualOverride,
    UpdateTaskStatus,
    UpdateTurnoverDates,
    UpdateTurnoverStatus,
)
from application.workflows import (
    clear_manual_override_workflow,
    update_task_status_workflow,
    update_turnover_dates_workflow,
    update_turnover_status_workflow,
)
from config.settings import get_settings
from ui.data.backend import db_write, get_conn, note_service_mod, turnover_service_mod
from ui.data.cache import (
    cached_get_dmrb_board_rows,
    cached_get_turnover_detail,
    db_available,
    db_cache_identity,
    render_active_property_banner,
)
from ui.helpers.dates import parse_date, parse_date_for_input
from ui.helpers.dates import fmt_date
from ui.helpers.formatting import normalize_enum, normalize_label, safe_index
from ui.state import (
    ASSIGNEE_OPTIONS,
    BLOCK_OPTIONS,
    CONFIRM_LABEL_TO_VALUE,
    CONFIRM_VALUE_TO_LABEL,
    DEFAULT_TASK_OFFSETS,
    EXEC_LABEL_TO_VALUE,
    EXEC_VALUE_TO_LABEL,
    STATUS_OPTIONS,
    TASK_DISPLAY_NAMES,
)

CONFIRM_LABELS = list(CONFIRM_LABEL_TO_VALUE.keys())
EXEC_LABELS = [k for k in EXEC_LABEL_TO_VALUE if k]


def render() -> None:
    APP_SETTINGS = get_settings()
    active_property = render_active_property_banner()
    if active_property is None:
        return
    if st.session_state.selected_turnover_id is None:
        st.subheader("Turnover Detail")
        unit_search = st.text_input("Unit code", key="detail_unit_search")
        if st.button("Go"):
            if not db_available():
                st.error("Database not available")
                return
            try:
                rows = cached_get_dmrb_board_rows(
                    db_cache_identity(),
                    st.session_state.get("selected_property_id"),
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    date.today().isoformat(),
                )
                norm = (unit_search or "").strip().lower()
                for r in rows:
                    if norm and norm in (r.get("unit_code") or "").lower():
                        st.session_state.selected_turnover_id = r["turnover_id"]
                        st.rerun()
                        return
            except Exception as e:
                st.error(str(e))
                return
            st.warning("Unit not found")
        return

    tid = st.session_state.selected_turnover_id
    if not db_available():
        st.error("Database not available")
        return
    try:
        detail = cached_get_turnover_detail(db_cache_identity(), tid, date.today().isoformat())
    except Exception as e:
        st.error(str(e))
        return
    if not detail or not detail.get("turnover"):
        st.warning("Turnover not found")
        st.session_state.selected_turnover_id = None
        st.rerun()
        return
    t = detail["turnover"]
    u = detail.get("unit")
    enriched = detail.get("enriched_fields") or {}
    dv = enriched.get("dv")
    dtbr = enriched.get("dtbr")
    nvm = enriched.get("nvm", "")
    assign_display = enriched.get("assign_display", "")
    tasks_for_turnover = detail.get("tasks") or []
    notes_for_turnover = detail.get("notes") or []
    risks_for_turnover = detail.get("risks") or []

    unit_code = (u.get("unit_code_raw") or u.get("unit_code_norm") or "") if u else ""
    phase_display = (u.get("phase_code") or str(u.get("property_id", ""))) if u else ""
    building = (u.get("building_code") or "") if u else ""
    unit_number = (u.get("unit_number") or "") if u else ""
    if not building and not unit_number and u:
        _uc_parts = (u.get("unit_code_raw") or "").split("-")
        building = _uc_parts[1] if len(_uc_parts) >= 3 else ""
        unit_number = _uc_parts[-1] if len(_uc_parts) >= 2 else (_uc_parts[0] if _uc_parts else "")

    # ===================================================================
    # PANEL A: UNIT INFORMATION
    # ===================================================================
    with st.container(border=True):
        st.markdown("**UNIT INFORMATION**")
        hdr_left, hdr_right = st.columns([4, 1])
        with hdr_left:
            legal_src = t.get("legal_confirmation_source")
            legal_dot_html = (
                '<span title="Legal move-out confirmed" style="color:#28a745;font-size:1.1em;">●</span>'
                if legal_src else
                '<span title="No legal confirmation" style="color:#dc3545;font-size:1.1em;">●</span>'
            )
            unit_label = f"Unit {unit_code}" if unit_code else f"Turnover {tid}"
            st.markdown(f"<h3 style='margin:0;'>{unit_label} {legal_dot_html}</h3>", unsafe_allow_html=True)
        with hdr_right:
            if st.button("← Back"):
                st.session_state.page = "dmrb_board"
                st.rerun()
        id1, id2, id3, id4, id5 = st.columns([0.8, 0.8, 0.8, 0.8, 1.2])
        id1.write(f"**Phase:** {phase_display}")
        id2.write(f"**Building:** {building}" if building else "**Building:** —")
        id3.write(f"**Unit:** {unit_number}")
        id4.write(f"**N/V/M:** {nvm}")
        id5.write(f"**Assignee:** {assign_display}")

    # ===================================================================
    # PANEL B: STATUS & QC ACTION
    # ===================================================================
    today = date.today()
    actor = APP_SETTINGS.default_actor
    _detail_writes = st.session_state.enable_db_writes
    with st.container(border=True):
        s1, s2 = st.columns([2, 1])
        with s1:
            cur_status = (t.get("manual_ready_status") or "Vacant not ready").strip()
            idx = safe_index(STATUS_OPTIONS, cur_status)
            new_status = st.selectbox(
                "Status", STATUS_OPTIONS, index=idx, key="detail_status", disabled=not _detail_writes
            )
            if _detail_writes and new_status != cur_status:
                if db_write(
                    lambda c: update_turnover_status_workflow(
                        c,
                        UpdateTurnoverStatus(
                            turnover_id=tid,
                            manual_ready_status=new_status,
                            today=today,
                            actor=actor,
                        ),
                    )
                ):
                    st.rerun()
        with s2:
            st.write("")
            if st.button("✅ Confirm Quality Control", type="primary", use_container_width=True, key="detail_confirm_qc", disabled=not _detail_writes):
                qc_task = next((task for task in tasks_for_turnover if task.get("task_type") == "QC"), None)
                if qc_task:
                    if db_write(
                        lambda c: update_task_status_workflow(
                            c,
                            UpdateTaskStatus(
                                task_id=qc_task["task_id"],
                                fields={"confirmation_status": "CONFIRMED"},
                                today=today,
                                actor=actor,
                            ),
                        )
                    ):
                        st.rerun()

    # ===================================================================
    # PANEL C: DATES & METRICS
    # ===================================================================
    with st.container(border=True):
        st.markdown("**DATES**")
        dt1, dt2, dt3, dt4, dt5 = st.columns([1.2, 0.6, 1.2, 1.2, 0.6])
        # Move_out + DV
        with dt1:
            mo_val = parse_date(t.get("move_out_date"))
            new_mo = st.date_input(
                "Move-Out", value=mo_val or date.today(), key="detail_mo", format="MM/DD/YYYY",
                disabled=not _detail_writes
            )
            if _detail_writes and mo_val is not None and new_mo != mo_val:
                if db_write(
                    lambda c: update_turnover_dates_workflow(
                        c,
                        UpdateTurnoverDates(
                            turnover_id=tid,
                            move_out_date=new_mo,
                            today=today,
                            actor=actor,
                        ),
                    )
                ):
                    st.rerun()
        if dv is not None and dv > 10:
            dt2.markdown(f'**DV**<br><span style="color:#dc3545;font-weight:bold">{dv}</span>', unsafe_allow_html=True)
        else:
            dt2.write(f"**DV:** {dv if dv is not None else '—'}")
        # Ready_Date
        with dt3:
            rr_val = parse_date(t.get("report_ready_date"))
            new_rr = st.date_input(
                "Ready Date", value=rr_val, key="detail_rr", format="MM/DD/YYYY",
                disabled=not _detail_writes
            )
            if _detail_writes and new_rr is not None and new_rr != rr_val:
                if db_write(
                    lambda c: update_turnover_dates_workflow(
                        c,
                        UpdateTurnoverDates(
                            turnover_id=tid,
                            report_ready_date=new_rr,
                            today=today,
                            actor=actor,
                        ),
                    )
                ):
                    st.rerun()
        # Move_in + DTBR
        with dt4:
            mi_val = parse_date(t.get("move_in_date"))
            new_mi = st.date_input(
                "Move-In", value=mi_val, key="detail_mi", format="MM/DD/YYYY",
                disabled=not _detail_writes
            )
            if _detail_writes and new_mi is not None and new_mi != mi_val:
                if db_write(
                    lambda c: update_turnover_dates_workflow(
                        c,
                        UpdateTurnoverDates(
                            turnover_id=tid,
                            move_in_date=new_mi,
                            today=today,
                            actor=actor,
                        ),
                    )
                ):
                    st.rerun()
        dt5.write(f"**DTBR:** {dtbr if dtbr is not None else '—'}")

    # ===================================================================
    # PANEL D: W/D STATUS — Present (dropdown) | Notified (button) | Installed (button)
    # ===================================================================
    with st.container(border=True):
        st.markdown("**W/D STATUS**")
        w1, w2, w3 = st.columns(3)
        with w1:
            wd_opts = ["No", "Yes", "Yes stack"]
            cur_wd = "No"
            if t.get("wd_present"):
                cur_wd = (t.get("wd_present_type") or "Yes").strip()
            wd_idx = safe_index(wd_opts, cur_wd)
            new_wd = st.selectbox(
                "Present", wd_opts, index=wd_idx, key="detail_wd_present", disabled=not _detail_writes
            )
            if _detail_writes and new_wd != cur_wd:
                wd_bool = new_wd != "No"
                if db_write(lambda c: turnover_service_mod.update_wd_panel(
                    conn=c, turnover_id=tid, today=today, wd_present=wd_bool, wd_present_type=new_wd, actor=actor
                )):
                    st.rerun()
        with w2:
            st.write("")  # spacer to align with selectbox label
            notified = "✅ Yes" if t.get("wd_supervisor_notified") else "No"
            st.markdown(f'<p style="text-align:left;"><strong>Notified:</strong> {notified}</p>', unsafe_allow_html=True)
            if not t.get("wd_supervisor_notified"):
                if st.button("Mark Notified", key="detail_wd_notified", disabled=not _detail_writes):
                    if db_write(lambda c: turnover_service_mod.update_wd_panel(
                        conn=c, turnover_id=tid, today=today, wd_supervisor_notified=True, actor=actor
                    )):
                        st.rerun()
        with w3:
            st.write("")  # spacer to align with selectbox label
            installed = "✅ Yes" if t.get("wd_installed") else "No"
            st.markdown(f'<p style="text-align:left;"><strong>Installed:</strong> {installed}</p>', unsafe_allow_html=True)
            if not t.get("wd_installed"):
                if st.button("Mark Installed", key="detail_wd_installed", disabled=not _detail_writes):
                    if db_write(lambda c: turnover_service_mod.update_wd_panel(
                        conn=c, turnover_id=tid, today=today, wd_installed=True, actor=actor
                    )):
                        st.rerun()

    # ===================================================================
    # PANEL D: RISKS (always visible)
    # ===================================================================
    with st.container(border=True):
        st.markdown('<p style="text-align:left;"><strong>RISKS</strong></p>', unsafe_allow_html=True)
        risks = risks_for_turnover
        if risks:
            for r in risks:
                sev = r.get("severity", "")
                icon = "🔴" if sev == "CRITICAL" else "🟡" if sev == "WARNING" else "⚪"
                st.markdown(f'<p style="text-align:left;">{icon} {r.get("risk_type", "")} ({sev}) — {r.get("description", "") or ""}</p>', unsafe_allow_html=True)
        else:
            st.caption("No active risks")

    # ===================================================================
    # PANEL E2: AUTHORITY & IMPORT COMPARISON (collapsible)
    # ===================================================================
    _override_fields = [
        ("Move-Out Date", "move_out_date", "last_import_move_out_date", "move_out_manual_override_at"),
        ("Ready Date", "report_ready_date", "last_import_ready_date", "ready_manual_override_at"),
        ("Move-In Date", "move_in_date", "last_import_move_in_date", "move_in_manual_override_at"),
        ("Status", "manual_ready_status", "last_import_status", "status_manual_override_at"),
    ]
    _any_override = any(t.get(of[3]) for of in _override_fields)
    _any_divergence = any(
        t.get(of[2]) is not None and str(t.get(of[1]) or "") != str(t.get(of[2]) or "")
        for of in _override_fields
    )
    _panel_indicator = " ⚠" if (_any_override or _any_divergence) else ""

    with st.expander(f"▶ Authority & Import Comparison{_panel_indicator}", expanded=False):
        auth_rows = []
        for label, sys_key, import_key, override_key in _override_fields:
            sys_val = t.get(sys_key) or ""
            if sys_key != "manual_ready_status":
                sys_val = fmt_date(sys_val) if sys_val else "—"
            else:
                sys_val = sys_val or "—"
            import_val = t.get(import_key) or ""
            if import_key != "last_import_status":
                import_val = fmt_date(import_val) if import_val else "—"
            else:
                import_val = import_val or "—"
            override_at = t.get(override_key)
            override_active = override_at is not None
            # Source
            legal_src = t.get("legal_confirmation_source")
            if sys_key == "move_out_date" and legal_src:
                source = "Legal Confirmed"
            elif override_active:
                source = "Manual"
            else:
                source = "Import"
            override_display = "Active" if override_active else ""
            auth_rows.append({
                "Field": label,
                "Current (System)": sys_val,
                "Last Import": import_val,
                "Source": source,
                "Override": override_display,
                "_override_active": override_active,
                "_divergent": override_active and str(t.get(sys_key) or "") != str(t.get(import_key) or "") and t.get(import_key) is not None,
                "_pending_clear": override_active and str(t.get(sys_key) or "") == str(t.get(import_key) or "") and t.get(import_key) is not None,
                "_override_key": override_key,
            })

        # Render table with row highlighting
        for i, ar in enumerate(auth_rows):
            if ar["_divergent"]:
                bg = "background-color: rgba(255, 193, 7, 0.15);"
            else:
                bg = ""
            cols = st.columns([1.5, 1.5, 1.5, 1, 0.8, 0.8])
            if i == 0:
                cols[0].markdown("**Field**")
                cols[1].markdown("**Current (System)**")
                cols[2].markdown("**Last Import**")
                cols[3].markdown("**Source**")
                cols[4].markdown("**Override**")
                cols[5].markdown("")
                cols = st.columns([1.5, 1.5, 1.5, 1, 0.8, 0.8])
            if ar["_divergent"]:
                cols[0].markdown(f'<span style="background-color:rgba(255,193,7,0.2);padding:2px 4px;border-radius:3px;">{ar["Field"]}</span>', unsafe_allow_html=True)
            else:
                cols[0].write(ar["Field"])
            cols[1].write(ar["Current (System)"])
            cols[2].write(ar["Last Import"])
            cols[3].write(ar["Source"])
            if ar["_pending_clear"]:
                cols[4].caption("Pending Clear")
            else:
                cols[4].write(ar["Override"])
            if ar["_override_active"]:
                if cols[5].button("Clear", key=f"clear_override_{ar['_override_key']}"):
                    override_field = ar["_override_key"]
                    def _do_clear(c, field=override_field):
                        clear_manual_override_workflow(
                            c,
                            ClearManualOverride(
                                turnover_id=tid,
                                override_field=field,
                                actor=actor,
                            ),
                        )
                    if db_write(_do_clear):
                        st.rerun()

    # ===================================================================
    # PANEL F: TASKS — Task | Assignee | Date | Exec | Confirm | Req ☑ | Block ▼
    # ===================================================================
    block_opts = BLOCK_OPTIONS
    with st.container(border=True):
        st.markdown("**TASKS**")
        th1, th2, th3, th4, th5, th6, th7 = st.columns([1.0, 1.2, 1.0, 1.2, 1.0, 0.5, 1.2])
        th1.markdown("**Task**")
        th2.markdown("**Assignee**")
        th3.markdown("**Date**")
        th4.markdown("**Execution**")
        th5.markdown("**Confirm**")
        th6.markdown("**Req**")
        th7.markdown("**Blocking**")
        st.divider()

        task_assignees_cfg = st.session_state.dropdown_config.get("task_assignees", {})
        detail_offsets_cfg = st.session_state.dropdown_config.get("task_offsets", DEFAULT_TASK_OFFSETS)
        detail_move_out = parse_date(t.get("move_out_date"))
        tasks_sorted = sorted(tasks_for_turnover, key=lambda t: (t.get("task_type", ""), t.get("task_id", 0)))
        for task in tasks_sorted:
                task_type = task.get("task_type", "")
                task_id = task.get("task_id")
                if not task_id:
                    continue
                display_name = TASK_DISPLAY_NAMES.get(task_type, task_type)
                if task.get("vendor_due_date"):
                    due_val = parse_date_for_input(task.get("vendor_due_date"))
                elif detail_move_out:
                    offset = detail_offsets_cfg.get(task_type, 1)
                    due_val = detail_move_out + timedelta(days=offset)
                else:
                    due_val = date.today()
                exec_cur = normalize_enum(task.get("execution_status")) or "NOT_STARTED"
                exec_label = EXEC_VALUE_TO_LABEL.get(exec_cur)
                exec_options = list(EXEC_LABELS)
                if exec_label and exec_label not in exec_options:
                    exec_options.append(exec_label)
                exec_idx = safe_index(exec_options, exec_label)

                conf_cur = normalize_enum(task.get("confirmation_status")) or "PENDING"
                conf_label = CONFIRM_VALUE_TO_LABEL.get(conf_cur)
                conf_options = list(CONFIRM_LABELS)
                if conf_label and conf_label not in conf_options:
                    conf_options.append(conf_label)
                conf_idx = safe_index(conf_options, conf_label)

                db_assignee = normalize_label(task.get("assignee") or "")
                cfg = task_assignees_cfg.get(task_type, {})
                # Stable, deterministic options (sorted so order never shifts between reruns).
                cfg_opts = cfg.get("options") or [o for o in ASSIGNEE_OPTIONS if o]
                assignee_opts = ("",) + tuple(sorted({normalize_label(x) for x in cfg_opts if normalize_label(x)}))
                # Ensure DB value is selectable even if not in config
                if db_assignee and db_assignee not in assignee_opts:
                    assignee_opts = assignee_opts + (db_assignee,)
                assignee_key = f"detail_assignee_{task_id}_{task_type}"
                # Drive selection via session_state (not index) so widget + frontend always agree.
                cur_widget = st.session_state.get(assignee_key, "")
                if not isinstance(cur_widget, str) or cur_widget not in assignee_opts:
                    st.session_state[assignee_key] = db_assignee if db_assignee in assignee_opts else ""

                cur_block = task.get("blocking_reason") or ("Not Blocking" if not task.get("blocking") else "Other")
                block_options = list(block_opts)
                if cur_block and cur_block not in block_options:
                    block_options.append(cur_block)
                block_idx = safe_index(block_options, cur_block)

                tc1, tc2, tc3, tc4, tc5, tc6, tc7 = st.columns([1.0, 1.2, 1.0, 1.2, 1.0, 0.5, 1.2])
                tc1.write(display_name)
                with tc2:
                    new_assignee = st.selectbox(
                        "Assignee",
                        assignee_opts,
                        key=assignee_key,
                        label_visibility="collapsed",
                        disabled=not _detail_writes
                    )
                    if _detail_writes and normalize_label(new_assignee) != db_assignee:
                        if db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"assignee": new_assignee or None},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.rerun()
                with tc3:
                    new_due = st.date_input(
                        "Date", value=due_val, key=f"detail_due_{task_id}_{task_type}", label_visibility="collapsed",
                        format="MM/DD/YYYY", disabled=not _detail_writes
                    )
                    if _detail_writes and new_due != due_val:
                        if db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"vendor_due_date": new_due},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.rerun()
                with tc4:
                    new_exec = st.selectbox(
                        "Exec", exec_options, index=exec_idx, key=f"detail_exec_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    new_exec_val = EXEC_LABEL_TO_VALUE.get(new_exec)
                    if _detail_writes and new_exec_val is not None and normalize_enum(task.get("execution_status")) != (new_exec_val or "").upper():
                        if db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"execution_status": new_exec_val},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.toast(f"Execution → {new_exec}", icon="✅")
                            st.rerun()
                with tc5:
                    new_conf = st.selectbox(
                        "Confirm", conf_options, index=conf_idx, key=f"detail_conf_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    new_conf_val = CONFIRM_LABEL_TO_VALUE.get(new_conf)
                    if _detail_writes and new_conf_val and normalize_enum(task.get("confirmation_status")) != (new_conf_val or "").upper():
                        if db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"confirmation_status": new_conf_val},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.toast(f"Confirmation → {new_conf}", icon="✅")
                            st.rerun()
                with tc6:
                    req_val = bool(task.get("required"))
                    new_req = st.checkbox(
                        "Req", value=req_val, key=f"detail_req_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    if _detail_writes and new_req != req_val:
                        if db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"required": new_req},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.rerun()
                with tc7:
                    new_block = st.selectbox(
                        "Block", block_options, index=block_idx, key=f"detail_block_{task_id}_{task_type}",
                        label_visibility="collapsed", disabled=not _detail_writes
                    )
                    if _detail_writes and new_block != cur_block:
                        if db_write(
                            lambda c: update_task_status_workflow(
                                c,
                                UpdateTaskStatus(
                                    task_id=task_id,
                                    fields={"blocking": new_block != "Not Blocking", "blocking_reason": new_block},
                                    today=today,
                                    actor=actor,
                                ),
                            )
                        ):
                            st.rerun()

    # ===================================================================
    # PANEL G: NOTES
    # ===================================================================
    with st.container(border=True):
        st.markdown("**NOTES**")
        notes = notes_for_turnover
        for n in notes:
            col1, col2 = st.columns([4, 1])
            severity = n.get("note_type", "info")
            icon = "⛔" if n.get("blocking") else ""
            with col1:
                st.write(f"- {icon} {(n.get('description') or '')} ({severity})")
            with col2:
                if n.get("resolved_at"):
                    st.caption("Resolved")
                elif st.session_state.get("enable_db_writes") and note_service_mod and st.button("Resolve", key=f"note_resolve_{n.get('note_id')}"):
                    if db_write(lambda c: note_service_mod.resolve_note(conn=c, note_id=n["note_id"], actor=actor)):
                        st.rerun()
        new_note = st.text_area("Add note (free text)", key="detail_new_note", placeholder="Description...")
        if st.button("Add note") and (new_note or "").strip():
            if st.session_state.get("enable_db_writes") and note_service_mod and db_write(lambda c: note_service_mod.create_note(
                conn=c, turnover_id=tid, description=(new_note or "").strip(), actor=actor
            )):
                st.rerun()

# ---------------------------------------------------------------------------
