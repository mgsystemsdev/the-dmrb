"""Report Operations: missing move-out queue and FAS tracker. Uses existing turnover lifecycle."""
from __future__ import annotations

from datetime import date
from typing import Any

from config.settings import get_settings
from db import repository
from services import manual_availability_service

DEFAULT_ACTOR = get_settings().default_actor


def get_missing_move_out_queue(conn: Any, *, property_id: int) -> list[dict]:
    """
    Return import_row exceptions (MOVE_IN_WITHOUT_OPEN_TURNOVER, MOVE_OUT_DATE_MISSING)
    where the unit exists for the property and has no open turnover (so they can be resolved).
    Each row includes unit_code, report_type, move_in_date, conflict_reason, imported_at,
    and unit identity (unit_id, phase_code, building_code, unit_number) for resolve.
    """
    exceptions = repository.get_missing_move_out_exceptions(conn)
    out: list[dict] = []
    for row in exceptions:
        unit_code_norm = (row.get("unit_code_norm") or "").strip()
        if not unit_code_norm:
            continue
        unit_row = repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=unit_code_norm)
        if unit_row is None:
            continue
        unit_id = unit_row["unit_id"]
        open_turnover = repository.get_open_turnover_by_unit(conn, unit_id)
        if open_turnover is not None:
            continue
        out.append({
            "row_id": row.get("row_id"),
            "batch_id": row.get("batch_id"),
            "unit_code": row.get("unit_code_raw") or unit_code_norm,
            "unit_code_norm": unit_code_norm,
            "report_type": row.get("report_type"),
            "move_in_date": row.get("move_in_date"),
            "conflict_reason": row.get("conflict_reason"),
            "imported_at": row.get("imported_at"),
            "unit_id": unit_id,
            "phase_code": unit_row.get("phase_code"),
            "building_code": unit_row.get("building_code"),
            "unit_number": unit_row.get("unit_number"),
        })
    return out


def resolve_missing_move_out(
    conn: Any,
    *,
    property_id: int,
    phase_code: str,
    building_code: str,
    unit_number: str,
    move_out_date: date,
    today: date | None = None,
    actor: str = DEFAULT_ACTOR,
) -> int:
    """
    Create a turnover via manual_availability_service (reuse existing workflow).
    Caller must ensure unit exists and has no open turnover; otherwise ValueError is raised.
    Returns turnover_id.
    """
    return manual_availability_service.add_manual_availability(
        conn=conn,
        property_id=property_id,
        phase_code=phase_code,
        building_code=building_code,
        unit_number=unit_number,
        move_out_date=move_out_date,
        move_in_date=None,
        report_ready_date=None,
        today=today,
        actor=actor,
    )


def get_fas_tracker_rows(conn: Any, *, property_id: int) -> list[dict]:
    """
    Return rows for the FAS Tracker tab: PENDING_FAS import_row data with unit and note.
    Each dict has: unit_code, fas_date, imported_at, unit_id, note_text.
    """
    pending = repository.get_import_rows_pending_fas(conn)
    out: list[dict] = []
    for row in pending:
        unit_code_norm = (row.get("unit_code_norm") or "").strip()
        if not unit_code_norm:
            continue
        unit_row = repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=unit_code_norm)
        if unit_row is None:
            continue
        unit_id = unit_row["unit_id"]
        fas_date = row.get("move_out_date") or ""
        note_row = repository.get_fas_note(conn, unit_id=unit_id, fas_date=fas_date)
        note_text = (note_row.get("note_text") or "") if note_row else ""
        out.append({
            "row_id": row.get("row_id"),
            "unit_code": row.get("unit_code_raw") or unit_code_norm,
            "fas_date": fas_date,
            "imported_at": row.get("imported_at"),
            "unit_id": unit_id,
            "note_text": note_text,
        })
    return out


def upsert_fas_note(conn: Any, *, unit_id: int, fas_date: str, note_text: str) -> None:
    """Persist FAS tracker note for (unit_id, fas_date)."""
    repository.upsert_fas_tracker_note(conn, unit_id=unit_id, fas_date=fas_date, note_text=note_text or "")
