import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.risk_radar import score_enriched_turnover


def test_low_risk_when_no_signals():
    row = {
        "inspection_sla_breach": False,
        "is_task_stalled": False,
        "sla_breach": False,
        "sla_movein_breach": False,
        "days_to_move_in": 10,
        "is_unit_ready": True,
        "is_ready_for_moving": True,
        "task_qc": {"confirmation_status": "CONFIRMED"},
    }
    result = score_enriched_turnover(row)
    assert result["risk_score"] == 0
    assert result["risk_level"] == "LOW"
    assert result["risk_reasons"] == []


def test_scoring_increases_with_signals_and_reasons_present():
    row = {
        "inspection_sla_breach": True,
        "is_task_stalled": True,
        "sla_breach": False,
        "sla_movein_breach": False,
        "days_to_move_in": 2,
        "is_unit_ready": False,
        "is_ready_for_moving": False,
        "current_task": "MR",
        "next_task": "HK",
        "task_qc": {"confirmation_status": "REJECTED"},
    }
    result = score_enriched_turnover(row)
    assert result["risk_score"] >= 6
    assert result["risk_level"] == "HIGH"
    assert "Inspection overdue" in result["risk_reasons"]
    assert "QC rejected task" in result["risk_reasons"]
    assert "Move-in approaching with incomplete tasks" in result["risk_reasons"]


def test_medium_classification_threshold():
    row = {
        "inspection_sla_breach": True,  # +3
        "is_task_stalled": False,
        "sla_breach": False,
        "sla_movein_breach": False,
        "days_to_move_in": None,
        "is_unit_ready": True,
        "is_ready_for_moving": True,
        "task_qc": {"confirmation_status": "PENDING"},
    }
    result = score_enriched_turnover(row)
    assert result["risk_score"] == 3
    assert result["risk_level"] == "MEDIUM"


def test_high_classification_threshold():
    row = {
        "inspection_sla_breach": True,  # +3
        "is_task_stalled": True,  # +2
        "sla_breach": True,  # +3
        "sla_movein_breach": False,
        "days_to_move_in": None,
        "is_unit_ready": True,
        "is_ready_for_moving": True,
        "task_qc": {"confirmation_status": "PENDING"},
    }
    result = score_enriched_turnover(row)
    assert result["risk_score"] >= 8
    assert result["risk_level"] == "HIGH"
