"""
Mock data for UI prototype v2. No db or services imports.
V2: 6 task types per turnover (Insp, Paint, MR, HK, CC, QC), assignee per task,
3-stage enrichment, get_dmrb_board_rows, get_flag_bridge_rows.
"""
from datetime import date, timedelta
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Task type constants (DMRB column set)
# ---------------------------------------------------------------------------
TASK_TYPES_SEQUENCE = ["Insp", "CB", "MRB", "Paint", "MR", "HK", "CC", "FW"]
TASK_TYPES_ALL = ["Insp", "CB", "MRB", "Paint", "MR", "HK", "CC", "FW", "QC"]

TASK_DISPLAY_NAMES = {
    "Insp": "Inspection",
    "CB": "Carpet Bid",
    "MRB": "Make Ready Bid",
    "Paint": "Paint",
    "MR": "Make Ready",
    "HK": "Housekeeping",
    "CC": "Carpet Clean",
    "FW": "Final Walk",
    "QC": "Quality Control",
}

# ---------------------------------------------------------------------------
# Assignee options for all assignee dropdowns (DMRB Assign, Detail, filters)
# ---------------------------------------------------------------------------
ASSIGNEE_OPTIONS = ["", "Michael", "Brad", "Miguel A", "Roadrunner", "Make Ready Co"]

BLOCK_OPTIONS = ["Not Blocking", "Key Delivery", "Vendor Delay", "Parts on Order", "Permit Required", "Other"]

DEFAULT_TASK_ASSIGNEES = {
    "Insp": {"options": ["Michael", "Miguel A"], "default": "Michael"},
    "CB": {"options": ["Make Ready Co"], "default": ""},
    "MRB": {"options": ["Make Ready Co"], "default": "Make Ready Co"},
    "Paint": {"options": ["Roadrunner"], "default": "Roadrunner"},
    "MR": {"options": ["Make Ready Co"], "default": "Make Ready Co"},
    "HK": {"options": ["Brad"], "default": "Brad"},
    "CC": {"options": ["Brad"], "default": ""},
    "FW": {"options": ["Michael", "Miguel A"], "default": ""},
    "QC": {"options": ["Michael", "Miguel A", "Brad"], "default": "Michael"},
}

# ---------------------------------------------------------------------------
# Units: property_id 5, 7, 8 for Phase filter
# ---------------------------------------------------------------------------
def _today() -> date:
    return date.today()

def _move_in_this_week() -> str:
    return (_today() + timedelta(days=2)).isoformat()

def _move_in_next_week() -> str:
    return (_today() + timedelta(days=10)).isoformat()

def _move_in_next_month() -> str:
    return (_today() + timedelta(days=25)).isoformat()

def _move_out_days_ago(days: int) -> str:
    return (_today() - timedelta(days=days)).isoformat()

MOCK_UNITS_V2 = [
    {"unit_id": 1, "property_id": 5, "unit_code_raw": "5-1-101", "unit_code_norm": "5-1-101", "has_carpet": 1, "has_wd_expected": 1, "is_active": 1},
    {"unit_id": 2, "property_id": 5, "unit_code_raw": "5-1-102", "unit_code_norm": "5-1-102", "has_carpet": 0, "has_wd_expected": 1, "is_active": 1},
    {"unit_id": 3, "property_id": 7, "unit_code_raw": "7-2-201", "unit_code_norm": "7-2-201", "has_carpet": 1, "has_wd_expected": 0, "is_active": 1},
    {"unit_id": 4, "property_id": 7, "unit_code_raw": "7-2-202", "unit_code_norm": "7-2-202", "has_carpet": 0, "has_wd_expected": 0, "is_active": 1},
    {"unit_id": 5, "property_id": 8, "unit_code_raw": "8-3-301", "unit_code_norm": "8-3-301", "has_carpet": 1, "has_wd_expected": 1, "is_active": 1},
    {"unit_id": 6, "property_id": 8, "unit_code_raw": "8-3-302", "unit_code_norm": "8-3-302", "has_carpet": 0, "has_wd_expected": 0, "is_active": 1},
]

