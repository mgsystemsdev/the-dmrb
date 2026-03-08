import os

from db.config import resolve_database_config


def test_resolve_database_config_defaults_to_sqlite(monkeypatch):
    monkeypatch.delenv("DB_ENGINE", raising=False)
    monkeypatch.delenv("COCKPIT_DB_PATH", raising=False)
    cfg = resolve_database_config()
    assert cfg.engine == "sqlite"
    assert cfg.sqlite_path.endswith("data/cockpit.db")


def test_resolve_database_config_for_postgres(monkeypatch):
    monkeypatch.setenv("DB_ENGINE", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/dmrb")
    cfg = resolve_database_config()
    assert cfg.engine == "postgres"
    assert cfg.postgres_url == "postgresql://u:p@localhost:5432/dmrb"
