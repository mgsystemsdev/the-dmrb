from __future__ import annotations

import glob
import os

from db.adapters.base_adapter import ConnectionWrapper


def _current_schema_version(conn: ConnectionWrapper) -> int:
    """Return the current schema_version, or 0 if the table doesn't exist yet."""
    try:
        row = conn.execute("SELECT version FROM schema_version WHERE singleton = 1").fetchone()
        if row is None:
            return 0
        return row["version"] if isinstance(row, dict) else row[0]
    except Exception:
        return 0


def _apply_migrations(conn: ConnectionWrapper) -> None:
    """Run any numbered migration files whose number exceeds the current schema_version."""
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    if not os.path.isdir(migrations_dir):
        return
    current = _current_schema_version(conn)
    files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))
    for fpath in files:
        basename = os.path.basename(fpath)
        # Extract leading number, e.g. "014_property_id_identity.sql" → 14
        num_str = basename.split("_", 1)[0]
        try:
            num = int(num_str)
        except ValueError:
            continue
        if num <= current:
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.execute(
            "UPDATE schema_version SET version = %s WHERE singleton = 1",
            (num,),
        )
        conn.commit()


def ensure_postgres_ready(conn: ConnectionWrapper) -> None:
    schema_path = os.path.join(os.path.dirname(__file__), "postgres_schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    _apply_migrations(conn)
