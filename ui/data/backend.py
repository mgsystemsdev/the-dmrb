"""
Backend availability and service refs for UI layer.
Importing this module triggers loading of db and services; use from app entrypoint and cache only.
"""
from __future__ import annotations

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
