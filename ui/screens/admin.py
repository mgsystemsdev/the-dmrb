"""Admin screen: tabs for Add Unit, Import, Unit Master Import, Exports, Dropdown Manager."""
from __future__ import annotations

import json
import os
from datetime import date

import pandas as pd
import streamlit as st

from application.commands import ApplyImportRow, CreateTurnover
from application.workflows import apply_import_row_workflow, create_turnover_workflow
from config.settings import get_settings
from ui.data.backend import (
    BACKEND_ERROR,
    get_conn,
    get_db_path,
    import_service_mod,
    manual_availability_service_mod,
    property_service_mod,
    unit_master_import_service_mod,
)
from ui.data.cache import (
    cached_list_buildings,
    cached_list_properties,
    cached_list_phases,
    cached_list_units,
    db_available,
    db_cache_identity,
    db_write,
    invalidate_ui_caches,
    render_active_property_banner,
    set_active_property,
    sync_active_property,
)
from ui.helpers.dropdowns import save_dropdown_config
from ui.state import (
    BLOCK_OPTIONS,
    CONFIRM_LABEL_TO_VALUE,
    DEFAULT_TASK_OFFSETS,
    EXEC_LABEL_TO_VALUE,
    OFFSET_OPTIONS,
    TASK_DISPLAY_NAMES,
    TASK_TYPES_ALL,
)

CONFIRM_LABELS = list(CONFIRM_LABEL_TO_VALUE.keys())
EXEC_LABELS = [k for k in EXEC_LABEL_TO_VALUE if k]

APP_SETTINGS = get_settings()


# ---------------------------------------------------------------------------
# Dropdown Manager
# ---------------------------------------------------------------------------
def _render_dropdown_manager() -> None:
    st.subheader("Dropdown Manager")
    st.caption(
        "Manage assignees per task type. Execution statuses, confirmation statuses, "
        "and blocking reasons are system-controlled and cannot be changed here."
    )
    if render_active_property_banner() is None:
        return

    cfg = st.session_state.dropdown_config
    task_assignees = cfg.get("task_assignees", {})

    with st.container(border=True):
        st.markdown("**TASK ASSIGNEES**")
        st.caption("Add or remove assignees for each task type.")

        for task_code in TASK_TYPES_ALL:
            display_name = TASK_DISPLAY_NAMES.get(task_code, task_code)
            ta_cfg = task_assignees.get(task_code, {"options": [], "default": ""})
            opts = ta_cfg.get("options", [])

            with st.expander(f"{display_name} — {len(opts)} assignee(s)"):
                for i, opt in enumerate(opts):
                    c1, c3 = st.columns([4, 1])
                    c1.write(opt)
                    if c3.button("Remove", key=f"dd_rm_{task_code}_{i}"):
                        opts.pop(i)
                        save_dropdown_config()
                        st.rerun()

                new_assignee = st.text_input(
                    "Add assignee", key=f"dd_add_{task_code}", placeholder="Name..."
                )
                if st.button("Add", key=f"dd_add_btn_{task_code}") and (new_assignee or "").strip():
                    name = new_assignee.strip()
                    if name not in opts:
                        opts.append(name)
                        ta_cfg["options"] = opts
                        task_assignees[task_code] = ta_cfg
                        save_dropdown_config()
                        st.rerun()

    task_offsets = cfg.get("task_offsets", {})
    with st.container(border=True):
        st.markdown("**TASK OFFSET SCHEDULE**")
        st.caption(
            "Days after move-out when each task is scheduled. Select an offset and hit Save."
        )

        for task_code in TASK_TYPES_ALL:
            display_name = TASK_DISPLAY_NAMES.get(task_code, task_code)
            current_offset = task_offsets.get(
                task_code, DEFAULT_TASK_OFFSETS.get(task_code, 1)
            )
            c1, c2, c3 = st.columns([2, 1.5, 1])
            c1.write(f"**{display_name}**")
            offset_idx = (
                OFFSET_OPTIONS.index(current_offset)
                if current_offset in OFFSET_OPTIONS
                else 0
            )
            new_offset = c2.selectbox(
                "Offset",
                OFFSET_OPTIONS,
                index=offset_idx,
                key=f"dd_offset_{task_code}",
                label_visibility="collapsed",
            )
            if c3.button("Save", key=f"dd_offset_save_{task_code}"):
                task_offsets[task_code] = new_offset
                cfg["task_offsets"] = task_offsets
                save_dropdown_config()
                st.rerun()

        st.divider()
        st.caption("Current schedule (days after move-out):")
        sorted_tasks = sorted(TASK_TYPES_ALL, key=lambda tc: task_offsets.get(tc, 99))
        for tc in sorted_tasks:
            dn = TASK_DISPLAY_NAMES.get(tc, tc)
            off = task_offsets.get(tc, "—")
            st.write(f"Day {off} → {dn}")

    with st.container(border=True):
        st.markdown(
            "**SYSTEM-CONTROLLED VALUES** *(read-only — managed by backend)*"
        )
        r1, r2, r3 = st.columns(3)
        with r1:
            st.caption("Execution Statuses")
            for label in EXEC_LABELS:
                st.write(f"· {label}")
        with r2:
            st.caption("Confirmation Statuses")
            for label in CONFIRM_LABELS:
                st.write(f"· {label}")
        with r3:
            st.caption("Blocking Reasons")
            for label in BLOCK_OPTIONS:
                st.write(f"· {label}")


