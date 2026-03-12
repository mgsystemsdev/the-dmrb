"""Turnover and enrichment cache repository functions."""
from __future__ import annotations

import json
from datetime import datetime

import sqlite3

from db.repository._helpers import (
    TURNOVER_UPDATE_COLS,
    _inserted_id,
    _row_to_dict,
    _rows_to_dicts,
)
from db.repository.risks import _ensure_confirmation_invariant


def invalidate_turnover_enrichment_cache(conn, turnover_id: int) -> None:
    """Best-effort cache invalidation for one turnover."""
    try:
        conn.execute(
            "DELETE FROM turnover_enrichment_cache WHERE turnover_id = ?",
            (turnover_id,),
        )
    except Exception:
        return


def get_enrichment_cache_for_turnover_ids(conn, turnover_ids: list[int], *, as_of_date: str) -> dict[int, dict]:
    """Return {turnover_id: cached_enriched_fields} for rows matching as_of_date."""
    if not turnover_ids:
        return {}
    unique_ids = list(dict.fromkeys(x for x in turnover_ids if x is not None))
    if not unique_ids:
        return {}
    placeholders = ",".join("?" * len(unique_ids))
    try:
        rows = conn.execute(
            f"""SELECT turnover_id, cache_payload FROM turnover_enrichment_cache
                WHERE turnover_id IN ({placeholders}) AND as_of_date = ?""",
            unique_ids + [as_of_date],
        ).fetchall()
    except Exception:
        return {}
    out: dict[int, dict] = {}
    for row in rows:
        try:
            payload = json.loads(row["cache_payload"] or "{}")
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            out[row["turnover_id"]] = payload
    return out


def upsert_turnover_enrichment_cache(conn, *, turnover_id: int, as_of_date: str, payload: dict) -> None:
    """Store enrichment payload for turnover and date."""
    now_iso = datetime.utcnow().isoformat()
    payload_json = json.dumps(payload or {}, separators=(",", ":"), sort_keys=True)
    try:
        conn.execute(
            """INSERT INTO turnover_enrichment_cache (turnover_id, as_of_date, cache_payload, refreshed_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(turnover_id) DO UPDATE SET
                 as_of_date = excluded.as_of_date,
                 cache_payload = excluded.cache_payload,
                 refreshed_at = excluded.refreshed_at""",
            (turnover_id, as_of_date, payload_json, now_iso),
        )
    except Exception:
        return


def list_open_turnovers_by_property(conn: sqlite3.Connection, *, property_id: int):
    cursor = conn.execute(
        """SELECT * FROM turnover
           WHERE property_id = ? AND closed_at IS NULL AND canceled_at IS NULL
             AND move_out_date IS NOT NULL""",
        (property_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def list_open_turnovers(
    conn: sqlite3.Connection,
    *,
    property_ids: list | None = None,
    phase_ids: list | None = None,
):
    """
    Open turnovers. If both are None, return all.
    If phase_ids is set, filter by unit.phase_id IN (phase_ids) via join.
    Else if property_ids is set, filter by turnover.property_id IN (property_ids).
    """
    if phase_ids is not None:
        if not phase_ids:
            return []
        placeholders = ",".join("?" * len(phase_ids))
        cursor = conn.execute(
            f"""SELECT t.* FROM turnover t
                JOIN unit u ON t.unit_id = u.unit_id
                WHERE u.phase_id IN ({placeholders})
                  AND t.closed_at IS NULL AND t.canceled_at IS NULL
                  AND t.move_out_date IS NOT NULL""",
            phase_ids,
        )
        return _rows_to_dicts(cursor.fetchall())
    if property_ids is None:
        cursor = conn.execute(
            """SELECT * FROM turnover
               WHERE closed_at IS NULL AND canceled_at IS NULL
                 AND move_out_date IS NOT NULL""",
        )
        return _rows_to_dicts(cursor.fetchall())
    if not property_ids:
        return []
    placeholders = ",".join("?" * len(property_ids))
    cursor = conn.execute(
        f"""SELECT * FROM turnover
            WHERE property_id IN ({placeholders}) AND closed_at IS NULL AND canceled_at IS NULL
              AND move_out_date IS NOT NULL""",
        property_ids,
    )
    return _rows_to_dicts(cursor.fetchall())


def get_turnover_by_id(conn: sqlite3.Connection, turnover_id: int):
    cursor = conn.execute(
        "SELECT * FROM turnover WHERE turnover_id = ?",
        (turnover_id,),
    )
    return _row_to_dict(cursor.fetchone())


def get_open_turnover_by_unit(conn: sqlite3.Connection, unit_id: int):
    cursor = conn.execute(
        """SELECT * FROM turnover
           WHERE unit_id = ? AND closed_at IS NULL AND canceled_at IS NULL""",
        (unit_id,),
    )
    return _row_to_dict(cursor.fetchone())


def insert_turnover(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """INSERT INTO turnover (
            property_id, unit_id, source_turnover_key, move_out_date, move_in_date, report_ready_date,
            manual_ready_status, manual_ready_confirmed_at, expedited_flag,
            wd_present, wd_supervisor_notified, wd_notified_at, wd_installed, wd_installed_at,
            closed_at, canceled_at, cancel_reason, last_seen_moveout_batch_id, missing_moveout_count,
            created_at, updated_at,
            scheduled_move_out_date, confirmed_move_out_date,
            legal_confirmation_source, legal_confirmed_at, legal_confirmation_note,
            available_date, availability_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["property_id"],
            data["unit_id"],
            data["source_turnover_key"],
            data["move_out_date"],
            data.get("move_in_date"),
            data.get("report_ready_date"),
            data.get("manual_ready_status"),
            data.get("manual_ready_confirmed_at"),
            data.get("expedited_flag", 0),
            data.get("wd_present"),
            data.get("wd_supervisor_notified"),
            data.get("wd_notified_at"),
            data.get("wd_installed"),
            data.get("wd_installed_at"),
            data.get("closed_at"),
            data.get("canceled_at"),
            data.get("cancel_reason"),
            data.get("last_seen_moveout_batch_id"),
            data.get("missing_moveout_count", 0),
            data["created_at"],
            data["updated_at"],
            data.get("scheduled_move_out_date"),
            data.get("confirmed_move_out_date"),
            data.get("legal_confirmation_source"),
            data.get("legal_confirmed_at"),
            data.get("legal_confirmation_note"),
            data.get("available_date"),
            data.get("availability_status"),
        ),
    )
    turnover_id = _inserted_id(conn, "turnover", "turnover_id", cursor=cursor)
    _ensure_confirmation_invariant(conn, turnover_id)
    invalidate_turnover_enrichment_cache(conn, turnover_id)
    return turnover_id


def update_turnover_fields(conn: sqlite3.Connection, turnover_id: int, fields: dict, *, strict: bool = True) -> None:
    allowed = {k: v for k, v in fields.items() if k in TURNOVER_UPDATE_COLS}
    if strict:
        unknown = set(fields.keys()) - TURNOVER_UPDATE_COLS
        if unknown:
            raise ValueError(f"Unknown turnover fields: {sorted(unknown)}")
    if not allowed:
        return
    set_clause = ", ".join(f"{k} = ?" for k in allowed)
    values = list(allowed.values()) + [turnover_id]
    conn.execute(
        f"UPDATE turnover SET {set_clause} WHERE turnover_id = ?",
        values,
    )
    invalidate_turnover_enrichment_cache(conn, turnover_id)
    _ensure_confirmation_invariant(conn, turnover_id)
