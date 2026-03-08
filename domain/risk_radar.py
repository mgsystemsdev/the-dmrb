"""
Risk Radar scoring for enriched turnover rows.
Pure logic: no DB or UI dependencies.
"""
from __future__ import annotations

from typing import Any


RISK_WEIGHTS = {
    "inspection_overdue": 3,
    "task_execution_overdue": 2,
    "qc_rejected": 2,
    "sla_breach": 3,
    "sla_near_breach": 2,
    "blocked_dependency": 1,
    "movein_approaching_incomplete": 2,
}

LOW_MAX = 2
MEDIUM_MAX = 5


def _risk_level_for_score(score: int) -> str:
    if score <= LOW_MAX:
        return "LOW"
    if score <= MEDIUM_MAX:
        return "MEDIUM"
    return "HIGH"


def score_enriched_turnover(row: dict[str, Any]) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []

    if row.get("inspection_sla_breach"):
        score += RISK_WEIGHTS["inspection_overdue"]
        reasons.append("Inspection overdue")

    if row.get("is_task_stalled"):
        score += RISK_WEIGHTS["task_execution_overdue"]
        reasons.append("Task execution overdue")

    task_qc = row.get("task_qc") or {}
    if (task_qc.get("confirmation_status") or "").upper() == "REJECTED":
        score += RISK_WEIGHTS["qc_rejected"]
        reasons.append("QC rejected task")

    if row.get("sla_breach"):
        score += RISK_WEIGHTS["sla_breach"]
        reasons.append("SLA breach active")

    if row.get("sla_movein_breach") or (
        row.get("days_to_move_in") is not None
        and int(row.get("days_to_move_in")) <= 2
        and not bool(row.get("is_ready_for_moving"))
    ):
        score += RISK_WEIGHTS["sla_near_breach"]
        reasons.append("SLA near breach")

    if row.get("current_task") and row.get("next_task") and row.get("is_task_stalled"):
        score += RISK_WEIGHTS["blocked_dependency"]
        reasons.append("Blocked task dependency")

    if (
        row.get("days_to_move_in") is not None
        and int(row.get("days_to_move_in")) <= 3
        and not bool(row.get("is_unit_ready"))
    ):
        score += RISK_WEIGHTS["movein_approaching_incomplete"]
        reasons.append("Move-in approaching with incomplete tasks")

    return {
        "risk_score": score,
        "risk_level": _risk_level_for_score(score),
        "risk_reasons": reasons,
    }
