from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from db import repository
from domain.lifecycle import effective_move_out_date
from services import import_service
from services.risk_service import reconcile_risks_for_turnover
from services.sla_service import reconcile_sla_for_turnover


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _get_turnover(conn, turnover_id: int):
    row = repository.get_turnover_by_id(conn, turnover_id)
    if row is None:
        raise ValueError("Turnover not found")
    return row


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    s = str(value).strip()
    if len(s) < 10:
        raise ValueError("Date value too short for YYYY-MM-DD parse")
    return date.fromisoformat(s[:10])


def _task_row_to_risk_dict(row) -> Dict[str, Any]:
    vd = row["vendor_due_date"]
    vc = row["vendor_completed_at"]
    return {
        "task_type": row["task_type"],
        "required": bool(row["required"]),
        "blocking": bool(row["blocking"]),
        "vendor_due_date": _parse_iso_date(vd) if (vd and str(vd).strip()) else None,
        "vendor_completed_date": _parse_iso_date(vc) if (vc and str(vc).strip()) else None,
        "manager_confirmed_at": row["manager_confirmed_at"],
        "execution_status": row["execution_status"],
        "confirmation_status": row["confirmation_status"],
    }


def _audit(conn, turnover_id: int, field_name: str, old_value: Optional[str], new_value: Optional[str], actor: str, source: str) -> None:
    repository.insert_audit_log(
        conn,
        {
            "entity_type": "turnover",
            "entity_id": turnover_id,
            "field_name": field_name,
            "old_value": old_value,
            "new_value": new_value,
            "changed_at": _now_iso(),
            "actor": actor,
            "source": source,
            "correlation_id": None,
        },
    )


def create_turnover_and_reconcile(
    *,
    conn,
    unit_id: int,
    unit_row: Dict[str, Any],
    property_id: int,
    source_turnover_key: str,
    move_out_date: date,
    move_in_date: Optional[date] = None,
    report_ready_date: Optional[date] = None,
    today: date,
    actor: str = "manager",
) -> int:
    """
    Create one open turnover, instantiate tasks from templates, run SLA and risk reconciliation.
    Used by manual availability and any flow that creates a turnover without import.
    Caller must ensure unit has no open turnover. Returns turnover_id.
    """
    now_iso = _now_iso()
    move_out_iso = move_out_date.isoformat()
    move_in_iso = move_in_date.isoformat() if move_in_date else None
    report_ready_iso = report_ready_date.isoformat() if report_ready_date else None

    turnover_id = repository.insert_turnover(
        conn,
        {
            "property_id": property_id,
            "unit_id": unit_id,
            "source_turnover_key": source_turnover_key,
            "move_out_date": move_out_iso,
            "move_in_date": move_in_iso,
            "report_ready_date": report_ready_iso,
            "created_at": now_iso,
            "updated_at": now_iso,
            "last_seen_moveout_batch_id": None,
            "missing_moveout_count": 0,
        },
    )
    import_service.instantiate_tasks_for_turnover(conn, turnover_id, unit_row, property_id)
    _audit(conn, turnover_id, "created", None, "manual_availability", actor, "manual")

    reconcile_sla_for_turnover(
        conn=conn,
        turnover_id=turnover_id,
        move_out_date=move_out_date,
        manual_ready_confirmed_at=None,
        today=today,
        actor=actor,
        source="manual",
        correlation_id=None,
    )
    tasks_rows = repository.get_tasks_by_turnover(conn, turnover_id)
    tasks = [_task_row_to_risk_dict(r) for r in tasks_rows]
    reconcile_risks_for_turnover(
        conn=conn,
        turnover_id=turnover_id,
        move_in_date=move_in_date,
        move_out_date=move_out_date,
        today=today,
        tasks=tasks,
        wd_present=None,
        wd_supervisor_notified=None,
        has_data_integrity_conflict=False,
        has_duplicate_open_turnover=False,
        actor=actor,
    )
    return turnover_id


