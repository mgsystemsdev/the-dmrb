"""Move-out import: parse and apply MOVE_OUTS report."""
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
from services.imports.constants import OUTCOME_APPLIED, OUTCOME_SKIPPED_OVERRIDE
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
                update_fields: dict[str, Any] = {
                    "last_seen_moveout_batch_id": batch_id,
                    "missing_moveout_count": 0,
                    "updated_at": now_iso,
                }
                # When there is no legal confirmation and no manual override,
                # treat differing move-out dates as corrections rather than conflicts.
                if open_turnover.get("legal_confirmation_source") is None:
                    existing_move_out_iso = open_turnover["move_out_date"]
                    existing_norm = _normalize_date_str(existing_move_out_iso)
                    if existing_norm != incoming_norm:
                        update_fields["move_out_date"] = move_out_iso
                        _audit(conn, tid, "move_out_date", existing_move_out_iso, move_out_iso, actor, corr_id)
                # Always keep scheduled_move_out_date aligned with the import.
                existing_sched = open_turnover.get("scheduled_move_out_date")
                if existing_sched != move_out_iso:
                    update_fields["scheduled_move_out_date"] = move_out_iso
                    _audit(conn, tid, "scheduled_move_out_date", existing_sched, move_out_iso, actor, corr_id)
                repository.update_turnover_fields(conn, tid, update_fields)
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
            # No open turnover: create one via shared helper so tasks/SLA/risk flows
            # are handled by turnover_service.
            move_out_date = row["move_out_date"]
            move_out_iso = _to_iso_date(move_out_date)
            today = date.fromisoformat(now_iso[:10]) if now_iso and len(now_iso) >= 10 else date.today()
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
                report_ready_date=None,
            )
            if new_turnover is not None:
                turnover_id = new_turnover["turnover_id"]
                repository.update_turnover_fields(conn, turnover_id, {
                    "last_seen_moveout_batch_id": batch_id,
                    "missing_moveout_count": 0,
                    "scheduled_move_out_date": move_out_iso,
                    "updated_at": now_iso,
                })
                _audit(conn, turnover_id, "created", None, "import:MOVE_OUTS", actor, corr_id)
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
