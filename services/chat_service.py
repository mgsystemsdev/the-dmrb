from __future__ import annotations

from datetime import datetime, timezone, date
import os
from typing import Any

from db import repository
from services import ai_context_service


SUGGESTED_QUESTIONS = [
    "How many units are vacant right now?",
    "How has our SLA compliance changed recently?",
    "Which units have been stuck on the same task for 3+ days?",
    "Which units are about to breach SLA?",
    "Who has the most open units?",
    "Which units have blocking notes?",
    "Any data integrity flags right now?",
    "Give me a morning briefing",
    "Which units still need W/D installation?",
    "Compare Phase 5 vs Phase 7 performance",
]

DEFAULT_MODEL = "gpt-4o-mini"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_openai_reply(messages: list[dict[str, str]]) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY"),
        base_url=os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL"),
    )
    completion = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=messages,
    )
    if not completion.choices:
        return "I could not generate a response for that request."
    content = completion.choices[0].message.content
    if isinstance(content, str):
        return content.strip() or "I could not generate a response for that request."
    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        merged = "\n".join(p for p in text_parts if p).strip()
        return merged or "I could not generate a response for that request."
    return "I could not generate a response for that request."


def _ensure_session(conn, session_id: str, user_message: str) -> None:
    existing = repository.get_chat_session(conn, session_id)
    if existing is not None:
        return
    now_iso = _utc_now_iso()
    repository.insert_chat_session(
        conn,
        {
            "session_id": session_id,
            "title": (user_message or "New Chat").strip()[:50] or "New Chat",
            "started_at": now_iso,
            "last_message_at": now_iso,
        },
    )


def _save_message(conn, *, session_id: str, role: str, content: str, model: str | None) -> None:
    repository.insert_chat_message(
        conn,
        {
            "session_id": session_id,
            "role": role,
            "content": content,
            "model": model,
            "created_at": _utc_now_iso(),
        },
    )


def _recent_history(conn, session_id: str, limit: int = 20) -> list[dict[str, str]]:
    rows = repository.get_chat_messages(conn, session_id)
    rows = rows[-limit:]
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def list_sessions(conn) -> list[dict]:
    return repository.get_chat_sessions(conn)


def create_session(conn, title: str | None = None, *, session_id: str | None = None) -> dict:
    import uuid

    sid = session_id or str(uuid.uuid4())
    now_iso = _utc_now_iso()
    repository.insert_chat_session(
        conn,
        {
            "session_id": sid,
            "title": (title or "New Chat").strip()[:50] or "New Chat",
            "started_at": now_iso,
            "last_message_at": now_iso,
        },
    )
    return repository.get_chat_session(conn, sid)


def delete_session(conn, session_id: str) -> None:
    repository.delete_chat_session(conn, session_id)


def get_session_messages(conn, session_id: str) -> list[dict]:
    return repository.get_chat_messages(conn, session_id)


def chat(
    conn,
    *,
    session_id: str,
    user_message: str,
    turnovers: list[dict],
    model: str = DEFAULT_MODEL,
    reply_fn: Any | None = None,
    today: date | None = None,
) -> dict:
    message_text = (user_message or "").strip()
    if not message_text:
        raise ValueError("message must not be empty")
    _ensure_session(conn, session_id, message_text)
    _save_message(conn, session_id=session_id, role="user", content=message_text, model=None)

    system_prompt = ai_context_service.build_system_prompt(turnovers, conn=conn, today=today)
    history = _recent_history(conn, session_id, limit=20)
    llm_messages = [{"role": "system", "content": system_prompt}] + history

    if reply_fn is None:
        reply_text = _default_openai_reply(llm_messages)
    else:
        reply_text = reply_fn(llm_messages)
    reply_text = (reply_text or "").strip() or "I could not generate a response for that request."

    _save_message(conn, session_id=session_id, role="assistant", content=reply_text, model=model)
    repository.update_chat_session_fields(conn, session_id, {"last_message_at": _utc_now_iso()})
    return {"reply": reply_text, "session_id": session_id}
