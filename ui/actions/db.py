from __future__ import annotations

import streamlit as st

from config.settings import get_settings
from db.connection import get_connection


def get_db_path() -> str:
    """Path used for SQLite; for Postgres this is only used as a logical identifier (e.g. ensure_database_ready)."""
    return get_settings().database_path


def get_conn(backend_available: bool):
    if not backend_available:
        return None
    try:
        settings = get_settings()
        # Postgres: use config from settings (DATABASE_URL); no file path.
        # SQLite: pass path so resolve_database_config uses it for sqlite_path.
        db_path_override = None if settings.database_engine == "postgres" else get_db_path()
        return get_connection(db_path_override)
    except Exception:
        return None


def db_write(do_write, *, backend_available: bool):
    if not st.session_state.get("enable_db_writes"):
        return False
    conn = get_conn(backend_available)
    if not conn:
        st.error("Database not available")
        return False
    try:
        do_write(conn)
        conn.commit()
        st.cache_data.clear()
        return True
    except Exception as exc:
        conn.rollback()
        st.error(str(exc))
        return False
    finally:
        conn.close()
