import os
import shutil
import sqlite3
from datetime import datetime, timezone


def get_connection(db_path: str) -> sqlite3.Connection:
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(db_path: str, schema_path: str) -> None:
    conn = None
    try:
        if not os.path.isfile(db_path):
            conn = get_connection(db_path)
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            conn.executescript(schema_sql)
            conn.commit()
    finally:
        if conn is not None:
            conn.close()


def run_integrity_check(db_path: str) -> None:
    conn = None
    try:
        conn = get_connection(db_path)
        cursor = conn.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        if result is None or result[0] != "ok":
            raise RuntimeError("Database integrity check failed. Restore from backup.")
    finally:
        if conn is not None:
            conn.close()


def backup_database(db_path: str, backup_dir: str, batch_id: int) -> str:
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_batch_{batch_id}.db"
    dest_path = os.path.join(backup_dir, filename)
    shutil.copy2(db_path, dest_path)
    return os.path.abspath(dest_path)


# Migration scripts applied in order; version N means 001..N applied.
_MIGRATIONS = [
    (1, "001_add_report_ready_date.sql"),
    (2, "002_add_exposure_risk_type.sql"),
    (3, "003_add_assignee_blocking_wd_type.sql"),
    (4, "004_add_unit_identity_columns.sql"),
    (5, "005_add_phase_building.sql"),
    (6, "006_add_unit_attrs.sql"),
    (7, "007_add_unit_hierarchy_fk.sql"),
    (8, "008_task_template_phase_id.sql"),
    (9, "009_add_legal_and_availability_columns.sql"),
    (10, "010_add_sla_event_anchor_snapshot.sql"),
    (11, "011_add_manual_override_timestamps.sql"),
    (12, "012_add_last_import_columns.sql"),
]


def _backfill_task_template_phase_id(conn: sqlite3.Connection) -> None:
    """
    After 008: backfill task_template.phase_id from property_id (1:1 mapping).
    Create phase(property_id, phase_code=str(property_id)) for each distinct property_id in task_template,
    then recreate task_template with phase_id NOT NULL, UNIQUE(phase_id, task_type, is_active), no property_id.
    """
    cursor = conn.execute("SELECT DISTINCT property_id FROM task_template")
    for row in cursor.fetchall():
        pid = row[0]
        phase_code = str(pid)
        r = conn.execute(
            "SELECT phase_id FROM phase WHERE property_id = ? AND phase_code = ?",
            (pid, phase_code),
        ).fetchone()
        if r is not None:
            phase_id = r[0]
        else:
            conn.execute(
                "INSERT INTO phase (property_id, phase_code) VALUES (?, ?)",
                (pid, phase_code),
            )
            phase_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "UPDATE task_template SET phase_id = ? WHERE property_id = ?",
            (phase_id, pid),
        )
    # Recreate task_template without property_id
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        """
        CREATE TABLE task_template_new (
          template_id INTEGER PRIMARY KEY,
          phase_id INTEGER NOT NULL REFERENCES phase(phase_id),
          task_type TEXT NOT NULL,
          required INTEGER NOT NULL CHECK(required IN (0, 1)),
          blocking INTEGER NOT NULL CHECK(blocking IN (0, 1)),
          sort_order INTEGER NOT NULL,
          applies_if_has_carpet INTEGER CHECK(applies_if_has_carpet IN (0, 1)),
          applies_if_has_wd_expected INTEGER CHECK(applies_if_has_wd_expected IN (0, 1)),
          is_active INTEGER NOT NULL CHECK(is_active IN (0, 1)),
          UNIQUE(phase_id, task_type, is_active),
          CHECK(task_type <> '')
        )
        """
    )
    conn.execute(
        """INSERT INTO task_template_new (
             template_id, phase_id, task_type, required, blocking, sort_order,
             applies_if_has_carpet, applies_if_has_wd_expected, is_active
           ) SELECT
             template_id, phase_id, task_type, required, blocking, sort_order,
             applies_if_has_carpet, applies_if_has_wd_expected, is_active
           FROM task_template"""
    )
    conn.execute("DROP TABLE task_template")
    conn.execute("ALTER TABLE task_template_new RENAME TO task_template")
    conn.execute("PRAGMA foreign_keys = ON")


