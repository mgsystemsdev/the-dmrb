"""Chat sessions and messages repository functions."""
from __future__ import annotations

import sqlite3

from db.repository._helpers import _inserted_id, _row_to_dict, _rows_to_dicts


def get_chat_sessions(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute(
        """SELECT * FROM chat_session
           ORDER BY last_message_at DESC, id DESC"""
    )
    return _rows_to_dicts(cursor.fetchall())


def get_chat_session(conn: sqlite3.Connection, session_id: str):
    cursor = conn.execute(
        "SELECT * FROM chat_session WHERE session_id = ? LIMIT 1",
        (session_id,),
    )
    return _row_to_dict(cursor.fetchone())


def insert_chat_session(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """INSERT INTO chat_session (
            session_id, title, started_at, last_message_at
        ) VALUES (?, ?, ?, ?)""",
        (
            data["session_id"],
            data.get("title", "New Chat"),
            data.get("started_at"),
            data.get("last_message_at"),
        ),
    )
    return _inserted_id(conn, "chat_session", "id", cursor=cursor)


def update_chat_session_fields(conn: sqlite3.Connection, session_id: str, fields: dict) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [session_id]
    conn.execute(
        f"UPDATE chat_session SET {set_clause} WHERE session_id = ?",
        values,
    )


def get_chat_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    cursor = conn.execute(
        """SELECT * FROM chat_message
           WHERE session_id = ?
           ORDER BY id ASC""",
        (session_id,),
    )
    return _rows_to_dicts(cursor.fetchall())


def insert_chat_message(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """INSERT INTO chat_message (
            session_id, role, content, model, created_at
        ) VALUES (?, ?, ?, ?, ?)""",
        (
            data["session_id"],
            data["role"],
            data["content"],
            data.get("model"),
            data.get("created_at"),
        ),
    )
    return _inserted_id(conn, "chat_message", "id", cursor=cursor)


def delete_chat_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM chat_message WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM chat_session WHERE session_id = ?", (session_id,))
