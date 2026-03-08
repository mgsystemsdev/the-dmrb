"""
Board query service: load turnovers/units/tasks/notes via repository, build flat rows, enrich, filter, sort.
Uses domain.enrichment only; no Streamlit. Returns list[dict] for DMRB board, flag bridge, and turnover detail.
"""
from datetime import date
from typing import Any, Optional

from db import repository
from domain import enrichment


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _row_to_dict(row) -> dict | None:
    """Convert sqlite3.Row to dict; None -> None."""
    if row is None:
        return None
    return dict(row)


def _parse_unit_code(unit_code_raw: Optional[str]) -> tuple[str, str]:
    """Return (building, unit_number). Mirrors mock_data_v2.parse_unit_code."""
    if not unit_code_raw or not (unit_code_raw or "").strip():
        return ("", "")
    parts = (unit_code_raw or "").strip().split("-")
    if len(parts) >= 3:
        return (parts[1], parts[2])
    if len(parts) == 2:
        return ("", parts[1])
    return ("", parts[0] if parts else "")


def _unit_display_code(unit: dict) -> str:
    """Unit display string: phase_code-building_code-unit_number from table, else unit_code_raw/norm."""
    pc = unit.get("phase_code") or ""
    bc = unit.get("building_code") or ""
    un = unit.get("unit_number") or ""
    if pc or bc or un:
        return f"{pc}-{bc}-{un}".strip("-") or (unit.get("unit_code_raw") or unit.get("unit_code_norm") or "")
    return unit.get("unit_code_raw") or unit.get("unit_code_norm") or ""


def _build_flat_row(
    turnover: dict,
    unit: dict,
    tasks_for_turnover: list[dict],
    notes_for_turnover: list[dict],
) -> dict:
    """Build one flat dict per turnover with task_insp..task_qc and notes_text. Mirrors mock_data_v2.build_flat_row."""
    turnover_id = turnover["turnover_id"]
    unit_code = _unit_display_code(unit)
    # Prefer phase_code, building_code, unit_number from unit (post-004/007); fallback parse
    building = unit.get("building_code")
    unit_number = unit.get("unit_number")
    if building is None or unit_number is None:
        building, unit_number = _parse_unit_code(unit.get("unit_code_raw"))
    building = building or ""
    unit_number = unit_number or ""

    task_by_type = {t["task_type"]: t for t in tasks_for_turnover if t.get("turnover_id") == turnover_id}
    task_insp = task_by_type.get("Insp", {})
    task_paint = task_by_type.get("Paint", {})
    task_mr = task_by_type.get("MR", {})
    task_hk = task_by_type.get("HK", {})
    task_cc = task_by_type.get("CC", {})
    task_cb = task_by_type.get("CB", {})
    task_mrb = task_by_type.get("MRB", {})
    task_fw = task_by_type.get("FW", {})
    task_qc = task_by_type.get("QC", {})

    notes_text = " ".join(
        (n.get("description") or "") for n in notes_for_turnover if n.get("description")
    ).strip() or ""

    return {
        "turnover_id": turnover_id,
        "unit_id": unit.get("unit_id"),
        "unit_code": unit_code,
        "property_id": unit.get("property_id"),
        "phase_id": unit.get("phase_id"),
        "phase_code": unit.get("phase_code") or "",
        "building": building,
        "unit_number": unit_number,
        "move_out_date": turnover.get("move_out_date"),
        "move_in_date": turnover.get("move_in_date"),
        "report_ready_date": turnover.get("report_ready_date"),
        "scheduled_move_out_date": turnover.get("scheduled_move_out_date"),
        "confirmed_move_out_date": turnover.get("confirmed_move_out_date"),
        "legal_confirmation_source": turnover.get("legal_confirmation_source"),
        "legal_confirmed_at": turnover.get("legal_confirmed_at"),
        "manual_ready_status": turnover.get("manual_ready_status") or "Vacant not ready",
        "move_out_manual_override_at": turnover.get("move_out_manual_override_at"),
        "ready_manual_override_at": turnover.get("ready_manual_override_at"),
        "move_in_manual_override_at": turnover.get("move_in_manual_override_at"),
        "status_manual_override_at": turnover.get("status_manual_override_at"),
        "last_import_move_out_date": turnover.get("last_import_move_out_date"),
        "last_import_ready_date": turnover.get("last_import_ready_date"),
        "last_import_move_in_date": turnover.get("last_import_move_in_date"),
        "last_import_status": turnover.get("last_import_status"),
        "closed_at": turnover.get("closed_at"),
        "canceled_at": turnover.get("canceled_at"),
        "wd_present": turnover.get("wd_present") or 0,
        "wd_supervisor_notified": turnover.get("wd_supervisor_notified") or 0,
        "wd_installed": turnover.get("wd_installed") or 0,
        "task_insp": task_insp,
        "task_paint": task_paint,
        "task_mr": task_mr,
        "task_hk": task_hk,
        "task_cc": task_cc,
        "task_cb": task_cb,
        "task_mrb": task_mrb,
        "task_fw": task_fw,
        "task_qc": task_qc,
        "notes_text": notes_text,
    }


