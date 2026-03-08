"""
Mock data for UI prototype. No db or services imports.
Dicts use same keys as schema/sqlite3.Row so UI can switch to real data later.
"""
from datetime import date, timedelta
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Units: property_id 5, 7, 8 for Phase filter (PH)
# ---------------------------------------------------------------------------
MOCK_UNITS = [
    {"unit_id": 1, "property_id": 5, "unit_code_raw": "5-101", "unit_code_norm": "5-101", "has_carpet": 1, "has_wd_expected": 1, "is_active": 1},
    {"unit_id": 2, "property_id": 5, "unit_code_raw": "5-102", "unit_code_norm": "5-102", "has_carpet": 0, "has_wd_expected": 1, "is_active": 1},
    {"unit_id": 3, "property_id": 7, "unit_code_raw": "7-201", "unit_code_norm": "7-201", "has_carpet": 1, "has_wd_expected": 0, "is_active": 1},
    {"unit_id": 4, "property_id": 7, "unit_code_raw": "7-202", "unit_code_norm": "7-202", "has_carpet": 0, "has_wd_expected": 0, "is_active": 1},
    {"unit_id": 5, "property_id": 8, "unit_code_raw": "8-301", "unit_code_norm": "8-301", "has_carpet": 1, "has_wd_expected": 1, "is_active": 1},
    {"unit_id": 6, "property_id": 8, "unit_code_raw": "8-302", "unit_code_norm": "8-302", "has_carpet": 0, "has_wd_expected": 0, "is_active": 1},
]

def _today() -> date:
    return date.today()

# Spread move_in: this week, next week, next month
def _move_in_this_week() -> str:
    d = _today() + timedelta(days=2)
    return d.isoformat()

def _move_in_next_week() -> str:
    d = _today() + timedelta(days=10)
    return d.isoformat()

def _move_in_next_month() -> str:
    d = _today() + timedelta(days=25)
    return d.isoformat()

def _move_out_days_ago(days: int) -> str:
    return (_today() - timedelta(days=days)).isoformat()

# ---------------------------------------------------------------------------
# Turnovers: open only (closed_at, canceled_at None), assignee for filter
# ---------------------------------------------------------------------------
MOCK_TURNOVERS = [
    {
        "turnover_id": 1, "unit_id": 1, "property_id": 5,
        "move_out_date": _move_out_days_ago(12), "move_in_date": _move_in_this_week(),
        "manual_ready_status": "Vacant not ready", "manual_ready_confirmed_at": None,
        "report_ready_date": _move_out_days_ago(5), "wd_present": 1, "wd_supervisor_notified": 0,
        "wd_notified_at": None, "wd_installed": 0, "closed_at": None, "canceled_at": None,
        "assignee": "Michael",
    },
    {
        "turnover_id": 2, "unit_id": 2, "property_id": 5,
        "move_out_date": _move_out_days_ago(8), "move_in_date": _move_in_next_week(),
        "manual_ready_status": "Vacant ready", "manual_ready_confirmed_at": _move_out_days_ago(2) + "T12:00:00Z",
        "report_ready_date": _move_out_days_ago(3), "wd_present": 1, "wd_supervisor_notified": 1,
        "wd_notified_at": _move_out_days_ago(1) + "T09:00:00Z", "wd_installed": 1, "closed_at": None, "canceled_at": None,
        "assignee": "Brad",
    },
    {
        "turnover_id": 3, "unit_id": 3, "property_id": 7,
        "move_out_date": _move_out_days_ago(3), "move_in_date": _move_in_next_month(),
        "manual_ready_status": "On notice", "manual_ready_confirmed_at": None,
        "report_ready_date": None, "wd_present": 0, "wd_supervisor_notified": 0,
        "wd_notified_at": None, "wd_installed": 0, "closed_at": None, "canceled_at": None,
        "assignee": "Miguel A",
    },
    {
        "turnover_id": 4, "unit_id": 4, "property_id": 7,
        "move_out_date": _move_out_days_ago(15), "move_in_date": _move_in_this_week(),
        "manual_ready_status": "Vacant not ready", "manual_ready_confirmed_at": None,
        "report_ready_date": _move_out_days_ago(10), "wd_present": 0, "wd_supervisor_notified": 0,
        "wd_notified_at": None, "wd_installed": 0, "closed_at": None, "canceled_at": None,
        "assignee": "Miguel G",
    },
    {
        "turnover_id": 5, "unit_id": 5, "property_id": 8,
        "move_out_date": _move_out_days_ago(5), "move_in_date": _move_in_next_week(),
        "manual_ready_status": "Vacant ready", "manual_ready_confirmed_at": None,
        "report_ready_date": _move_out_days_ago(2), "wd_present": 1, "wd_supervisor_notified": 1,
        "wd_notified_at": None, "wd_installed": 0, "closed_at": None, "canceled_at": None,
        "assignee": "Michael",
    },
    {
        "turnover_id": 6, "unit_id": 6, "property_id": 8,
        "move_out_date": _move_out_days_ago(20), "move_in_date": _move_in_next_month(),
        "manual_ready_status": "Vacant not ready", "manual_ready_confirmed_at": None,
        "report_ready_date": _move_out_days_ago(15), "wd_present": 0, "wd_supervisor_notified": 0,
        "wd_notified_at": None, "wd_installed": 0, "closed_at": None, "canceled_at": None,
        "assignee": "Brad",
    },
]

