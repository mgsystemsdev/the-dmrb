"""Unit CRUD and resolution repository functions."""
from __future__ import annotations

import sqlite3

from db.repository._helpers import (
    UNIT_UPDATE_COLS,
    _inserted_id,
    _row_to_dict,
    _rows_to_dicts,
)
from db.repository.properties import (
    get_building,
    get_phase,
    resolve_building,
    resolve_phase,
)


def get_unit_by_id(conn: sqlite3.Connection, unit_id: int):
    cursor = conn.execute("SELECT * FROM unit WHERE unit_id = ?", (unit_id,))
    return _row_to_dict(cursor.fetchone())


def list_unit_master_import_units(conn):
    """Return importer-written unit fields only, ordered by raw unit code."""
    cursor = conn.execute(
        """
        SELECT
            unit_code_raw,
            floor_plan AS unit_type,
            gross_sq_ft AS square_feet
        FROM unit
        ORDER BY unit_code_raw
        """
    )
    return _rows_to_dicts(cursor.fetchall())


def get_unit_by_norm(conn: sqlite3.Connection, *, property_id: int, unit_code_norm: str):
    cursor = conn.execute(
        "SELECT * FROM unit WHERE property_id = ? AND unit_code_norm = ?",
        (property_id, unit_code_norm),
    )
    return _row_to_dict(cursor.fetchone())


def get_unit_by_identity_key(conn: sqlite3.Connection, *, property_id: int, unit_identity_key: str):
    """Look up unit by (property_id, unit_identity_key). Returns row or None."""
    cursor = conn.execute(
        "SELECT * FROM unit WHERE property_id = ? AND unit_identity_key = ?",
        (property_id, unit_identity_key),
    )
    return _row_to_dict(cursor.fetchone())


def get_unit_by_building_and_number(conn: sqlite3.Connection, *, building_id: int, unit_number: str):
    """Look up unit by (building_id, unit_number). Returns row or None."""
    cursor = conn.execute(
        "SELECT * FROM unit WHERE building_id = ? AND unit_number = ?",
        (building_id, unit_number),
    )
    return _row_to_dict(cursor.fetchone())


def resolve_unit(
    conn: sqlite3.Connection,
    *,
    property_id: int,
    phase_code: str,
    building_code: str,
    unit_number: str,
    unit_code_raw: str = "",
    unit_code_norm: str = "",
    unit_identity_key: str = "",
    has_carpet: int = 0,
    has_wd_expected: int = 0,
    is_active: int = 1,
    floor_plan: str | None = None,
    gross_sq_ft: int | None = None,
    **kwargs,
) -> dict:
    """
    Get or create unit by (property_id, phase_code, building_code, unit_number).
    Uses resolve_phase, resolve_building, then get_unit_by_building_and_number or insert_unit.
    Returns unit row as dict. Bridge: still uses property_id for insert and UNIQUE(property_id, unit_identity_key).
    """
    phase_row = resolve_phase(conn, property_id=property_id, phase_code=phase_code)
    phase_id = phase_row["phase_id"]
    building_row = resolve_building(conn, phase_id=phase_id, building_code=building_code)
    building_id = building_row["building_id"]
    row = get_unit_by_building_and_number(conn, building_id=building_id, unit_number=unit_number)
    if row is not None:
        return dict(row)
    unit_id = insert_unit(
        conn,
        {
            "property_id": property_id,
            "unit_code_raw": unit_code_raw or unit_number,
            "unit_code_norm": unit_code_norm or unit_number,
            "has_carpet": has_carpet,
            "has_wd_expected": has_wd_expected,
            "is_active": is_active,
            "phase_code": phase_code,
            "building_code": building_code,
            "unit_number": unit_number,
            "unit_identity_key": unit_identity_key or unit_number,
            "phase_id": phase_id,
            "building_id": building_id,
            "floor_plan": floor_plan,
            "gross_sq_ft": gross_sq_ft,
        },
    )
    row = conn.execute("SELECT * FROM unit WHERE unit_id = ?", (unit_id,)).fetchone()
    return dict(row)


def get_units_by_ids(conn: sqlite3.Connection, unit_ids: list) -> list:
    """Batch fetch units by id. Returns list of rows."""
    if not unit_ids:
        return []
    unique_ids = list(dict.fromkeys(x for x in unit_ids if x is not None))
    if not unique_ids:
        return []
    placeholders = ",".join("?" * len(unique_ids))
    cursor = conn.execute(
        f"SELECT * FROM unit WHERE unit_id IN ({placeholders})",
        unique_ids,
    )
    return _rows_to_dicts(cursor.fetchall())


def insert_unit(conn: sqlite3.Connection, data: dict) -> int:
    cols = [
        "property_id", "unit_code_raw", "unit_code_norm", "has_carpet", "has_wd_expected", "is_active",
        "phase_code", "building_code", "unit_number", "unit_identity_key",
    ]
    vals = [
        data["property_id"],
        data["unit_code_raw"],
        data["unit_code_norm"],
        data.get("has_carpet", 0),
        data.get("has_wd_expected", 0),
        data.get("is_active", 1),
        data["phase_code"],
        data["building_code"],
        data["unit_number"],
        data["unit_identity_key"],
    ]
    if data.get("phase_id") is not None:
        cols.append("phase_id")
        vals.append(data["phase_id"])
    if data.get("building_id") is not None:
        cols.append("building_id")
        vals.append(data["building_id"])
    for opt in ("floor_plan", "gross_sq_ft", "bed_count", "bath_count", "layout_code"):
        if opt in data and data[opt] is not None:
            cols.append(opt)
            vals.append(data[opt])
    placeholders = ",".join("?" * len(cols))
    col_list = ", ".join(cols)
    cursor = conn.execute(
        f"INSERT INTO unit ({col_list}) VALUES ({placeholders})",
        vals,
    )
    return _inserted_id(conn, "unit", "unit_id", cursor=cursor)


def update_unit_fields(conn: sqlite3.Connection, unit_id: int, fields: dict, *, strict: bool = True) -> None:
    allowed = {k: v for k, v in fields.items() if k in UNIT_UPDATE_COLS}
    if strict:
        unknown = set(fields.keys()) - UNIT_UPDATE_COLS
        if unknown:
            raise ValueError(f"Unknown unit fields: {sorted(unknown)}")
    if not allowed:
        return
    set_clause = ", ".join(f"{k} = ?" for k in allowed)
    values = list(allowed.values()) + [unit_id]
    conn.execute(
        f"UPDATE unit SET {set_clause} WHERE unit_id = ?",
        values,
    )


def list_units(conn: sqlite3.Connection, *, building_id: int | None = None) -> list:
    """Return units, optionally filtered by building_id. Each row has unit_id, building_id, phase_id, unit_number, etc."""
    if building_id is not None:
        cursor = conn.execute(
            "SELECT * FROM unit WHERE building_id = ? ORDER BY unit_number",
            (building_id,),
        )
    else:
        cursor = conn.execute("SELECT * FROM unit ORDER BY building_id, unit_number")
    return _rows_to_dicts(cursor.fetchall())
