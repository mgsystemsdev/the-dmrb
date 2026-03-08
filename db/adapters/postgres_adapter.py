from __future__ import annotations

from db.adapters.base_adapter import BaseAdapter, ConnectionWrapper, DatabaseConfig


class PostgresAdapter(BaseAdapter):
    engine = "postgres"

    def connect(self, config: DatabaseConfig | None = None, db_path: str | None = None) -> ConnectionWrapper:
        raise NotImplementedError("Postgres adapter scaffold exists, runtime support is not enabled yet.")
