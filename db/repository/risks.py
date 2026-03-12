"""Risk flags repository functions."""
from __future__ import annotations

from datetime import datetime

import sqlite3

from db.repository._helpers import _inserted_id, _rows_to_dicts
from db.repository.imports import insert_audit_log


def get_active_risks_by_turnover(conn: sqlite3.Connection, turnover_id: int):
    cursor = conn.execute(
        "SELECT * FROM risk_flag WHERE turnover_id = ? AND resolved_at IS NULL",
        (turnover_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def upsert_risk(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """SELECT risk_id FROM risk_flag
           WHERE turnover_id = ? AND risk_type = ? AND resolved_at IS NULL""",
        (data["turnover_id"], data["risk_type"]),
    )
    row = cursor.fetchone()
    if row is not None:
        return row[0]
    cursor = conn.execute(
        """INSERT INTO risk_flag (turnover_id, risk_type, severity, triggered_at, auto_resolve)
           VALUES (?, ?, ?, ?, ?)""",
        (
            data["turnover_id"],
            data["risk_type"],
            data["severity"],
            data["triggered_at"],
            data.get("auto_resolve", 1),
        ),
    )
    return _inserted_id(conn, "risk_flag", "risk_id", cursor=cursor)


def _ensure_confirmation_invariant(conn: sqlite3.Connection, turnover_id: int) -> None:
    """
    Enforce: IF legal_confirmation_source IS NOT NULL THEN confirmed_move_out_date MUST NOT be NULL.
    On violation, do NOT crash; instead:
      - upsert risk_flag(DATA_INTEGRITY)
      - insert audit_log: field_name="confirmed_invariant_violation",
        new_value="legal_source_without_date", source="system".
    """
    try:
        cursor = conn.execute(
            "SELECT legal_confirmation_source, confirmed_move_out_date "
            "FROM turnover WHERE turnover_id = ?",
            (turnover_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return
        source = row["legal_confirmation_source"]
        confirmed = row["confirmed_move_out_date"]
        if source is not None and (confirmed is None or str(confirmed).strip() == ""):
            now_iso = datetime.utcnow().isoformat()
            upsert_risk(
                conn,
                {
                    "turnover_id": turnover_id,
                    "risk_type": "DATA_INTEGRITY",
                    "severity": "CRITICAL",
                    "triggered_at": now_iso,
                    "auto_resolve": 0,
                },
            )
            insert_audit_log(
                conn,
                {
                    "entity_type": "turnover",
                    "entity_id": turnover_id,
                    "field_name": "confirmed_invariant_violation",
                    "old_value": None,
                    "new_value": "legal_source_without_date",
                    "changed_at": now_iso,
                    "actor": "system",
                    "source": "system",
                    "correlation_id": None,
                },
            )
    except Exception:
        pass


def resolve_risk(conn: sqlite3.Connection, risk_id: int, resolved_at: str) -> None:
    conn.execute(
        "UPDATE risk_flag SET resolved_at = ? WHERE risk_id = ?",
        (resolved_at, risk_id),
    )
