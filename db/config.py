from __future__ import annotations

import os

from db.adapters.base_adapter import DatabaseConfig
from config.settings import get_settings


def resolve_database_config(db_path_override: str | None = None) -> DatabaseConfig:
    settings = get_settings()
    engine = settings.database_engine.strip().lower()
    if engine not in {"sqlite", "postgres"}:
        raise ValueError("DB_ENGINE must be 'sqlite' or 'postgres'")
    if engine == "postgres":
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL required for postgres engine")
    sqlite_path = db_path_override or os.environ.get("COCKPIT_DB_PATH") or settings.database_path
    postgres_url = settings.database_url
    return DatabaseConfig(engine=engine, sqlite_path=sqlite_path, postgres_url=postgres_url)
