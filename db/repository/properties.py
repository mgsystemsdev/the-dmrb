"""Property, phase, and building repository functions."""
from __future__ import annotations

import sqlite3

from db.errors import DatabaseIntegrityError
from db.repository._helpers import _inserted_id, _row_to_dict, _rows_to_dicts


def list_properties(conn: sqlite3.Connection) -> list:
    """Return all properties. Each row has property_id, name."""
    cursor = conn.execute("SELECT * FROM property ORDER BY property_id")
    return _rows_to_dicts(cursor.fetchall())


def insert_property(conn: sqlite3.Connection, name: str) -> int | None:
    """Insert a property and return the database-generated property_id."""
    try:
        cursor = conn.execute(
            "INSERT INTO property (name) VALUES (%s) RETURNING property_id",
            (name,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return row.get("property_id")
        return row[0]
    except DatabaseIntegrityError as exc:
        if getattr(conn, "engine", None) != "postgres":
            raise
        if 'null value in column "property_id"' not in str(exc):
            raise
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()

    conn.execute("LOCK TABLE property IN EXCLUSIVE MODE")
    row = conn.execute("SELECT COALESCE(MAX(property_id), 0) + 1 AS next_property_id FROM property").fetchone()
    next_property_id = row["next_property_id"] if isinstance(row, dict) else row[0]
    cursor = conn.execute(
        "INSERT INTO property (property_id, name) VALUES (%s, %s) RETURNING property_id",
        (next_property_id, name),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get("property_id")
    return row[0]


def list_phases(conn: sqlite3.Connection, *, property_id: int | None = None) -> list:
    """Return all phases, optionally filtered by property_id. Each row has phase_id, property_id, phase_code, name."""
    if property_id is not None:
        cursor = conn.execute(
            "SELECT * FROM phase WHERE property_id = ? ORDER BY phase_code",
            (property_id,),
        )
    else:
        cursor = conn.execute("SELECT * FROM phase ORDER BY property_id, phase_code")
    return _rows_to_dicts(cursor.fetchall())


def get_first_phase_for_property(conn: sqlite3.Connection, property_id: int):
    """Return first phase row for property (by phase_code), or None. Used to scope task templates when unit has no phase_id."""
    cursor = conn.execute(
        "SELECT * FROM phase WHERE property_id = ? ORDER BY phase_code LIMIT 1",
        (property_id,),
    )
    return _row_to_dict(cursor.fetchone())


def list_buildings(conn: sqlite3.Connection, *, phase_id: int | None = None) -> list:
    """Return all buildings, optionally filtered by phase_id. Each row has building_id, phase_id, building_code."""
    if phase_id is not None:
        cursor = conn.execute(
            "SELECT * FROM building WHERE phase_id = ? ORDER BY building_code",
            (phase_id,),
        )
    else:
        cursor = conn.execute("SELECT * FROM building ORDER BY phase_id, building_code")
    return _rows_to_dicts(cursor.fetchall())


def get_phase(conn: sqlite3.Connection, *, property_id: int, phase_code: str):
    """Look up phase by (property_id, phase_code). Returns row as dict or None. Read-only; does not create."""
    cursor = conn.execute(
        "SELECT * FROM phase WHERE property_id = ? AND phase_code = ?",
        (property_id, phase_code),
    )
    row = cursor.fetchone()
    return dict(row) if row is not None else None


def get_building(conn: sqlite3.Connection, *, phase_id: int, building_code: str):
    """Look up building by (phase_id, building_code). Returns row as dict or None. Read-only; does not create."""
    cursor = conn.execute(
        "SELECT * FROM building WHERE phase_id = ? AND building_code = ?",
        (phase_id, building_code),
    )
    row = cursor.fetchone()
    return dict(row) if row is not None else None


def resolve_phase(conn: sqlite3.Connection, *, property_id: int, phase_code: str) -> dict:
    """Get or create phase for (property_id, phase_code). Returns phase row as dict."""
    cursor = conn.execute(
        "SELECT * FROM phase WHERE property_id = ? AND phase_code = ?",
        (property_id, phase_code),
    )
    row = cursor.fetchone()
    if row is not None:
        return dict(row)
    conn.execute(
        "INSERT INTO phase (property_id, phase_code) VALUES (?, ?)",
        (property_id, phase_code),
    )
    phase_id = _inserted_id(conn, "phase", "phase_id")
    cursor = conn.execute("SELECT * FROM phase WHERE phase_id = ?", (phase_id,))
    return dict(cursor.fetchone())


def resolve_building(conn: sqlite3.Connection, *, phase_id: int, building_code: str) -> dict:
    """Get or create building for (phase_id, building_code). Returns building row as dict."""
    cursor = conn.execute(
        "SELECT * FROM building WHERE phase_id = ? AND building_code = ?",
        (phase_id, building_code),
    )
    row = cursor.fetchone()
    if row is not None:
        return dict(row)
    conn.execute(
        "INSERT INTO building (phase_id, building_code) VALUES (?, ?)",
        (phase_id, building_code),
    )
    building_id = _inserted_id(conn, "building", "building_id")
    cursor = conn.execute("SELECT * FROM building WHERE building_id = ?", (building_id,))
    return dict(cursor.fetchone())