# ---------------------------------------------------------------------------
# Property Structure (read-only hierarchy)
# ---------------------------------------------------------------------------
def _render_property_structure() -> None:
    st.subheader("Property structure")
    st.caption(
        "Read-only view: property → phase → building → unit. "
        "Use to validate hierarchy migration."
    )
    if render_active_property_banner() is None:
        return
    if not property_service_mod:
        st.info("Backend not available.")
        return
    if not db_available():
        st.error("Database not available")
        return
    db_identity = db_cache_identity()
    properties = cached_list_properties(db_identity)
    if not properties:
        st.write("No properties in database. Create one below.")
        if st.session_state.get("enable_db_writes"):
            name = st.text_input(
                "Property name", value="My Property", key="ps_new_property_name"
            )
            if st.button("Create property", key="ps_create_property"):
                def do_create(conn):
                    property_service_mod.insert_property(conn, name or "My Property")

                if db_write(do_create):
                    st.success("Property created.")
                    st.rerun()
        else:
            st.caption("Enable DB Writes in the sidebar to create a property.")
        return
    for prop in properties:
        pid = prop["property_id"]
        name = prop.get("name") or f"Property {pid}"
        with st.expander(f"**{name}** (id={pid})", expanded=True):
            phases = cached_list_phases(db_identity, pid)
            if st.session_state.get("enable_db_writes"):
                st.caption("Add another phase to this property:")
                add_phase_col1, add_phase_col2 = st.columns([1, 3])
                with add_phase_col1:
                    new_phase_code = st.text_input(
                        "Phase code",
                        value="",
                        key=f"ps_phase_code_{pid}",
                        placeholder="e.g. 5, 7, 8",
                    )
                with add_phase_col2:
                    if (
                        st.button("Add phase", key=f"ps_add_phase_{pid}")
                        and (new_phase_code or "").strip()
                    ):
                        def do_add_phase(conn, prop_id=pid, code=new_phase_code.strip()):
                            property_service_mod.resolve_phase(
                                conn, property_id=prop_id, phase_code=code
                            )

                        if db_write(lambda c: do_add_phase(c)):
                            st.success(f"Phase {new_phase_code.strip()} added.")
                            st.rerun()
            if not phases:
                st.caption("No phases yet.")
                continue
            for ph in phases:
                phase_id = ph["phase_id"]
                phase_code = ph.get("phase_code") or ""
                st.markdown(f"Phase **{phase_code}** (id={phase_id})")
                buildings = cached_list_buildings(db_identity, phase_id)
                if not buildings:
                    st.caption("  No buildings.")
                    continue
                for b in buildings:
                    building_id = b["building_id"]
                    bcode = b.get("building_code") or ""
                    units = cached_list_units(db_identity, building_id)
                    unit_list = (
                        ", ".join(
                            str(u.get("unit_number") or u.get("unit_id"))
                            for u in units
                        )
                        if units
                        else "—"
                    )
                    st.caption(
                        f"  Building {bcode} (id={building_id}): units {unit_list}"
                    )