def reconcile_missing_tasks(conn) -> int:
    """
    Find open turnovers with zero tasks and instantiate default tasks from templates.
    Returns the number of turnovers that were backfilled.
    """
    rows = conn.execute(
        """SELECT t.turnover_id, t.unit_id, t.property_id
           FROM turnover t
           WHERE t.closed_at IS NULL AND t.canceled_at IS NULL
             AND NOT EXISTS (SELECT 1 FROM task tk WHERE tk.turnover_id = t.turnover_id)"""
    ).fetchall()
    count = 0
    for row in rows:
        turnover_id = row["turnover_id"]
        unit_id = row["unit_id"]
        property_id = row["property_id"]
        unit_row = repository.get_unit_by_id(conn, unit_id)
        if unit_row is None:
            continue
        unit_dict = dict(unit_row)
        import_service.instantiate_tasks_for_turnover(conn, turnover_id, unit_dict, property_id)
        count += 1
    return count


def set_manual_ready_status(
    *,
    conn,
    turnover_id: int,
    manual_ready_status: str,
    today: date,
    actor: str = "manager",
) -> None:
    row = _get_turnover(conn, turnover_id)
    old_status = row["manual_ready_status"]
    now_iso = _now_iso()
    repository.update_turnover_fields(
        conn,
        turnover_id,
        {"manual_ready_status": manual_ready_status, "status_manual_override_at": now_iso},
    )
    _audit(conn, turnover_id, "manual_ready_status", old_status, manual_ready_status, actor, "manual")
    _audit(conn, turnover_id, "manual_override_set", None, "manual_ready_status", actor, "manual")

    move_out_date = effective_move_out_date(dict(row))
    reconcile_sla_for_turnover(
        conn=conn,
        turnover_id=turnover_id,
        move_out_date=move_out_date,
        manual_ready_confirmed_at=row["manual_ready_confirmed_at"],
        today=today,
        actor=actor,
        source="manual",
        correlation_id=None,
    )

    tasks_rows = repository.get_tasks_by_turnover(conn, turnover_id)
    tasks = [_task_row_to_risk_dict(r) for r in tasks_rows]
    move_in_date = _parse_iso_date(row["move_in_date"])
    wd_present = None if row["wd_present"] is None else bool(row["wd_present"])
    wd_supervisor_notified = None if row["wd_supervisor_notified"] is None else bool(row["wd_supervisor_notified"])
    reconcile_risks_for_turnover(
        conn=conn,
        turnover_id=turnover_id,
        move_in_date=move_in_date,
        move_out_date=move_out_date,
        today=today,
        tasks=tasks,
        wd_present=wd_present,
        wd_supervisor_notified=wd_supervisor_notified,
        has_data_integrity_conflict=False,
        has_duplicate_open_turnover=False,
        actor=actor,
    )


def confirm_manual_ready(
    *,
    conn,
    turnover_id: int,
    today: date,
    actor: str = "manager",
) -> None:
    row = _get_turnover(conn, turnover_id)
    old_value = row["manual_ready_confirmed_at"]
    now_iso = _now_iso()
    repository.update_turnover_fields(
        conn,
        turnover_id,
        {"manual_ready_confirmed_at": now_iso},
    )
    _audit(conn, turnover_id, "manual_ready_confirmed_at", old_value, now_iso, actor, "manual")

    move_out_date = effective_move_out_date(dict(row))
    reconcile_sla_for_turnover(
        conn=conn,
        turnover_id=turnover_id,
        move_out_date=move_out_date,
        manual_ready_confirmed_at=now_iso,
        today=today,
        actor=actor,
        source="manual",
        correlation_id=None,
    )

    tasks_rows = repository.get_tasks_by_turnover(conn, turnover_id)
    tasks = [_task_row_to_risk_dict(r) for r in tasks_rows]
    move_in_date = _parse_iso_date(row["move_in_date"])
    wd_present = None if row["wd_present"] is None else bool(row["wd_present"])
    wd_supervisor_notified = None if row["wd_supervisor_notified"] is None else bool(row["wd_supervisor_notified"])
    reconcile_risks_for_turnover(
        conn=conn,
        turnover_id=turnover_id,
        move_in_date=move_in_date,
        move_out_date=move_out_date,
        today=today,
        tasks=tasks,
        wd_present=wd_present,
        wd_supervisor_notified=wd_supervisor_notified,
        has_data_integrity_conflict=False,
        has_duplicate_open_turnover=False,
        actor=actor,
    )


