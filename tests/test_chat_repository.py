from __future__ import annotations

from db import repository
from tests.helpers.db_bootstrap import runtime_db


def test_chat_session_and_messages_crud_with_delete_cascade():
    with runtime_db() as (conn, _):
        repository.insert_chat_session(
            conn,
            {
                "session_id": "s-1",
                "title": "Morning Brief",
                "started_at": "2026-03-08T10:00:00+00:00",
                "last_message_at": "2026-03-08T10:00:00+00:00",
            },
        )
        repository.insert_chat_message(
            conn,
            {
                "session_id": "s-1",
                "role": "user",
                "content": "How many units are vacant?",
                "model": None,
                "created_at": "2026-03-08T10:00:01+00:00",
            },
        )
        repository.insert_chat_message(
            conn,
            {
                "session_id": "s-1",
                "role": "assistant",
                "content": "There are 10 vacant units.",
                "model": "gpt-4o-mini",
                "created_at": "2026-03-08T10:00:03+00:00",
            },
        )
        conn.commit()

        sessions = repository.get_chat_sessions(conn)
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s-1"

        messages = repository.get_chat_messages(conn, "s-1")
        assert [m["role"] for m in messages] == ["user", "assistant"]

        repository.delete_chat_session(conn, "s-1")
        conn.commit()

        assert repository.get_chat_session(conn, "s-1") is None
        assert repository.get_chat_messages(conn, "s-1") == []