def _backfill_hierarchy(conn: sqlite3.Connection) -> None:
    """
    After 007: create phase/building rows from existing units and set unit.phase_id, unit.building_id.
    Uses unit_code_norm and domain.unit_identity.parse_unit_parts (already backfilled in 004).
    Fails loudly on parse errors.
    """
    from domain import unit_identity

    cursor = conn.execute(
        "SELECT unit_id, property_id, unit_code_norm FROM unit"
    )
    rows = cursor.fetchall()
    if not rows:
        return
    for row in rows:
        uid = row["unit_id"]
        pid = row["property_id"]
        norm = row["unit_code_norm"]
        try:
            phase_code, building_code, unit_number = unit_identity.parse_unit_parts(norm)
        except ValueError as e:
            raise RuntimeError(f"Unit unit_id={uid} unit_code_norm={norm!r}: {e}") from e
        # Get or create phase
        r = conn.execute(
            "SELECT phase_id FROM phase WHERE property_id = ? AND phase_code = ?",
            (pid, phase_code),
        ).fetchone()
        if r is not None:
            phase_id = r[0]
        else:
            conn.execute(
                "INSERT INTO phase (property_id, phase_code) VALUES (?, ?)",
                (pid, phase_code),
            )
            phase_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # Get or create building
        r = conn.execute(
            "SELECT building_id FROM building WHERE phase_id = ? AND building_code = ?",
            (phase_id, building_code),
        ).fetchone()
        if r is not None:
            building_id = r[0]
        else:
            conn.execute(
                "INSERT INTO building (phase_id, building_code) VALUES (?, ?)",
                (phase_id, building_code),
            )
            building_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "UPDATE unit SET phase_id = ?, building_id = ? WHERE unit_id = ?",
            (phase_id, building_id, uid),
        )


