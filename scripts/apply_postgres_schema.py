#!/usr/bin/env python3
"""
Apply db/postgres_schema.sql to the Postgres database.

Reads DATABASE_URL from environment or .streamlit/secrets.toml, connects with
psycopg, executes the schema SQL, commits, and prints success.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    secrets_path = _repo_root() / ".streamlit" / "secrets.toml"
    if secrets_path.is_file():
        try:
            import tomllib
        except ImportError:
            pass
        else:
            with open(secrets_path, "rb") as f:
                secrets = tomllib.load(f)
            url = secrets.get("DATABASE_URL")
            if url:
                return url
    raise SystemExit(
        "DATABASE_URL not set. Set the environment variable or add DATABASE_URL to .streamlit/secrets.toml"
    )


def main() -> None:
    url = _get_database_url()
    schema_path = _repo_root() / "db" / "postgres_schema.sql"
    if not schema_path.is_file():
        raise SystemExit(f"Schema file not found: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for raw in schema_sql.split(";"):
                stmt = raw.strip()
                if not stmt:
                    continue
                first_line = stmt.split("\n")[0].strip()
                if first_line.startswith("--"):
                    continue
                cur.execute(stmt)
        conn.commit()

    print("Schema creation finished successfully.")


if __name__ == "__main__":
    main()
