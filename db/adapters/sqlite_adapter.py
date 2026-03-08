from __future__ import annotations

import os
import sqlite3

from db.adapters.base_adapter import BaseAdapter, ConnectionWrapper, DatabaseConfig
from config.settings import get_settings


class SqliteAdapter(BaseAdapter):
    engine = "sqlite"

    def connect(self, config: DatabaseConfig | None = None, db_path: str | None = None) -> ConnectionWrapper:
        resolved_path = db_path
        if resolved_path is None and config is not None:
            resolved_path = config.sqlite_path
        if resolved_path is None:
            resolved_path = get_settings().database_path
        db_path = resolved_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.row_factory = sqlite3.Row
        return ConnectionWrapper(conn, engine=self.engine)