def update_wd_panel(
    *,
    conn,
    turnover_id: int,
    today: date,
    wd_present: Optional[bool] = None,
    wd_present_type: Optional[str] = None,
    wd_supervisor_notified: Optional[bool] = None,
    wd_installed: Optional[bool] = None,
    actor: str = "manager",
) -> None:
    row = _get_turnover(conn, turnover_id)
    now_iso = _now_iso()
    fields = {}
    if wd_present is not None:
        fields["wd_present"] = 1 if wd_present else 0
        if row["wd_present"] != fields["wd_present"]:
            _audit(conn, turnover_id, "wd_present", str(row["wd_present"]), str(fields["wd_present"]), actor, "manual")
    if wd_present_type is not None:
        fields["wd_present_type"] = wd_present_type
        if row.get("wd_present_type") != wd_present_type:
            _audit(conn, turnover_id, "wd_present_type", str(row.get("wd_present_type") or ""), wd_present_type, actor, "manual")
    if wd_supervisor_notified is not None:
        fields["wd_supervisor_notified"] = 1 if wd_supervisor_notified else 0
        if wd_supervisor_notified:
            fields["wd_notified_at"] = now_iso
        _audit(conn, turnover_id, "wd_supervisor_notified", str(row["wd_supervisor_notified"]), str(fields["wd_supervisor_notified"]), actor, "manual")
    if wd_installed is not None:
        old_installed = row["wd_installed"]
        fields["wd_installed"] = 1 if wd_installed else 0
        if wd_installed and not old_installed:
            fields["wd_installed_at"] = now_iso
        _audit(conn, turnover_id, "wd_installed", str(old_installed), str(fields["wd_installed"]), actor, "manual")
    if fields:
        repository.update_turnover_fields(conn, turnover_id, fields)

    tasks_rows = repository.get_tasks_by_turnover(conn, turnover_id)
    tasks = [_task_row_to_risk_dict(r) for r in tasks_rows]
    move_in_date = _parse_iso_date(row["move_in_date"])
    move_out_date = _parse_iso_date(row["move_out_date"])
    wd_present_val = None if row["wd_present"] is None else bool(row["wd_present"])
    wd_supervisor_notified_val = None if row["wd_supervisor_notified"] is None else bool(row["wd_supervisor_notified"])
    if wd_present is not None:
        wd_present_val = wd_present
    if wd_supervisor_notified is not None:
        wd_supervisor_notified_val = wd_supervisor_notified
    reconcile_risks_for_turnover(
        conn=conn,
        turnover_id=turnover_id,
        move_in_date=move_in_date,
        move_out_date=move_out_date,
        today=today,
        tasks=tasks,
        wd_present=wd_present_val,
        wd_supervisor_notified=wd_supervisor_notified_val,
        has_data_integrity_conflict=False,
        has_duplicate_open_turnover=False,
        actor=actor,
    )


