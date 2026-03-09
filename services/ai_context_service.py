from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from io import StringIO
import csv
import json

from db import repository
from services import board_query_service


def build_enriched_turnovers(conn, *, today: date | None = None) -> list[dict]:
    return board_query_service.get_dmrb_board_rows(conn, property_ids=None, today=today or date.today())


def _unit_list(rows: list[dict], limit: int = 10) -> str:
    units = [r.get("unit_code") for r in rows if r.get("unit_code")]
    if not units:
        return "None"
    if len(units) <= limit:
        return ", ".join(units)
    return ", ".join(units[:limit]) + f" (+{len(units) - limit} more)"


def build_operational_summary(turnovers: list[dict]) -> str:
    total_units = len(turnovers)
    vacant_units = sum(1 for r in turnovers if r.get("is_vacant"))
    on_notice = sum(1 for r in turnovers if r.get("is_on_notice"))
    sla_breaches = sum(1 for r in turnovers if r.get("sla_breach"))
    inspection_overdue = sum(1 for r in turnovers if r.get("inspection_sla_breach"))
    plan_breaches = sum(1 for r in turnovers if r.get("plan_breach"))
    move_in_risks = sum(1 for r in turnovers if str(r.get("operational_state") or "") == "Move-In Risk")
    dv_values = [r.get("dv") for r in turnovers if isinstance(r.get("dv"), int)]
    avg_dv = round((sum(dv_values) / len(dv_values)), 1) if dv_values else 0.0
    units_ready = sum(1 for r in turnovers if r.get("is_unit_ready"))
    state_distribution = Counter(str(r.get("operational_state") or "Unknown") for r in turnovers)
    return "\n".join(
        [
            f"- Total Units: {total_units}",
            f"- Vacant Units: {vacant_units}",
            f"- On Notice: {on_notice}",
            f"- SLA Breaches: {sla_breaches}",
            f"- Inspection Overdue: {inspection_overdue}",
            f"- Plan Breaches: {plan_breaches}",
            f"- Move-In Risks: {move_in_risks}",
            f"- Average Days Vacant: {avg_dv}",
            f"- Units Ready: {units_ready}",
            f"- State Distribution: {json.dumps(dict(state_distribution), separators=(',', ':'))}",
        ]
    )


def build_task_pipeline_context(turnovers: list[dict]) -> str:
    stalled = [r for r in turnovers if r.get("is_task_stalled")]
    task_counts = Counter((r.get("current_task") or "None") for r in turnovers)
    return "\n".join(
        [
            f"- Stuck Units: {_unit_list(stalled)}",
            f"- Per-Task Counts (Current): {json.dumps(dict(task_counts), separators=(',', ':'))}",
            f"- Bottleneck Analysis: Identified {len(stalled)} units with stalled tasks.",
        ]
    )


def build_risk_forecast_context(turnovers: list[dict]) -> str:
    approaching = [r for r in turnovers if (r.get("dv") or 0) >= 8 and not r.get("sla_breach")]
    at_risk_move_ins = [
        r for r in turnovers if r.get("days_to_move_in") is not None and int(r.get("days_to_move_in")) <= 3 and not r.get("is_ready_for_moving")
    ]
    plan_breach = [r for r in turnovers if r.get("plan_breach")]
    return "\n".join(
        [
            f"- Approaching SLA Breach (DV 8+): {_unit_list(approaching)}",
            f"- At-Risk Move-Ins (<= 3 days): {_unit_list(at_risk_move_ins)}",
            f"- Plan Breach (Missed Ready Date): {_unit_list(plan_breach)}",
        ]
    )


def build_assignee_context(turnovers: list[dict]) -> str:
    grouped: dict[str, list[int]] = defaultdict(list)
    for row in turnovers:
        assignee = (row.get("assign_display") or "").strip() or "Unassigned"
        grouped[assignee].append(int(row.get("task_completion_ratio") or 0))
    lines: list[str] = []
    for assignee in sorted(grouped):
        progress = grouped[assignee]
        avg_progress = round(sum(progress) / len(progress), 1) if progress else 0.0
        lines.append(f"{assignee}: {len(progress)} units, Avg Progress: {avg_progress}%")
    return "\n".join(lines) if lines else "No assignee data."


def build_notes_context(conn, turnovers: list[dict]) -> str:
    turnover_ids = [r.get("turnover_id") for r in turnovers if r.get("turnover_id") is not None]
    notes = repository.get_notes_for_turnover_ids(conn, turnover_ids, unresolved_only=True)
    blocking = [n for n in notes if bool(n.get("blocking"))]
    by_type = Counter((n.get("note_type") or "Unknown") for n in blocking)
    return "\n".join(
        [
            f"- Active Blocking Notes: {len(blocking)}",
            f"- Count by Type: {json.dumps(dict(by_type), separators=(',', ':'))}",
        ]
    )


def build_wd_context(turnovers: list[dict]) -> str:
    needs_install = [r for r in turnovers if bool(r.get("wd_present")) and not bool(r.get("wd_installed"))]
    notified = [r for r in needs_install if bool(r.get("wd_supervisor_notified"))]
    pending = [r for r in needs_install if not bool(r.get("wd_supervisor_notified"))]
    return "\n".join(
        [
            f"- Units needing W/D installation: {len(needs_install)}",
            f"- Supervisor Notified: {len(notified)}",
            f"- Pending Notification: {len(pending)}",
        ]
    )


