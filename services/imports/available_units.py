"""Available units import: parse and apply AVAILABLE_UNITS report (ready date + availability_status)."""
from __future__ import annotations

import json
from datetime import date
from typing import Any

import pandas as pd

from db import repository

from services.imports.common import (
    _append_diagnostic,
    _audit,
    _ensure_unit,
    _filter_phase,
    _normalize_unit,
    _row_to_dict,
    _to_iso_date,
    _write_import_row,
    _write_skip_audit_if_new,
    find_or_create_turnover_for_unit,
)
from services.imports.validation import _normalize_date_str, _normalize_status

# Canonical status sets for AVAILABLE_UNITS vacancy semantics.
VACANT_STATUSES = frozenset({"vacant ready", "vacant not ready"})
NOTICE_STATUSES = frozenset({"on notice", "on notice (break)"})

# Status values that allow creating a turnover when no open turnover exists
# (Available Date used as move_out_date). Only VACANT_STATUSES are required
# to create turnovers; Beacon statuses are allowed but not required by the
# invariant, and Notice statuses do not auto-create turnovers.
STATUSES_ALLOWING_TURNOVER_CREATION = frozenset(
    set(VACANT_STATUSES) | {"beacon ready", "beacon not ready"}
)


def _status_allows_turnover_creation(status: str | None) -> bool:
    """True when status allows creating a turnover from this report (case-insensitive)."""
    if not status or not isinstance(status, str):
        return False
    normalized = status.strip().lower()
    return normalized in STATUSES_ALLOWING_TURNOVER_CREATION


# #region agent log
import json as _au_json
import time as _au_time

_DEBUG_LOG_PATH = "/Users/miguelgonzalez/Projects/GitHub/Private/GitHub_Linked/the-dmrb/.cursor/debug-47f25f.log"


def _log_available_units_reconcile(message: str, data: dict, *, run_id: str, hypothesis_id: str) -> None:
    """Append a single NDJSON debug log line for AVAILABLE_UNITS reconciliation."""
    try:
        payload = {
            "sessionId": "47f25f",
            "id": f"log_{int(_au_time.time() * 1000)}",
            "timestamp": int(_au_time.time() * 1000),
            "location": "services/imports/available_units.py",
            "message": message,
            "data": data,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(_au_json.dumps(payload) + "\n")
    except Exception:
        # Logging must never break imports.
        pass


# #endregion


def reconcile_available_units_vacancy_invariant(conn, *, property_id: int, today: date, actor: str) -> None:
    """
    One-off reconciliation for legacy AVAILABLE_UNITS batches:

    For the latest AVAILABLE_UNITS batch, find rows that were previously
    IGNORED/NO_OPEN_TURNOVER_FOR_READY_DATE but whose raw Status/Available Date
    indicate a Vacant unit with a known Available Date. For each such row:

    - Ensure the unit exists.
    - Ensure an open turnover exists (creating one if needed) with
      move_out_date = Available Date.
    - Update the import_row to validation_status=OK and
      conflict_reason=CREATED_TURNOVER_FROM_AVAILABILITY, setting move_out_date.
    """
    rows = repository.get_latest_import_rows(conn, "AVAILABLE_UNITS")
    if not rows:
        _log_available_units_reconcile(
            "available_units_reconcile_no_rows",
            {"property_id": property_id},
            run_id="post-fix",
            hypothesis_id="H1",
        )
        return

    processed = 0
    created_turnovers = 0
    updated_rows_only = 0

    # Reuse today's value for SLA/lifecycle hooks.
    for row in rows:
        if row.get("validation_status") != "IGNORED":
            continue
        if row.get("conflict_reason") != "NO_OPEN_TURNOVER_FOR_READY_DATE":
            continue

        try:
            raw = _au_json.loads(row["raw_json"])
        except Exception:
            continue

        raw_status = raw.get("Status")
        status_norm = None
        if isinstance(raw_status, str):
            status_norm = raw_status.strip().lower() or None
        if status_norm not in VACANT_STATUSES:
            continue

        raw_available = raw.get("Available Date")
        if not raw_available:
            continue

        dt_avail = pd.to_datetime(raw_available, errors="coerce")
        if pd.isna(dt_avail) or not hasattr(dt_avail, "date"):
            continue
        available_date = dt_avail.date()

        unit_norm = row["unit_code_norm"]
        unit_row = repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=unit_norm)
        if unit_row is None:
            unit_row = _ensure_unit(conn, property_id, row["unit_code_raw"], unit_norm)

        unit_id = unit_row["unit_id"]
        open_turnover = repository.get_open_turnover_by_unit(conn, unit_id)

        move_out_iso = available_date.isoformat()

        if open_turnover is None:
            # Create turnover anchored on Available Date.
            source_turnover_key = f"{property_id}:{unit_norm}:{move_out_iso}"
            tid = turnover_service.create_turnover_and_reconcile(
                conn=conn,
                unit_id=unit_id,
                unit_row=unit_row,
                property_id=property_id,
                source_turnover_key=source_turnover_key,
                move_out_date=available_date,
                move_in_date=None,
                report_ready_date=None,
                today=today,
                actor=actor,
            )
            created_turnovers += 1
        else:
            tid = open_turnover["turnover_id"]
            updated_rows_only += 1

        # Update import_row to reflect successful application.
        conn.execute(
            """
            UPDATE import_row
            SET validation_status = ?, conflict_flag = 0,
                conflict_reason = 'CREATED_TURNOVER_FROM_AVAILABILITY',
                move_out_date = ?, move_in_date = NULL
            WHERE row_id = ?
            """,
            ("OK", move_out_iso, row["row_id"]),
        )

        # Also ensure turnover fields reflect availability info.
        repository.update_turnover_fields(
            conn,
            tid,
            {
                "available_date": move_out_iso,
                "availability_status": raw_status.strip() if isinstance(raw_status, str) else None,
            },
        )

        processed += 1

    _log_available_units_reconcile(
        "available_units_reconcile_completed",
        {
            "property_id": property_id,
            "processed": processed,
            "created_turnovers": created_turnovers,
            "updated_rows_only": updated_rows_only,
        },
        run_id="post-fix",
        hypothesis_id="H1",
    )


