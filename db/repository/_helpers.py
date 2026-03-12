"""Shared helpers and update-column constants for db.repository."""
from __future__ import annotations

import sqlite3


def _row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows):
    return [dict(r) for r in rows]


def _inserted_id(conn, table: str, id_column: str, cursor=None) -> int:
    if hasattr(conn, "inserted_id"):
        return conn.inserted_id(table, id_column, cursor=cursor)
    if cursor is not None and getattr(cursor, "lastrowid", None) is not None:
        return int(cursor.lastrowid)
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    return int(row[0])


# Allowed columns for dynamic UPDATE (avoid injection).
# When strict=True, update_*_fields raise ValueError on unknown keys.
TURNOVER_UPDATE_COLS = frozenset({
    "property_id", "unit_id", "source_turnover_key", "move_out_date", "move_in_date", "report_ready_date",
    "manual_ready_status", "manual_ready_confirmed_at", "expedited_flag",
    "wd_present", "wd_supervisor_notified", "wd_notified_at", "wd_installed", "wd_installed_at",
    "wd_present_type",
    "closed_at", "canceled_at", "cancel_reason", "last_seen_moveout_batch_id", "missing_moveout_count",
    "created_at", "updated_at",
    "scheduled_move_out_date", "confirmed_move_out_date",
    "legal_confirmation_source", "legal_confirmed_at", "legal_confirmation_note",
    "available_date", "availability_status",
    "move_out_manual_override_at", "ready_manual_override_at",
    "move_in_manual_override_at", "status_manual_override_at",
    "last_import_move_out_date", "last_import_ready_date",
    "last_import_move_in_date", "last_import_status",
})
TASK_UPDATE_COLS = frozenset({
    "turnover_id", "task_type", "required", "blocking",
    "scheduled_date", "vendor_due_date",
    "vendor_completed_at", "manager_confirmed_at",
    "execution_status", "confirmation_status",
    "assignee", "blocking_reason",
})
UNIT_UPDATE_COLS = frozenset({
    "unit_code_raw", "has_carpet", "has_wd_expected", "is_active",
    "phase_code", "building_code", "unit_number", "unit_identity_key",
    "phase_id", "building_id", "floor_plan", "gross_sq_ft", "bed_count", "bath_count", "layout_code",
})