# ---------------------------------------------------------------------------
# Tasks: 2-4 per turnover; at least one QC, mix of statuses
# ---------------------------------------------------------------------------
MOCK_TASKS = [
    {"task_id": 1, "turnover_id": 1, "task_type": "Make Ready", "required": 1, "blocking": 1,
     "vendor_due_date": _move_out_days_ago(2), "vendor_completed_at": None, "manager_confirmed_at": None,
     "execution_status": "IN_PROGRESS", "confirmation_status": "PENDING"},
    {"task_id": 2, "turnover_id": 1, "task_type": "QC", "required": 1, "blocking": 1,
     "vendor_due_date": _move_in_this_week(), "vendor_completed_at": _move_out_days_ago(1) + "T14:00:00Z", "manager_confirmed_at": None,
     "execution_status": "VENDOR_COMPLETED", "confirmation_status": "PENDING"},
    {"task_id": 3, "turnover_id": 2, "task_type": "Paint", "required": 1, "blocking": 0,
     "vendor_due_date": _move_out_days_ago(5), "vendor_completed_at": _move_out_days_ago(4) + "T10:00:00Z", "manager_confirmed_at": _move_out_days_ago(3) + "T09:00:00Z",
     "execution_status": "VENDOR_COMPLETED", "confirmation_status": "CONFIRMED"},
    {"task_id": 4, "turnover_id": 2, "task_type": "QC", "required": 1, "blocking": 1,
     "vendor_due_date": _move_out_days_ago(2), "vendor_completed_at": _move_out_days_ago(1) + "T16:00:00Z", "manager_confirmed_at": _move_out_days_ago(1) + "T17:00:00Z",
     "execution_status": "VENDOR_COMPLETED", "confirmation_status": "CONFIRMED"},
    {"task_id": 5, "turnover_id": 3, "task_type": "Carpet Clean", "required": 1, "blocking": 0,
     "vendor_due_date": _move_in_next_month(), "vendor_completed_at": None, "manager_confirmed_at": None,
     "execution_status": "NOT_STARTED", "confirmation_status": "PENDING"},
    {"task_id": 6, "turnover_id": 3, "task_type": "QC", "required": 1, "blocking": 1,
     "vendor_due_date": _move_in_next_month(), "vendor_completed_at": None, "manager_confirmed_at": None,
     "execution_status": "NOT_STARTED", "confirmation_status": "PENDING"},
    {"task_id": 7, "turnover_id": 4, "task_type": "Make Ready", "required": 1, "blocking": 1,
     "vendor_due_date": _move_out_days_ago(8), "vendor_completed_at": _move_out_days_ago(6) + "T11:00:00Z", "manager_confirmed_at": None,
     "execution_status": "VENDOR_COMPLETED", "confirmation_status": "PENDING"},
    {"task_id": 8, "turnover_id": 4, "task_type": "QC", "required": 1, "blocking": 1,
     "vendor_due_date": _move_in_this_week(), "vendor_completed_at": None, "manager_confirmed_at": None,
     "execution_status": "SCHEDULED", "confirmation_status": "PENDING"},
    {"task_id": 9, "turnover_id": 5, "task_type": "Paint", "required": 0, "blocking": 0,
     "vendor_due_date": _move_in_next_week(), "vendor_completed_at": None, "manager_confirmed_at": None,
     "execution_status": "NOT_STARTED", "confirmation_status": "PENDING"},
    {"task_id": 10, "turnover_id": 5, "task_type": "QC", "required": 1, "blocking": 1,
     "vendor_due_date": _move_in_next_week(), "vendor_completed_at": None, "manager_confirmed_at": None,
     "execution_status": "NOT_STARTED", "confirmation_status": "PENDING"},
    {"task_id": 11, "turnover_id": 6, "task_type": "Make Ready", "required": 1, "blocking": 1,
     "vendor_due_date": _move_out_days_ago(15), "vendor_completed_at": None, "manager_confirmed_at": None,
     "execution_status": "NOT_STARTED", "confirmation_status": "PENDING"},
    {"task_id": 12, "turnover_id": 6, "task_type": "QC", "required": 1, "blocking": 1,
     "vendor_due_date": _move_in_next_month(), "vendor_completed_at": None, "manager_confirmed_at": None,
     "execution_status": "NOT_STARTED", "confirmation_status": "PENDING"},
]

# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------
MOCK_RISKS = [
    {"risk_id": 1, "turnover_id": 1, "risk_type": "QC_RISK", "severity": "CRITICAL", "triggered_at": _today().isoformat() + "T08:00:00Z", "resolved_at": None},
    {"risk_id": 2, "turnover_id": 1, "risk_type": "WD_RISK", "severity": "WARNING", "triggered_at": _today().isoformat() + "T08:00:00Z", "resolved_at": None},
    {"risk_id": 3, "turnover_id": 4, "risk_type": "CONFIRMATION_BACKLOG", "severity": "WARNING", "triggered_at": _today().isoformat() + "T08:00:00Z", "resolved_at": None},
    {"risk_id": 4, "turnover_id": 4, "risk_type": "SLA_BREACH", "severity": "CRITICAL", "triggered_at": _today().isoformat() + "T08:00:00Z", "resolved_at": None},
]

# ---------------------------------------------------------------------------
# Conflicts (import)
# ---------------------------------------------------------------------------
MOCK_CONFLICTS = [
    {"row_id": 1, "batch_id": 1, "unit_code_raw": "5-999", "unit_code_norm": "5-999", "conflict_reason": "WEAK_MATCH_MOVE_OUT_DATE", "validation_status": "CONFLICT"},
    {"row_id": 2, "batch_id": 1, "unit_code_raw": "7-200", "unit_code_norm": "7-200", "conflict_reason": "MOVE_IN_WITHOUT_TURNOVER", "validation_status": "CONFLICT"},
]

# ---------------------------------------------------------------------------
# Notes (optional)
# ---------------------------------------------------------------------------
MOCK_NOTES = [
    {"note_id": 1, "turnover_id": 1, "note_type": "blocking", "blocking": 1, "severity": "WARNING", "description": "Waiting on key delivery", "resolved_at": None},
    {"note_id": 2, "turnover_id": 4, "note_type": "info", "blocking": 0, "severity": "INFO", "description": "Expedited request", "resolved_at": None},
]

# ---------------------------------------------------------------------------
# Helpers: derive phase from turnover dates (simplified)
# ---------------------------------------------------------------------------
def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None

def _derive_phase(t: dict, today: Optional[date] = None) -> str:
    today = today or _today()
    move_out = _parse_date(t.get("move_out_date"))
    move_in = _parse_date(t.get("move_in_date"))
    if not move_out:
        return "NOTICE"
    if t.get("canceled_at"):
        return "CANCELED"
    if t.get("closed_at"):
        return "CLOSED"
    if move_in:
        if today > move_in and today <= move_in + timedelta(days=14):
            return "STABILIZATION"
        if today >= move_out and today < move_in:
            return "SMI"
    if today >= move_out:
        return "VACANT"
    return "NOTICE"

def _unit_by_id(unit_id: int) -> Optional[dict]:
    for u in MOCK_UNITS:
        if u["unit_id"] == unit_id:
            return u
    return None

def _turnover_has_qc_not_confirmed(turnover_id: int, tasks: list) -> bool:
    for t in tasks:
        if t["turnover_id"] == turnover_id and t.get("task_type") == "QC" and t.get("confirmation_status") != "CONFIRMED":
            return True
    return False

def _move_in_band(move_in_str: Optional[str], today: Optional[date] = None) -> Optional[str]:
    """Return 'this_week' | 'next_week' | 'next_month' or None if no move_in."""
    d = _parse_date(move_in_str)
    if not d:
        return None
    today = today or _today()
    delta = (d - today).days
    if delta <= 7:
        return "this_week"
    if delta <= 14:
        return "next_week"
    if delta <= 31:
        return "next_month"
    return None