# ---------------------------------------------------------------------------
# Add Unit (add unit to active turnover)
# ---------------------------------------------------------------------------
def _render_add_availability() -> None:
    st.subheader("Add unit")
    st.caption(
        "Add unit to active turnover. Unit must already exist in the database "
        "(e.g. from Unit Master Import); one open turnover per unit. "
        "If Phase + Building + Unit does not match a unit in the database, "
        "it cannot enter the lifecycle."
    )
    if not manual_availability_service_mod or not property_service_mod:
        st.warning("Backend or manual availability service not available.")
        if BACKEND_ERROR is not None:
            with st.expander("Details"):
                st.code(str(BACKEND_ERROR), language=None)
                st.caption("Run from repo root: streamlit run the-dmrb/app.py")
        return
    if not st.session_state.get("enable_db_writes"):
        st.caption("Turn on **Enable DB Writes** in the sidebar to submit.")
    active_property = render_active_property_banner()
    if active_property is None:
        return
    if not db_available():
        st.error("Database not available")
        return
    db_identity = db_cache_identity()
    property_id = active_property["property_id"]
    phases = cached_list_phases(db_identity, property_id)
    if not phases:
        st.warning(
            "No phases for this property. Run **Admin → Unit Master Import** "
            "with your Units CSV first to populate Phase and Building dropdowns, "
            "or create one phase below."
        )
        if not st.session_state.get("enable_db_writes"):
            st.caption(
                "Turn on **Enable DB Writes** in the sidebar, then use the form below."
            )
        phase_code_input = st.text_input(
            "Phase code", value="5", key="add_avail_new_phase_code", help="e.g. 5, 7, or 8"
        )
        if st.button("Create phase", key="add_avail_create_phase"):
            if not st.session_state.get("enable_db_writes"):
                st.error("Enable DB Writes in the sidebar first.")
            else:
                code = (phase_code_input or "5").strip()
                if not code:
                    st.error("Enter a phase code.")
                else:
                    def do_create_phase(conn):
                        property_service_mod.resolve_phase(
                            conn, property_id=property_id, phase_code=code
                        )

                    if db_write(do_create_phase):
                        st.success("Phase created. Refreshing.")
                        st.rerun()
        return
    phase_opts = sorted(
        [
            str(p.get("phase_code") or p.get("phase_id") or "")
            for p in phases
            if (p.get("phase_code") or p.get("phase_id"))
        ],
        key=lambda x: (int(x) if x.isdigit() else float("inf"), x),
    )
    if not phase_opts:
        phase_opts = [str(p.get("phase_id", "")) for p in phases]
    prev_phase = st.session_state.get("add_avail_phase")
    phase_idx = phase_opts.index(prev_phase) if prev_phase in phase_opts else 0
    phase_code = st.selectbox("Phase", phase_opts, index=phase_idx, key="add_avail_phase")
    if prev_phase is not None and prev_phase != phase_code:
        st.session_state.pop("add_avail_building", None)
    phase_row = next(
        (
            p
            for p in phases
            if str(p.get("phase_code") or p.get("phase_id") or "") == phase_code
        ),
        phases[0] if phases else None,
    )
    phase_id = int(phase_row["phase_id"]) if phase_row else None
    buildings = cached_list_buildings(db_identity, phase_id) if phase_id else []
    building_opts = sorted(
        [
            str(b.get("building_code") or b.get("building_id") or "")
            for b in buildings
            if (b.get("building_code") or b.get("building_id"))
        ],
        key=lambda x: (int(x) if x.isdigit() else float("inf"), x),
    )
    if not building_opts:
        building_opts = [str(b.get("building_id", "")) for b in buildings]
    if building_opts:
        prev_bldg = st.session_state.get("add_avail_building")
        building_idx = building_opts.index(prev_bldg) if prev_bldg in building_opts else 0
        building_code = st.selectbox(
            "Building", building_opts, index=building_idx, key="add_avail_building"
        )
    else:
        st.warning(
            f"No buildings found for Phase {phase_code}. "
            "Run **Unit Master Import** or create one below."
        )
        if not st.session_state.get("enable_db_writes"):
            st.caption(
                "Turn on **Enable DB Writes** in the sidebar, then use the form below."
            )
        building_code_input = st.text_input(
            "Building code",
            value="1",
            key="add_avail_new_building_code",
            help="e.g. 1, 2, A, B",
        )
        if st.button("Create building", key="add_avail_create_building"):
            if not st.session_state.get("enable_db_writes"):
                st.error("Enable DB Writes in the sidebar first.")
            else:
                bcode = (building_code_input or "1").strip()
                if not bcode:
                    st.error("Enter a building code.")
                else:
                    def do_create_building(conn):
                        property_service_mod.resolve_building(
                            conn, phase_id=phase_id, building_code=bcode
                        )

                    if db_write(do_create_building):
                        st.success(
                            f"Building {bcode} created under Phase {phase_code}. Refreshing."
                        )
                        st.rerun()
        return
    unit_number = st.text_input("Unit", key="add_avail_unit_number").strip()
    move_out_date = st.date_input(
        "Move out", key="add_avail_move_out", format="MM/DD/YYYY"
    )
    report_ready_date = st.date_input(
        "Ready date (optional)",
        value=None,
        key="add_avail_report_ready",
        format="MM/DD/YYYY",
    )
    move_in_date = st.date_input(
        "Move in (optional)", value=None, key="add_avail_move_in", format="MM/DD/YYYY"
    )
    if st.button("Add unit", key="add_avail_submit"):
        if not st.session_state.get("enable_db_writes"):
            st.error("Enable DB Writes in the sidebar to create a turnover.")
        elif not unit_number:
            st.error("Unit is required.")
        else:

            def do_add(conn):
                return create_turnover_workflow(
                    conn,
                    CreateTurnover(
                        property_id=property_id,
                        phase_code=phase_code,
                        building_code=building_code,
                        unit_number=unit_number,
                        move_out_date=move_out_date,
                        move_in_date=move_in_date if move_in_date else None,
                        report_ready_date=report_ready_date if report_ready_date else None,
                        today=date.today(),
                        actor=APP_SETTINGS.default_actor,
                    ),
                )

            if db_write(do_add):
                st.success(
                    "Turnover created. You can open it from the board or detail."
                )
                st.rerun()


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------
def _run_import_for_report(
    *,
    report_type: str,
    uploaded,
    active_property: dict,
) -> None:
    if uploaded is None:
        st.warning("Upload a file first.")
        return
    import tempfile

    db_path = get_db_path()
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name
    conn = get_conn()
    if not conn:
        st.error("Database not available")
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return
    try:
        result = apply_import_row_workflow(
            conn,
            ApplyImportRow(
                report_type=report_type,
                file_path=tmp_path,
                property_id=active_property["property_id"],
                db_path=db_path,
            ),
        )
        conn.commit()
        invalidate_ui_caches()
        status = result.get("status", "SUCCESS")
        batch_id = result.get("batch_id", "")
        record_count = result.get("record_count", 0)
        applied_count = result.get("applied_count", 0)
        conflict_count = result.get("conflict_count", 0)
        invalid_count = result.get("invalid_count", 0)
        diagnostics = result.get("diagnostics", []) or []
        if status == "NO_OP":
            st.info(
                f"No-op: file already imported (checksum match). "
                f"Batch ID: {batch_id} | Records: {record_count} | Applied: 0"
            )
        else:
            st.success(
                f"Batch ID: {batch_id} | Status: {status} | Records: {record_count} | "
                f"Applied: {applied_count} | Conflicts: {conflict_count} | Invalid: {invalid_count}"
            )
        if diagnostics:
            st.warning(f"Row diagnostics: {len(diagnostics)} issue(s)")
            for diag in diagnostics[:50]:
                row_label = (
                    f"Row {diag.get('row_index')}"
                    if diag.get("row_index") is not None
                    else "File"
                )
                column = diag.get("column")
                column_text = f" | Column: {column}" if column else ""
                msg = diag.get("error_message") or diag.get("reason") or "Import issue"
                suggestion = diag.get("suggestion")
                line = f"- {row_label}{column_text} | {msg}"
                if suggestion:
                    line += f" | Suggestion: {suggestion}"
                st.write(line)
            if len(diagnostics) > 50:
                st.caption(f"... and {len(diagnostics) - 50} more diagnostics.")

        try:
            rows = import_service_mod.get_import_rows_by_batch(conn, batch_id)
        except Exception:
            rows = []

        if not rows:
            return

        values: list[dict] = []
        for r in rows:
            try:
                raw = json.loads(r.get("raw_json") or "{}")
            except Exception:
                raw = {}

            base = {
                "validation_status": r.get("validation_status"),
                "conflict_flag": bool(r.get("conflict_flag")),
                "conflict_reason": r.get("conflict_reason"),
            }

            if report_type == "AVAILABLE_UNITS":
                base.update(
                    {
                        "Unit": raw.get("Unit"),
                        "Status": raw.get("Status"),
                        "Available Date": raw.get("Available Date"),
                        "Move-In Ready Date": raw.get("Move-In Ready Date"),
                    }
                )
            elif report_type == "MOVE_OUTS":
                base.update(
                    {
                        "Unit": raw.get("Unit"),
                        "Move-Out Date": raw.get("Move-Out Date"),
                    }
                )
            elif report_type == "PENDING_MOVE_INS":
                base.update(
                    {
                        "Unit": raw.get("Unit"),
                        "Move-In Date": raw.get("Move-In Date"),
                    }
                )
            elif report_type == "PENDING_FAS":
                base.update(
                    {
                        "Unit": raw.get("Unit"),
                        "MO / Cancel Date": raw.get("MO / Cancel Date"),
                    }
                )
            values.append(base)

        if values:
            if report_type == "AVAILABLE_UNITS":
                heading = "Available Units — Imported Rows"
            elif report_type == "MOVE_OUTS":
                heading = "Move Outs — Imported Rows"
            elif report_type == "PENDING_MOVE_INS":
                heading = "Pending Move-Ins — Imported Rows"
            elif report_type == "PENDING_FAS":
                heading = "FAS — Imported Rows"
            else:
                heading = "Imported Rows"
            st.markdown(f"### {heading}")
            st.dataframe(
                pd.DataFrame(values), use_container_width=True, hide_index=True
            )
    except Exception as e:
        conn.rollback()
        payload = e.to_dict() if hasattr(e, "to_dict") else None
        if isinstance(payload, dict) and payload.get("error_type") == "IMPORT_VALIDATION_FAILED":
            st.error(payload.get("message", "Import validation failed."))
            errors = payload.get("errors") or []
            if errors:
                st.warning(f"Validation diagnostics: {len(errors)} issue(s)")
                for diag in errors[:50]:
                    row_label = (
                        f"Row {diag.get('row_index')}"
                        if diag.get("row_index") is not None
                        else "File"
                    )
                    column = diag.get("column")
                    column_text = f" | Column: {column}" if column else ""
                    msg = diag.get("error_message") or "Validation issue"
                    suggestion = diag.get("suggestion")
                    line = f"- {row_label}{column_text} | {msg}"
                    if suggestion:
                        line += f" | Suggestion: {suggestion}"
                    st.write(line)
                if len(errors) > 50:
                    st.caption(f"... and {len(errors) - 50} more diagnostics.")
        else:
            st.error(str(e))
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Import console
# ---------------------------------------------------------------------------
def _render_import() -> None:
    st.subheader("Import console")
    if not import_service_mod:
        st.warning("Backend or import service not available.")
        if BACKEND_ERROR is not None:
            with st.expander("Details"):
                st.code(str(BACKEND_ERROR), language=None)
        return
    if not st.session_state.get("enable_db_writes"):
        st.warning("Enable **Enable DB Writes** in the sidebar to run import.")
        return
    active_property = render_active_property_banner()
    if active_property is None:
        return
    tab_available, tab_move_outs, tab_pending_move_ins, tab_fas = st.tabs(
        ["Available Units", "Move Outs", "Pending Move-Ins", "Final Account Statement (FAS)"]
    )

    with tab_available:
        uploaded_au = st.file_uploader(
            "Available Units.csv", key="import_file_available_units", type=["csv"]
        )
        if st.button("Run Available Units import", key="import_run_available_units"):
            _run_import_for_report(
                report_type="AVAILABLE_UNITS",
                uploaded=uploaded_au,
                active_property=active_property,
            )

    with tab_move_outs:
        uploaded_mo = st.file_uploader(
            "Move Outs.csv", key="import_file_move_outs", type=["csv"]
        )
        if st.button("Run Move Outs import", key="import_run_move_outs"):
            _run_import_for_report(
                report_type="MOVE_OUTS",
                uploaded=uploaded_mo,
                active_property=active_property,
            )

    with tab_pending_move_ins:
        uploaded_pmi = st.file_uploader(
            "Pending Move-Ins.csv",
            key="import_file_pending_move_ins",
            type=["csv"],
        )
        if st.button("Run Pending Move-Ins import", key="import_run_pending_move_ins"):
            _run_import_for_report(
                report_type="PENDING_MOVE_INS",
                uploaded=uploaded_pmi,
                active_property=active_property,
            )

    with tab_fas:
        uploaded_fas = st.file_uploader(
            "Pending FAS.csv", key="import_file_fas", type=["csv"]
        )
        if st.button("Run FAS import", key="import_run_fas"):
            _run_import_for_report(
                report_type="PENDING_FAS",
                uploaded=uploaded_fas,
                active_property=active_property,
            )

    st.subheader("Conflicts")
    st.caption(
        "Conflict details are recorded in import_row for the batch. "
        "List conflicts here when a batch is selected (future)."
    )