# ---------------------------------------------------------------------------
# Turnovers: no turnover-level assignee; variety for enrichment
# ---------------------------------------------------------------------------
MOCK_TURNOVERS_V2 = [
    {
        "turnover_id": 1, "unit_id": 1, "property_id": 5,
        "move_out_date": _move_out_days_ago(12), "move_in_date": _move_in_this_week(),
        "manual_ready_status": "Vacant not ready", "manual_ready_confirmed_at": None,
        "report_ready_date": _move_out_days_ago(5), "wd_present": 1, "wd_supervisor_notified": 0,
        "wd_notified_at": None, "wd_installed": 0, "closed_at": None, "canceled_at": None,
    },
    {
        "turnover_id": 2, "unit_id": 2, "property_id": 5,
        "move_out_date": _move_out_days_ago(8), "move_in_date": _move_in_next_week(),
        "manual_ready_status": "Vacant ready", "manual_ready_confirmed_at": _move_out_days_ago(2) + "T12:00:00Z",
        "report_ready_date": _move_out_days_ago(3), "wd_present": 1, "wd_supervisor_notified": 1,
        "wd_notified_at": _move_out_days_ago(1) + "T09:00:00Z", "wd_installed": 1, "closed_at": None, "canceled_at": None,
    },
    {
        "turnover_id": 3, "unit_id": 3, "property_id": 7,
        "move_out_date": _move_out_days_ago(3), "move_in_date": _move_in_next_month(),
        "manual_ready_status": "On notice", "manual_ready_confirmed_at": None,
        "report_ready_date": None, "wd_present": 0, "wd_supervisor_notified": 0,
        "wd_notified_at": None, "wd_installed": 0, "closed_at": None, "canceled_at": None,
    },
    {
        "turnover_id": 4, "unit_id": 4, "property_id": 7,
        "move_out_date": _move_out_days_ago(15), "move_in_date": _move_in_this_week(),
        "manual_ready_status": "Vacant not ready", "manual_ready_confirmed_at": None,
        "report_ready_date": _move_out_days_ago(10), "wd_present": 0, "wd_supervisor_notified": 0,
        "wd_notified_at": None, "wd_installed": 0, "closed_at": None, "canceled_at": None,
    },
    {
        "turnover_id": 5, "unit_id": 5, "property_id": 8,
        "move_out_date": _move_out_days_ago(5), "move_in_date": _move_in_next_week(),
        "manual_ready_status": "Vacant ready", "manual_ready_confirmed_at": None,
        "report_ready_date": _move_out_days_ago(2), "wd_present": 1, "wd_supervisor_notified": 1,
        "wd_notified_at": None, "wd_installed": 0, "closed_at": None, "canceled_at": None,
    },
    {
        "turnover_id": 6, "unit_id": 6, "property_id": 8,
        "move_out_date": _move_out_days_ago(20), "move_in_date": _move_in_next_month(),
        "manual_ready_status": "Vacant not ready", "manual_ready_confirmed_at": None,
        "report_ready_date": _move_out_days_ago(15), "wd_present": 0, "wd_supervisor_notified": 0,
        "wd_notified_at": None, "wd_installed": 0, "closed_at": None, "canceled_at": None,
    },
]

# ---------------------------------------------------------------------------
# Tasks: exactly 6 per turnover (Insp, Paint, MR, HK, CC, QC); assignee per task
# ---------------------------------------------------------------------------
def _task( tid: int, turnover_id: int, task_type: str, required: int, blocking: int,
           vendor_due: str, vendor_done: Optional[str], exec_status: str, confirm_status: str,
           assignee: str = "" ) -> dict:
    return {
        "task_id": tid, "turnover_id": turnover_id, "task_type": task_type,
        "required": required, "blocking": blocking,
        "vendor_due_date": vendor_due, "vendor_completed_at": vendor_done, "manager_confirmed_at": None,
        "execution_status": exec_status, "confirmation_status": confirm_status,
        "assignee": assignee,
    }

