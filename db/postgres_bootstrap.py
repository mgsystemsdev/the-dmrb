from __future__ import annotations

import os

from db.adapters.base_adapter import ConnectionWrapper


def ensure_postgres_ready(conn: ConnectionWrapper) -> None:
    schema_path = os.path.join(os.path.dirname(__file__), "postgres_schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
