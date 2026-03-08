from __future__ import annotations

from datetime import datetime, timezone

from application.commands.write_commands import (
    ApplyImportRow,
    ClearManualOverride,
    CreateTurnover,
    UpdateTaskStatus,
    UpdateTurnoverDates,
    UpdateTurnoverStatus,
)
from db import repository
from services import import_service, manual_availability_service, task_service, turnover_service


def update_turnover_status_workflow(conn, command: UpdateTurnoverStatus) -> None:
    turnover_service.set_manual_ready_status(
        conn=conn,
        turnover_id=command.turnover_id,
        manual_ready_status=command.manual_ready_status,
        today=command.today,
        actor=command.actor,
    )


def update_turnover_dates_workflow(conn, command: UpdateTurnoverDates) -> None:
    payload = {
        "move_out_date": command.move_out_date,
        "report_ready_date": command.report_ready_date,
        "move_in_date": command.move_in_date,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    if not payload:
        return
    turnover_service.update_turnover_dates(
        conn=conn,
        turnover_id=command.turnover_id,
        today=command.today,
        actor=command.actor,
        **payload,
    )


def update_task_status_workflow(conn, command: UpdateTaskStatus) -> None:
    task_service.update_task_fields(
        conn=conn,
        task_id=command.task_id,
        fields=command.fields,
        today=command.today,
        actor=command.actor,
    )


def create_turnover_workflow(conn, command: CreateTurnover) -> int:
    return manual_availability_service.add_manual_availability(
        conn=conn,
        property_id=command.property_id,
        phase_code=command.phase_code,
        building_code=command.building_code,
        unit_number=command.unit_number,
        move_out_date=command.move_out_date,
        move_in_date=command.move_in_date,
        report_ready_date=command.report_ready_date,
        today=command.today,
        actor=command.actor,
    )


def apply_import_row_workflow(conn, command: ApplyImportRow):
    return import_service.import_report_file(
        conn=conn,
        report_type=command.report_type,
        file_path=command.file_path,
        property_id=command.property_id,
        db_path=command.db_path,
    )


def clear_manual_override_workflow(conn, command: ClearManualOverride) -> None:
    now = datetime.now(timezone.utc).isoformat()
    repository.update_turnover_fields(
        conn,
        command.turnover_id,
        {command.override_field: None, "updated_at": now},
        strict=False,
    )
    repository.insert_audit_log(
        conn,
        {
            "entity_type": "turnover",
            "entity_id": command.turnover_id,
            "field_name": "manual_override_cleared",
            "old_value": command.override_field,
            "new_value": None,
            "changed_at": now,
            "actor": command.actor,
            "source": "manual",
            "correlation_id": None,
        },
    )
