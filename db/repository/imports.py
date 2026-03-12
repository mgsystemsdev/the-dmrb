"""Import batches, rows, and audit log repository functions."""
from __future__ import annotations

import sqlite3

from db.repository._helpers import _inserted_id, _row_to_dict, _rows_to_dicts


def insert_import_batch(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """INSERT INTO import_batch (
            report_type, checksum, source_file_name, record_count, status, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        (
            data["report_type"],
            data["checksum"],
            data["source_file_name"],
            data["record_count"],
            data["status"],
            data["imported_at"],
        ),
    )
    return _inserted_id(conn, "import_batch", "batch_id", cursor=cursor)


def get_import_batch_by_checksum(conn: sqlite3.Connection, checksum: str):
    cursor = conn.execute(
        "SELECT * FROM import_batch WHERE checksum = ?",
        (checksum,),
    )
    return _row_to_dict(cursor.fetchone())


def insert_import_row(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """INSERT INTO import_row (
            batch_id, raw_json, unit_code_raw, unit_code_norm,
            move_out_date, move_in_date, validation_status, conflict_flag, conflict_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["batch_id"],
            data["raw_json"],
            data["unit_code_raw"],
            data["unit_code_norm"],
            data.get("move_out_date"),
            data.get("move_in_date"),
            data["validation_status"],
            data.get("conflict_flag", 0),
            data.get("conflict_reason"),
        ),
    )
    return _inserted_id(conn, "import_row", "row_id", cursor=cursor)


def get_import_rows_by_batch(conn: sqlite3.Connection, batch_id: int) -> list[dict]:
    """Return all import_row entries for a given batch_id as dicts."""
    cursor = conn.execute(
        "SELECT * FROM import_row WHERE batch_id = ? ORDER BY row_id",
        (batch_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def insert_audit_log(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """INSERT INTO audit_log (
            entity_type, entity_id, field_name, old_value, new_value,
            changed_at, actor, source, correlation_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["entity_type"],
            data["entity_id"],
            data["field_name"],
            data.get("old_value"),
            data.get("new_value"),
            data["changed_at"],
            data["actor"],
            data["source"],
            data.get("correlation_id"),
        ),
    )
    return _inserted_id(conn, "audit_log", "audit_id", cursor=cursor)
