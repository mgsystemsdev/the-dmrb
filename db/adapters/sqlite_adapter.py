from __future__ import annotations

import sqlite3

from db.adapters.base_adapter import BaseAdapter, ConnectionWrapper, DatabaseConfig


class SQLiteAdapter(BaseAdapter):
    engine = "sqlite"

    def connect(self, config: DatabaseConfig | None = None, db_path: str | None = None) -> ConnectionWrapper:
        """
        Connect to a SQLite database.

        - Prefer config.sqlite_path when provided.
        - Fallback to db_path (for backwards compatibility).
        """
        if config is not None and config.sqlite_path:
            path = config.sqlite_path
        elif db_path is not None:
            path = db_path
        else:
            # In tests we always pass a path one way or another; this is defensive.
            path = "test_runtime.db"
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return ConnectionWrapper(conn, engine=self.engine)

