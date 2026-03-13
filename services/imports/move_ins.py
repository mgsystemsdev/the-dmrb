"""Pending move-in import: parse and apply PENDING_MOVE_INS report."""
from __future__ import annotations

import json
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
)
from services.imports.validation import _normalize_date_str


def _parse_pending_move_ins(file_path: str) -> list[dict]:
    # Skip header metadata rows and read only the two relevant columns.
    # This ensures extra columns like Name or task statuses are ignored entirely.
    df = pd.read_csv(
        file_path,
        skiprows=5,
        usecols=["Unit", "Move In Date"],
    )
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


def apply_pending_move_ins(
    conn,
    batch_id: int,
    rows: list[dict],
    property_id: int,
    now_iso: str,
    actor: str,
    corr_id: str,
) -> tuple[int, int, int, list[dict]]:
    """Apply PENDING_MOVE_INS rows. Returns (applied_count, conflict_count, invalid_count, diagnostics)."""
    applied_count = 0
    conflict_count = 0
    invalid_count = 0
    diagnostics: list[dict[str, Any]] = []

    for row_index, row in enumerate(rows, start=1):
        unit_row = repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=row["unit_norm"])
        if unit_row is None:
            # Ensure the unit exists so future workflows have a unit record,
            # but still treat absence of an open turnover as a conflict below.
            unit_row = _ensure_unit(conn, property_id, row["unit_raw"], row["unit_norm"])
        unit_id = unit_row["unit_id"]
        open_turnover = _row_to_dict(repository.get_open_turnover_by_unit(conn, unit_id))
        if open_turnover is None:
            _append_diagnostic(
                diagnostics,
                row_index=row_index,
                column="Unit",
                error_type="UNKNOWN_UNIT_REFERENCE",
                error_message="No open turnover found for pending move-in row.",
                suggestion="Verify unit identity and open turnover state, then retry import.",
            )
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

    return (applied_count, conflict_count, invalid_count, diagnostics)