# ---------------------------------------------------------------------------
# Admin (tabbed page) — single render() entrypoint
# ---------------------------------------------------------------------------
def render() -> None:
    st.subheader("Admin")

    admin_col1, admin_col2, admin_col3 = st.columns([1.2, 1.6, 1.6])
    with admin_col1:
        st.checkbox(
            "Enable DB Writes (⚠ irreversible)",
            value=st.session_state.get("enable_db_writes", False),
            key="enable_db_writes",
            on_change=lambda: st.rerun(),
        )
    properties = cached_list_properties(db_cache_identity())
    active_property = sync_active_property(properties)
    with admin_col2:
        if properties:
            property_options = {}
            for p in properties:
                property_name = p.get("name") or f"Property {p['property_id']}"
                property_options[f"{property_name} (id={p['property_id']})"] = p
            active_label = next(
                (
                    label
                    for label, prop in property_options.items()
                    if prop["property_id"] == active_property["property_id"]
                ),
                next(iter(property_options)),
            )
            selected_label = st.selectbox(
                "Active Property",
                list(property_options.keys()),
                index=list(property_options.keys()).index(active_label),
                key="admin_active_property",
            )
            selected_property = property_options[selected_label]
            set_active_property(
                selected_property["property_id"],
                selected_property.get("name")
                or f"Property {selected_property['property_id']}",
            )
        else:
            st.caption("Create a property in the Admin tab to begin.")
    with admin_col3:
        new_property_name = st.text_input(
            "New Property",
            value="",
            key="admin_new_property_name",
            placeholder="Property name",
        )
        if st.button("Create Property", key="admin_create_property"):
            if not st.session_state.get("enable_db_writes"):
                st.error("Enable DB Writes in the Admin tab first.")
            elif not (new_property_name or "").strip():
                st.error("Enter a property name.")
            else:
                created = {"property_id": None}

                def do_create(conn):
                    created["property_id"] = property_service_mod.insert_property(
                        conn, (new_property_name or "").strip()
                    )

                if db_write(do_create):
                    property_id = created["property_id"]
                    property_name = (new_property_name or "").strip()
                    if property_id is None:
                        st.error(
                            "Property creation failed: no property_id was returned."
                        )
                    else:
                        set_active_property(property_id, property_name)
                        st.success(f"Active Property: {property_name}")
                        st.rerun()

    if st.session_state.get("enable_db_writes"):
        st.caption("DB writes are **on**. Edits and status changes will be persisted.")
    else:
        st.caption(
            "DB writes are **off**. You can browse and export; turn this on here to save changes."
        )
    if st.session_state.get("selected_property_id") is not None:
        st.caption(
            f"Active Property: {st.session_state.get('selected_property_name')}"
        )
    else:
        st.caption("Create a property in the Admin tab to begin.")

    tab_add, tab_import, tab_unit_master, tab_export, tab_dropdown = st.tabs(
        ["Add Unit", "Import", "Unit Master Import", "Exports", "Dropdown Manager"]
    )
    with tab_add:
        _render_add_availability()
    with tab_import:
        _render_import()
    with tab_unit_master:
        from ui.screens.unit_import import render as render_unit_master_import

        render_unit_master_import()
    with tab_export:
        from ui.screens.exports import render as render_exports

        render_exports()
    with tab_dropdown:
        _render_dropdown_manager()
