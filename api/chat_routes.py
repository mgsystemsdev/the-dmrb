from __future__ import annotations

from datetime import date
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.settings import get_settings
from db.connection import ensure_database_ready, get_connection
from services import ai_context_service, chat_service


router = APIRouter(prefix="/api/chat", tags=["chat"])


class CreateSessionBody(BaseModel):
    title: str | None = None


class ChatBody(BaseModel):
    sessionId: str
    message: str = Field(min_length=1)


def _db_path() -> str:
    return get_settings().database_path


def _conn():
    ensure_database_ready(_db_path())
    return get_connection(_db_path())


@router.get("/sessions")
def list_chat_sessions():
    conn = _conn()
    try:
        sessions = chat_service.list_sessions(conn)
        return sessions
    finally:
        conn.close()


@router.post("/sessions")
def create_chat_session(body: CreateSessionBody):
    conn = _conn()
    try:
        session = chat_service.create_session(conn, title=body.title)
        conn.commit()
        return session
    finally:
        conn.close()


@router.get("/sessions/{session_id}/messages")
def get_chat_messages(session_id: str):
    conn = _conn()
    try:
        return chat_service.get_session_messages(conn, session_id)
    finally:
        conn.close()


@router.delete("/sessions/{session_id}")
def delete_chat_session(session_id: str):
    conn = _conn()
    try:
        chat_service.delete_session(conn, session_id)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.get("/suggestions")
def get_chat_suggestions():
    return chat_service.SUGGESTED_QUESTIONS


@router.post("")
def post_chat(body: ChatBody):
    session_id = body.sessionId
    if session_id == "new":
        session_id = str(uuid.uuid4())

    conn = _conn()
    try:
        turnovers = ai_context_service.build_enriched_turnovers(conn, today=date.today())
        result = chat_service.chat(
            conn,
            session_id=session_id,
            user_message=body.message,
            turnovers=turnovers,
            today=date.today(),
        )
        conn.commit()
        return {"reply": result["reply"], "sessionId": result["session_id"]}
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        conn.close()
