"""
Backend availability and service refs for UI layer.
Importing this module triggers loading of db and services; use from app entrypoint and cache only.

This module is also responsible for a one-time, backend-only bootstrap that:
- Ensures the database schema/migrations are applied.
- Runs global maintenance like backfilling missing tasks.

The bootstrap runs at most once per process, respects SKIP_DB_BOOTSTRAP, and never calls Streamlit APIs.
"""
from __future__ import annotations

import os

from ui.actions.db import db_write as ui_db_write, get_conn as ui_get_conn, get_db_path as ui_get_db_path

BACKEND_AVAILABLE = False
BACKEND_ERROR: Exception | None = None
db_repository = None
board_query_service = None
export_service_mod = None
import_service_mod = None
manual_availability_service_mod = None
note_service_mod = None
property_service_mod = None
task_service_mod = None
turnover_service_mod = None
unit_master_import_service_mod = None
unit_service_mod = None
get_connection = None
ensure_database_ready = None

_BOOTSTRAPPED = False


def _bootstrap_once() -> None:
    """
    One-time backend bootstrap for this process.

    - Honors SKIP_DB_BOOTSTRAP.
    - Ensures the database is schema-initialized and migrated.
    - Backfills missing tasks for open turnovers.
    - Never uses Streamlit; exceptions are swallowed so UI can still start.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    # Honor SKIP_DB_BOOTSTRAP for local workflows and tests.
    skip = os.getenv("SKIP_DB_BOOTSTRAP", "").strip().lower()
    if skip in ("1", "true", "yes", "on", "y"):
        _BOOTSTRAPPED = True
        return

    if not BACKEND_AVAILABLE or get_connection is None:
        _BOOTSTRAPPED = True
        return

    db_path = ui_get_db_path()

    # Ensure DB is schema-initialized and migrated before any read path.
    try:
        if ensure_database_ready is not None:
            ensure_database_ready(db_path)
    except Exception:
        # Match previous behavior: initialization failures should not hard-crash the UI.
        pass

    # Backfill tasks for any open turnovers that have none (one-time reconciliation).
    if turnover_service_mod is not None:
        conn = None
        try:
            conn = get_connection(db_path)
            backfilled = turnover_service_mod.reconcile_missing_tasks(conn)
            if backfilled:
                conn.commit()
        except Exception:
            # Any failure here should not block backend availability.
            pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    _BOOTSTRAPPED = True


def bootstrap_backend_once() -> None:
    """
    One-time backend bootstrap for this process. Safe to call from app entrypoint.
    Honors SKIP_DB_BOOTSTRAP; ensures DB schema and runs reconcile_missing_tasks.
    Does not use Streamlit. Exported for use from app.py.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    skip = os.getenv("SKIP_DB_BOOTSTRAP", "").strip().lower()
    if skip in ("1", "true", "yes", "on", "y"):
        _BOOTSTRAPPED = True
        return

    if get_connection is None or ensure_database_ready is None or turnover_service_mod is None:
        _BOOTSTRAPPED = True
        return

    ensure_database_ready(get_db_path())

    conn = get_connection(get_db_path())
    try:
        backfilled = turnover_service_mod.reconcile_missing_tasks(conn)
        if backfilled:
            conn.commit()
    finally:
        conn.close()

    _BOOTSTRAPPED = True


try:
    from db.connection import get_connection as _get_connection, ensure_database_ready as _ensure_database_ready
    from db import repository as db_repository
    from services import board_query_service
    from services import export_service as export_service_mod
    from services import import_service as import_service_mod
    from services import manual_availability_service as manual_availability_service_mod
    from services import note_service as note_service_mod
    from services import property_service as property_service_mod
    from services import task_service as task_service_mod
    from services import turnover_service as turnover_service_mod
    from services import unit_master_import_service as unit_master_import_service_mod
    from services import unit_service as unit_service_mod

    get_connection = _get_connection
    ensure_database_ready = _ensure_database_ready
    BACKEND_AVAILABLE = True

    # Execute backend bootstrap once when services are available.
    _bootstrap_once()
except Exception as e:
    BACKEND_ERROR = e
    db_repository = None
    board_query_service = None
    export_service_mod = None
    import_service_mod = None
    manual_availability_service_mod = None
    note_service_mod = None
    property_service_mod = None
    task_service_mod = None
    turnover_service_mod = None
    unit_master_import_service_mod = None
    unit_service_mod = None


def get_conn():
    return ui_get_conn(BACKEND_AVAILABLE)


def db_write(do_write):
    return ui_db_write(
        do_write,
        backend_available=BACKEND_AVAILABLE and turnover_service_mod is not None,
    )


def get_db_path() -> str:
    return ui_get_db_path()
