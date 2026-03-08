"""
Manual add single unit availability: create one open turnover for an existing unit.
Resolves unit by property / phase / building / unit_number (lookup only; does not create units).
Uses turnover_service for create + task instantiation + SLA/risk reconciliation.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from domain import unit_identity
from db import repository
from services import turnover_service


def add_manual_availability(
    *,
    conn,
    property_id: int,
    phase_code: str,
    building_code: str,
    unit_number: str,
    move_out_date: date,
    move_in_date: Optional[date] = None,
    report_ready_date: Optional[date] = None,
    today: Optional[date] = None,
    actor: str = "manager",
) -> int:
    """
    Look up unit by (property_id, phase_code, building_code, unit_number).
    If unit not found → ValueError (does not create unit).
    If unit has open turnover → ValueError.
    Else create turnover, instantiate tasks, reconcile SLA/risks; return turnover_id.
    Caller owns connection and transaction; rollback on raised exception.
    """
    unit_number = (unit_number or "").strip()
    if not unit_number:
        raise ValueError("Unit number is required.")

    phase_row = repository.get_phase(conn, property_id=property_id, phase_code=phase_code)
    if phase_row is None:
        raise ValueError("Unit not found for the given property, phase, building, and unit number.")

    building_row = repository.get_building(
        conn, phase_id=phase_row["phase_id"], building_code=building_code
    )
    if building_row is None:
        raise ValueError("Unit not found for the given property, phase, building, and unit number.")

    unit_row_raw = repository.get_unit_by_building_and_number(
        conn,
        building_id=building_row["building_id"],
        unit_number=unit_number,
    )
    if unit_row_raw is None:
        raise ValueError(
            "This unit is not in the database. Phase + Building + Unit must match an existing unit "
            "(e.g. from Unit Master Import) before it can enter the lifecycle."
        )

    unit_row = dict(unit_row_raw)
    unit_id = unit_row["unit_id"]

    open_turnover = repository.get_open_turnover_by_unit(conn, unit_id)
    if open_turnover is not None:
        raise ValueError("This unit already has an open turnover. Close or cancel it first.")

    unit_identity_key = unit_row.get("unit_identity_key") or unit_identity.compose_identity_key(
        phase_code, building_code, unit_number
    )
    move_out_iso = move_out_date.isoformat()
    source_turnover_key = f"manual:{property_id}:{unit_identity_key}:{move_out_iso}"

    if today is None:
        today = date.today()

    return turnover_service.create_turnover_and_reconcile(
        conn=conn,
        unit_id=unit_id,
        unit_row=unit_row,
        property_id=property_id,
        source_turnover_key=source_turnover_key,
        move_out_date=move_out_date,
        move_in_date=move_in_date,
        report_ready_date=report_ready_date,
        today=today,
        actor=actor,
    )
