"""SLA events repository functions."""
from __future__ import annotations

import sqlite3

from db.repository._helpers import _inserted_id, _row_to_dict


def get_open_sla_event(conn: sqlite3.Connection, turnover_id: int):
    cursor = conn.execute(
        """SELECT * FROM sla_event
           WHERE turnover_id = ? AND breach_resolved_at IS NULL""",
        (turnover_id,),
    )
    return _row_to_dict(cursor.fetchone())


def insert_sla_event(conn: sqlite3.Connection, data: dict) -> int:
    try:
        cursor = conn.execute(
            """INSERT INTO sla_event (
                 turnover_id, breach_started_at, breach_resolved_at,
                 opened_anchor_date, current_anchor_date, evaluated_threshold_days
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                data["turnover_id"],
                data["breach_started_at"],
                data.get("breach_resolved_at"),
                data.get("opened_anchor_date"),
                data.get("current_anchor_date"),
                data.get("evaluated_threshold_days"),
            ),
        )
        return _inserted_id(conn, "sla_event", "sla_event_id", cursor=cursor)
    except Exception:
        cursor = conn.execute(
            """INSERT INTO sla_event (turnover_id, breach_started_at, breach_resolved_at)
               VALUES (?, ?, ?)""",
            (
                data["turnover_id"],
                data["breach_started_at"],
                data.get("breach_resolved_at"),
            ),
        )
        return _inserted_id(conn, "sla_event", "sla_event_id", cursor=cursor)


def close_sla_event(conn: sqlite3.Connection, sla_event_id: int, resolved_at: str) -> None:
    conn.execute(
        "UPDATE sla_event SET breach_resolved_at = ? WHERE sla_event_id = ?",
        (resolved_at, sla_event_id),
    )


def update_sla_event_current_anchor(conn: sqlite3.Connection, sla_event_id: int, current_anchor_date: str) -> None:
    try:
        conn.execute(
            "UPDATE sla_event SET current_anchor_date = ? WHERE sla_event_id = ?",
            (current_anchor_date, sla_event_id),
        )
    except Exception:
        return
