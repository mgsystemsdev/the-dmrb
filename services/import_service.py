"""
Thin shim: re-export import service API so "from services import import_service" works unchanged.
"""
from __future__ import annotations

from db import repository
from services.imports.constants import (
    AVAILABLE_UNITS,
    DMRB,
    MOVE_OUTS,
    PENDING_FAS,
    PENDING_MOVE_INS,
)
from services.imports.orchestrator import import_report_file, instantiate_tasks_for_turnover


def get_import_rows_by_batch(conn, batch_id: int):
    return repository.get_import_rows_by_batch(conn, batch_id)


def get_latest_import_batch(conn, report_type: str):
    """Return the most recent import_batch for the given report_type, or None."""
    return repository.get_latest_import_batch(conn, report_type)


def get_latest_import_rows(conn, report_type: str):
    """Return rows from the most recent batch for the given report_type (deterministic)."""
    return repository.get_latest_import_rows(conn, report_type)


def get_latest_available_units_rows(conn):
    return get_latest_import_rows(conn, AVAILABLE_UNITS)


def get_latest_move_out_rows(conn):
    return get_latest_import_rows(conn, MOVE_OUTS)


def get_latest_pending_move_in_rows(conn):
    return get_latest_import_rows(conn, PENDING_MOVE_INS)


def get_latest_pending_fas_rows(conn):
    return get_latest_import_rows(conn, PENDING_FAS)


def get_latest_dmrb_rows(conn):
    return get_latest_import_rows(conn, DMRB)


__all__ = [
    "AVAILABLE_UNITS",
    "DMRB",
    "get_import_rows_by_batch",
    "get_latest_available_units_rows",
    "get_latest_import_batch",
    "get_latest_dmrb_rows",
    "get_latest_import_rows",
    "get_latest_move_out_rows",
    "get_latest_pending_fas_rows",
    "get_latest_pending_move_in_rows",
    "MOVE_OUTS",
    "PENDING_FAS",
    "PENDING_MOVE_INS",
    "import_report_file",
    "instantiate_tasks_for_turnover",
]
