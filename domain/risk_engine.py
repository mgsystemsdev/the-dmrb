from datetime import date
from typing import Any, Dict, List, Optional

SLA_BREACH = "SLA_BREACH"
QC_RISK = "QC_RISK"
WD_RISK = "WD_RISK"
CONFIRMATION_BACKLOG = "CONFIRMATION_BACKLOG"
EXECUTION_OVERDUE = "EXECUTION_OVERDUE"
DATA_INTEGRITY = "DATA_INTEGRITY"
DUPLICATE_OPEN_TURNOVER = "DUPLICATE_OPEN_TURNOVER"
EXPOSURE_RISK = "EXPOSURE_RISK"

INFO = "INFO"
WARNING = "WARNING"
CRITICAL = "CRITICAL"

_SEVERITY_ORDER = {CRITICAL: 3, WARNING: 2, INFO: 1}


def _max_severity(severities: List[str]) -> str:
    if not severities:
        return INFO
    return max(severities, key=lambda s: _SEVERITY_ORDER.get(s, 0))


def evaluate_risks(
    *,
    move_in_date: Optional[date],
    move_out_date: Optional[date],
    today: date,
    tasks: List[Dict[str, Any]],
    wd_present: Optional[bool],
    wd_supervisor_notified: Optional[bool],
    has_data_integrity_conflict: bool,
    has_duplicate_open_turnover: bool,
    report_ready_date: Optional[date] = None,
    manual_ready_confirmed_at: Optional[str] = None,
) -> List[Dict[str, str]]:
    by_type: Dict[str, List[str]] = {}

    def add(risk_type: str, severity: str) -> None:
        by_type.setdefault(risk_type, []).append(severity)

    if move_in_date is not None:
        days_to_move_in = (move_in_date - today).days
        if days_to_move_in <= 3:
            qc_task = next(
                (t for t in tasks if t.get("task_type") == "QC" and t.get("confirmation_status") != "CONFIRMED"),
                None,
            )
            if qc_task is not None:
                add(QC_RISK, CRITICAL if days_to_move_in <= 2 else WARNING)

        if days_to_move_in <= 7 and wd_present is False and wd_supervisor_notified is not True:
            add(WD_RISK, CRITICAL if days_to_move_in <= 3 else WARNING)

    backlog_severities: List[str] = []
    for t in tasks:
        vc = t.get("vendor_completed_date")
        mc = t.get("manager_confirmed_at")
        if vc is not None and mc is None:
            age = (today - vc).days
            if age > 2:
                if age >= 5:
                    backlog_severities.append(CRITICAL)
                elif 3 <= age <= 4:
                    backlog_severities.append(WARNING)
    if backlog_severities:
        add(CONFIRMATION_BACKLOG, _max_severity(backlog_severities))

    overdue = any(
        t.get("vendor_due_date") is not None
        and t["vendor_due_date"] < today
        and t.get("execution_status") != "VENDOR_COMPLETED"
        for t in tasks
    )
    if overdue:
        add(EXECUTION_OVERDUE, WARNING)

    if has_data_integrity_conflict:
        add(DATA_INTEGRITY, CRITICAL)
    if has_duplicate_open_turnover:
        add(DUPLICATE_OPEN_TURNOVER, CRITICAL)

    if (
        report_ready_date is not None
        and manual_ready_confirmed_at is None
        and today >= report_ready_date
    ):
        days_past = (today - report_ready_date).days
        add(EXPOSURE_RISK, CRITICAL if days_past >= 3 else WARNING)

    result = [
        {"risk_type": rt, "severity": _max_severity(sevs)}
        for rt, sevs in sorted(by_type.items())
    ]
    return result