# ---------------------------------------------------------------------------
# Public helpers (accept turnover list from session state when used by app)
# ---------------------------------------------------------------------------
def get_turnovers_for_dashboard(
    turnovers: list[dict],
    units: list[dict],
    tasks: list[dict],
    search_unit: Optional[str] = None,
    filter_phase: Optional[str] = None,
    filter_assignee: Optional[str] = None,
    filter_move_ins: Optional[str] = None,
    filter_phase_id: Optional[str] = None,
    filter_qc: Optional[str] = None,
    today: Optional[date] = None,
) -> list[dict]:
    """
    Filter turnovers and attach unit_code. Uses provided turnovers/tasks (e.g. from session state).
    """
    today = today or _today()
    unit_by_id = {u["unit_id"]: u for u in units}
    result = []
    for t in turnovers:
        u = unit_by_id.get(t["unit_id"])
        if not u:
            continue
        unit_code = u.get("unit_code_raw") or u.get("unit_code_norm") or ""
        if search_unit and search_unit.strip():
            if search_unit.strip().lower() not in unit_code.lower():
                continue
        phase = _derive_phase(t, today)
        if filter_phase and filter_phase != "All":
            if phase != filter_phase.upper():
                continue
        if filter_assignee and filter_assignee != "All":
            if t.get("assignee") != filter_assignee:
                continue
        band = _move_in_band(t.get("move_in_date"), today)
        if filter_move_ins and filter_move_ins != "All":
            if filter_move_ins == "Today / This week" and band != "this_week":
                continue
            if filter_move_ins == "Next week" and band != "next_week":
                continue
            if filter_move_ins == "Next month" and band != "next_month":
                continue
        if filter_phase_id and filter_phase_id != "All":
            pid = t.get("property_id")
            if str(pid) != str(filter_phase_id):
                continue
        if filter_qc and filter_qc != "All":
            qc_done = not _turnover_has_qc_not_confirmed(t["turnover_id"], tasks)
            if filter_qc == "QC Done" and not qc_done:
                continue
            if filter_qc == "QC Not done" and qc_done:
                continue
        out = dict(t)
        out["unit_code"] = unit_code
        out["phase"] = phase
        result.append(out)
    return result

def get_tasks_for_turnover(turnover_id: int, tasks: list[dict]) -> list[dict]:
    return [t for t in tasks if t.get("turnover_id") == turnover_id]

def get_risks_for_turnover(turnover_id: int) -> list[dict]:
    return [r for r in MOCK_RISKS if r.get("turnover_id") == turnover_id and not r.get("resolved_at")]

def get_unit_for_turnover(turnover_id: int, turnovers: list[dict], units: list[dict]) -> Optional[dict]:
    for t in turnovers:
        if t.get("turnover_id") == turnover_id:
            return _unit_by_id(t["unit_id"])
    return None

# ---------------------------------------------------------------------------
# Simple getters for prototype (filter static MOCK_* lists; no session state)
# ---------------------------------------------------------------------------
def get_open_turnovers() -> list[dict]:
    """Open turnovers only (no closed_at, canceled_at)."""
    return [t for t in MOCK_TURNOVERS if not t.get("closed_at") and not t.get("canceled_at")]

def get_tasks_for_turnover_simple(turnover_id: int) -> list[dict]:
    """Tasks for one turnover from MOCK_TASKS."""
    return [t for t in MOCK_TASKS if t.get("turnover_id") == turnover_id]

def get_unit_for_turnover_simple(turnover_id: int) -> Optional[dict]:
    """Unit for turnover from MOCK_TURNOVERS + MOCK_UNITS."""
    for t in MOCK_TURNOVERS:
        if t.get("turnover_id") == turnover_id:
            return _unit_by_id(t["unit_id"])
    return None

def get_turnover_by_id(turnover_id: int) -> Optional[dict]:
    for t in MOCK_TURNOVERS:
        if t.get("turnover_id") == turnover_id:
            return t
    return None

def get_notes_for_turnover(turnover_id: int) -> list[dict]:
    """Unresolved notes for turnover."""
    return [n for n in MOCK_NOTES if n.get("turnover_id") == turnover_id and not n.get("resolved_at")]

def get_tasks_flat(turnovers: list[dict], tasks: list[dict], units: list[dict]) -> list[dict]:
    """
    Flat list of tasks for the given turnovers, with unit_code, manual_ready_status, move_in_date for Control Board 2.
    """
    turnover_ids_allowed = {t["turnover_id"] for t in turnovers}
    unit_by_id = {u["unit_id"]: u for u in units}
    turnover_by_id = {t["turnover_id"]: t for t in turnovers}
    result = []
    for task in tasks:
        tid = task.get("turnover_id")
        if tid not in turnover_ids_allowed:
            continue
        t = turnover_by_id.get(tid)
        if not t:
            continue
        u = unit_by_id.get(t["unit_id"])
        unit_code = (u.get("unit_code_raw") or u.get("unit_code_norm") or "") if u else ""
        row = dict(task)
        row["unit_code"] = unit_code
        row["manual_ready_status"] = t.get("manual_ready_status")
        row["move_in_date"] = t.get("move_in_date")
        result.append(row)
    return result
