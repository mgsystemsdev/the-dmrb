from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class UpdateTurnoverStatus:
    turnover_id: int
    manual_ready_status: str
    today: date
    actor: str


@dataclass(frozen=True)
class UpdateTurnoverDates:
    turnover_id: int
    today: date
    actor: str
    move_out_date: date | None = None
    report_ready_date: date | None = None
    move_in_date: date | None = None


@dataclass(frozen=True)
class UpdateTaskStatus:
    task_id: int
    fields: dict[str, Any]
    today: date
    actor: str


@dataclass(frozen=True)
class CreateTurnover:
    property_id: int
    phase_code: str
    building_code: str
    unit_number: str
    move_out_date: date
    move_in_date: date | None
    report_ready_date: date | None
    today: date
    actor: str


@dataclass(frozen=True)
class ApplyImportRow:
    report_type: str
    file_path: str
    property_id: int
    db_path: str


@dataclass(frozen=True)
class ClearManualOverride:
    turnover_id: int
    override_field: str
    actor: str