MOCK_TASKS_V2 = [
    # Turnover 1: in progress, move-in soon (Move-In Risk / QC Hold scenario)
    _task(1, 1, "Insp", 1, 1, _move_out_days_ago(10), _move_out_days_ago(11) + "T10:00:00Z", "VENDOR_COMPLETED", "PENDING", "Michael"),
    _task(2, 1, "Paint", 1, 0, _move_out_days_ago(8), _move_out_days_ago(7) + "T14:00:00Z", "VENDOR_COMPLETED", "PENDING", "Roadrunner"),
    _task(3, 1, "MR", 1, 1, _move_out_days_ago(4), None, "IN_PROGRESS", "PENDING", "Make Ready Co"),
    _task(4, 1, "HK", 1, 0, _move_in_this_week(), None, "NOT_STARTED", "PENDING", "Brad"),
    _task(5, 1, "CC", 1, 0, _move_in_this_week(), None, "NOT_STARTED", "PENDING", ""),
    _task(6, 1, "QC", 1, 1, _move_in_this_week(), None, "NOT_STARTED", "PENDING", "Michael"),
    # Turnover 2: apartment ready, QC done
    _task(7, 2, "Insp", 1, 1, _move_out_days_ago(7), _move_out_days_ago(7) + "T09:00:00Z", "VENDOR_COMPLETED", "PENDING", "Michael"),
    _task(8, 2, "Paint", 1, 0, _move_out_days_ago(5), _move_out_days_ago(5) + "T10:00:00Z", "VENDOR_COMPLETED", "PENDING", "Roadrunner"),
    _task(9, 2, "MR", 1, 1, _move_out_days_ago(3), _move_out_days_ago(3) + "T11:00:00Z", "VENDOR_COMPLETED", "PENDING", "Make Ready Co"),
    _task(10, 2, "HK", 1, 0, _move_out_days_ago(2), _move_out_days_ago(2) + "T16:00:00Z", "VENDOR_COMPLETED", "PENDING", "Brad"),
    _task(11, 2, "CC", 1, 0, _move_out_days_ago(1), _move_out_days_ago(1) + "T12:00:00Z", "VENDOR_COMPLETED", "PENDING", ""),
    _task(12, 2, "QC", 1, 1, _move_out_days_ago(1), _move_out_days_ago(1) + "T17:00:00Z", "VENDOR_COMPLETED", "CONFIRMED", "Michael"),
    # Turnover 3: on notice
    _task(13, 3, "Insp", 1, 1, _move_in_next_month(), None, "NOT_STARTED", "PENDING", "Miguel A"),
    _task(14, 3, "Paint", 1, 0, _move_in_next_month(), None, "NOT_STARTED", "PENDING", "Roadrunner"),
    _task(15, 3, "MR", 1, 1, _move_in_next_month(), None, "NOT_STARTED", "PENDING", ""),
    _task(16, 3, "HK", 1, 0, _move_in_next_month(), None, "NOT_STARTED", "PENDING", "Brad"),
    _task(17, 3, "CC", 1, 0, _move_in_next_month(), None, "NOT_STARTED", "PENDING", ""),
    _task(18, 3, "QC", 1, 1, _move_in_next_month(), None, "NOT_STARTED", "PENDING", "Miguel A"),
    # Turnover 4: stalled, SLA breach
    _task(19, 4, "Insp", 1, 1, _move_out_days_ago(14), _move_out_days_ago(13) + "T10:00:00Z", "VENDOR_COMPLETED", "PENDING", "Michael"),
    _task(20, 4, "Paint", 1, 0, _move_out_days_ago(12), None, "IN_PROGRESS", "PENDING", "Roadrunner"),
    _task(21, 4, "MR", 1, 1, _move_out_days_ago(8), None, "NOT_STARTED", "PENDING", "Make Ready Co"),
    _task(22, 4, "HK", 1, 0, _move_in_this_week(), None, "NOT_STARTED", "PENDING", ""),
    _task(23, 4, "CC", 1, 0, _move_in_this_week(), None, "NOT_STARTED", "PENDING", ""),
    _task(24, 4, "QC", 1, 1, _move_in_this_week(), None, "NOT_STARTED", "PENDING", "Brad"),
    # Turnover 5: mixed assignees
    _task(25, 5, "Insp", 1, 1, _move_out_days_ago(4), _move_out_days_ago(4) + "T09:00:00Z", "VENDOR_COMPLETED", "PENDING", "Michael"),
    _task(26, 5, "Paint", 1, 0, _move_out_days_ago(2), None, "SCHEDULED", "PENDING", "Roadrunner"),
    _task(27, 5, "MR", 1, 1, _move_in_next_week(), None, "NOT_STARTED", "PENDING", "Make Ready Co"),
    _task(28, 5, "HK", 1, 0, _move_in_next_week(), None, "NOT_STARTED", "PENDING", "Brad"),
    _task(29, 5, "CC", 0, 0, _move_in_next_week(), None, "NA", "PENDING", ""),
    _task(30, 5, "QC", 1, 1, _move_in_next_week(), None, "NOT_STARTED", "PENDING", "Miguel A"),
    # Turnover 6: not started
    _task(31, 6, "Insp", 1, 1, _move_out_days_ago(18), None, "NOT_STARTED", "PENDING", ""),
    _task(32, 6, "Paint", 1, 0, _move_out_days_ago(16), None, "NOT_STARTED", "PENDING", "Roadrunner"),
    _task(33, 6, "MR", 1, 1, _move_out_days_ago(14), None, "NOT_STARTED", "PENDING", "Make Ready Co"),
    _task(34, 6, "HK", 1, 0, _move_in_next_month(), None, "NOT_STARTED", "PENDING", "Brad"),
    _task(35, 6, "CC", 1, 0, _move_in_next_month(), None, "NOT_STARTED", "PENDING", ""),
    _task(36, 6, "QC", 1, 1, _move_in_next_month(), None, "NOT_STARTED", "PENDING", "Michael"),
    # --- Carpet Bid (CB), Make Ready Bid (MRB), Final Walk (FW) ---
    # Turnover 1
    _task(37, 1, "CB", 1, 0, _move_out_days_ago(10), None, "NOT_STARTED", "PENDING", ""),
    _task(38, 1, "MRB", 1, 0, _move_out_days_ago(9), None, "NOT_STARTED", "PENDING", "Make Ready Co"),
    _task(39, 1, "FW", 1, 0, _move_in_this_week(), None, "NOT_STARTED", "PENDING", "Michael"),
    # Turnover 2
    _task(40, 2, "CB", 0, 0, _move_out_days_ago(6), _move_out_days_ago(6) + "T10:00:00Z", "VENDOR_COMPLETED", "PENDING", ""),
    _task(41, 2, "MRB", 1, 0, _move_out_days_ago(6), _move_out_days_ago(5) + "T10:00:00Z", "VENDOR_COMPLETED", "PENDING", "Make Ready Co"),
    _task(42, 2, "FW", 1, 0, _move_out_days_ago(1), _move_out_days_ago(1) + "T15:00:00Z", "VENDOR_COMPLETED", "PENDING", "Michael"),
    # Turnover 3
    _task(43, 3, "CB", 1, 0, _move_in_next_month(), None, "NOT_STARTED", "PENDING", ""),
    _task(44, 3, "MRB", 1, 0, _move_in_next_month(), None, "NOT_STARTED", "PENDING", ""),
    _task(45, 3, "FW", 1, 0, _move_in_next_month(), None, "NOT_STARTED", "PENDING", ""),
    # Turnover 4
    _task(46, 4, "CB", 1, 0, _move_out_days_ago(13), None, "NOT_STARTED", "PENDING", ""),
    _task(47, 4, "MRB", 1, 0, _move_out_days_ago(12), None, "NOT_STARTED", "PENDING", "Make Ready Co"),
    _task(48, 4, "FW", 1, 0, _move_in_this_week(), None, "NOT_STARTED", "PENDING", ""),
    # Turnover 5
    _task(49, 5, "CB", 1, 0, _move_out_days_ago(3), None, "NOT_STARTED", "PENDING", ""),
    _task(50, 5, "MRB", 1, 0, _move_out_days_ago(3), None, "SCHEDULED", "PENDING", "Make Ready Co"),
    _task(51, 5, "FW", 1, 0, _move_in_next_week(), None, "NOT_STARTED", "PENDING", "Miguel A"),
    # Turnover 6
    _task(52, 6, "CB", 1, 0, _move_out_days_ago(17), None, "NOT_STARTED", "PENDING", ""),
    _task(53, 6, "MRB", 1, 0, _move_out_days_ago(16), None, "NOT_STARTED", "PENDING", "Make Ready Co"),
    _task(54, 6, "FW", 1, 0, _move_in_next_month(), None, "NOT_STARTED", "PENDING", ""),
]

