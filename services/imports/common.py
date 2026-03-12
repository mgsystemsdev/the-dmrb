"""Shared helpers used by apply logic (ensure_unit, write_import_row, audit, etc.)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from db import repository
from domain import unit_identity
from services import turnover_service
from services.imports.constants import VALID_PHASES


def _row_to_dict(r) -> Optional[dict]:
    """Convert sqlite3.Row to dict so .get() works; None stays None."""
    if r is None:
        return None
    return dict(r)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_iso_date(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d is not None else None


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


def _append_diagnostic(
    diagnostics: list[dict[str, Any]],
    *,
    row_index: int,
    error_type: str,
    error_message: str,
    column: Optional[str] = None,
    suggestion: Optional[str] = None,
) -> None:
    diagnostics.append(
        {
            "row_index": row_index,
            "error_type": error_type,
            "error_message": error_message,
            "column": column,
            "suggestion": suggestion,
        }
    )


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
    """Return the normalized value from the most recent import_skipped_due_to_manual_override audit for this turnover and field."""
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


def find_or_create_turnover_for_unit(
    conn,
    property_id: int,
    unit_row: dict,
    *,
    move_out_date: Optional[date],
    source_turnover_key: str,
    today: date,
    actor: str,
    corr_id: str,
    report_ready_date: Optional[date] = None,
) -> Optional[dict]:
    """
    Find an open turnover for the given unit or create one using turnover_service.create_turnover_and_reconcile.

    Creation path delegates to turnover_service so task instantiation, SLA, and risk reconciliation
    follow the standard lifecycle behavior. Importers remain responsible for reconciling their own
    authoritative fields on the returned turnover.
    """
    unit_id = unit_row["unit_id"]
    existing = repository.get_open_turnover_by_unit(conn, unit_id)
    existing_dict = _row_to_dict(existing)
    if existing_dict is not None:
        return existing_dict

    if move_out_date is None:
        return None

    turnover_id = turnover_service.create_turnover_and_reconcile(
        conn=conn,
        unit_id=unit_id,
        unit_row=unit_row,
        property_id=property_id,
        source_turnover_key=source_turnover_key,
        move_out_date=move_out_date,
        move_in_date=None,
        report_ready_date=report_ready_date,
        today=today,
        actor=actor,
    )
    return _row_to_dict(repository.get_turnover_by_id(conn, turnover_id))
