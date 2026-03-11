from db.adapters import get_adapter
from db.adapters.base_adapter import ConnectionWrapper
from db.config import resolve_database_config
from db.postgres_bootstrap import ensure_postgres_ready
from db.sqlite_bootstrap import (
    backup_sqlite_database,
    ensure_sqlite_ready,
    initialize_sqlite_database,
    run_sqlite_integrity_check,
)

def get_connection(db_path: str | None = None) -> ConnectionWrapper:
    config = resolve_database_config(db_path_override=db_path)
    adapter = get_adapter(config)
    return adapter.connect(config)


def initialize_database(db_path: str, schema_path: str) -> None:
    conn = None
    try:
        conn = get_connection(db_path)
        if conn.engine == "postgres":
            ensure_postgres_ready(conn)
            return
        if conn.engine == "sqlite":
            initialize_sqlite_database(conn, db_path, schema_path)
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
        if conn.engine == "sqlite":
            run_sqlite_integrity_check(conn)
            return
        raise RuntimeError(f"Unsupported database engine: {conn.engine}")
    finally:
        if conn is not None:
            conn.close()


def backup_database(db_path: str, backup_dir: str, batch_id: int) -> str:
    config = resolve_database_config(db_path_override=db_path)
    if config.engine == "sqlite":
        return backup_sqlite_database(db_path, backup_dir, batch_id)
    raise RuntimeError("Backup not implemented for postgres")


def ensure_database_ready(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        if conn.engine == "postgres":
            ensure_postgres_ready(conn)
            return
        if conn.engine == "sqlite":
            ensure_sqlite_ready(conn)
            return
        raise RuntimeError(f"Unsupported database engine: {conn.engine}")
    finally:
        conn.close()
