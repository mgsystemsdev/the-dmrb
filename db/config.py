from __future__ import annotations

import os

from db.adapters.base_adapter import DatabaseConfig
from config.settings import get_settings


def resolve_database_config(db_path_override: str | None = None) -> DatabaseConfig:
    settings = get_settings()
    engine = (os.environ.get("DB_ENGINE") or settings.database_engine).strip().lower()
    if engine not in {"sqlite", "postgres"}:
        raise ValueError("DB_ENGINE must be 'sqlite' or 'postgres'")
    sqlite_path = db_path_override or os.environ.get("COCKPIT_DB_PATH") or settings.database_path
    postgres_url = os.environ.get("DATABASE_URL")
    return DatabaseConfig(engine=engine, sqlite_path=sqlite_path, postgres_url=postgres_url)
