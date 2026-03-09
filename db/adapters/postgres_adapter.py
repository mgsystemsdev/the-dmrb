from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from db.adapters.base_adapter import BaseAdapter, ConnectionWrapper, DatabaseConfig


class PostgresAdapter(BaseAdapter):
    engine = "postgres"

    def connect(self, config: DatabaseConfig | None = None, db_path: str | None = None) -> ConnectionWrapper:
        if config is None or not config.postgres_url:
            raise RuntimeError("Postgres adapter requires DatabaseConfig with postgres_url")
        conn = psycopg.connect(config.postgres_url, row_factory=dict_row)
        return ConnectionWrapper(conn, engine=self.engine)
