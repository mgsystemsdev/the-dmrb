from datetime import datetime, date
from typing import Any, Dict, List, Optional

from db import repository
from domain.risk_engine import evaluate_risks


def _parse_report_ready_date(value: Optional[str]) -> Optional[date]:
    """Parse turnover.report_ready_date (TEXT ISO YYYY-MM-DD) to date for risk_engine; None if missing/invalid."""
    if value is None or not isinstance(value, str):
        return None
    s = value.strip()
    if len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def reconcile_risks_for_turnover(
    *,
    conn,
    turnover_id: int,
    move_in_date: date | None,
    move_out_date: date | None,
    today: date,
    tasks: List[Dict[str, Any]],
    wd_present: bool | None,
    wd_supervisor_notified: bool | None,
    has_data_integrity_conflict: bool,
    has_duplicate_open_turnover: bool,
    actor: str = "system",
) -> None:
    existing_rows = repository.get_active_risks_by_turnover(conn, turnover_id)
    existing_by_type = {row["risk_type"]: row for row in existing_rows}

    # Load turnover for EXPOSURE_RISK: report_ready_date and manual_ready_confirmed_at (not passed in by callers).
    turnover_row = repository.get_turnover_by_id(conn, turnover_id)
    report_ready_date: Optional[date] = None
    manual_ready_confirmed_at: Optional[str] = None
    if turnover_row is not None:
        report_ready_date = _parse_report_ready_date(turnover_row["report_ready_date"])
        manual_ready_confirmed_at = turnover_row["manual_ready_confirmed_at"]

    desired_risks = evaluate_risks(
        move_in_date=move_in_date,
        move_out_date=move_out_date,
        today=today,
        tasks=tasks,
        wd_present=wd_present,
        wd_supervisor_notified=wd_supervisor_notified,
        has_data_integrity_conflict=has_data_integrity_conflict,
        has_duplicate_open_turnover=has_duplicate_open_turnover,
        report_ready_date=report_ready_date,
        manual_ready_confirmed_at=manual_ready_confirmed_at,
    )
    desired_by_type = {r["risk_type"]: r for r in desired_risks}

    now_iso = datetime.utcnow().isoformat()

    for risk_type, risk in desired_by_type.items():
        if risk_type not in existing_by_type:
            repository.upsert_risk(
                conn,
                {
                    "turnover_id": turnover_id,
                    "risk_type": risk_type,
                    "severity": risk["severity"],
                    "triggered_at": now_iso,
                    "auto_resolve": 1,
                },
            )
            repository.insert_audit_log(
                conn,
                {
                    "entity_type": "turnover",
                    "entity_id": turnover_id,
                    "field_name": "risk_flag",
                    "old_value": None,
                    "new_value": risk_type,
                    "changed_at": now_iso,
                    "actor": actor,
                    "source": "system",
                    "correlation_id": None,
                },
            )

    for risk_type, row in existing_by_type.items():
        if risk_type not in desired_by_type:
            repository.resolve_risk(conn, row["risk_id"], now_iso)
            repository.insert_audit_log(
                conn,
                {
                    "entity_type": "turnover",
                    "entity_id": turnover_id,
                    "field_name": "risk_flag",
                    "old_value": risk_type,
                    "new_value": "RESOLVED",
                    "changed_at": now_iso,
                    "actor": actor,
                    "source": "system",
                    "correlation_id": None,
                },
            )
