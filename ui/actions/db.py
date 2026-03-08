from __future__ import annotations

import streamlit as st

from config.settings import get_settings
from db.connection import get_connection


def get_db_path() -> str:
    return get_settings().database_path


def get_conn(backend_available: bool):
    if not backend_available:
        return None
    try:
        return get_connection(get_db_path())
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
        return True
    except Exception as exc:
        conn.rollback()
        st.error(str(exc))
        return False
    finally:
        conn.close()
