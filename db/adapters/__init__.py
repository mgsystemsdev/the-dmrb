from db.adapters.base_adapter import ConnectionWrapper, DatabaseConfig
from db.adapters.postgres_adapter import PostgresAdapter
from db.adapters.sqlite_adapter import SqliteAdapter


def get_adapter(config: DatabaseConfig):
    if config.engine == "postgres":
        return PostgresAdapter()
    return SqliteAdapter()


__all__ = ["ConnectionWrapper", "DatabaseConfig", "get_adapter"]
