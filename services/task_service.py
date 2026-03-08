from datetime import date, datetime
from typing import Any, Optional

from db import repository
from services.turnover_service import reconcile_after_task_change

ALLOWED_TASK_FIELDS = frozenset({
    "execution_status", "confirmation_status", "vendor_due_date",
    "assignee", "blocking_reason", "required", "blocking",
})


def _get_task(conn, task_id: int):
    cursor = conn.execute("SELECT * FROM task WHERE task_id = ?", (task_id,))
    return cursor.fetchone()


def _audit(conn, task_id: int, field_name: str, old_value: Optional[str], new_value: Optional[str], actor: str, source: str) -> None:
    repository.insert_audit_log(
        conn,
        {
            "entity_type": "task",
            "entity_id": task_id,
            "field_name": field_name,
            "old_value": old_value,
            "new_value": new_value,
            "changed_at": datetime.utcnow().isoformat(),
            "actor": actor,
            "source": source,
            "correlation_id": None,
        },
    )


def mark_vendor_completed(
    *,
    conn,
    task_id: int,
    today: Optional[date] = None,
    actor: str = "manager",
) -> None:
    row = _get_task(conn, task_id)
    if row is None:
        raise ValueError("Task not found")
    old_status = row["execution_status"]
    now_iso = datetime.utcnow().isoformat()
    repository.update_task_fields(
        conn,
        task_id,
        {
            "execution_status": "VENDOR_COMPLETED",
            "vendor_completed_at": now_iso,
        },
    )
    _audit(conn, task_id, "execution_status", old_status, "VENDOR_COMPLETED", actor, "manual")
    if today is None:
        today = date.today()
    reconcile_after_task_change(conn=conn, turnover_id=row["turnover_id"], today=today, actor=actor)


def confirm_task(
    *,
    conn,
    task_id: int,
    today: Optional[date] = None,
    actor: str = "manager",
) -> None:
    row = _get_task(conn, task_id)
    if row is None:
        raise ValueError("Task not found")
    if row["execution_status"] != "VENDOR_COMPLETED":
        raise ValueError("Cannot confirm task: execution_status is not VENDOR_COMPLETED")
    old_status = row["confirmation_status"]
    now_iso = datetime.utcnow().isoformat()
    repository.update_task_fields(
        conn,
        task_id,
        {
            "confirmation_status": "CONFIRMED",
            "manager_confirmed_at": now_iso,
        },
    )
    _audit(conn, task_id, "confirmation_status", old_status, "CONFIRMED", actor, "manual")
    if today is None:
        today = date.today()
    reconcile_after_task_change(conn=conn, turnover_id=row["turnover_id"], today=today, actor=actor)


def reject_task(
    *,
    conn,
    task_id: int,
    today: Optional[date] = None,
    actor: str = "manager",
) -> None:
    row = _get_task(conn, task_id)
    if row is None:
        raise ValueError("Task not found")
    if row["confirmation_status"] != "CONFIRMED":
        raise ValueError("Cannot reject task: confirmation_status is not CONFIRMED")
    old_confirmation = row["confirmation_status"]
    old_execution = row["execution_status"]
    repository.update_task_fields(
        conn,
        task_id,
        {
            "confirmation_status": "REJECTED",
            "execution_status": "IN_PROGRESS",
            "manager_confirmed_at": None,
        },
    )
    _audit(conn, task_id, "confirmation_status", old_confirmation, "REJECTED", actor, "manual")
    _audit(conn, task_id, "execution_status", old_execution, "IN_PROGRESS", actor, "manual")
    if today is None:
        today = date.today()
    reconcile_after_task_change(conn=conn, turnover_id=row["turnover_id"], today=today, actor=actor)


def update_task_fields(
    *,
    conn,
    task_id: int,
    fields: dict[str, Any],
    today: Optional[date] = None,
    actor: str = "manager",
) -> None:
    """Update task fields; delegate to mark_vendor_completed/confirm_task/reject_task when appropriate. Reconcile once per mutation."""
    row = _get_task(conn, task_id)
    if row is None:
        raise ValueError("Task not found")
    if today is None:
        today = date.today()
    turnover_id = row["turnover_id"]

    # Delegate canonical transitions
    if "execution_status" in fields:
        new_exec = (fields.get("execution_status") or "").strip().upper()
        if new_exec == "VENDOR_COMPLETED":
            mark_vendor_completed(conn=conn, task_id=task_id, today=today, actor=actor)
            return
    if "confirmation_status" in fields:
        new_conf = (fields.get("confirmation_status") or "").strip().upper()
        cur_conf = (row["confirmation_status"] or "").strip().upper()
        if new_conf == "CONFIRMED":
            confirm_task(conn=conn, task_id=task_id, today=today, actor=actor)
            return
        if new_conf == "REJECTED" and cur_conf == "CONFIRMED":
            reject_task(conn=conn, task_id=task_id, today=today, actor=actor)
            return

    # Build repo update dict and audit list for remaining/changed fields
    repo_updates = {}
    for key in ALLOWED_TASK_FIELDS:
        if key not in fields:
            continue
        new_val = fields[key]
        if key in ("required", "blocking"):
            new_val = 1 if new_val else 0
        elif key == "vendor_due_date" and new_val is not None:
            if hasattr(new_val, "isoformat"):
                new_val = new_val.isoformat()
            else:
                new_val = str(new_val).strip() or None
        cur = row[key]
        if cur == new_val:
            continue
        repo_updates[key] = new_val
        _audit(conn, task_id, key, str(cur) if cur is not None else None, str(new_val) if new_val is not None else None, actor, "manual")

    if not repo_updates:
        return
    repository.update_task_fields(conn, task_id, repo_updates, strict=False)
    reconcile_after_task_change(conn=conn, turnover_id=turnover_id, today=today, actor=actor)
