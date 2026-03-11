from db.adapters.base_adapter import ConnectionWrapper, DatabaseConfig
from db.adapters.postgres_adapter import PostgresAdapter


def get_adapter(config: DatabaseConfig):
    if config.engine == "postgres":
        return PostgresAdapter()
    raise RuntimeError(f"Unsupported database engine: {config.engine}")


__all__ = ["ConnectionWrapper", "DatabaseConfig", "get_adapter"]