def _parse_available_units(file_path: str) -> list[dict]:
    df = pd.read_csv(file_path, skiprows=5)
    df = df[["Unit", "Status", "Available Date", "Move-In Ready Date"]].copy()
    rows = []
    for _, r in df.iterrows():
        raw = str(r["Unit"]) if pd.notna(r["Unit"]) else ""
        unit_raw, unit_norm = _normalize_unit(raw)
        dt_ready = pd.to_datetime(r["Move-In Ready Date"], errors="coerce")
        report_ready_date = dt_ready.date() if pd.notna(dt_ready) and hasattr(dt_ready, "date") else None
        dt_avail = pd.to_datetime(r["Available Date"], errors="coerce")
        available_date = dt_avail.date() if pd.notna(dt_avail) and hasattr(dt_avail, "date") else None
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
            "available_date": available_date,
            "status": status,
            "raw_json": raw_json,
        })
    return _filter_phase(rows)


def apply_available_units(
    conn,
    batch_id: int,
    rows: list[dict],
    property_id: int,
    now_iso: str,
    actor: str,
    corr_id: str,
) -> tuple[int, int, int, list[dict]]:
    """Apply AVAILABLE_UNITS rows (ready date + availability_status). Returns (applied_count, conflict_count, invalid_count, diagnostics)."""
    applied_count = 0
    conflict_count = 0
    invalid_count = 0
    diagnostics: list[dict[str, Any]] = []
    today = date.fromisoformat(now_iso[:10]) if now_iso and len(now_iso) >= 10 else date.today()

    for row_index, row in enumerate(rows, start=1):
        raw_status = row.get("status")
        normalized_status = None
        if isinstance(raw_status, str):
            normalized_status = raw_status.strip().lower() or None
        available_date = row.get("available_date")
        ready_iso = _to_iso_date(row.get("report_ready_date"))
        unit_row = repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=row["unit_norm"])
        if unit_row is None:
            # Get-or-create unit when status allows turnover creation (same as Move-Outs), so Vacant/Beacon/On notice rows create the unit and turnover.
            if _status_allows_turnover_creation(normalized_status):
                unit_row = _ensure_unit(conn, property_id, row["unit_raw"], row["unit_norm"])
            else:
                _append_diagnostic(
                    diagnostics,
                    row_index=row_index,
                    column="Unit",
                    error_type="UNKNOWN_UNIT_REFERENCE",
                    error_message="Unit was not found for ready-date import row.",
                    suggestion="Ensure the unit exists and has an open turnover before importing.",
                )
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
            # No open turnover: create one when status indicates vacancy (vacancy truth); else ignore.
            if _status_allows_turnover_creation(normalized_status):
                if available_date is None:
                    _append_diagnostic(
                        diagnostics,
                        row_index=row_index,
                        column="Available Date",
                        error_type="MISSING_REQUIRED_FIELD",
                        error_message="Missing required field 'Available Date' for vacancy status.",
                        suggestion="Populate a valid available date (YYYY-MM-DD) for vacant units.",
                    )
                    _write_import_row(
                        conn,
                        batch_id,
                        row,
                        validation_status="INVALID",
                        conflict_flag=1,
                        conflict_reason="AVAILABLE_DATE_MISSING",
                        move_out_date=None,
                        move_in_date=None,
                    )
                    invalid_count += 1
                    continue
                move_out_date = available_date
                move_out_iso = move_out_date.isoformat()
                source_turnover_key = f"{property_id}:{row['unit_norm']}:{move_out_iso}"
                new_turnover = find_or_create_turnover_for_unit(
                    conn=conn,
                    property_id=property_id,
                    unit_row=unit_row,
                    move_out_date=move_out_date,
                    source_turnover_key=source_turnover_key,
                    today=today,
                    actor=actor,
                    corr_id=corr_id,
                    report_ready_date=row.get("report_ready_date"),
                )
                if new_turnover is None:
                    # Should not happen when move_out_date is provided, but guard defensively.
                    _append_diagnostic(
                        diagnostics,
                        row_index=row_index,
                        column="Unit",
                        error_type="TURNOVER_CREATION_FAILED",
                        error_message="Failed to create turnover from availability row.",
                        suggestion="Review import row and turnover state before retrying.",
                    )
                    _write_import_row(
                        conn,
                        batch_id,
                        row,
                        validation_status="CONFLICT",
                        conflict_flag=1,
                        conflict_reason="TURNOVER_CREATION_FAILED",
                        move_out_date=None,
                        move_in_date=None,
                    )
                    conflict_count += 1
                    continue
                tid = new_turnover["turnover_id"]
                status_val = (row.get("status") or "").strip() or None
                # Prefer explicit Move-In Ready Date, but when missing fall back to Available Date
                ready_date_value = row.get("report_ready_date") or available_date
                ready_iso_from_row = _to_iso_date(ready_date_value)
                available_date_iso = _to_iso_date(row.get("available_date")) or ready_iso_from_row
                update_fields = {
                    "report_ready_date": ready_iso_from_row,
                    "available_date": available_date_iso,
                    "availability_status": status_val,
                    "updated_at": now_iso,
                }
                repository.update_turnover_fields(conn, tid, update_fields)
                _write_import_row(
                    conn,
                    batch_id,
                    row,
                    validation_status="OK",
                    conflict_reason="CREATED_TURNOVER_FROM_AVAILABILITY",
                    move_out_date=move_out_iso,
                    move_in_date=None,
                )
                applied_count += 1
            else:
                # Invariant safeguard: a Vacant row with an Available Date and no
                # open turnover must never be silently ignored. If we ever reach
                # this branch for such a row, surface an explicit INVALID
                # diagnostic so it appears in Import Diagnostics.
                if normalized_status in VACANT_STATUSES and available_date is not None:
                    _append_diagnostic(
                        diagnostics,
                        row_index=row_index,
                        column="Status",
                        error_type="VACANT_ROW_WITHOUT_TURNOVER",
                        error_message=(
                            "Vacant row reached IGNORED branch without creating a turnover. "
                            f"unit_code_norm={row.get('unit_norm')}, "
                            f"status={raw_status}, "
                            f"available_date={_to_iso_date(available_date)}, "
                            f"batch_id={batch_id}"
                        ),
                        suggestion="Investigate invariant breach: VACANT row with Available Date must create a turnover.",
                    )
                    _write_import_row(
                        conn,
                        batch_id,
                        row,
                        validation_status="INVALID",
                        conflict_flag=1,
                        conflict_reason="VACANT_ROW_WITHOUT_TURNOVER",
                        move_out_date=None,
                        move_in_date=None,
                    )
                    invalid_count += 1
                else:
                    _append_diagnostic(
                        diagnostics,
                        row_index=row_index,
                        column="Unit",
                        error_type="UNKNOWN_UNIT_REFERENCE",
                        error_message="No open turnover found for ready-date import row.",
                        suggestion="Verify unit identity and open turnover state, then retry import.",
                    )
                    _write_import_row(
                        conn,
                        batch_id,
                        row,
                        validation_status="IGNORED",
                        conflict_reason="NO_OPEN_TURNOVER_FOR_READY_DATE",
                        move_out_date=None,
                        move_in_date=None,
                    )
            continue
        # Open turnover exists: update report_ready_date, available_date, availability_status (respect overrides).
        old_ready = open_turnover["report_ready_date"]
        tid = open_turnover["turnover_id"]
        override_at = open_turnover.get("ready_manual_override_at")
        current_ready_norm = _normalize_date_str(old_ready)
        incoming_ready_norm = _normalize_date_str(ready_iso) if ready_iso else None
        old_available = open_turnover.get("available_date")
        status_val = (row.get("status") or "").strip() or None
        status_override_at = open_turnover.get("status_manual_override_at")
        current_status_norm = _normalize_status(open_turnover.get("availability_status"))
        incoming_status_norm = _normalize_status(status_val)
        old_status = open_turnover.get("availability_status")

        # Determine which date to treat as the incoming "ready" signal: prefer explicit ready date,
        # but fall back to available_date when ready is missing.
        effective_ready_iso = ready_iso or _to_iso_date(available_date)

        if override_at is not None and ready_iso is not None:
            # Ready-date override exists and we have an incoming ready date to compare.
            if current_ready_norm == incoming_ready_norm:
                update_fields = {"report_ready_date": ready_iso, "updated_at": now_iso, "ready_manual_override_at": None}
                _audit(conn, tid, "manual_override_cleared", None, "report_ready_date|validated_by=AVAILABLE_UNITS", actor, corr_id)
                update_fields["available_date"] = ready_iso
                if old_available != ready_iso:
                    _audit(conn, tid, "available_date", old_available, ready_iso, actor, corr_id)
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
                _write_skip_audit_if_new(conn, tid, "report_ready_date", "AVAILABLE_UNITS", incoming_ready_norm, actor, corr_id)
                if status_override_at is not None:
                    if current_status_norm == incoming_status_norm:
                        uf = {"status_manual_override_at": None, "availability_status": status_val, "updated_at": now_iso}
                        _audit(conn, tid, "manual_override_cleared", None, "availability_status|validated_by=AVAILABLE_UNITS", actor, corr_id)
                        repository.update_turnover_fields(conn, tid, uf)
                    else:
                        _write_skip_audit_if_new(conn, tid, "availability_status", "AVAILABLE_UNITS", incoming_status_norm, actor, corr_id)
        else:
            update_fields: dict[str, Any] = {"updated_at": now_iso}
            # If we have an effective ready date (ready or available), keep report_ready_date aligned.
            if effective_ready_iso is not None:
                if old_ready != effective_ready_iso:
                    update_fields["report_ready_date"] = effective_ready_iso
                    _audit(conn, tid, "report_ready_date", old_ready, effective_ready_iso, actor, corr_id)
                    applied_count += 1
                update_fields["available_date"] = effective_ready_iso
                if old_available != effective_ready_iso:
                    _audit(conn, tid, "available_date", old_available, effective_ready_iso, actor, corr_id)
            # Always attempt to synchronize availability_status with override protection.
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

    return (applied_count, conflict_count, invalid_count, diagnostics)
