"""Task instantiation for new turnover (used by move_outs and manual availability)."""
from __future__ import annotations

from db import repository


def _apply_template_filter(template_row, unit_row) -> bool:
    ac = template_row["applies_if_has_carpet"] if "applies_if_has_carpet" in template_row.keys() else None
    if ac is not None and ac != "":
        if int(ac) != int(unit_row.get("has_carpet") or 0):
            return False
    aw = template_row["applies_if_has_wd_expected"] if "applies_if_has_wd_expected" in template_row.keys() else None
    if aw is not None and aw != "":
        if int(aw) != int(unit_row.get("has_wd_expected") or 0):
            return False
    return True


def instantiate_tasks_for_turnover(conn, turnover_id: int, unit_row, property_id: int) -> None:
    """
    Create tasks for a turnover from active task templates (by phase or property).
    Same logic as import; used by manual availability and turnover creation.
    unit_row must have phase_id (optional) and fields used by template filter (e.g. has_wd_expected, unit_code_norm).
    """
    _instantiate_tasks_for_turnover_impl(conn, turnover_id, unit_row, property_id)


def _instantiate_tasks_for_turnover_impl(conn, turnover_id: int, unit_row, property_id: int) -> None:
    """Use phase_id from unit when present (post-007), else resolve first phase for property so
    task templates work on post-008 DBs (task_template has phase_id only). If the phase (or
    property) has no templates, ensure default templates so the turnover gets tasks as soon as
    it has a move-out date."""
    turnover = repository.get_turnover_by_id(conn, turnover_id)
    if not turnover or not turnover.get("move_out_date"):
        return
    phase_id = unit_row.get("phase_id")
    if phase_id is None:
        phase_row = repository.get_first_phase_for_property(conn, property_id)
        if phase_row is not None:
            phase_id = phase_row["phase_id"]
    if phase_id is not None:
        repository.ensure_default_task_templates(conn, phase_id=phase_id)
        templates = repository.get_active_task_templates_by_phase(conn, phase_id=phase_id)
    else:
        repository.ensure_default_task_templates(conn, property_id=property_id)
        templates = repository.get_active_task_templates(conn, property_id=property_id)
    included = [t for t in templates if _apply_template_filter(t, unit_row)]
    template_id_to_task_id: dict[int, int] = {}
    for t in included:
        task_id = repository.insert_task(conn, {
            "turnover_id": turnover_id,
            "task_type": t["task_type"],
            "required": t["required"],
            "blocking": t["blocking"],
            "scheduled_date": None,
            "vendor_due_date": None,
            "vendor_completed_at": None,
            "manager_confirmed_at": None,
            "execution_status": "NOT_STARTED",
            "confirmation_status": "PENDING",
        })
        template_id_to_task_id[t["template_id"]] = task_id
    if not included:
        return
    template_ids = [t["template_id"] for t in included]
    deps = repository.get_task_template_dependencies(conn, template_ids=template_ids)
    for dep in deps:
        tid = dep["template_id"]
        dep_tid = dep["depends_on_template_id"]
        if tid in template_id_to_task_id and dep_tid in template_id_to_task_id:
            repository.insert_task_dependency(conn, {
                "task_id": template_id_to_task_id[tid],
                "depends_on_task_id": template_id_to_task_id[dep_tid],
            })