# Bridge filter label -> row key (for get_flag_bridge_rows)
BRIDGE_MAP = {
    "All": None,
    "Insp Breach": "inspection_sla_breach",
    "SLA Breach": "sla_breach",
    "SLA MI Breach": "sla_movein_breach",
    "Plan Bridge": "plan_breach",
}


def get_dmrb_board_rows(
    conn,
    *,
    property_ids: Optional[list[int]] = None,
    phase_ids: Optional[list[int]] = None,
    search_unit: Optional[str] = None,
    filter_phase: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_nvm: Optional[str] = None,
    filter_assignee: Optional[str] = None,
    filter_qc: Optional[str] = None,
    today: Optional[date] = None,
) -> list[dict]:
    """
    Load open turnovers, batch units/tasks/notes, build flat rows, enrich, filter, sort.
    phase_ids: filter by unit.phase_id (preferred when hierarchy present).
    property_ids: filter by turnover.property_id when phase_ids not set.
    filter_phase: legacy property_id as string ("5", "7", "8") for in-memory filter when not using phase_ids.
    """
    today = today or date.today()
    if phase_ids is not None:
        turnovers = repository.list_open_turnovers(conn, phase_ids=phase_ids)
    else:
        turnovers = repository.list_open_turnovers(conn, property_ids=property_ids)
    if not turnovers:
        return []
    turnovers = [_row_to_dict(r) for r in turnovers]
    turnover_ids = [t["turnover_id"] for t in turnovers]
    unit_ids = list(dict.fromkeys(t["unit_id"] for t in turnovers if t.get("unit_id") is not None))

    units = repository.get_units_by_ids(conn, unit_ids)
    units = [_row_to_dict(r) for r in units]
    unit_by_id = {u["unit_id"]: u for u in units}

    tasks = repository.get_tasks_for_turnover_ids(conn, turnover_ids)
    tasks = [_row_to_dict(r) for r in tasks]
    tasks_by_tid: dict[int, list[dict]] = {}
    for t in tasks:
        tid = t.get("turnover_id")
        if tid is not None:
            tasks_by_tid.setdefault(tid, []).append(t)

    notes = repository.get_notes_for_turnover_ids(conn, turnover_ids, unresolved_only=True)
    notes = [_row_to_dict(r) for r in notes]
    notes_by_tid: dict[int, list[dict]] = {}
    for n in notes:
        tid = n.get("turnover_id")
        if tid is not None:
            notes_by_tid.setdefault(tid, []).append(n)

    rows = []
    for t in turnovers:
        u = unit_by_id.get(t["unit_id"])
        if not u:
            continue
        unit_code = _unit_display_code(u)
        if search_unit and search_unit.strip():
            if search_unit.strip().lower() not in (unit_code or "").lower():
                continue
        if filter_phase and filter_phase != "All" and phase_ids is None:
            if str(u.get("property_id")) != str(filter_phase):
                continue

        tasks_for_t = tasks_by_tid.get(t["turnover_id"], [])
        notes_for_t = notes_by_tid.get(t["turnover_id"], [])
        row = _build_flat_row(t, u, tasks_for_t, notes_for_t)
        row = enrichment.enrich_row(row, today)

        if filter_status and filter_status != "All":
            if (row.get("manual_ready_status") or "") != filter_status:
                continue
        if filter_nvm and filter_nvm != "All":
            if (row.get("nvm") or "") != filter_nvm:
                continue
        if filter_assignee and filter_assignee != "All":
            assignees = set()
            for key in ("task_insp", "task_cb", "task_mrb", "task_paint", "task_mr", "task_hk", "task_cc", "task_fw", "task_qc"):
                task = row.get(key) or {}
                a = (task.get("assignee") or "").strip()
                if a:
                    assignees.add(a)
            if filter_assignee not in assignees:
                continue
        if filter_qc and filter_qc != "All":
            qc_done = row.get("is_qc_done")
            if filter_qc == "QC Done" and not qc_done:
                continue
            if filter_qc == "QC Not done" and qc_done:
                continue

        rows.append(row)

    def _sort_move_in(r: dict):
        move_in = _parse_date(r.get("move_in_date"))
        dv = r.get("dv") or 0
        return (0 if move_in is None else 1, move_in or date.max, -dv)

    rows.sort(key=_sort_move_in)
    return rows


