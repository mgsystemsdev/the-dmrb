import os
import sqlite3
import tempfile
from contextlib import contextmanager

from db.connection import ensure_database_ready, get_connection


def create_runtime_db_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def bootstrap_runtime_db(path: str | None = None) -> tuple[sqlite3.Connection, str]:
    """
    Bootstrap a runtime database for tests.

    - Forces TEST_MODE=true so the connection layer uses SQLite.
    - Initializes schema + migrations via ensure_database_ready.
    - Returns a SQLite connection and the DB path.
    """
    os.environ["TEST_MODE"] = "true"
    # Use provided path when specified; otherwise default to a stable test file.
    db_path = path or "test_runtime.db"
    ensure_database_ready(db_path)
    conn = get_connection(db_path)
    conn.row_factory = sqlite3.Row
    return conn, db_path


@contextmanager
def runtime_db(path: str | None = None):
    conn, db_path = bootstrap_runtime_db(path)
    try:
        yield conn, db_path
    finally:
        conn.close()
        try:
            os.unlink(db_path)
        except OSError:
            pass