def _backfill_unit_identity(conn: sqlite3.Connection) -> None:
    """
    Backfill phase_code, building_code, unit_number, unit_identity_key for all units
    using domain.unit_identity. Then recreate unit table with NOT NULL + UNIQUE(property_id, unit_identity_key).
    Fails loudly on parse errors or duplicate (property_id, unit_identity_key).
    """
    from domain import unit_identity

    cursor = conn.execute(
        "SELECT unit_id, property_id, unit_code_raw, unit_code_norm FROM unit"
    )
    rows = cursor.fetchall()
    if not rows:
        # No units: still recreate table with NOT NULL columns; insert none.
        conn.execute("PRAGMA foreign_keys = OFF")
        _recreate_unit_table(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        return
    for row in rows:
        uid = row["unit_id"]
        norm = row["unit_code_norm"]
        try:
            pc, bc, un = unit_identity.parse_unit_parts(norm)
            key = unit_identity.compose_identity_key(pc, bc, un)
        except ValueError as e:
            raise RuntimeError(f"Unit unit_id={uid} unit_code_norm={norm!r}: {e}") from e
        conn.execute(
            "UPDATE unit SET phase_code = ?, building_code = ?, unit_number = ?, unit_identity_key = ? WHERE unit_id = ?",
            (pc, bc, un, key, row["unit_id"]),
        )

    # Check for duplicates; fail loudly with conflicting rows
    dup_pairs = conn.execute(
        """SELECT property_id, unit_identity_key FROM unit
           WHERE unit_identity_key IS NOT NULL
           GROUP BY property_id, unit_identity_key HAVING COUNT(*) > 1"""
    ).fetchall()
    if dup_pairs:
        lines = ["Duplicate (property_id, unit_identity_key) found:"]
        for pair in dup_pairs:
            pid, key = pair["property_id"], pair["unit_identity_key"]
            conflict = conn.execute(
                "SELECT unit_id, property_id, unit_code_raw, unit_code_norm, unit_identity_key FROM unit WHERE property_id = ? AND unit_identity_key = ?",
                (pid, key),
            ).fetchall()
            for c in conflict:
                lines.append(
                    f"  property_id={c['property_id']}, unit_id={c['unit_id']}, "
                    f"unit_code_raw={c['unit_code_raw']!r}, unit_code_norm={c['unit_code_norm']!r}, "
                    f"unit_identity_key={c['unit_identity_key']!r}"
                )
        raise RuntimeError("\n".join(lines))

    # Recreate unit table with NOT NULL and UNIQUE(property_id, unit_identity_key)
    conn.execute("PRAGMA foreign_keys = OFF")
    _recreate_unit_table(conn)
    conn.execute("PRAGMA foreign_keys = ON")


def _recreate_unit_table(conn: sqlite3.Connection) -> None:
    """Create unit_new with identity columns NOT NULL + UNIQUE(property_id, unit_identity_key), copy from unit, drop, rename."""
    conn.execute(
        """
        CREATE TABLE unit_new (
          unit_id INTEGER PRIMARY KEY,
          property_id INTEGER NOT NULL REFERENCES property(property_id),
          unit_code_raw TEXT NOT NULL,
          unit_code_norm TEXT NOT NULL,
          has_carpet INTEGER NOT NULL DEFAULT 0 CHECK(has_carpet IN (0, 1)),
          has_wd_expected INTEGER NOT NULL DEFAULT 0 CHECK(has_wd_expected IN (0, 1)),
          is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
          phase_code TEXT NOT NULL,
          building_code TEXT NOT NULL,
          unit_number TEXT NOT NULL,
          unit_identity_key TEXT NOT NULL CHECK(unit_identity_key <> ''),
          UNIQUE(property_id, unit_code_norm),
          UNIQUE(property_id, unit_identity_key),
          CHECK(unit_code_norm <> '')
        )
        """
    )
    conn.execute(
        """INSERT INTO unit_new (
             unit_id, property_id, unit_code_raw, unit_code_norm,
             has_carpet, has_wd_expected, is_active,
             phase_code, building_code, unit_number, unit_identity_key
           ) SELECT
             unit_id, property_id, unit_code_raw, unit_code_norm,
             has_carpet, has_wd_expected, is_active,
             phase_code, building_code, unit_number, unit_identity_key
           FROM unit"""
    )
    conn.execute("DROP TABLE unit")
    conn.execute("ALTER TABLE unit_new RENAME TO unit")


def ensure_database_ready(db_path: str) -> None:
    """
    Ensure DB exists, schema is applied, and migrations 001–010 are applied.
    Raises on any failure. Idempotent; safe to call on every startup.
    """
    _db_dir = os.path.dirname(os.path.abspath(__file__))
    schema_path = os.path.join(_db_dir, "schema.sql")
    migrations_dir = os.path.join(_db_dir, "migrations")

    conn = get_connection(db_path)
    try:
        # 1) Ensure schema: if turnover table missing, run schema.sql (even if file exists)
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'turnover' LIMIT 1"
        )
        if cur.fetchone() is None:
            with open(schema_path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.commit()
            # schema.sql is current (includes 001–003); skip those migrations
            conn.execute("UPDATE schema_version SET version = 3 WHERE singleton = 1")
            conn.commit()

        # 2) Ensure schema_version exists and has a row
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version' LIMIT 1"
        )
        if cur.fetchone() is None:
            conn.execute(
                """
                CREATE TABLE schema_version (
                  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                  version INTEGER NOT NULL
                )
                """
            )
            conn.execute("INSERT INTO schema_version (singleton, version) VALUES (1, 0)")
            conn.commit()

        cur = conn.execute("SELECT version FROM schema_version WHERE singleton = 1 LIMIT 1")
        row = cur.fetchone()
        current = row[0] if row is not None else 0

        # 3) Apply migrations in order, commit per migration
        for n, filename in _MIGRATIONS:
            if current >= n:
                continue
            path = os.path.join(migrations_dir, filename)
            with open(path, "r", encoding="utf-8") as f:
                sql = f.read()
            conn.executescript(sql)
            if n == 4:
                _backfill_unit_identity(conn)
            if n == 7:
                _backfill_hierarchy(conn)
            if n == 8:
                _backfill_task_template_phase_id(conn)
            conn.execute("UPDATE schema_version SET version = ? WHERE singleton = 1", (n,))
            conn.commit()
            current = n
    finally:
        conn.close()
