#!/usr/bin/env python3
"""
Verify connection to Supabase Postgres. Run from repo root:
  python test_supabase_connection.py

Loads DATABASE_URL from .streamlit/secrets.toml or DATABASE_URL env var.
Uses same options as the app (prepare_threshold=None for pooler, dict_row).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _get_database_url() -> str | None:
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
    return None


def main() -> None:
    url = _get_database_url()
    if not url:
        print("DATABASE_URL not set. Set the env var or add it to .streamlit/secrets.toml", file=sys.stderr)
        sys.exit(1)
    try:
        conn = psycopg.connect(
            url,
            row_factory=dict_row,
            prepare_threshold=None,
        )
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        if "Circuit breaker" in str(e) or "upstream database" in str(e).lower():
            print(
                "\nThis usually means the Supabase project is paused or the DB is starting. "
                "Open https://supabase.com/dashboard → your project → Restore project if paused, then try again.",
                file=sys.stderr,
            )
        sys.exit(1)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
        host = conn.info.host
        port = conn.info.port
        conn.close()
    except Exception as e:
        print(f"Query failed: {e}", file=sys.stderr)
        conn.close()
        sys.exit(1)
    print(f"OK: connected to {host}:{port}")
    print(f"  host = {host!r}, port = {port}")


if __name__ == "__main__":
    main()
