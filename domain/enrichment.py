"""
Pure enrichment for DMRB board: facts, intelligence, SLA breaches.
No Streamlit or DB imports. All functions deterministic; today passed explicitly.
"""
from datetime import date, timedelta
from typing import Any, Optional

from domain.lifecycle import (
    CANCELED,
    CLOSED,
    MOVE_IN_COMPLETE,
    NOTICE,
    NOTICE_SMI,
    SMI,
    STABILIZATION,
    VACANT,
    derive_lifecycle_phase,
    derive_nvm,
    effective_move_out_date,
)

# Task type sequence for execution order (used by compute_facts)
TASK_TYPES_SEQUENCE = ["Insp", "CB", "MRB", "Paint", "MR", "HK", "CC", "FW"]
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


def derive_phase(t: dict, today: date) -> str:
    """Phase: preserve mock behavior when move_out_date is None; otherwise use domain.lifecycle.derive_lifecycle_phase."""
    move_out = _parse_date(t.get("move_out_date"))
    move_in = _parse_date(t.get("move_in_date"))
    if move_out is None:
        return NOTICE_SMI if move_in else NOTICE
    return derive_lifecycle_phase(
        move_out_date=move_out,
        move_in_date=move_in,
        closed_at=t.get("closed_at"),
        canceled_at=t.get("canceled_at"),
        today=today,
    )


def compute_facts(row: dict, today: date) -> dict:
    """Stage 1: dv, dtbr, phase, nvm, task_state, current_task, is_task_stalled, etc."""
    move_out = effective_move_out_date(row)
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

    dv = (today - move_out).days if move_out and today >= move_out else None
    dtbr = (move_in - today).days if move_in else None
    phase = derive_phase(
        {
            "move_out_date": move_out,
            "move_in_date": row.get("move_in_date"),
            "closed_at": row.get("closed_at"),
            "canceled_at": row.get("canceled_at"),
        },
        today,
    )
    nvm = derive_nvm(phase)

    is_vacant = phase == VACANT
    is_smi = phase in (SMI, MOVE_IN_COMPLETE, STABILIZATION)
    is_on_notice = phase in (NOTICE, NOTICE_SMI)
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
    row["has_move_out_drift"] = bool(
        _parse_date(row.get("move_out_date")) is not None
        and move_out is not None
        and _parse_date(row.get("move_out_date")) != move_out
    )
    manual_override_active = row.get("move_out_manual_override_at") is not None and _parse_date(row.get("move_out_date")) is not None
    row["is_effective_anchor_confirmed"] = (row.get("legal_confirmation_source") is not None) and not manual_override_active
    row["legal_dot"] = "GREEN" if row.get("legal_confirmation_source") else "RED"
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


# Badge map for Alert column (tags). Matches backup frontend mock_data_v2 Stage 2.
ATTENTION_BADGE_MAP = {
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


def compute_intelligence(row: dict) -> dict:
    """Stage 2: is_unit_ready, operational_state, attention_badge (tags for Alert column)."""
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

    attention_badge = ATTENTION_BADGE_MAP.get(operational_state, operational_state)

    row = dict(row)
    row["is_unit_ready"] = is_unit_ready
    row["is_ready_for_moving"] = is_ready_for_moving
    row["in_turn_execution"] = in_turn_execution
    row["operational_state"] = operational_state
    row["attention_badge"] = attention_badge
    return row


def compute_sla_breaches(row: dict, today: date) -> dict:
    """Stage 3: inspection_sla_breach, sla_breach, sla_movein_breach, plan_breach, has_violation."""
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


def _wd_summary(row: dict) -> str:
    if not row.get("wd_present"):
        return "—"
    if row.get("wd_supervisor_notified") and row.get("wd_installed"):
        return "\u2705"  # checkmark (mock: ✅)
    return "\u26a0"  # warning (mock: ⚠)


def _assign_display(row: dict) -> str:
    """Assignee = whoever is assigned to the Make Ready task."""
    mr = row.get("task_mr") or {}
    return (mr.get("assignee") or "").strip()


def enrich_row(row: dict, today: date) -> dict:
    """Run compute_facts -> compute_intelligence -> compute_sla_breaches; set wd_summary and assign_display."""
    row = compute_facts(row, today)
    row = compute_intelligence(row)
    row = compute_sla_breaches(row, today)
    row["wd_summary"] = _wd_summary(row)
    row["assign_display"] = _assign_display(row)
    return row
