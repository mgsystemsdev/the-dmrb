"""Move-out import: parse and apply MOVE_OUTS report."""
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
from services.imports.constants import OUTCOME_APPLIED, OUTCOME_CONFLICT, OUTCOME_SKIPPED_OVERRIDE
from services.imports.tasks import _instantiate_tasks_for_turnover_impl
from services.imports.validation import _normalize_date_str, _validation_status_from_outcome


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


def apply_move_outs(
    conn,
    batch_id: int,
    rows: list[dict],
    property_id: int,
    now_iso: str,
    actor: str,
    corr_id: str,
) -> tuple[int, int, int, list[dict], set[int]]:
    """Apply MOVE_OUTS rows. Returns (applied_count, conflict_count, invalid_count, diagnostics, seen_unit_ids)."""
    applied_count = 0
    conflict_count = 0
    invalid_count = 0
    diagnostics: list[dict[str, Any]] = []
    seen_unit_ids: set[int] = set()

    for row_index, row in enumerate(rows, start=1):
        move_out_iso = _to_iso_date(row.get("move_out_date"))
        if row.get("move_out_date") is None:
            _append_diagnostic(
                diagnostics,
                row_index=row_index,
                column="Move-Out Date",
                error_type="MISSING_REQUIRED_FIELD",
                error_message="Missing required field 'Move-Out Date'.",
                suggestion="Populate a valid move-out date (YYYY-MM-DD).",
            )
            _write_import_row(
                conn, batch_id, row,
                validation_status=_validation_status_from_outcome("INVALID"),
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
            row_outcome = OUTCOME_APPLIED
            if open_turnover.get("legal_confirmation_source") is None:
                existing_move_out = open_turnover["move_out_date"]
            else:
                existing_move_out = None
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
                    row_outcome = OUTCOME_SKIPPED_OVERRIDE
            else:
                if existing_move_out is not None and existing_move_out != move_out_iso:
                    _append_diagnostic(
                        diagnostics,
                        row_index=row_index,
                        column="Move-Out Date",
                        error_type="CONFLICT",
                        error_message="Move-out date does not match existing open turnover.",
                        suggestion="Review source data and existing turnover move-out date before retrying.",
                    )
                    _write_import_row(
                        conn, batch_id, row,
                        validation_status=_validation_status_from_outcome(OUTCOME_CONFLICT),
                        conflict_flag=1,
                        conflict_reason="MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER",
                        move_out_date=move_out_iso,
                        move_in_date=None,
                    )
                    conflict_count += 1
                    continue
                repository.update_turnover_fields(conn, tid, {
                    "last_seen_moveout_batch_id": batch_id,
                    "missing_moveout_count": 0,
                    "updated_at": now_iso,
                    "scheduled_move_out_date": move_out_iso,
                })
            seen_unit_ids.add(unit_id)
            _write_import_row(
                conn, batch_id, row,
                validation_status=_validation_status_from_outcome(row_outcome),
                move_out_date=move_out_iso,
                move_in_date=None,
            )
            if row_outcome == OUTCOME_APPLIED:
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
            seen_unit_ids.add(unit_id)
            _write_import_row(
                conn, batch_id, row,
                validation_status=_validation_status_from_outcome(OUTCOME_APPLIED),
                move_out_date=move_out_iso,
                move_in_date=None,
            )
            applied_count += 1

    return (applied_count, conflict_count, invalid_count, diagnostics, seen_unit_ids)


def post_process_after_move_outs(
    conn,
    property_id: int,
    batch_id: int,
    seen_unit_ids: set[int],
    now_iso: str,
    actor: str,
    corr_id: str,
) -> None:
    """Update missing_moveout_count / canceled_at for open turnovers not in this batch."""
    open_turnovers = repository.list_open_turnovers_by_property(conn, property_id=property_id)
    for t in open_turnovers:
        uid = t["unit_id"]
        if uid in seen_unit_ids:
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