# ---------------------------------------------------------------------------
# Notes, risks, conflicts
# ---------------------------------------------------------------------------
MOCK_NOTES_V2 = [
    {"note_id": 1, "turnover_id": 1, "note_type": "blocking", "blocking": 1, "severity": "WARNING", "description": "Waiting on key delivery", "resolved_at": None},
    {"note_id": 2, "turnover_id": 4, "note_type": "info", "blocking": 0, "severity": "INFO", "description": "Expedited request", "resolved_at": None},
]

MOCK_RISKS_V2 = [
    {"risk_id": 1, "turnover_id": 1, "risk_type": "QC_RISK", "severity": "CRITICAL", "triggered_at": _today().isoformat() + "T08:00:00Z", "resolved_at": None},
    {"risk_id": 2, "turnover_id": 1, "risk_type": "WD_RISK", "severity": "WARNING", "triggered_at": _today().isoformat() + "T08:00:00Z", "resolved_at": None},
    {"risk_id": 3, "turnover_id": 4, "risk_type": "CONFIRMATION_BACKLOG", "severity": "WARNING", "triggered_at": _today().isoformat() + "T08:00:00Z", "resolved_at": None},
    {"risk_id": 4, "turnover_id": 4, "risk_type": "SLA_BREACH", "severity": "CRITICAL", "triggered_at": _today().isoformat() + "T08:00:00Z", "resolved_at": None},
]

MOCK_CONFLICTS_V2 = [
    {"row_id": 1, "batch_id": 1, "unit_code_raw": "5-999", "unit_code_norm": "5-999", "conflict_reason": "WEAK_MATCH_MOVE_OUT_DATE", "validation_status": "CONFLICT"},
    {"row_id": 2, "batch_id": 1, "unit_code_raw": "7-200", "unit_code_norm": "7-200", "conflict_reason": "MOVE_IN_WITHOUT_TURNOVER", "validation_status": "CONFLICT"},
]

# ---------------------------------------------------------------------------
# Helpers: parse unit_code for building (B) and unit number (U)
# ---------------------------------------------------------------------------
def parse_unit_code(unit_code_raw: Optional[str]) -> tuple[str, str]:
    """Return (building, unit_number). E.g. '5-18-0206' -> ('18', '0206'); '5-101' -> ('', '101')."""
    if not unit_code_raw or not unit_code_raw.strip():
        return ("", "")
    parts = unit_code_raw.strip().split("-")
    if len(parts) >= 3:
        return (parts[1], parts[2])
    if len(parts) == 2:
        return ("", parts[1])
    return ("", parts[0] if parts else "")

