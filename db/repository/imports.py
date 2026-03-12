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


def get_missing_move_out_exceptions(conn: sqlite3.Connection) -> list[dict]:
    """Return import_row rows with conflict_reason MOVE_IN_WITHOUT_OPEN_TURNOVER or MOVE_OUT_DATE_MISSING, joined with batch for report_type and imported_at."""
    cursor = conn.execute(
        """SELECT r.row_id, r.batch_id, r.unit_code_raw, r.unit_code_norm,
                  r.move_out_date, r.move_in_date, r.conflict_reason,
                  b.report_type, b.imported_at
           FROM import_row r
           JOIN import_batch b ON r.batch_id = b.batch_id
           WHERE r.conflict_reason IN ('MOVE_IN_WITHOUT_OPEN_TURNOVER', 'MOVE_OUT_DATE_MISSING')
           ORDER BY b.imported_at DESC, r.row_id"""
    )
    rows = cursor.fetchall()
    return _rows_to_dicts(rows)


def get_import_rows_pending_fas(conn: sqlite3.Connection) -> list[dict]:
    """Return import_row rows from PENDING_FAS batches, joined with batch for imported_at."""
    cursor = conn.execute(
        """SELECT r.row_id, r.batch_id, r.unit_code_raw, r.unit_code_norm,
                  r.move_out_date, r.move_in_date, b.imported_at
           FROM import_row r
           JOIN import_batch b ON r.batch_id = b.batch_id
           WHERE b.report_type = 'PENDING_FAS'
           ORDER BY b.imported_at DESC, r.row_id"""
    )
    return _rows_to_dicts(cursor.fetchall())


def get_import_diagnostics(conn: sqlite3.Connection, since_imported_at: str | None = None) -> list[dict]:
    """
    Return non-OK import_row rows joined to import_batch, deduplicated to most recent
    per (unit_code_norm, report_type). For Import Diagnostics tab.
    since_imported_at: optional ISO timestamp; only rows with b.imported_at >= this are returned.
    """
    base_sql = """WITH diag AS (
            SELECT
                r.row_id,
                r.batch_id,
                r.unit_code_raw,
                r.unit_code_norm,
                r.move_out_date,
                r.move_in_date,
                r.validation_status,
                r.conflict_flag,
                r.conflict_reason,
                b.report_type,
                b.imported_at,
                b.source_file_name,
                ROW_NUMBER() OVER (
                    PARTITION BY r.unit_code_norm, b.report_type
                    ORDER BY b.imported_at DESC, r.row_id DESC
                ) AS rn
            FROM import_row r
            JOIN import_batch b ON r.batch_id = b.batch_id
            WHERE r.validation_status != 'OK'
              {date_filter}
        )
        SELECT
            row_id,
            batch_id,
            unit_code_raw,
            unit_code_norm,
            move_out_date,
            move_in_date,
            validation_status,
            conflict_flag,
            conflict_reason,
            report_type,
            imported_at,
            source_file_name
        FROM diag
        WHERE rn = 1
        ORDER BY imported_at DESC, row_id"""
    if since_imported_at is not None:
        sql = base_sql.format(date_filter="AND b.imported_at >= ?")
        params: tuple = (since_imported_at,)
    else:
        sql = base_sql.format(date_filter="")
        params = ()
    cursor = conn.execute(sql, params)
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
