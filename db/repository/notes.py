"""Notes repository functions."""
from __future__ import annotations

import sqlite3

from db.repository._helpers import _inserted_id, _row_to_dict, _rows_to_dicts


def get_note_by_id(conn: sqlite3.Connection, note_id: int):
    cursor = conn.execute("SELECT * FROM note WHERE note_id = ?", (note_id,))
    return _row_to_dict(cursor.fetchone())


def get_notes_by_turnover(conn: sqlite3.Connection, turnover_id: int):
    cursor = conn.execute(
        "SELECT * FROM note WHERE turnover_id = ? ORDER BY note_id",
        (turnover_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def insert_note(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """INSERT INTO note (turnover_id, note_type, blocking, severity, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (
            data["turnover_id"],
            data["note_type"],
            data["blocking"],
            data["severity"],
            data["description"],
            data["created_at"],
        ),
    )
    return _inserted_id(conn, "note", "note_id", cursor=cursor)


def update_note_resolved(conn: sqlite3.Connection, note_id: int, resolved_at: str) -> None:
    conn.execute(
        "UPDATE note SET resolved_at = ? WHERE note_id = ?",
        (resolved_at, note_id),
    )


def get_notes_for_turnover_ids(conn: sqlite3.Connection, turnover_ids: list, *, unresolved_only: bool = True) -> list:
    """Batch fetch notes for given turnover_ids. If unresolved_only=True, only notes with resolved_at IS NULL."""
    if not turnover_ids:
        return []
    placeholders = ",".join("?" * len(turnover_ids))
    if unresolved_only:
        cursor = conn.execute(
            f"""SELECT * FROM note WHERE turnover_id IN ({placeholders}) AND resolved_at IS NULL ORDER BY turnover_id, note_id""",
            turnover_ids,
        )
    else:
        cursor = conn.execute(
            f"SELECT * FROM note WHERE turnover_id IN ({placeholders}) ORDER BY turnover_id, note_id",
            turnover_ids,
        )
    return _rows_to_dicts(cursor.fetchall())
