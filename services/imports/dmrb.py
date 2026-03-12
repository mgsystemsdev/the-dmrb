"""DMRB import: parse Excel and apply ready-date-only (no availability_status)."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from db import repository

from services.imports.common import (
    _append_diagnostic,
    _audit,
    _filter_phase,
    _normalize_unit,
    _row_to_dict,
    _to_iso_date,
    _write_import_row,
    _write_skip_audit_if_new,
)
from services.imports.validation import _normalize_date_str


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


def apply_dmrb(
    conn,
    batch_id: int,
    rows: list[dict],
    property_id: int,
    now_iso: str,
    actor: str,
    corr_id: str,
) -> tuple[int, int, int, list[dict]]:
    """Apply DMRB rows (ready date only, no availability_status). Returns (applied_count, conflict_count, invalid_count, diagnostics)."""
    applied_count = 0
    conflict_count = 0
    invalid_count = 0
    diagnostics: list[dict[str, Any]] = []

    for row_index, row in enumerate(rows, start=1):
        ready_iso = _to_iso_date(row.get("report_ready_date"))
        unit_row = repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=row["unit_norm"])
        if unit_row is None:
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
            _append_diagnostic(
                diagnostics,
                row_index=row_index,
                column="Unit",
                error_type="UNKNOWN_UNIT_REFERENCE",
                error_message="No open turnover found for ready-date import row.",
                suggestion="Verify unit identity and open turnover state, then retry import.",
            )
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

            if override_at is not None:
                if current_ready_norm == incoming_ready_norm:
                    update_fields = {"report_ready_date": ready_iso, "updated_at": now_iso, "ready_manual_override_at": None}
                    _audit(conn, tid, "manual_override_cleared", None, "report_ready_date|validated_by=DMRB", actor, corr_id)
                    update_fields["available_date"] = ready_iso
                    if old_available != ready_iso:
                        _audit(conn, tid, "available_date", old_available, ready_iso, actor, corr_id)
                    repository.update_turnover_fields(conn, tid, update_fields)
                    applied_count += 1
                else:
                    _write_skip_audit_if_new(conn, tid, "report_ready_date", "DMRB", incoming_ready_norm, actor, corr_id)
            else:
                update_fields = {"report_ready_date": ready_iso, "updated_at": now_iso}
                if old_ready != ready_iso:
                    _audit(conn, tid, "report_ready_date", old_ready, ready_iso, actor, corr_id)
                    applied_count += 1
                update_fields["available_date"] = ready_iso
                if old_available != ready_iso:
                    _audit(conn, tid, "available_date", old_available, ready_iso, actor, corr_id)
                repository.update_turnover_fields(conn, tid, update_fields)
            _write_import_row(
                conn, batch_id, row,
                validation_status="OK",
                move_out_date=None,
                move_in_date=None,
            )

    return (applied_count, conflict_count, invalid_count, diagnostics)