# ---------------------------------------------------------------------------
# Build flat row (no enrichment) — identity, dates, task dicts, notes
# ---------------------------------------------------------------------------
def build_flat_row(
    turnover: dict,
    unit: dict,
    tasks_by_turnover: list[dict],
    notes_by_turnover: list[dict],
) -> dict:
    """Build one flat dict per turnover with task_insp..task_qc and notes_text. No Stage 1–3."""
    turnover_id = turnover["turnover_id"]
    unit_code = unit.get("unit_code_raw") or unit.get("unit_code_norm") or ""
    building, unit_number = parse_unit_code(unit.get("unit_code_raw"))

    task_by_type = {t["task_type"]: t for t in tasks_by_turnover if t.get("turnover_id") == turnover_id}
    task_insp = task_by_type.get("Insp", {})
    task_paint = task_by_type.get("Paint", {})
    task_mr = task_by_type.get("MR", {})
    task_hk = task_by_type.get("HK", {})
    task_cc = task_by_type.get("CC", {})
    task_cb = task_by_type.get("CB", {})
    task_mrb = task_by_type.get("MRB", {})
    task_fw = task_by_type.get("FW", {})
    task_qc = task_by_type.get("QC", {})

    notes_text = " ".join(
        n.get("description", "") or ""
        for n in notes_by_turnover
        if n.get("turnover_id") == turnover_id and n.get("description")
    ).strip() or ""

    return {
        "turnover_id": turnover_id,
        "unit_id": unit.get("unit_id"),
        "unit_code": unit_code,
        "property_id": unit.get("property_id"),
        "building": building,
        "unit_number": unit_number,
        "move_out_date": turnover.get("move_out_date"),
        "move_in_date": turnover.get("move_in_date"),
        "report_ready_date": turnover.get("report_ready_date"),
        "manual_ready_status": turnover.get("manual_ready_status") or "Vacant not ready",
        "closed_at": turnover.get("closed_at"),
        "canceled_at": turnover.get("canceled_at"),
        "wd_present": turnover.get("wd_present", 0),
        "wd_supervisor_notified": turnover.get("wd_supervisor_notified", 0),
        "wd_installed": turnover.get("wd_installed", 0),
        "task_insp": task_insp,
        "task_paint": task_paint,
        "task_mr": task_mr,
        "task_hk": task_hk,
        "task_cc": task_cc,
        "task_cb": task_cb,
        "task_mrb": task_mrb,
        "task_fw": task_fw,
        "task_qc": task_qc,
        "notes_text": notes_text,
    }


# ---------------------------------------------------------------------------
# Enrichment: helpers
# ---------------------------------------------------------------------------
TASK_EXPECTED_DAYS = {"Insp": 1, "CB": 2, "MRB": 2, "Paint": 2, "MR": 3, "HK": 6, "CC": 7, "FW": 8}

def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None

def business_days(start: Any, end: Any) -> Optional[int]:
    """Business days between start and end (inclusive of start, exclusive of end if end > start). Accept date or ISO string."""
    d_start = _parse_date(start) if not isinstance(start, date) else start
    d_end = _parse_date(end) if not isinstance(end, date) else end
    if d_start is None or d_end is None:
        return None
    if d_end < d_start:
        d_start, d_end = d_end, d_start
    count = 0
    d = d_start
    while d < d_end:
        if d.weekday() < 5:  # Mon=0 .. Fri=4
            count += 1
        d += timedelta(days=1)
    return count

def derive_phase(t: dict, today: Optional[date] = None) -> str:
    """Phase: NOTICE, NOTICE_SMI, VACANT, SMI, MOVE_IN_COMPLETE, STABILIZATION, CLOSED, CANCELED."""
    today = today or _today()
    move_out = _parse_date(t.get("move_out_date"))
    move_in = _parse_date(t.get("move_in_date"))
    if not move_out:
        return "NOTICE_SMI" if move_in else "NOTICE"
    if t.get("canceled_at"):
        return "CANCELED"
    if t.get("closed_at"):
        return "CLOSED"
    if move_in:
        if today > move_in and today <= move_in + timedelta(days=14):
            return "STABILIZATION"
        if today == move_in:
            return "MOVE_IN_COMPLETE"
        if today >= move_out and today < move_in:
            return "SMI"
    if today >= move_out:
        return "VACANT"
    return "NOTICE_SMI" if move_in else "NOTICE"

