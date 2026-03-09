from __future__ import annotations

from datetime import datetime

from db import repository
from services import chat_service
from tests.helpers.db_bootstrap import runtime_db


def _seed(conn):
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT INTO property (property_id, name) VALUES (?, ?)", (1, "P1"))
    unit = repository.resolve_unit(
        conn,
        property_id=1,
        phase_code="7",
        building_code="20",
        unit_number="0303",
        unit_code_raw="7-20-0303",
        unit_code_norm="7-20-0303",
        unit_identity_key="7-20-0303",
    )
    turnover_id = repository.insert_turnover(
        conn,
        {
            "property_id": 1,
            "unit_id": unit["unit_id"],
            "source_turnover_key": "CHAT-1",
            "move_out_date": "2026-03-01",
            "move_in_date": "2026-03-20",
            "report_ready_date": "2026-03-12",
            "manual_ready_status": "Vacant not ready",
            "wd_present": 0,
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
            "execution_status": "NOT_STARTED",
            "confirmation_status": "PENDING",
        },
    )
    conn.commit()


def test_chat_creates_session_and_persists_messages():
    with runtime_db() as (conn, _):
        _seed(conn)
        turnovers = [{"unit_code": "7-20-0303"}]

        def fake_reply(messages):
            assert messages[0]["role"] == "system"
            return "Assistant response"

        result = chat_service.chat(
            conn,
            session_id="session-1",
            user_message="Give me a morning briefing",
            turnovers=turnovers,
            reply_fn=fake_reply,
        )
        conn.commit()

        assert result["session_id"] == "session-1"
        assert result["reply"] == "Assistant response"

        session = repository.get_chat_session(conn, "session-1")
        assert session is not None
        assert session["title"] == "Give me a morning briefing"

        messages = repository.get_chat_messages(conn, "session-1")
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[1]["model"] == "gpt-4o-mini"
