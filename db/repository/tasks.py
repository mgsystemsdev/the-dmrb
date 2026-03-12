"""Task templates and tasks repository functions."""
from __future__ import annotations

import sqlite3

from db.repository._helpers import (
    TASK_UPDATE_COLS,
    _inserted_id,
    _rows_to_dicts,
)
from db.repository.turnovers import invalidate_turnover_enrichment_cache


def get_active_task_templates(conn: sqlite3.Connection, *, property_id: int):
    cursor = conn.execute(
        """SELECT * FROM task_template
           WHERE property_id = ? AND is_active = 1 ORDER BY sort_order, template_id""",
        (property_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_active_task_templates_by_phase(conn: sqlite3.Connection, *, phase_id: int):
    """
    Get active task templates for a phase. After migration 008 uses phase_id on task_template.
    Until then, looks up property_id from phase and uses get_active_task_templates(property_id).
    """
    try:
        cursor = conn.execute(
            "SELECT * FROM task_template WHERE phase_id = ? AND is_active = 1 ORDER BY sort_order, template_id",
            (phase_id,),
        )
        return _rows_to_dicts(cursor.fetchall())
    except Exception:
        row = conn.execute("SELECT property_id FROM phase WHERE phase_id = ?", (phase_id,)).fetchone()
        if row is None:
            return []
        return get_active_task_templates(conn, property_id=row[0])


def get_task_template_dependencies(conn: sqlite3.Connection, *, template_ids: list):
    if not template_ids:
        return []
    placeholders = ",".join("?" * len(template_ids))
    cursor = conn.execute(
        f"""SELECT template_id, depends_on_template_id FROM task_template_dependency
            WHERE template_id IN ({placeholders})""",
        template_ids,
    )
    return _rows_to_dicts(cursor.fetchall())


DEFAULT_TASK_TYPES = [
    ("Insp", 1, 1),
    ("CB", 1, 0),
    ("MRB", 1, 0),
    ("Paint", 1, 0),
    ("MR", 1, 0),
    ("HK", 1, 0),
    ("CC", 1, 0),
    ("FW", 1, 0),
    ("QC", 1, 1),
]


def insert_task_template(
    conn: sqlite3.Connection,
    *,
    phase_id: int | None = None,
    property_id: int | None = None,
    task_type: str,
    required: int,
    blocking: int,
    sort_order: int,
    is_active: int = 1,
    applies_if_has_carpet: int | None = None,
    applies_if_has_wd_expected: int | None = None,
) -> int:
    """Insert one task_template row. Uses phase_id if table has it (post-008), else property_id."""
    if phase_id is not None:
        try:
            cursor = conn.execute(
                """INSERT INTO task_template (
                    phase_id, task_type, required, blocking, sort_order,
                    applies_if_has_carpet, applies_if_has_wd_expected, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    phase_id,
                    task_type,
                    required,
                    blocking,
                    sort_order,
                    applies_if_has_carpet,
                    applies_if_has_wd_expected,
                    is_active,
                ),
            )
            return _inserted_id(conn, "task_template", "template_id", cursor=cursor)
        except Exception:
            pass
    if property_id is not None:
        cursor = conn.execute(
            """INSERT INTO task_template (
                property_id, task_type, required, blocking, sort_order,
                applies_if_has_carpet, applies_if_has_wd_expected, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                property_id,
                task_type,
                required,
                blocking,
                sort_order,
                applies_if_has_carpet,
                applies_if_has_wd_expected,
                is_active,
            ),
        )
        return _inserted_id(conn, "task_template", "template_id", cursor=cursor)
    raise ValueError("insert_task_template requires phase_id or property_id")


def ensure_default_task_templates(
    conn: sqlite3.Connection,
    *,
    phase_id: int | None = None,
    property_id: int | None = None,
) -> None:
    """
    If the phase (or property) has no active task templates, insert the default set
    so that new turnovers get tasks as soon as they have a move-out date.
    """
    if phase_id is not None:
        templates = get_active_task_templates_by_phase(conn, phase_id=phase_id)
        if templates:
            return
        row = conn.execute("SELECT property_id FROM phase WHERE phase_id = ?", (phase_id,)).fetchone()
        if row is None:
            prop_id = None
        elif isinstance(row, dict):
            prop_id = row.get("property_id")
        else:
            prop_id = row[0]
        for sort_order, (task_type, required, blocking) in enumerate(DEFAULT_TASK_TYPES):
            insert_task_template(
                conn,
                phase_id=phase_id,
                property_id=prop_id,
                task_type=task_type,
                required=required,
                blocking=blocking,
                sort_order=sort_order,
            )
        return
    if property_id is not None:
        templates = get_active_task_templates(conn, property_id=property_id)
        if templates:
            return
        for sort_order, (task_type, required, blocking) in enumerate(DEFAULT_TASK_TYPES):
            insert_task_template(
                conn,
                phase_id=None,
                property_id=property_id,
                task_type=task_type,
                required=required,
                blocking=blocking,
                sort_order=sort_order,
            )
        return
    raise ValueError("ensure_default_task_templates requires phase_id or property_id")


def insert_task_dependency(conn: sqlite3.Connection, data: dict) -> None:
    conn.execute(
        """INSERT INTO task_dependency (task_id, depends_on_task_id) VALUES (?, ?)""",
        (data["task_id"], data["depends_on_task_id"]),
    )


def get_tasks_by_turnover(conn: sqlite3.Connection, turnover_id: int):
    cursor = conn.execute(
        "SELECT * FROM task WHERE turnover_id = ? ORDER BY task_type",
        (turnover_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def get_tasks_for_turnover_ids(conn: sqlite3.Connection, turnover_ids: list) -> list:
    """Batch fetch tasks for given turnover_ids. Returns list of rows."""
    if not turnover_ids:
        return []
    placeholders = ",".join("?" * len(turnover_ids))
    cursor = conn.execute(
        f"SELECT * FROM task WHERE turnover_id IN ({placeholders}) ORDER BY turnover_id, task_type",
        turnover_ids,
    )
    return _rows_to_dicts(cursor.fetchall())


def insert_task(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """INSERT INTO task (
            turnover_id, task_type, required, blocking,
            scheduled_date, vendor_due_date,
            vendor_completed_at, manager_confirmed_at,
            execution_status, confirmation_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["turnover_id"],
            data["task_type"],
            data["required"],
            data["blocking"],
            data.get("scheduled_date"),
            data.get("vendor_due_date"),
            data.get("vendor_completed_at"),
            data.get("manager_confirmed_at"),
            data["execution_status"],
            data["confirmation_status"],
        ),
    )
    task_id = _inserted_id(conn, "task", "task_id", cursor=cursor)
    turnover_id = data.get("turnover_id")
    if turnover_id is not None:
        invalidate_turnover_enrichment_cache(conn, int(turnover_id))
    return task_id


def update_task_fields(conn: sqlite3.Connection, task_id: int, fields: dict, *, strict: bool = True) -> None:
    allowed = {k: v for k, v in fields.items() if k in TASK_UPDATE_COLS}
    if strict:
        unknown = set(fields.keys()) - TASK_UPDATE_COLS
        if unknown:
            raise ValueError(f"Unknown task fields: {sorted(unknown)}")
    if not allowed:
        return
    set_clause = ", ".join(f"{k} = ?" for k in allowed)
    values = list(allowed.values()) + [task_id]
    conn.execute(
        f"UPDATE task SET {set_clause} WHERE task_id = ?",
        values,
    )
    row = conn.execute("SELECT turnover_id FROM task WHERE task_id = ?", (task_id,)).fetchone()
    if row is not None:
        invalidate_turnover_enrichment_cache(conn, int(row["turnover_id"]))
