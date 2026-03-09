import os
import tempfile

from db.connection import ensure_database_ready, get_connection


def _db_with_schema_and_version_12():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    conn = get_connection(path)
    schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
    with open(schema_path, encoding="utf-8") as fp:
        conn.executescript(fp.read())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (singleton INTEGER PRIMARY KEY CHECK (singleton=1), version INTEGER NOT NULL)"
    )
    conn.execute("INSERT OR REPLACE INTO schema_version (singleton, version) VALUES (1, 12)")
    conn.commit()
    conn.close()
    return path


def test_ensure_database_ready_repairs_missing_migration_003_columns():
    path = _db_with_schema_and_version_12()
    try:
        ensure_database_ready(path)
        conn = get_connection(path)
        try:
            task_cols = {r["name"] for r in conn.execute("PRAGMA table_info(task)").fetchall()}
            turnover_cols = {r["name"] for r in conn.execute("PRAGMA table_info(turnover)").fetchall()}
            assert "assignee" in task_cols
            assert "blocking_reason" in task_cols
            assert "wd_present_type" in turnover_cols
        finally:
            conn.close()
    finally:
        os.unlink(path)