def derive_nvm(phase: str) -> str:
    """N/V/M from phase. NOTICE|NOTICE_SMI -> N, VACANT -> V, SMI|MOVE_IN_COMPLETE|STABILIZATION -> M."""
    if phase in ("NOTICE", "NOTICE_SMI"):
        return "N"
    if phase == "VACANT":
        return "V"
    if phase in ("SMI", "MOVE_IN_COMPLETE", "STABILIZATION"):
        return "M"
    return "—"

# ---------------------------------------------------------------------------
# Stage 1 — Fact engine
# ---------------------------------------------------------------------------
def compute_facts(row: dict, today: Optional[date] = None) -> dict:
    today = today or _today()
    move_out = _parse_date(row.get("move_out_date"))
    move_in = _parse_date(row.get("move_in_date"))
    task_qc = row.get("task_qc") or {}
    task_insp = row.get("task_insp") or {}
    task_paint = row.get("task_paint") or {}
    task_mr = row.get("task_mr") or {}
    task_hk = row.get("task_hk") or {}
    task_cc = row.get("task_cc") or {}
    task_cb = row.get("task_cb") or {}
    task_mrb = row.get("task_mrb") or {}
    task_fw = row.get("task_fw") or {}

    dv = business_days(move_out, today) if move_out else None
    dtbr = business_days(today, move_in) if move_in else None
    phase = derive_phase(
        {
            "move_out_date": row.get("move_out_date"),
            "move_in_date": row.get("move_in_date"),
            "closed_at": row.get("closed_at"),
            "canceled_at": row.get("canceled_at"),
        },
        today,
    )
    nvm = derive_nvm(phase)

    is_vacant = phase == "VACANT"
    is_smi = phase in ("SMI", "MOVE_IN_COMPLETE", "STABILIZATION")
    is_on_notice = phase in ("NOTICE", "NOTICE_SMI")
    is_move_in_present = move_in is not None
    is_ready_declared = row.get("report_ready_date") is not None
    is_qc_done = (task_qc.get("confirmation_status") or "").upper() == "CONFIRMED"

    exec_tasks = [task_insp, task_cb, task_mrb, task_paint, task_mr, task_hk, task_cc, task_fw]
    done_count = sum(1 for t in exec_tasks if (t.get("execution_status") or "").upper() == "VENDOR_COMPLETED")
    n_exec = len(exec_tasks)
    task_state = "All Tasks Complete" if done_count >= n_exec else ("Not Started" if done_count == 0 else "In Progress")
    task_completion_ratio = (done_count * 100) // n_exec if n_exec else 0

    current_task = None
    next_task = None
    for i, tt in enumerate(TASK_TYPES_SEQUENCE):
        t = exec_tasks[i] if i < len(exec_tasks) else {}
        if (t.get("execution_status") or "").upper() != "VENDOR_COMPLETED":
            current_task = tt
            if i + 1 < len(TASK_TYPES_SEQUENCE):
                next_task = TASK_TYPES_SEQUENCE[i + 1]
            break

    is_task_stalled = False
    if is_vacant and current_task and dv is not None:
        expected = TASK_EXPECTED_DAYS.get(current_task, 7)
        if dv > expected + 1:
            is_task_stalled = True

    row = dict(row)
    row["dv"] = dv
    row["dtbr"] = dtbr
    row["phase"] = phase
    row["nvm"] = nvm
    row["is_vacant"] = is_vacant
    row["is_smi"] = is_smi
    row["is_on_notice"] = is_on_notice
    row["is_move_in_present"] = is_move_in_present
    row["is_ready_declared"] = is_ready_declared
    row["is_qc_done"] = is_qc_done
    row["task_state"] = task_state
    row["task_completion_ratio"] = task_completion_ratio
    row["current_task"] = current_task
    row["next_task"] = next_task
    row["is_task_stalled"] = is_task_stalled
    return row

