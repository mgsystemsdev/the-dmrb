from __future__ import annotations

from datetime import date, datetime

from db import repository
from services import ai_context_service
from tests.helpers.db_bootstrap import runtime_db


def _seed(conn):
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT INTO property (property_id, name) VALUES (?, ?)", (1, "P1"))
    unit = repository.resolve_unit(
        conn,
        property_id=1,
        phase_code="5",
        building_code="70",
        unit_number="0101",
        unit_code_raw="5-70-0101",
        unit_code_norm="5-70-0101",
        unit_identity_key="5-70-0101",
    )
    turnover_id = repository.insert_turnover(
        conn,
        {
            "property_id": 1,
            "unit_id": unit["unit_id"],
            "source_turnover_key": "CTX-1",
            "move_out_date": "2026-03-01",
            "move_in_date": "2026-03-20",
            "report_ready_date": "2026-03-15",
            "manual_ready_status": "Vacant not ready",
            "wd_present": 1,
            "wd_supervisor_notified": 0,
            "wd_installed": 0,
            "created_at": now,
            "updated_at": now,
        },
    )
    repository.insert_task(
        conn,
        {
            "turnover_id": turnover_id,
            "task_type": "Insp",
            "required": 1,
            "blocking": 1,
            "execution_status": "IN_PROGRESS",
            "confirmation_status": "PENDING",
        },
    )
    repository.insert_note(
        conn,
        {
            "turnover_id": turnover_id,
            "note_type": "Maintenance",
            "blocking": 1,
            "severity": "WARNING",
            "description": "Waiting on vendor",
            "created_at": now,
        },
    )
    conn.commit()


def test_build_system_prompt_contains_all_sections_and_csv():
    with runtime_db() as (conn, _):
        _seed(conn)
        turnovers = ai_context_service.build_enriched_turnovers(conn, today=date(2026, 3, 8))
        prompt = ai_context_service.build_system_prompt(turnovers, conn=conn, today=date(2026, 3, 8))

        assert "[SECTION 1: OPERATIONAL SUMMARY]" in prompt
        assert "[SECTION 10: FULL DATA CSV]" in prompt
        assert "Unit,Phase,Status,DV,DTBR,State,Badge,Current Task,Progress%,Move-In Date,Assignee,WD" in prompt
        assert "5-70-0101" in prompt
