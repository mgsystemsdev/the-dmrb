"""Pending FAS import: parse and apply PENDING_FAS report (effective_move_out_date, reconcile_sla)."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from db import repository
from domain.lifecycle import effective_move_out_date
from services.sla_service import reconcile_sla_for_turnover

from services.imports.common import (
    _append_diagnostic,
    _audit,
    _filter_phase,
    _normalize_unit,
    _row_to_dict,
    _to_iso_date,
    _write_import_row,
)


def _parse_pending_fas(file_path: str) -> list[dict]:
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


def apply_pending_fas(
    conn,
    batch_id: int,
    rows: list[dict],
    property_id: int,
    now_iso: str,
    actor: str,
    corr_id: str,
    today,
) -> tuple[int, int, int, list[dict]]:
    """Apply PENDING_FAS rows. Returns (applied_count, conflict_count, invalid_count, diagnostics)."""
    applied_count = 0
    conflict_count = 0
    invalid_count = 0
    diagnostics: list[dict[str, Any]] = []

    for row_index, row in enumerate(rows, start=1):
        unit_row = repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=row["unit_norm"])
        if unit_row is None:
            _append_diagnostic(
                diagnostics,
                row_index=row_index,
                column="Unit",
                error_type="UNKNOWN_UNIT_REFERENCE",
                error_message="Unit was not found for pending FAS row.",
                suggestion="Ensure the unit exists and has an open turnover before importing.",
            )
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
            _append_diagnostic(
                diagnostics,
                row_index=row_index,
                column="Unit",
                error_type="UNKNOWN_UNIT_REFERENCE",
                error_message="No open turnover found for pending FAS row.",
                suggestion="Verify unit identity and open turnover state, then retry import.",
            )
            _write_import_row(
                conn, batch_id, row,
                validation_status="IGNORED",
                conflict_reason="NO_OPEN_TURNOVER_FOR_VALIDATION",
                move_out_date=None,
                move_in_date=None,
            )
            continue
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

    return (applied_count, conflict_count, invalid_count, diagnostics)