# ---------------------------------------------------------------------------
# Stage 2 — Intelligence engine
# ---------------------------------------------------------------------------
def compute_intelligence(row: dict) -> dict:
    is_unit_ready = (
        (row.get("manual_ready_status") or "").lower() == "vacant ready"
        and row.get("task_state") == "All Tasks Complete"
    )
    is_ready_for_moving = (
        row.get("is_unit_ready") and row.get("is_move_in_present") and row.get("is_qc_done")
    )
    in_turn_execution = row.get("is_vacant") and not row.get("is_unit_ready")

    if row.get("is_on_notice"):
        operational_state = "On Notice - Scheduled" if row.get("is_move_in_present") else "On Notice"
    elif not (row.get("is_vacant") or row.get("is_smi")):
        operational_state = "Out of Scope"
    elif row.get("is_move_in_present") and not row.get("is_ready_for_moving") and in_turn_execution:
        operational_state = "Move-In Risk"
    elif row.get("is_unit_ready") and row.get("is_move_in_present") and not row.get("is_qc_done"):
        operational_state = "QC Hold"
    elif row.get("is_task_stalled"):
        operational_state = "Work Stalled"
    elif row.get("task_state") == "In Progress":
        operational_state = "In Progress"
    elif row.get("is_unit_ready"):
        operational_state = "Apartment Ready"
    else:
        operational_state = "Pending Start"

    badge_map = {
        "On Notice - Scheduled": "📋 On Notice - Scheduled",
        "On Notice": "📋 On Notice",
        "Scheduled to Move In": "📅 Scheduled to Move In",
        "Move-In Risk": "🔴 Move-In Risk",
        "QC Hold": "🚫 QC Hold",
        "Work Stalled": "⏸️ Work Stalled",
        "Needs Attention": "🟡 Needs Attention",
        "In Progress": "🔧 In Progress",
        "Pending Start": "⏳ Pending Start",
        "Apartment Ready": "🟢 Apartment Ready",
        "Out of Scope": "Out of Scope",
    }
    attention_badge = badge_map.get(operational_state, operational_state)

    row = dict(row)
    row["is_unit_ready"] = is_unit_ready
    row["is_ready_for_moving"] = is_ready_for_moving
    row["in_turn_execution"] = in_turn_execution
    row["operational_state"] = operational_state
    row["attention_badge"] = attention_badge
    return row

# ---------------------------------------------------------------------------
# Stage 3 — SLA engine
# ---------------------------------------------------------------------------
def compute_sla_breaches(row: dict, today: Optional[date] = None) -> dict:
    today = today or _today()
    move_in = _parse_date(row.get("move_in_date"))
    days_to_move_in = (move_in - today).days if move_in else None
    is_vacant = row.get("is_vacant")
    is_unit_ready = row.get("is_unit_ready")
    is_ready_for_moving = row.get("is_ready_for_moving")
    is_move_in_present = row.get("is_move_in_present")
    report_ready_date = _parse_date(row.get("report_ready_date"))
    dv = row.get("dv")
    task_insp = row.get("task_insp") or {}
    insp_done = (task_insp.get("execution_status") or "").upper() == "VENDOR_COMPLETED"

    inspection_sla_breach = bool(is_vacant and not insp_done and dv is not None and dv > 1)
    sla_breach = bool(is_vacant and not is_unit_ready and dv is not None and dv > 10)
    sla_movein_breach = bool(
        is_move_in_present and not is_ready_for_moving and days_to_move_in is not None and days_to_move_in <= 2
    )
    plan_breach = bool(
        report_ready_date is not None and today >= report_ready_date and not is_unit_ready
    )
    has_violation = inspection_sla_breach or sla_breach or sla_movein_breach or plan_breach

    row = dict(row)
    row["days_to_move_in"] = days_to_move_in
    row["inspection_sla_breach"] = inspection_sla_breach
    row["sla_breach"] = sla_breach
    row["sla_movein_breach"] = sla_movein_breach
    row["plan_breach"] = plan_breach
    row["has_violation"] = has_violation
    return row

# ---------------------------------------------------------------------------
# WD summary and assign_display
# ---------------------------------------------------------------------------
def _wd_summary(row: dict) -> str:
    if not row.get("wd_present"):
        return "—"
    if row.get("wd_supervisor_notified") and row.get("wd_installed"):
        return "✅"
    return "⚠"

def _assign_display(row: dict) -> str:
    """Assignee = whoever is assigned to the Make Ready task."""
    mr = row.get("task_mr") or {}
    return (mr.get("assignee") or "").strip()

def enrich_row(row: dict, today: Optional[date] = None) -> dict:
    """Run compute_facts -> compute_intelligence -> compute_sla_breaches; set wd_summary and assign_display."""
    today = today or _today()
    row = compute_facts(row, today)
    row = compute_intelligence(row)
    row = compute_sla_breaches(row, today)
    row["wd_summary"] = _wd_summary(row)
    row["assign_display"] = _assign_display(row)
    return row


# ---------------------------------------------------------------------------
# Label maps (for UI dropdowns)
# ---------------------------------------------------------------------------
EXEC_LABEL_TO_VALUE = {
    "": None,
    "Not Started": "NOT_STARTED",
    "Scheduled": "SCHEDULED",
    "In Progress": "IN_PROGRESS",
    "Done": "VENDOR_COMPLETED",
    "N/A": "NA",
    "Canceled": "CANCELED",
}
EXEC_VALUE_TO_LABEL = {v: k for k, v in EXEC_LABEL_TO_VALUE.items() if v is not None}
EXEC_VALUE_TO_LABEL[None] = ""

CONFIRM_LABEL_TO_VALUE = {
    "Pending": "PENDING",
    "Confirmed": "CONFIRMED",
    "Rejected": "REJECTED",
    "Waived": "WAIVED",
}
CONFIRM_VALUE_TO_LABEL = {v: k for k, v in CONFIRM_LABEL_TO_VALUE.items()}

