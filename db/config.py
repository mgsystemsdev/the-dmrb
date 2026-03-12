from __future__ import annotations

import os

from db.adapters.base_adapter import DatabaseConfig
from config.settings import get_settings


def resolve_database_config(db_path_override: str | None = None) -> DatabaseConfig:
    """
    Resolve database configuration for the current environment.

    - When TEST_MODE=true: use a local SQLite database (for tests/offline runs).
    - Otherwise: use the configured Postgres/Supabase URL (production behavior).
    """
    if os.getenv("TEST_MODE", "").lower() == "true":
        # Tests use SQLite and must not attempt any Postgres connection.
        sqlite_path = db_path_override or "test_runtime.db"
        return DatabaseConfig(engine="sqlite", sqlite_path=sqlite_path, postgres_url=None)

    settings = get_settings()
    engine = settings.database_engine.strip().lower()
    if engine != "postgres":
        raise ValueError("DB_ENGINE must be 'postgres'")
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL required for postgres engine")
    postgres_url = settings.database_url
    return DatabaseConfig(engine=engine, sqlite_path="", postgres_url=postgres_url)