def get_flag_bridge_rows(
    conn,
    *,
    property_ids: Optional[list[int]] = None,
    phase_ids: Optional[list[int]] = None,
    search_unit: Optional[str] = None,
    filter_phase: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_nvm: Optional[str] = None,
    filter_assignee: Optional[str] = None,
    filter_qc: Optional[str] = None,
    breach_filter: Optional[str] = None,
    breach_value: Optional[str] = None,
    today: Optional[date] = None,
) -> list[dict]:
    """Same as get_dmrb_board_rows with optional breach_filter (BRIDGE_MAP key) and breach_value (All/Yes/No)."""
    rows = get_dmrb_board_rows(
        conn,
        property_ids=property_ids,
        phase_ids=phase_ids,
        search_unit=search_unit,
        filter_phase=filter_phase,
        filter_status=filter_status,
        filter_nvm=filter_nvm,
        filter_assignee=filter_assignee,
        filter_qc=filter_qc,
        today=today,
    )
    if not breach_filter or breach_filter == "All" or not breach_value or breach_value == "All":
        return rows
    key = BRIDGE_MAP.get(breach_filter)
    if key is None:
        return rows
    want_true = breach_value == "Yes"
    return [r for r in rows if (r.get(key) is True) == want_true]


def get_turnover_detail(
    conn,
    turnover_id: int,
    *,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """
    Return {turnover, unit, tasks, notes, risks, enriched_fields}.
    enriched_fields is the enriched flat row (single turnover) for dv, nvm, operational_state, etc.
    """
    today = today or date.today()
    turnover_row = repository.get_turnover_by_id(conn, turnover_id)
    if turnover_row is None:
        return {}
    turnover = _row_to_dict(turnover_row)
    unit_id = turnover.get("unit_id")
    if unit_id is None:
        return {"turnover": turnover, "unit": None, "tasks": [], "notes": [], "risks": [], "enriched_fields": {}}
    unit_row = repository.get_unit_by_id(conn, unit_id)
    unit = _row_to_dict(unit_row) if unit_row else None
    tasks = repository.get_tasks_by_turnover(conn, turnover_id)
    tasks = [_row_to_dict(r) for r in tasks]
    notes = repository.get_notes_by_turnover(conn, turnover_id)
    notes = [_row_to_dict(r) for r in notes]
    notes_unresolved = [n for n in notes if not n.get("resolved_at")]
    risks = repository.get_active_risks_by_turnover(conn, turnover_id)
    risks = [_row_to_dict(r) for r in risks]

    enriched_fields = {}
    if unit:
        flat = _build_flat_row(turnover, unit, tasks, notes_unresolved)
        enriched_row = enrichment.enrich_row(flat, today)
        enriched_fields = enriched_row

    return {
        "turnover": turnover,
        "unit": unit,
        "tasks": tasks,
        "notes": notes,
        "risks": risks,
        "enriched_fields": enriched_fields,
    }
