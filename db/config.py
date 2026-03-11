from __future__ import annotations

from db.adapters.base_adapter import DatabaseConfig
from config.settings import get_settings


def resolve_database_config(db_path_override: str | None = None) -> DatabaseConfig:
    settings = get_settings()
    engine = settings.database_engine.strip().lower()
    if engine != "postgres":
        raise ValueError("DB_ENGINE must be 'postgres'")
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL required for postgres engine")
    postgres_url = settings.database_url
    return DatabaseConfig(engine=engine, sqlite_path="", postgres_url=postgres_url)
