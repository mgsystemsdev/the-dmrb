import sqlite3
from datetime import datetime

def _row_to_dict(row):
    if row is None:
        return None
    return dict(row)

def _rows_to_dicts(rows):
    return [dict(r) for r in rows]

# Allowed columns for dynamic UPDATE (avoid injection).
# When strict=True, update_*_fields raise ValueError on unknown keys.
TURNOVER_UPDATE_COLS = frozenset({
    "property_id", "unit_id", "source_turnover_key", "move_out_date", "move_in_date", "report_ready_date",
    "manual_ready_status", "manual_ready_confirmed_at", "expedited_flag",
    "wd_present", "wd_supervisor_notified", "wd_notified_at", "wd_installed", "wd_installed_at",
    "wd_present_type",
    "closed_at", "canceled_at", "cancel_reason", "last_seen_moveout_batch_id", "missing_moveout_count",
    "created_at", "updated_at",
    "scheduled_move_out_date", "confirmed_move_out_date",
    "legal_confirmation_source", "legal_confirmed_at", "legal_confirmation_note",
    "available_date", "availability_status",
    "move_out_manual_override_at", "ready_manual_override_at",
    "move_in_manual_override_at", "status_manual_override_at",
    "last_import_move_out_date", "last_import_ready_date",
    "last_import_move_in_date", "last_import_status",
})
TASK_UPDATE_COLS = frozenset({
    "turnover_id", "task_type", "required", "blocking",
    "scheduled_date", "vendor_due_date",
    "vendor_completed_at", "manager_confirmed_at",
    "execution_status", "confirmation_status",
    "assignee", "blocking_reason",
})
UNIT_UPDATE_COLS = frozenset({
    "unit_code_raw", "has_carpet", "has_wd_expected", "is_active",
    "phase_code", "building_code", "unit_number", "unit_identity_key",
    "phase_id", "building_id", "floor_plan", "gross_sq_ft", "bed_count", "bath_count", "layout_code",
})


def get_unit_by_id(conn: sqlite3.Connection, unit_id: int):
    cursor = conn.execute("SELECT * FROM unit WHERE unit_id = ?", (unit_id,))
    return _row_to_dict(cursor.fetchone())


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
    phase_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
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
    building_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    cursor = conn.execute("SELECT * FROM building WHERE building_id = ?", (building_id,))
    return dict(cursor.fetchone())


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
    # Create unit: bridge schema still has property_id and UNIQUE(property_id, unit_identity_key)
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
    # Bridge schema: unit has phase_id, building_id, floor_plan, gross_sq_ft (nullable)
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
    return cursor.lastrowid


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


def list_properties(conn: sqlite3.Connection) -> list:
    """Return all properties. Each row has property_id, name."""
    cursor = conn.execute("SELECT * FROM property ORDER BY property_id")
    return _rows_to_dicts(cursor.fetchall())


def insert_property(conn: sqlite3.Connection, name: str) -> int:
    """Insert a property with next available property_id. Returns property_id."""
    row = conn.execute("SELECT COALESCE(MAX(property_id), 0) + 1 FROM property").fetchone()
    next_id = row[0]
    conn.execute("INSERT INTO property (property_id, name) VALUES (?, ?)", (next_id, name))
    return next_id


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
    except sqlite3.OperationalError:
        # phase_id column not yet on task_template (pre-008): resolve via phase -> property_id
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


# Default task types for ensure_default_task_templates (order = sort_order).
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
            return cursor.lastrowid
        except sqlite3.OperationalError:
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
        return cursor.lastrowid
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
        prop_id = row[0] if row else None
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


def list_open_turnovers_by_property(conn: sqlite3.Connection, *, property_id: int):
    cursor = conn.execute(
        """SELECT * FROM turnover
           WHERE property_id = ? AND closed_at IS NULL AND canceled_at IS NULL""",
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
                  AND t.closed_at IS NULL AND t.canceled_at IS NULL""",
            phase_ids,
        )
        return _rows_to_dicts(cursor.fetchall())
    if property_ids is None:
        cursor = conn.execute(
            """SELECT * FROM turnover
               WHERE closed_at IS NULL AND canceled_at IS NULL""",
        )
        return _rows_to_dicts(cursor.fetchall())
    if not property_ids:
        return []
    placeholders = ",".join("?" * len(property_ids))
    cursor = conn.execute(
        f"""SELECT * FROM turnover
            WHERE property_id IN ({placeholders}) AND closed_at IS NULL AND canceled_at IS NULL""",
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
    turnover_id = cursor.lastrowid
    _ensure_confirmation_invariant(conn, turnover_id)
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
    _ensure_confirmation_invariant(conn, turnover_id)


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
    return cursor.lastrowid


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
    return cursor.lastrowid


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
    return cursor.lastrowid


def _ensure_confirmation_invariant(conn: sqlite3.Connection, turnover_id: int) -> None:
    """
    Enforce: IF legal_confirmation_source IS NOT NULL THEN confirmed_move_out_date MUST NOT be NULL.
    On violation, do NOT crash; instead:
      - upsert risk_flag(DATA_INTEGRITY)
      - insert audit_log: field_name=\"confirmed_invariant_violation\",
        new_value=\"legal_source_without_date\", source=\"system\".
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
        # Hard safety: invariant checks must never break write paths.
        pass


def resolve_risk(conn: sqlite3.Connection, risk_id: int, resolved_at: str) -> None:
    conn.execute(
        "UPDATE risk_flag SET resolved_at = ? WHERE risk_id = ?",
        (resolved_at, risk_id),
    )


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
        return cursor.lastrowid
    except sqlite3.OperationalError:
        # Pre-migration schema: sla_event has only (turnover_id, breach_started_at, breach_resolved_at)
        cursor = conn.execute(
            """INSERT INTO sla_event (turnover_id, breach_started_at, breach_resolved_at)
               VALUES (?, ?, ?)""",
            (
                data["turnover_id"],
                data["breach_started_at"],
                data.get("breach_resolved_at"),
            ),
        )
        return cursor.lastrowid


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
    except sqlite3.OperationalError:
        # Pre-migration schema: column does not exist.
        return


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
    return cursor.lastrowid


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
    return cursor.lastrowid


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
    return cursor.lastrowid
