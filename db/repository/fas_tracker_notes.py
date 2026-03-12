"""FAS tracker notes: annotations for Pending FAS report rows."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from db.repository._helpers import _row_to_dict


def get_fas_note(conn: Any, *, unit_id: int, fas_date: str) -> dict | None:
    """Return the fas_tracker_notes row for (unit_id, fas_date), or None."""
    cursor = conn.execute(
        "SELECT unit_id, fas_date, note_text, updated_at FROM fas_tracker_notes WHERE unit_id = ? AND fas_date = ?",
        (unit_id, fas_date),
    )
    return _row_to_dict(cursor.fetchone())


def upsert_fas_tracker_note(conn: Any, *, unit_id: int, fas_date: str, note_text: str) -> None:
    """Insert or update note for (unit_id, fas_date)."""
    updated_at = datetime.utcnow().isoformat()
    conn.execute(
        """INSERT INTO fas_tracker_notes (unit_id, fas_date, note_text, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT (unit_id, fas_date) DO UPDATE SET note_text = excluded.note_text, updated_at = excluded.updated_at""",
        (unit_id, fas_date, note_text or "", updated_at),
    )
