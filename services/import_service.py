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


__all__ = [
    "AVAILABLE_UNITS",
    "DMRB",
    "get_import_rows_by_batch",
    "MOVE_OUTS",
    "PENDING_FAS",
    "PENDING_MOVE_INS",
    "import_report_file",
    "instantiate_tasks_for_turnover",
]