def build_phase_comparison(turnovers: list[dict]) -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in turnovers:
        groups[str(row.get("phase_code") or "Unknown")].append(row)
    lines: list[str] = []
    for phase_code in sorted(groups):
        rows = groups[phase_code]
        dv_values = [r.get("dv") for r in rows if isinstance(r.get("dv"), int)]
        avg_dv = round((sum(dv_values) / len(dv_values)), 1) if dv_values else 0.0
        breaches = sum(1 for r in rows if r.get("sla_breach"))
        avg_progress = round(sum(int(r.get("task_completion_ratio") or 0) for r in rows) / len(rows), 1) if rows else 0.0
        lines.append(
            f"Phase {phase_code}: {len(rows)} units, Avg DV: {avg_dv}, Breaches: {breaches}, Avg Progress: {avg_progress}%"
        )
    return "\n".join(lines) if lines else "No phase comparison data."


def build_aging_distribution(turnovers: list[dict]) -> str:
    buckets = {"1-10": 0, "11-20": 0, "21-30": 0, "31-60": 0, "61-120": 0, "120+": 0}
    for row in turnovers:
        dv = row.get("dv")
        if not isinstance(dv, int) or dv <= 0:
            continue
        if dv <= 10:
            buckets["1-10"] += 1
        elif dv <= 20:
            buckets["11-20"] += 1
        elif dv <= 30:
            buckets["21-30"] += 1
        elif dv <= 60:
            buckets["31-60"] += 1
        elif dv <= 120:
            buckets["61-120"] += 1
        else:
            buckets["120+"] += 1
    return json.dumps(buckets, separators=(",", ":"))


def build_trend_context() -> str:
    return ""


def build_data_csv(turnovers: list[dict]) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["Unit", "Phase", "Status", "DV", "DTBR", "State", "Badge", "Current Task", "Progress%", "Move-In Date", "Assignee", "WD"]
    )
    for row in turnovers:
        writer.writerow(
            [
                row.get("unit_code") or "",
                row.get("phase_code") or "",
                row.get("manual_ready_status") or "",
                row.get("dv") if row.get("dv") is not None else "N/A",
                row.get("dtbr") if row.get("dtbr") is not None else "N/A",
                row.get("operational_state") or "",
                row.get("attention_badge") or "",
                row.get("current_task") or "",
                f"{int(row.get('task_completion_ratio') or 0)}%",
                row.get("move_in_date") or "N/A",
                (row.get("assign_display") or "").strip() or "Unassigned",
                row.get("wd_summary") or "—",
            ]
        )
    return output.getvalue().strip()


def build_system_prompt(turnovers: list[dict], *, conn=None, today: date | None = None) -> str:
    today_value = today or date.today()
    notes_context = build_notes_context(conn, turnovers) if conn is not None else "- Active Blocking Notes: 0\n- Count by Type: {}"
    return (
        "You are the DMRB (Digital Make Ready Board) AI Assistant. You help property managers track and manage apartment turnovers.\n"
        "DOMAIN KNOWLEDGE:\n"
        "- 8 task types in order: Inspection, Carpet Bid, Make Ready Bid, Paint, Make Ready, Housekeeping, Carpet Clean, Final Walk.\n"
        "- SLA thresholds: Inspection=1 day, Paint=2, Make Ready=3, Housekeeping=6, Carpet Clean=7, Turn SLA=10 days total.\n"
        "- Lifecycle phases: NOTICE, NOTICE_SMI, VACANT, SMI, STABILIZATION, MOVE_IN_COMPLETE, CLOSED, CANCELED.\n"
        "- Operational states: On Notice, Pending Start, In Progress, Work Stalled, Blocked, Unit Ready, QC Hold, Ready for Move-In, Move-In, CLOSED, CANCELED.\n"
        "- Attention badges: On Notice, Pending Start, In Progress, Work Stalled, Blocked, Inspection Overdue, SLA Breach, Plan Breach, SLA + Plan Breach, CRITICAL Move-In Risk, QC Hold, Unit Ready, Apartment Ready, CLOSED, CANCELED.\n"
        "- Key metrics: dv (days vacant), dtbr (days to be ready), task completion ratio.\n"
        "Respond as a knowledgeable, efficient, and professional assistant. Use the data provided below to answer questions accurately.\n"
        f"TODAY'S DATE: {today_value.isoformat()}\n"
        "[SECTION 1: OPERATIONAL SUMMARY]\n"
        f"{build_operational_summary(turnovers)}\n"
        "[SECTION 2: TASK PIPELINE]\n"
        f"{build_task_pipeline_context(turnovers)}\n"
        "[SECTION 3: RISK FORECAST]\n"
        f"{build_risk_forecast_context(turnovers)}\n"
        "[SECTION 4: ASSIGNEE PERFORMANCE]\n"
        f"{build_assignee_context(turnovers)}\n"
        "[SECTION 5: NOTES CONTEXT]\n"
        f"{notes_context}\n"
        "[SECTION 6: W/D CONTEXT]\n"
        f"{build_wd_context(turnovers)}\n"
        "[SECTION 7: PHASE (BUILDING) COMPARISON]\n"
        f"{build_phase_comparison(turnovers)}\n"
        "[SECTION 8: AGING DISTRIBUTION]\n"
        f"{build_aging_distribution(turnovers)}\n"
        "[SECTION 9: TREND CONTEXT]\n"
        f"{build_trend_context()}\n"
        "[SECTION 10: FULL DATA CSV]\n"
        f"{build_data_csv(turnovers)}"
    )
