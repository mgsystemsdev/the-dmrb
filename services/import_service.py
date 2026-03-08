"""
Deterministic, idempotent import orchestrator for Turnover Cockpit v1.
Caller owns connection and transaction; this module does not commit.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from typing import Any, Optional

import pandas as pd

from db import connection as db_connection
from db import repository
from domain.lifecycle import effective_move_out_date
from domain import unit_identity
from services.sla_service import reconcile_sla_for_turnover

# Report type constants (exact strings for v1)
MOVE_OUTS = "MOVE_OUTS"
PENDING_MOVE_INS = "PENDING_MOVE_INS"
AVAILABLE_UNITS = "AVAILABLE_UNITS"
PENDING_FAS = "PENDING_FAS"
DMRB = "DMRB"

VALID_PHASES = (5, 7, 8)


def _sha256_file(report_type: str, file_path: str) -> str:
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    payload = (report_type + "\n").encode() + file_bytes
    return hashlib.sha256(payload).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_iso_date(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d is not None else None


def _normalize_date_str(s: Optional[str]) -> Optional[str]:
    """Normalize to YYYY-MM-DD for comparison; None and empty -> None."""
    if not s or not str(s).strip():
        return None
    return str(s).strip()[:10]


def _normalize_status(s: Optional[str]) -> Optional[str]:
    """Normalize status for comparison; None and empty -> None; strip and lowercase."""
    if s is None:
        return None
    t = str(s).strip()
    return t.lower() if t else None


def _row_to_dict(r) -> Optional[dict]:
    """Convert sqlite3.Row to dict so .get() works; None stays None."""
    if r is None:
        return None
    return dict(r)


def _normalize_unit(raw: str) -> tuple[str, str]:
    """Return (raw_clean, unit_code_norm) using canonical normalizer."""
    raw_clean = raw.strip()
    unit_code_norm = unit_identity.normalize_unit_code(raw)
    return (raw_clean, unit_code_norm)


def _phase_from_norm(unit_norm: str) -> Optional[int]:
    if not unit_norm:
        return None
    parts = unit_norm.split("-")
    if not parts:
        return None
    try:
        return int(parts[0].strip())
    except (ValueError, TypeError):
        return None


def _filter_phase(rows: list[dict]) -> list[dict]:
    return [r for r in rows if _phase_from_norm(r.get("unit_norm") or "") in VALID_PHASES]


def _parse_move_outs(file_path: str) -> list[dict]:
    df = pd.read_csv(file_path, skiprows=6)
    df = df[["Unit", "Move-Out Date"]].copy()
    rows = []
    for _, r in df.iterrows():
        raw = str(r["Unit"]) if pd.notna(r["Unit"]) else ""
        unit_raw, unit_norm = _normalize_unit(raw)
        dt = pd.to_datetime(r["Move-Out Date"], errors="coerce")
        move_out_date = dt.date() if pd.notna(dt) and hasattr(dt, "date") else None
        raw_json = json.dumps({"Unit": raw, "Move-Out Date": r["Move-Out Date"]})
        rows.append({
            "unit_raw": unit_raw,
            "unit_norm": unit_norm,
            "move_out_date": move_out_date,
            "raw_json": raw_json,
        })
    return _filter_phase(rows)


def _parse_pending_move_ins(file_path: str) -> list[dict]:
    df = pd.read_csv(file_path, skiprows=5)
    df = df[["Unit", "Move In Date"]].copy()
    rows = []
    for _, r in df.iterrows():
        raw = str(r["Unit"]) if pd.notna(r["Unit"]) else ""
        unit_raw, unit_norm = _normalize_unit(raw)
        dt = pd.to_datetime(r["Move In Date"], errors="coerce")
        move_in_date = dt.date() if pd.notna(dt) and hasattr(dt, "date") else None
        raw_json = json.dumps({"Unit": raw, "Move In Date": r["Move In Date"]})
        rows.append({
            "unit_raw": unit_raw,
            "unit_norm": unit_norm,
            "move_in_date": move_in_date,
            "raw_json": raw_json,
        })
    return _filter_phase(rows)


def _parse_available_units(file_path: str) -> list[dict]:
    df = pd.read_csv(file_path, skiprows=5)
    df = df[["Unit", "Status", "Available Date", "Move-In Ready Date"]].copy()
    rows = []
    for _, r in df.iterrows():
        raw = str(r["Unit"]) if pd.notna(r["Unit"]) else ""
        unit_raw, unit_norm = _normalize_unit(raw)
        dt = pd.to_datetime(r["Move-In Ready Date"], errors="coerce")
        report_ready_date = dt.date() if pd.notna(dt) and hasattr(dt, "date") else None
        status = str(r["Status"]).strip() if pd.notna(r["Status"]) else None
        raw_json = json.dumps({
            "Unit": raw,
            "Status": r["Status"],
            "Available Date": r["Available Date"],
            "Move-In Ready Date": r["Move-In Ready Date"],
        })
        rows.append({
            "unit_raw": unit_raw,
            "unit_norm": unit_norm,
            "report_ready_date": report_ready_date,
            "status": status,
            "raw_json": raw_json,
        })
    return _filter_phase(rows)


def _parse_pending_fas(file_path: str) -> list[dict]:
    # Standard report has 4 header lines; if file has fewer lines, use first line as header
    try:
        df = pd.read_csv(file_path, skiprows=4)
    except pd.errors.EmptyDataError:
        df = pd.read_csv(file_path)
    if df.empty or len(df.columns) == 0:
        df = pd.read_csv(file_path)
    if df.empty or len(df.columns) == 0:
        return []
    df = df.rename(columns={"Unit Number": "Unit"})
    df = df[["Unit", "MO / Cancel Date"]].copy()
    rows = []
    for _, r in df.iterrows():
        raw = str(r["Unit"]) if pd.notna(r["Unit"]) else ""
        unit_raw, unit_norm = _normalize_unit(raw)
        dt = pd.to_datetime(r["MO / Cancel Date"], errors="coerce")
        mo_cancel_date = dt.date() if pd.notna(dt) and hasattr(dt, "date") else None
        raw_json = json.dumps({"Unit": raw, "MO / Cancel Date": r["MO / Cancel Date"]})
        rows.append({
            "unit_raw": unit_raw,
            "unit_norm": unit_norm,
            "mo_cancel_date": mo_cancel_date,
            "raw_json": raw_json,
        })
    return _filter_phase(rows)


def _parse_dmrb(file_path: str) -> list[dict]:
    df = pd.read_excel(file_path, sheet_name="DMRB ")
    df.columns = df.columns.str.strip()
    df = df[["Unit", "Ready_Date", "Move_out", "Move_in", "Status"]].copy()
    df["Unit"] = df["Unit"].astype(str).str.strip()
    seen_norm = set()
    rows = []
    for _, r in df.iterrows():
        raw = str(r["Unit"]) if pd.notna(r["Unit"]) else ""
        unit_raw, unit_norm = _normalize_unit(raw)
        if unit_norm in seen_norm:
            continue
        seen_norm.add(unit_norm)
        dt = pd.to_datetime(r["Ready_Date"], errors="coerce")
        report_ready_date = dt.date() if pd.notna(dt) and hasattr(dt, "date") else None
        raw_json = json.dumps({
            "Unit": raw,
            "Ready_Date": str(r["Ready_Date"]) if pd.notna(r["Ready_Date"]) else None,
            "Move_out": str(r["Move_out"]) if pd.notna(r["Move_out"]) else None,
            "Move_in": str(r["Move_in"]) if pd.notna(r["Move_in"]) else None,
            "Status": str(r["Status"]) if pd.notna(r["Status"]) else None,
        })
        rows.append({
            "unit_raw": unit_raw,
            "unit_norm": unit_norm,
            "report_ready_date": report_ready_date,
            "raw_json": raw_json,
        })
    return _filter_phase(rows)


def _ensure_unit(conn, property_id: int, unit_raw: str, unit_norm: str):
    """Get or create unit via hierarchy resolver (property → phase → building → unit)."""
    phase_code, building_code, unit_number = unit_identity.parse_unit_parts(unit_norm)
    unit_identity_key = unit_identity.compose_identity_key(phase_code, building_code, unit_number)
    row = repository.resolve_unit(
        conn,
        property_id=property_id,
        phase_code=phase_code,
        building_code=building_code,
        unit_number=unit_number,
        unit_code_raw=unit_raw,
        unit_code_norm=unit_norm,
        unit_identity_key=unit_identity_key,
    )
    # Keep unit_code_raw up to date when row existed
    repository.update_unit_fields(conn, row["unit_id"], {"unit_code_raw": unit_raw})
    return _row_to_dict(repository.get_unit_by_id(conn, row["unit_id"]))


def _write_import_row(
    conn,
    batch_id: int,
    row: dict,
    validation_status: str,
    conflict_flag: int = 0,
    conflict_reason: Optional[str] = None,
    move_out_date: Optional[str] = None,
    move_in_date: Optional[str] = None,
) -> None:
    repository.insert_import_row(conn, {
        "batch_id": batch_id,
        "raw_json": row["raw_json"],
        "unit_code_raw": row["unit_raw"],
        "unit_code_norm": row["unit_norm"],
        "move_out_date": move_out_date,
        "move_in_date": move_in_date,
        "validation_status": validation_status,
        "conflict_flag": conflict_flag,
        "conflict_reason": conflict_reason,
    })


def _audit(
    conn,
    turnover_id: int,
    field_name: str,
    old_value: Optional[str],
    new_value: Optional[str],
    actor: str,
    correlation_id: str,
) -> None:
    repository.insert_audit_log(conn, {
        "entity_type": "turnover",
        "entity_id": turnover_id,
        "field_name": field_name,
        "old_value": old_value,
        "new_value": new_value,
        "changed_at": _now_iso(),
        "actor": actor,
        "source": "import",
        "correlation_id": correlation_id,
    })


def _get_last_skipped_value(conn, turnover_id: int, field_key: str):
    """Return the normalized value from the most recent import_skipped_due_to_manual_override audit for this turnover and field. new_value format: field|report=REPORT|v=value."""
    cursor = conn.execute(
        """SELECT new_value FROM audit_log
           WHERE entity_type = 'turnover' AND entity_id = ? AND field_name = 'import_skipped_due_to_manual_override'
             AND new_value LIKE ?
           ORDER BY audit_id DESC LIMIT 1""",
        (turnover_id, field_key + "|%"),
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        return None
    new_value = row[0]
    if "|v=" in new_value:
        return new_value.split("|v=", 1)[1]
    return None


def _write_skip_audit_if_new(
    conn,
    turnover_id: int,
    field_key: str,
    report_type: str,
    normalized_value: Optional[str],
    actor: str,
    correlation_id: str,
) -> None:
    """Write import_skipped_due_to_manual_override only when the last skip for this field was not for the same normalized value."""
    last_val = _get_last_skipped_value(conn, turnover_id, field_key)
    current = normalized_value if normalized_value is not None else ""
    if last_val is not None and last_val == current:
        return
    new_value = f"{field_key}|report={report_type}|v={current}"
    _audit(conn, turnover_id, "import_skipped_due_to_manual_override", None, new_value, actor, correlation_id)


def _apply_template_filter(template_row, unit_row) -> bool:
    ac = template_row["applies_if_has_carpet"] if "applies_if_has_carpet" in template_row.keys() else None
    if ac is not None and ac != "":
        if int(ac) != int(unit_row.get("has_carpet") or 0):
            return False
    aw = template_row["applies_if_has_wd_expected"] if "applies_if_has_wd_expected" in template_row.keys() else None
    if aw is not None and aw != "":
        if int(aw) != int(unit_row.get("has_wd_expected") or 0):
            return False
    return True


def instantiate_tasks_for_turnover(conn, turnover_id: int, unit_row, property_id: int) -> None:
    """
    Create tasks for a turnover from active task templates (by phase or property).
    Same logic as import; used by manual availability and turnover creation.
    unit_row must have phase_id (optional) and fields used by template filter (e.g. has_wd_expected, unit_code_norm).
    """
    _instantiate_tasks_for_turnover_impl(conn, turnover_id, unit_row, property_id)


def _instantiate_tasks_for_turnover_impl(conn, turnover_id: int, unit_row, property_id: int) -> None:
    """Use phase_id from unit when present (post-007), else resolve first phase for property so
    task templates work on post-008 DBs (task_template has phase_id only). If the phase (or
    property) has no templates, ensure default templates so the turnover gets tasks as soon as
    it has a move-out date."""
    phase_id = unit_row.get("phase_id")
    if phase_id is None:
        phase_row = repository.get_first_phase_for_property(conn, property_id)
        if phase_row is not None:
            phase_id = phase_row["phase_id"]
    if phase_id is not None:
        repository.ensure_default_task_templates(conn, phase_id=phase_id)
        templates = repository.get_active_task_templates_by_phase(conn, phase_id=phase_id)
    else:
        repository.ensure_default_task_templates(conn, property_id=property_id)
        templates = repository.get_active_task_templates(conn, property_id=property_id)
    included = [t for t in templates if _apply_template_filter(t, unit_row)]
    template_id_to_task_id: dict[int, int] = {}
    for t in included:
        task_id = repository.insert_task(conn, {
            "turnover_id": turnover_id,
            "task_type": t["task_type"],
            "required": t["required"],
            "blocking": t["blocking"],
            "scheduled_date": None,
            "vendor_due_date": None,
            "vendor_completed_at": None,
            "manager_confirmed_at": None,
            "execution_status": "NOT_STARTED",
            "confirmation_status": "PENDING",
        })
        template_id_to_task_id[t["template_id"]] = task_id
    if not included:
        return
    template_ids = [t["template_id"] for t in included]
    deps = repository.get_task_template_dependencies(conn, template_ids=template_ids)
    for dep in deps:
        tid = dep["template_id"]
        dep_tid = dep["depends_on_template_id"]
        if tid in template_id_to_task_id and dep_tid in template_id_to_task_id:
            repository.insert_task_dependency(conn, {
                "task_id": template_id_to_task_id[tid],
                "depends_on_task_id": template_id_to_task_id[dep_tid],
            })


def import_report_file(
    *,
    conn,
    report_type: str,
    file_path: str,
    property_id: int = 1,
    actor: str = "manager",
    correlation_id: Optional[str] = None,
    db_path: Optional[str] = None,
    backup_dir: Optional[str] = None,
    today: Optional[date] = None,
) -> dict:
    if today is None:
        today = date.today()
    source_file_name = os.path.basename(file_path)
    checksum = _sha256_file(report_type, file_path)

    existing = repository.get_import_batch_by_checksum(conn, checksum)
    if existing is not None:
        return {
            "report_type": report_type,
            "checksum": checksum,
            "status": "NO_OP",
            "batch_id": existing["batch_id"],
            "record_count": 0,
            "applied_count": 0,
            "conflict_count": 0,
            "invalid_count": 0,
        }

    try:
        if report_type == MOVE_OUTS:
            rows = _parse_move_outs(file_path)
        elif report_type == PENDING_MOVE_INS:
            rows = _parse_pending_move_ins(file_path)
        elif report_type == AVAILABLE_UNITS:
            rows = _parse_available_units(file_path)
        elif report_type == PENDING_FAS:
            rows = _parse_pending_fas(file_path)
        elif report_type == DMRB:
            rows = _parse_dmrb(file_path)
        else:
            raise ValueError(f"Unknown report_type: {report_type}")
    except Exception:
        repository.insert_import_batch(conn, {
            "report_type": report_type,
            "checksum": checksum,
            "source_file_name": source_file_name,
            "record_count": 0,
            "status": "FAILED",
            "imported_at": _now_iso(),
        })
        raise

    now_iso = _now_iso()
    batch_id = repository.insert_import_batch(conn, {
        "report_type": report_type,
        "checksum": checksum,
        "source_file_name": source_file_name,
        "record_count": len(rows),
        "status": "SUCCESS",
        "imported_at": now_iso,
    })
    corr_id = correlation_id or f"batch:{batch_id}"

    applied_count = 0
    conflict_count = 0
    invalid_count = 0
    seen_unit_ids_move_outs: set[int] = set()

    if report_type == MOVE_OUTS:
        for row in rows:
            move_out_iso = _to_iso_date(row.get("move_out_date"))
            if row.get("move_out_date") is None:
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="INVALID",
                    conflict_flag=1,
                    conflict_reason="MOVE_OUT_DATE_MISSING",
                    move_out_date=None,
                    move_in_date=None,
                )
                invalid_count += 1
                continue
            unit_row = _ensure_unit(conn, property_id, row["unit_raw"], row["unit_norm"])
            unit_id = unit_row["unit_id"]
            open_turnover = _row_to_dict(repository.get_open_turnover_by_unit(conn, unit_id))
            if open_turnover is not None:
                if open_turnover.get("legal_confirmation_source") is None:
                    existing_move_out = open_turnover["move_out_date"]
                    if existing_move_out != move_out_iso:
                        _write_import_row(
                            conn, batch_id, row,
                            validation_status="CONFLICT",
                            conflict_flag=1,
                            conflict_reason="MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER",
                            move_out_date=move_out_iso,
                            move_in_date=None,
                        )
                        conflict_count += 1
                        continue
                tid = open_turnover["turnover_id"]
                override_at = open_turnover.get("move_out_manual_override_at")
                current_sched = _normalize_date_str(open_turnover.get("scheduled_move_out_date"))
                incoming_norm = _normalize_date_str(move_out_iso)
                if override_at is not None:
                    if current_sched == incoming_norm:
                        repository.update_turnover_fields(conn, tid, {
                            "last_seen_moveout_batch_id": batch_id,
                            "missing_moveout_count": 0,
                            "updated_at": now_iso,
                            "scheduled_move_out_date": move_out_iso,
                            "move_out_manual_override_at": None,
                        })
                        _audit(conn, tid, "manual_override_cleared", None, "scheduled_move_out_date|validated_by=MOVE_OUTS", actor, corr_id)
                    else:
                        repository.update_turnover_fields(conn, tid, {
                            "last_seen_moveout_batch_id": batch_id,
                            "missing_moveout_count": 0,
                            "updated_at": now_iso,
                        })
                        _write_skip_audit_if_new(conn, tid, "scheduled_move_out_date", "MOVE_OUTS", incoming_norm, actor, corr_id)
                else:
                    repository.update_turnover_fields(conn, tid, {
                        "last_seen_moveout_batch_id": batch_id,
                        "missing_moveout_count": 0,
                        "updated_at": now_iso,
                        "scheduled_move_out_date": move_out_iso,
                    })
                seen_unit_ids_move_outs.add(unit_id)
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="OK",
                    move_out_date=move_out_iso,
                    move_in_date=None,
                )
                applied_count += 1
            else:
                turnover_id = repository.insert_turnover(conn, {
                    "property_id": property_id,
                    "unit_id": unit_id,
                    "source_turnover_key": f"{property_id}:{row['unit_norm']}:{move_out_iso}",
                    "move_out_date": move_out_iso,
                    "move_in_date": None,
                    "report_ready_date": None,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "last_seen_moveout_batch_id": batch_id,
                    "missing_moveout_count": 0,
                    "scheduled_move_out_date": move_out_iso,
                })
                _audit(conn, turnover_id, "created", None, "import:MOVE_OUTS", actor, corr_id)
                _instantiate_tasks_for_turnover_impl(conn, turnover_id, unit_row, property_id)
                seen_unit_ids_move_outs.add(unit_id)
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="OK",
                    move_out_date=move_out_iso,
                    move_in_date=None,
                )
                applied_count += 1

    elif report_type == PENDING_MOVE_INS:
        for row in rows:
            unit_row = repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=row["unit_norm"])
            if unit_row is None:
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="CONFLICT",
                    conflict_flag=1,
                    conflict_reason="MOVE_IN_WITHOUT_OPEN_TURNOVER",
                    move_out_date=None,
                    move_in_date=_to_iso_date(row.get("move_in_date")),
                )
                conflict_count += 1
                continue
            unit_id = unit_row["unit_id"]
            open_turnover = _row_to_dict(repository.get_open_turnover_by_unit(conn, unit_id))
            if open_turnover is None:
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="CONFLICT",
                    conflict_flag=1,
                    conflict_reason="MOVE_IN_WITHOUT_OPEN_TURNOVER",
                    move_out_date=None,
                    move_in_date=_to_iso_date(row.get("move_in_date")),
                )
                conflict_count += 1
            else:
                move_in_iso = _to_iso_date(row.get("move_in_date"))
                old_val = open_turnover["move_in_date"]
                tid = open_turnover["turnover_id"]
                override_at = open_turnover.get("move_in_manual_override_at")
                if override_at is not None:
                    current_norm = _normalize_date_str(old_val)
                    incoming_norm = _normalize_date_str(move_in_iso)
                    if current_norm == incoming_norm:
                        repository.update_turnover_fields(conn, tid, {
                            "move_in_date": move_in_iso,
                            "updated_at": now_iso,
                            "move_in_manual_override_at": None,
                        })
                        _audit(conn, tid, "manual_override_cleared", None, "move_in_date|validated_by=PENDING_MOVE_INS", actor, corr_id)
                        applied_count += 1
                    else:
                        _write_skip_audit_if_new(conn, tid, "move_in_date", "PENDING_MOVE_INS", incoming_norm, actor, corr_id)
                elif old_val != move_in_iso:
                    repository.update_turnover_fields(conn, tid, {
                        "move_in_date": move_in_iso,
                        "updated_at": now_iso,
                    })
                    _audit(conn, tid, "move_in_date", old_val, move_in_iso, actor, corr_id)
                    applied_count += 1
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="OK",
                    move_out_date=None,
                    move_in_date=move_in_iso,
                )

    elif report_type == PENDING_FAS:
        for row in rows:
            unit_row = repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=row["unit_norm"])
            if unit_row is None:
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="IGNORED",
                    conflict_reason="NO_OPEN_TURNOVER_FOR_VALIDATION",
                    move_out_date=None,
                    move_in_date=None,
                )
                continue
            unit_id = unit_row["unit_id"]
            open_turnover = _row_to_dict(repository.get_open_turnover_by_unit(conn, unit_id))
            if open_turnover is None:
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="IGNORED",
                    conflict_reason="NO_OPEN_TURNOVER_FOR_VALIDATION",
                    move_out_date=None,
                    move_in_date=None,
                )
                continue
            else:
                mo_iso = _to_iso_date(row.get("mo_cancel_date"))
                if open_turnover.get("legal_confirmation_source") is None:
                    tid = open_turnover["turnover_id"]
                    old_anchor = effective_move_out_date(open_turnover)
                    fas_fields = {
                        "confirmed_move_out_date": mo_iso,
                        "legal_confirmation_source": "fas",
                        "legal_confirmed_at": now_iso,
                        "updated_at": now_iso,
                    }
                    old_confirmed = open_turnover.get("confirmed_move_out_date")
                    if old_confirmed != mo_iso:
                        _audit(conn, tid, "confirmed_move_out_date", old_confirmed, mo_iso, actor, corr_id)
                    old_source = open_turnover.get("legal_confirmation_source")
                    if old_source != "fas":
                        _audit(conn, tid, "legal_confirmation_source", old_source, "fas", actor, corr_id)
                    old_at = open_turnover.get("legal_confirmed_at")
                    if old_at != now_iso:
                        _audit(conn, tid, "legal_confirmed_at", old_at, now_iso, actor, corr_id)
                    repository.update_turnover_fields(conn, tid, fas_fields)

                    new_turnover = dict(open_turnover)
                    new_turnover.update(fas_fields)
                    new_anchor = effective_move_out_date(new_turnover)
                    reconcile_sla_for_turnover(
                        conn=conn,
                        turnover_id=tid,
                        move_out_date=new_anchor,
                        manual_ready_confirmed_at=new_turnover.get("manual_ready_confirmed_at"),
                        today=today,
                        actor=actor,
                        source="import",
                        correlation_id=corr_id,
                        previous_effective_move_out_date=old_anchor,
                    )

                _write_import_row(
                    conn, batch_id, row,
                    validation_status="OK",
                    move_out_date=mo_iso,
                    move_in_date=None,
                )

    elif report_type in (AVAILABLE_UNITS, DMRB):
        for row in rows:
            ready_iso = _to_iso_date(row.get("report_ready_date"))
            unit_row = repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=row["unit_norm"])
            if unit_row is None:
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="IGNORED",
                    conflict_reason="NO_OPEN_TURNOVER_FOR_READY_DATE",
                    move_out_date=None,
                    move_in_date=None,
                )
                continue
            unit_id = unit_row["unit_id"]
            open_turnover = _row_to_dict(repository.get_open_turnover_by_unit(conn, unit_id))
            if open_turnover is None:
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="IGNORED",
                    conflict_reason="NO_OPEN_TURNOVER_FOR_READY_DATE",
                    move_out_date=None,
                    move_in_date=None,
                )
            elif row.get("report_ready_date") is None:
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="OK",
                    move_out_date=None,
                    move_in_date=None,
                )
            else:
                old_ready = open_turnover["report_ready_date"]
                tid = open_turnover["turnover_id"]
                override_at = open_turnover.get("ready_manual_override_at")
                current_ready_norm = _normalize_date_str(old_ready)
                incoming_ready_norm = _normalize_date_str(ready_iso)
                old_available = open_turnover.get("available_date")
                status_val = (row.get("status") or "").strip() or None if report_type == AVAILABLE_UNITS else None
                status_override_at = open_turnover.get("status_manual_override_at") if report_type == AVAILABLE_UNITS else None
                current_status_norm = _normalize_status(open_turnover.get("availability_status")) if report_type == AVAILABLE_UNITS else None
                incoming_status_norm = _normalize_status(status_val) if report_type == AVAILABLE_UNITS else None
                old_status = open_turnover.get("availability_status") if report_type == AVAILABLE_UNITS else None

                if override_at is not None:
                    if current_ready_norm == incoming_ready_norm:
                        update_fields = {"report_ready_date": ready_iso, "updated_at": now_iso, "ready_manual_override_at": None}
                        _audit(conn, tid, "manual_override_cleared", None, "report_ready_date|validated_by=" + report_type, actor, corr_id)
                        update_fields["available_date"] = ready_iso
                        if old_available != ready_iso:
                            _audit(conn, tid, "available_date", old_available, ready_iso, actor, corr_id)
                        if report_type == AVAILABLE_UNITS:
                            if status_override_at is not None:
                                if current_status_norm == incoming_status_norm:
                                    update_fields["availability_status"] = status_val
                                    update_fields["status_manual_override_at"] = None
                                    _audit(conn, tid, "manual_override_cleared", None, "availability_status|validated_by=AVAILABLE_UNITS", actor, corr_id)
                                else:
                                    _write_skip_audit_if_new(conn, tid, "availability_status", "AVAILABLE_UNITS", incoming_status_norm, actor, corr_id)
                            else:
                                update_fields["availability_status"] = status_val
                                if old_status != status_val:
                                    _audit(conn, tid, "availability_status", old_status, status_val, actor, corr_id)
                        repository.update_turnover_fields(conn, tid, update_fields)
                        applied_count += 1
                    else:
                        _write_skip_audit_if_new(conn, tid, "report_ready_date", report_type, incoming_ready_norm, actor, corr_id)
                        if report_type == AVAILABLE_UNITS and status_override_at is not None:
                            if current_status_norm == incoming_status_norm:
                                uf = {"status_manual_override_at": None, "availability_status": status_val, "updated_at": now_iso}
                                _audit(conn, tid, "manual_override_cleared", None, "availability_status|validated_by=AVAILABLE_UNITS", actor, corr_id)
                                repository.update_turnover_fields(conn, tid, uf)
                            else:
                                _write_skip_audit_if_new(conn, tid, "availability_status", "AVAILABLE_UNITS", incoming_status_norm, actor, corr_id)
                else:
                    update_fields = {"report_ready_date": ready_iso, "updated_at": now_iso}
                    if old_ready != ready_iso:
                        _audit(conn, tid, "report_ready_date", old_ready, ready_iso, actor, corr_id)
                        applied_count += 1
                    update_fields["available_date"] = ready_iso
                    if old_available != ready_iso:
                        _audit(conn, tid, "available_date", old_available, ready_iso, actor, corr_id)
                    if report_type == AVAILABLE_UNITS:
                        if status_override_at is not None:
                            if current_status_norm == incoming_status_norm:
                                update_fields["availability_status"] = status_val
                                update_fields["status_manual_override_at"] = None
                                _audit(conn, tid, "manual_override_cleared", None, "availability_status|validated_by=AVAILABLE_UNITS", actor, corr_id)
                            else:
                                _write_skip_audit_if_new(conn, tid, "availability_status", "AVAILABLE_UNITS", incoming_status_norm, actor, corr_id)
                        else:
                            update_fields["availability_status"] = status_val
                            if old_status != status_val:
                                _audit(conn, tid, "availability_status", old_status, status_val, actor, corr_id)
                    repository.update_turnover_fields(conn, tid, update_fields)
                _write_import_row(
                    conn, batch_id, row,
                    validation_status="OK",
                    move_out_date=None,
                    move_in_date=None,
                )

    if report_type == MOVE_OUTS:
        open_turnovers = repository.list_open_turnovers_by_property(conn, property_id=property_id)
        for t in open_turnovers:
            uid = t["unit_id"]
            if uid in seen_unit_ids_move_outs:
                repository.update_turnover_fields(conn, t["turnover_id"], {
                    "missing_moveout_count": 0,
                    "last_seen_moveout_batch_id": batch_id,
                    "updated_at": now_iso,
                })
            else:
                missing = int(t["missing_moveout_count"] or 0) + 1
                if missing >= 2:
                    repository.update_turnover_fields(conn, t["turnover_id"], {
                        "canceled_at": now_iso,
                        "cancel_reason": "Move-out disappeared from report twice",
                        "missing_moveout_count": missing,
                        "updated_at": now_iso,
                    })
                    _audit(conn, t["turnover_id"], "canceled_at", None, now_iso, actor, corr_id)
                    _audit(conn, t["turnover_id"], "cancel_reason", None, "Move-out disappeared from report twice", actor, corr_id)
                else:
                    repository.update_turnover_fields(conn, t["turnover_id"], {
                        "missing_moveout_count": missing,
                        "updated_at": now_iso,
                    })

    if db_path and backup_dir:
        db_connection.backup_database(db_path, backup_dir, batch_id)

    return {
        "report_type": report_type,
        "checksum": checksum,
        "status": "SUCCESS",
        "batch_id": batch_id,
        "record_count": len(rows),
        "applied_count": applied_count,
        "conflict_count": conflict_count,
        "invalid_count": invalid_count,
    }