STATUS_OPTIONS = ["Vacant ready", "Vacant not ready", "On notice"]

BRIDGE_MAP = {
    "All": None,
    "Insp Breach": "inspection_sla_breach",
    "SLA Breach": "sla_breach",
    "SLA MI Breach": "sla_movein_breach",
    "Plan Bridge": "plan_breach",
}


# ---------------------------------------------------------------------------
# Public API: get_dmrb_board_rows, get_flag_bridge_rows
# ---------------------------------------------------------------------------
def get_dmrb_board_rows(
    turnovers: list[dict],
    units: list[dict],
    tasks: list[dict],
    notes: list[dict],
    search_unit: Optional[str] = None,
    filter_phase: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_nvm: Optional[str] = None,
    filter_assignee: Optional[str] = None,
    filter_qc: Optional[str] = None,
    today: Optional[date] = None,
) -> list[dict]:
    """Build flat rows per turnover, enrich, filter, sort. filter_phase = property_id 5/7/8; filter_assignee = any task assignee."""
    today = today or _today()
    unit_by_id = {u["unit_id"]: u for u in units}
    tasks_by_tid: dict[int, list[dict]] = {}
    for t in tasks:
        tid = t.get("turnover_id")
        if tid is not None:
            tasks_by_tid.setdefault(tid, []).append(t)

    rows = []
    for t in turnovers:
        u = unit_by_id.get(t["unit_id"])
        if not u:
            continue
        unit_code = u.get("unit_code_raw") or u.get("unit_code_norm") or ""
        if search_unit and search_unit.strip():
            if search_unit.strip().lower() not in unit_code.lower():
                continue
        if filter_phase and filter_phase != "All":
            if str(u.get("property_id")) != str(filter_phase):
                continue

        tasks_for_t = tasks_by_tid.get(t["turnover_id"], [])
        notes_for_t = [n for n in notes if n.get("turnover_id") == t["turnover_id"]]
        row = build_flat_row(t, u, tasks_for_t, notes_for_t)
        row = enrich_row(row, today)

        if filter_status and filter_status != "All":
            if (row.get("manual_ready_status") or "") != filter_status:
                continue
        if filter_nvm and filter_nvm != "All":
            if (row.get("nvm") or "") != filter_nvm:
                continue
        if filter_assignee and filter_assignee != "All":
            assignees = set()
            for key in ("task_insp", "task_cb", "task_mrb", "task_paint", "task_mr", "task_hk", "task_cc", "task_fw", "task_qc"):
                task = row.get(key) or {}
                a = (task.get("assignee") or "").strip()
                if a:
                    assignees.add(a)
            if filter_assignee not in assignees:
                continue
        if filter_qc and filter_qc != "All":
            qc_done = row.get("is_qc_done")
            if filter_qc == "QC Done" and not qc_done:
                continue
            if filter_qc == "QC Not done" and qc_done:
                continue

        rows.append(row)

    def sort_key(r: dict):
        move_in = _parse_date(r.get("move_in_date"))
        dv = r.get("dv") or 0
        return (0 if move_in is None else 1, move_in or date.max, -dv)

    rows.sort(key=sort_key)
    return rows


def get_flag_bridge_rows(
    turnovers: list[dict],
    units: list[dict],
    tasks: list[dict],
    notes: list[dict],
    search_unit: Optional[str] = None,
    filter_phase: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_nvm: Optional[str] = None,
    filter_assignee: Optional[str] = None,
    filter_qc: Optional[str] = None,
    breach_filter: Optional[str] = None,
    breach_value: Optional[str] = None,
    today: Optional[date] = None,
) -> list[dict]:
    """Same as get_dmrb_board_rows with optional breach_filter (BRIDGE_MAP key) and breach_value (All/Yes/No)."""
    rows = get_dmrb_board_rows(
        turnovers, units, tasks, notes,
        search_unit=search_unit,
        filter_phase=filter_phase,
        filter_status=filter_status,
        filter_nvm=filter_nvm,
        filter_assignee=filter_assignee,
        filter_qc=filter_qc,
        today=today,
    )
    if not breach_filter or breach_filter == "All" or not breach_value or breach_value == "All":
        return rows
    key = BRIDGE_MAP.get(breach_filter)
    if key is None:
        return rows
    want_true = breach_value == "Yes"
    return [r for r in rows if (r.get(key) is True) == want_true]


def get_risks_for_turnover(turnover_id: int, risks: list[dict]) -> list[dict]:
    return [r for r in risks if r.get("turnover_id") == turnover_id and not r.get("resolved_at")]


def get_notes_for_turnover(turnover_id: int, notes: list[dict]) -> list[dict]:
    return [n for n in notes if n.get("turnover_id") == turnover_id and not n.get("resolved_at")]
