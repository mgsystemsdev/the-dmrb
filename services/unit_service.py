"""Unit service: thin wrapper around db.repository (units API)."""
from __future__ import annotations

from db import repository


def list_units(conn, *, building_id: int | None = None):
    return repository.list_units(conn, building_id=building_id)


def list_unit_master_import_units(conn):
    return repository.list_unit_master_import_units(conn)
