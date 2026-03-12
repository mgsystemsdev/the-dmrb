"""Property, phase, and building service: thin wrapper around db.repository (properties API)."""
from __future__ import annotations

from db import repository


def insert_property(conn, name: str):
    return repository.insert_property(conn, name)


def resolve_phase(conn, *, property_id: int, phase_code: str):
    return repository.resolve_phase(conn, property_id=property_id, phase_code=phase_code)


def resolve_building(conn, *, phase_id: int, building_code: str):
    return repository.resolve_building(conn, phase_id=phase_id, building_code=building_code)


def list_properties(conn):
    return repository.list_properties(conn)


def list_phases(conn, *, property_id: int | None = None):
    return repository.list_phases(conn, property_id=property_id)


def list_buildings(conn, *, phase_id: int | None = None):
    return repository.list_buildings(conn, phase_id=phase_id)