def update_turnover_dates(
    *,
    conn,
    turnover_id: int,
    move_out_date: Optional[date] = None,
    report_ready_date: Optional[date] = None,
    move_in_date: Optional[date] = None,
    today: Optional[date] = None,
    actor: str = "manager",
) -> None:
    """Update turnover date fields; audit each change; always run SLA and risk reconciliation."""
    row = _get_turnover(conn, turnover_id)
    if today is None:
        today = date.today()
    now_iso = _now_iso()
    old_anchor = effective_move_out_date(dict(row))
    fields = {}
    if move_out_date is not None:
        mo_str = move_out_date.isoformat() if hasattr(move_out_date, "isoformat") else str(move_out_date)[:10]
        cur_mo = _parse_iso_date(row["move_out_date"])
        if cur_mo != move_out_date and str(row["move_out_date"]) != mo_str:
            fields["move_out_date"] = mo_str
            fields["move_out_manual_override_at"] = now_iso
            _audit(conn, turnover_id, "move_out_date", str(row["move_out_date"]), mo_str, actor, "manual")
            _audit(conn, turnover_id, "manual_override_set", None, "move_out_date", actor, "manual")
    if report_ready_date is not None:
        rr_str = report_ready_date.isoformat() if hasattr(report_ready_date, "isoformat") else str(report_ready_date)[:10]
        old_rr = str(row["report_ready_date"]) if row["report_ready_date"] else None
        if old_rr != rr_str:
            fields["report_ready_date"] = rr_str
            fields["ready_manual_override_at"] = now_iso
            _audit(conn, turnover_id, "report_ready_date", old_rr, rr_str, actor, "manual")
            _audit(conn, turnover_id, "manual_override_set", None, "report_ready_date", actor, "manual")
    if move_in_date is not None:
        mi_str = move_in_date.isoformat() if hasattr(move_in_date, "isoformat") else str(move_in_date)[:10]
        old_mi = str(row["move_in_date"]) if row["move_in_date"] else None
        if old_mi != mi_str:
            fields["move_in_date"] = mi_str
            fields["move_in_manual_override_at"] = now_iso
            _audit(conn, turnover_id, "move_in_date", old_mi, mi_str, actor, "manual")
            _audit(conn, turnover_id, "manual_override_set", None, "move_in_date", actor, "manual")

    if not fields:
        return
    repository.update_turnover_fields(conn, turnover_id, fields)

    # Effective dates after update
    mo_eff = _parse_iso_date(fields.get("move_out_date", row["move_out_date"]) or row["move_out_date"])
    mi_eff = _parse_iso_date(fields.get("move_in_date", row["move_in_date"]) or row["move_in_date"])
    row_eff = dict(row)
    row_eff.update(fields)
    new_anchor = effective_move_out_date(row_eff)

    reconcile_sla_for_turnover(
        conn=conn,
        turnover_id=turnover_id,
        move_out_date=new_anchor,
        manual_ready_confirmed_at=row_eff.get("manual_ready_confirmed_at"),
        today=today,
        actor=actor,
        source="manual",
        correlation_id=None,
        previous_effective_move_out_date=old_anchor,
    )
    tasks_rows = repository.get_tasks_by_turnover(conn, turnover_id)
    tasks = [_task_row_to_risk_dict(r) for r in tasks_rows]
    wd_present = None if row_eff.get("wd_present") is None else bool(row_eff.get("wd_present"))
    wd_supervisor_notified = None if row_eff.get("wd_supervisor_notified") is None else bool(row_eff.get("wd_supervisor_notified"))
    reconcile_risks_for_turnover(
        conn=conn,
        turnover_id=turnover_id,
        move_in_date=mi_eff,
        move_out_date=mo_eff,
        today=today,
        tasks=tasks,
        wd_present=wd_present,
        wd_supervisor_notified=wd_supervisor_notified,
        has_data_integrity_conflict=False,
        has_duplicate_open_turnover=False,
        actor=actor,
    )


def reconcile_after_task_change(
    *,
    conn,
    turnover_id: int,
    today: date,
    actor: str = "system",
) -> None:
    """Called by task_service after mark/confirm/reject to reconcile risks and SLA."""
    row = _get_turnover(conn, turnover_id)
    tasks_rows = repository.get_tasks_by_turnover(conn, turnover_id)
    tasks = [_task_row_to_risk_dict(r) for r in tasks_rows]
    move_in_date = _parse_iso_date(row["move_in_date"])
    move_out_date = _parse_iso_date(row["move_out_date"])
    wd_present = None if row["wd_present"] is None else bool(row["wd_present"])
    wd_supervisor_notified = None if row["wd_supervisor_notified"] is None else bool(row["wd_supervisor_notified"])
    reconcile_risks_for_turnover(
        conn=conn,
        turnover_id=turnover_id,
        move_in_date=move_in_date,
        move_out_date=move_out_date,
        today=today,
        tasks=tasks,
        wd_present=wd_present,
        wd_supervisor_notified=wd_supervisor_notified,
        has_data_integrity_conflict=False,
        has_duplicate_open_turnover=False,
        actor=actor,
    )


def attempt_auto_close(
    *,
    conn,
    turnover_id: int,
    today: date,
    actor: str = "system",
) -> None:
    row = _get_turnover(conn, turnover_id)
    if row["closed_at"] is not None or row["canceled_at"] is not None:
        return
    move_in_date = _parse_iso_date(row["move_in_date"])
    if move_in_date is None:
        return
    if today <= move_in_date + timedelta(days=14):
        return
    active_risks = repository.get_active_risks_by_turnover(conn, turnover_id)
    if any(r["severity"] == "CRITICAL" for r in active_risks):
        return
    now_iso = _now_iso()
    repository.update_turnover_fields(conn, turnover_id, {"closed_at": now_iso})
    _audit(conn, turnover_id, "closed_at", None, now_iso, actor, "system")
