import os

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


def _initialize_sqlite_schema(conn: ConnectionWrapper) -> None:
    """
    Initialize SQLite schema + migrations for test/runtime DB.

    This is used only when TEST_MODE=true or when the resolved engine is sqlite.
    """
    base_dir = os.path.dirname(__file__)
    schema_path = os.path.join(base_dir, "schema.sql")

    # Apply base schema only. The schema file is expected to represent the
    # latest state, so migrations are not required for fresh test databases.
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    conn.commit()


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
