"""
Note service: create and resolve notes with audit. No reconciliation (notes do not affect lifecycle/risk).
"""
from datetime import datetime
from typing import Optional

from db import repository


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def create_note(
    *,
    conn,
    turnover_id: int,
    description: str,
    note_type: str = "info",
    blocking: int = 0,
    severity: str = "INFO",
    actor: str = "manager",
) -> int:
    created_at = _now_iso()
    note_id = repository.insert_note(
        conn,
        {
            "turnover_id": turnover_id,
            "note_type": note_type,
            "blocking": blocking,
            "severity": severity,
            "description": description,
            "created_at": created_at,
        },
    )
    repository.insert_audit_log(
        conn,
        {
            "entity_type": "note",
            "entity_id": note_id,
            "field_name": "created",
            "old_value": None,
            "new_value": str(note_id),
            "changed_at": created_at,
            "actor": actor,
            "source": "manual",
            "correlation_id": None,
        },
    )
    return note_id


def resolve_note(
    *,
    conn,
    note_id: int,
    resolved_at: Optional[str] = None,
    actor: str = "manager",
) -> None:
    row = repository.get_note_by_id(conn, note_id)
    if row is None:
        raise ValueError("Note not found")
    if row["resolved_at"] is not None:
        return
    resolved_at = resolved_at or _now_iso()
    repository.update_note_resolved(conn, note_id, resolved_at)
    repository.insert_audit_log(
        conn,
        {
            "entity_type": "note",
            "entity_id": note_id,
            "field_name": "resolved_at",
            "old_value": None,
            "new_value": resolved_at,
            "changed_at": resolved_at,
            "actor": actor,
            "source": "manual",
            "correlation_id": None,
        },
    )
