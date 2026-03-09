from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from db.adapters.base_adapter import BaseAdapter, ConnectionWrapper, DatabaseConfig


class PostgresAdapter(BaseAdapter):
    engine = "postgres"

    def connect(self, config: DatabaseConfig | None = None, db_path: str | None = None) -> ConnectionWrapper:
        if config is None or not config.postgres_url:
            raise RuntimeError("Postgres adapter requires DatabaseConfig with postgres_url")
        # prepare_threshold=None: required for Supabase/Supavisor transaction mode (port 6543)
        conn = psycopg.connect(
            config.postgres_url,
            row_factory=dict_row,
            prepare_threshold=None,
        )
        return ConnectionWrapper(conn, engine=self.engine)
