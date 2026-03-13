import glob
import os
import sqlite3

from db.adapters import get_adapter
from db.adapters.base_adapter import ConnectionWrapper
from db.config import resolve_database_config
from db.postgres_bootstrap import ensure_postgres_ready


def get_connection(db_path: str | None = None) -> ConnectionWrapper:
    """
    Return a database connection based on the resolved config.

    - In TEST_MODE=true: returns a SQLite-backed ConnectionWrapper.
    - Otherwise: returns a Postgres/Supabase ConnectionWrapper.
    """
    config = resolve_database_config(db_path_override=db_path)
    adapter = get_adapter(config)
    # For SQLite we ignore db_path and use config.sqlite_path; for Postgres db_path is unused.
    return adapter.connect(config, db_path=db_path)


def initialize_database(db_path: str, schema_path: str) -> None:
    """
    Initialize the database for non-test environments.

    Tests should rely on ensure_database_ready + TEST_MODE.
    """
    conn = None
    try:
        conn = get_connection(db_path)
        if conn.engine == "postgres":
            ensure_postgres_ready(conn)
            return
        raise RuntimeError(f"Unsupported database engine: {conn.engine}")
    finally:
        if conn is not None:
            conn.close()


def run_integrity_check(db_path: str) -> None:
    conn = None
    try:
        conn = get_connection(db_path)
        if conn.engine == "postgres":
            return
        raise RuntimeError(f"Unsupported database engine: {conn.engine}")
    finally:
        if conn is not None:
            conn.close()


def backup_database(db_path: str, backup_dir: str, batch_id: int) -> str:
    raise RuntimeError("Backup not implemented for postgres")


def _current_schema_version_sqlite(conn: ConnectionWrapper) -> int:
    """Return the current schema_version for SQLite, or 0 if missing."""
    try:
        row = conn.execute("SELECT version FROM schema_version WHERE singleton = 1").fetchone()
        if row is None:
            return 0
        return row["version"] if isinstance(row, dict) else row[0]
    except Exception:
        return 0


def _apply_sqlite_migrations(conn: ConnectionWrapper) -> None:
    """Run migration files in order and update schema_version (SQLite placeholder style)."""
    base_dir = os.path.dirname(__file__)
    migrations_dir = os.path.join(base_dir, "migrations")
    if not os.path.isdir(migrations_dir):
        return
    current = _current_schema_version_sqlite(conn)
    files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))
    for fpath in files:
        basename = os.path.basename(fpath)
        num_str = basename.split("_", 1)[0]
        try:
            num = int(num_str)
        except ValueError:
            continue
        if num <= current:
            continue
        # 001: report_ready_date may already exist in schema.sql; guard so migration is safe to run multiple times.
        if num == 1:
            rows = conn.execute("PRAGMA table_info(turnover)").fetchall()
            columns = [row[1] for row in rows]
            if "report_ready_date" not in columns:
                conn.execute("ALTER TABLE turnover ADD COLUMN report_ready_date TEXT")
            conn.execute(
                "UPDATE schema_version SET version = ? WHERE singleton = 1",
                (num,),
            )
            conn.commit()
            continue
        # 014 is Postgres-only (IDENTITY / DO $$); SQLite uses INTEGER PRIMARY KEY auto-increment.
        if num == 14:
            conn.execute(
                "UPDATE schema_version SET version = ? WHERE singleton = 1",
                (num,),
            )
            conn.commit()
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
        except sqlite3.OperationalError as e:
            # schema.sql may already include columns/tables from earlier migrations.
            # Treat duplicate column/table as already applied and continue.
            msg = str(e).lower()
            if "duplicate column" in msg or "duplicate column name" in msg or "already exists" in msg:
                pass  # no-op, still bump version below
            else:
                raise
        conn.execute(
            "UPDATE schema_version SET version = ? WHERE singleton = 1",
            (num,),
        )
        conn.commit()


def _initialize_sqlite_schema(conn: ConnectionWrapper) -> None:
    """
    Initialize SQLite schema + migrations for test/runtime DB.

    Applies schema.sql then runs migrations so that phase, building, and other
    migration-added structures exist (e.g. for import pipelines that resolve units).
    """
    base_dir = os.path.dirname(__file__)
    schema_path = os.path.join(base_dir, "schema.sql")

    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    conn.commit()
    _apply_sqlite_migrations(conn)


def ensure_database_ready(db_path: str) -> None:
    """
    Ensure the database is ready for use.

    - In TEST_MODE=true (or when engine=sqlite): initialize a local SQLite DB from schema.sql + migrations.
    - Otherwise: delegate to Postgres bootstrap logic (unchanged production behavior).
    """
    config = resolve_database_config(db_path_override=db_path)
    adapter = get_adapter(config)

    # SQLite / test mode: initialize local file if empty or missing.
    if config.engine == "sqlite":
        sqlite_path = config.sqlite_path
        # For tests we always want a fresh, isolated database. If the file
        # already exists, remove it so schema.sql can be applied cleanly.
        if os.path.exists(sqlite_path):
            try:
                os.unlink(sqlite_path)
            except OSError:
                pass
        conn = adapter.connect(config, db_path=db_path)
        try:
            _initialize_sqlite_schema(conn)
        finally:
            conn.close()
        return

    # Production path: Postgres only.
    conn = adapter.connect(config, db_path=db_path)
    try:
        if conn.engine == "postgres":
            ensure_postgres_ready(conn)
            return
        raise RuntimeError(f"Unsupported database engine: {conn.engine}")
    finally:
        conn.close()
