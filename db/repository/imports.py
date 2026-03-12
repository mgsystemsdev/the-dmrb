"""Import batches, rows, and audit log repository functions."""
from __future__ import annotations

import sqlite3
from typing import Any

from db.repository._helpers import _inserted_id, _row_to_dict, _rows_to_dicts


def _sqlite_version_ge_325(conn: Any) -> bool:
    """Return True if connection is SQLite and version >= 3.25 (window functions)."""
    if getattr(conn, "engine", None) == "postgres":
        return False
    try:
        cur = conn.execute("SELECT sqlite_version()")
        row = cur.fetchone()
        version_str = row[0] if row else "0.0"
        if hasattr(version_str, "strip"):
            version_str = version_str.strip()
        parts = str(version_str).split(".")[:2]
        major = int(parts[0]) if parts else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        return (major, minor) >= (3, 25)
    except Exception:
        return False


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


def get_latest_import_batch(conn: Any, report_type: str) -> dict | None:
    """Return the most recent import_batch row for the given report_type, or None if none exists."""
    cursor = conn.execute(
        """SELECT * FROM import_batch
           WHERE report_type = ?
           ORDER BY imported_at DESC, batch_id DESC
           LIMIT 1""",
        (report_type,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def get_latest_import_rows(conn: sqlite3.Connection, report_type: str) -> list[dict]:
    """Return import_row rows for the most recent batch of the given report_type.
    Latest batch is chosen by imported_at DESC, batch_id DESC for determinism.
    Returns [] if no batch exists for that report_type."""
    cursor = conn.execute(
        """SELECT batch_id FROM import_batch
           WHERE report_type = ?
           ORDER BY imported_at DESC, batch_id DESC
           LIMIT 1""",
        (report_type,),
    )
    row = cursor.fetchone()
    if not row:
        return []
    batch_id = row["batch_id"] if isinstance(row, dict) else row[0]
    return get_import_rows_by_batch(conn, batch_id)


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


def get_last_import_timestamps(conn: Any) -> dict[str, str]:
    """
    Return the most recent imported_at (ISO timestamp) per report_type for
    MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS.
    Keys are report_type; value is imported_at or missing if never imported.
    """
    cursor = conn.execute(
        """SELECT report_type, MAX(imported_at) AS imported_at
           FROM import_batch
           WHERE report_type IN ('MOVE_OUTS', 'PENDING_MOVE_INS', 'AVAILABLE_UNITS', 'PENDING_FAS')
           GROUP BY report_type"""
    )
    result: dict[str, str] = {}
    for row in cursor.fetchall():
        if isinstance(row, dict):
            report_type, imported_at = row.get("report_type"), row.get("imported_at")
        else:
            report_type, imported_at = row[0], row[1]
        if report_type is not None and imported_at:
            result[report_type] = imported_at
    return result


def get_import_diagnostics(conn: Any, since_imported_at: str | None = None) -> list[dict]:
    """
    Return non-OK import_row rows joined to import_batch, deduplicated to most recent
    per (unit_code_norm, report_type). For Import Diagnostics tab.
    Columns: unit_code_norm, report_type, validation_status, conflict_reason, imported_at, source_file_name.
    PostgreSQL and SQLite >= 3.25: window query; SQLite < 3.25: GROUP BY fallback.
    since_imported_at: optional ISO timestamp; only rows with b.imported_at >= this are returned.
    """
    date_filter = "AND (b.imported_at >= ? OR ? IS NULL)"
    params: tuple = (since_imported_at, since_imported_at)

    use_window = (
        getattr(conn, "engine", None) == "postgres"
        or _sqlite_version_ge_325(conn)
    )

    if use_window:
        sql = f"""WITH diag AS (
            SELECT
                r.unit_code_norm,
                b.report_type,
                r.validation_status,
                r.conflict_reason,
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
            unit_code_norm,
            report_type,
            validation_status,
            conflict_reason,
            imported_at,
            source_file_name
        FROM diag
        WHERE rn = 1
        ORDER BY imported_at DESC"""
        cursor = conn.execute(sql, params)
    else:
        sql = f"""WITH base AS (
            SELECT
                r.row_id,
                r.unit_code_norm,
                r.validation_status,
                r.conflict_reason,
                b.report_type,
                b.imported_at,
                b.source_file_name
            FROM import_row r
            JOIN import_batch b ON r.batch_id = b.batch_id
            WHERE r.validation_status != 'OK'
              {date_filter}
        ),
        latest_imported AS (
            SELECT
                unit_code_norm,
                report_type,
                MAX(imported_at) AS max_imported_at
            FROM base
            GROUP BY unit_code_norm, report_type
        ),
        latest_row AS (
            SELECT
                b.unit_code_norm,
                b.report_type,
                b.max_imported_at,
                MAX(base.row_id) AS max_row_id
            FROM latest_imported b
            JOIN base ON base.unit_code_norm = b.unit_code_norm
                AND base.report_type = b.report_type
                AND base.imported_at = b.max_imported_at
            GROUP BY b.unit_code_norm, b.report_type, b.max_imported_at
        )
        SELECT
            base.unit_code_norm,
            base.report_type,
            base.validation_status,
            base.conflict_reason,
            base.imported_at,
            base.source_file_name
        FROM base
        JOIN latest_row l
          ON base.unit_code_norm = l.unit_code_norm
          AND base.report_type = l.report_type
          AND base.imported_at = l.max_imported_at
          AND base.row_id = l.max_row_id
        ORDER BY base.imported_at DESC, base.row_id"""
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
