---
name: Prompt 2 Split Repository
overview: Refactor the 1137-line db/repository.py into a package db/repository/ with one module per entity (properties, units, turnovers, tasks, notes, risks, imports, sla, chat) plus a shared _helpers module, and re-export all public symbols from __init__.py so existing "from db import repository" usage continues to work without change.
todos: []
isProject: false
---

# Prompt 2 — Split the Repository

## Current state

- Single file [db/repository.py](db/repository.py) (~1137 lines) containing:
  - Shared helpers: `_row_to_dict`, `_rows_to_dicts`, `_inserted_id`; constants `TURNOVER_UPDATE_COLS`, `TASK_UPDATE_COLS`, `UNIT_UPDATE_COLS`.
  - Unit-related: `get_unit_by_id`, `list_unit_master_import_units`, `get_unit_by_norm`, `get_unit_by_identity_key`, `get_unit_by_building_and_number`, `get_phase`, `get_building`, `resolve_phase`, `resolve_building`, `resolve_unit`, `get_units_by_ids`, `insert_unit`, `update_unit_fields`, `list_units`.
  - Property/phase/building: `list_properties`, `insert_property`, `list_phases`, `get_first_phase_for_property`, `list_buildings`.
  - Task templates and tasks: `get_active_task_templates`, `get_active_task_templates_by_phase`, `get_task_template_dependencies`, `DEFAULT_TASK_TYPES`, `insert_task_template`, `ensure_default_task_templates`, `insert_task_dependency`, `get_tasks_by_turnover`, `get_tasks_for_turnover_ids`, `insert_task`, `update_task_fields`.
  - Turnovers and enrichment cache: `invalidate_turnover_enrichment_cache`, `get_enrichment_cache_for_turnover_ids`, `upsert_turnover_enrichment_cache`, `list_open_turnovers_by_property`, `list_open_turnovers`, `get_turnover_by_id`, `get_open_turnover_by_unit`, `insert_turnover`, `update_turnover_fields`.
  - Chat: `get_chat_sessions`, `get_chat_session`, `insert_chat_session`, `update_chat_session_fields`, `get_chat_messages`, `insert_chat_message`, `delete_chat_session`.
  - Notes: `get_note_by_id`, `get_notes_by_turnover`, `insert_note`, `update_note_resolved`, `get_notes_for_turnover_ids`.
  - Risks: `get_active_risks_by_turnover`, `upsert_risk`, `_ensure_confirmation_invariant`, `resolve_risk`. (`_ensure_confirmation_invariant` calls `upsert_risk` and `insert_audit_log`.)
  - SLA: `get_open_sla_event`, `insert_sla_event`, `close_sla_event`, `update_sla_event_current_anchor`.
  - Imports/audit: `insert_import_batch`, `get_import_batch_by_checksum`, `insert_import_row`, `get_import_rows_by_batch`, `insert_audit_log`.
- Callers use `from db import repository` and then `repository.<function>(conn, ...)`. No external code uses `TURNOVER_UPDATE_COLS` / `TASK_UPDATE_COLS` / `UNIT_UPDATE_COLS` or the private helpers; they are only used inside the repository.
- Note: The file uses `sqlite3.Connection` in type hints but does not import `sqlite3`; add `import sqlite3` (or a central place for the type) when splitting so type hints remain valid.

## Target structure

Create package **db/repository/** with these modules:


| Module            | Responsibility                             | Functions / constants (move here)                                                                                                                                                                                                                                                                         |
| ----------------- | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **_helpers.py**   | Shared helpers and update-column constants | `_row_to_dict`, `_rows_to_dicts`, `_inserted_id`, `TURNOVER_UPDATE_COLS`, `TASK_UPDATE_COLS`, `UNIT_UPDATE_COLS`. Import `db.errors.DatabaseIntegrityError` and `datetime`/`json` only if needed by helpers (they are not; keep them only in modules that need them).                                     |
| **properties.py** | Property, phase, building                  | `list_properties`, `insert_property`, `list_phases`, `get_first_phase_for_property`, `list_buildings`, `get_phase`, `get_building`, `resolve_phase`, `resolve_building`.                                                                                                                                  |
| **units.py**      | Unit CRUD and resolution                   | `get_unit_by_id`, `list_unit_master_import_units`, `get_unit_by_norm`, `get_unit_by_identity_key`, `get_unit_by_building_and_number`, `resolve_unit`, `get_units_by_ids`, `insert_unit`, `update_unit_fields`, `list_units`.                                                                              |
| **turnovers.py**  | Turnover and enrichment cache              | `invalidate_turnover_enrichment_cache`, `get_enrichment_cache_for_turnover_ids`, `upsert_turnover_enrichment_cache`, `list_open_turnovers_by_property`, `list_open_turnovers`, `get_turnover_by_id`, `get_open_turnover_by_unit`, `insert_turnover`, `update_turnover_fields`.                            |
| **tasks.py**      | Task templates and tasks                   | `get_active_task_templates`, `get_active_task_templates_by_phase`, `get_task_template_dependencies`, `DEFAULT_TASK_TYPES`, `insert_task_template`, `ensure_default_task_templates`, `insert_task_dependency`, `get_tasks_by_turnover`, `get_tasks_for_turnover_ids`, `insert_task`, `update_task_fields`. |
| **notes.py**      | Notes                                      | `get_note_by_id`, `get_notes_by_turnover`, `insert_note`, `update_note_resolved`, `get_notes_for_turnover_ids`.                                                                                                                                                                                           |
| **risks.py**      | Risk flags                                 | `get_active_risks_by_turnover`, `upsert_risk`, `_ensure_confirmation_invariant`, `resolve_risk`.                                                                                                                                                                                                          |
| **imports.py**    | Import batches, rows, audit log            | `insert_import_batch`, `get_import_batch_by_checksum`, `insert_import_row`, `get_import_rows_by_batch`, `insert_audit_log`.                                                                                                                                                                               |
| **sla.py**        | SLA events                                 | `get_open_sla_event`, `insert_sla_event`, `close_sla_event`, `update_sla_event_current_anchor`.                                                                                                                                                                                                           |
| **chat.py**       | Chat sessions and messages                 | `get_chat_sessions`, `get_chat_session`, `insert_chat_session`, `update_chat_session_fields`, `get_chat_messages`, `insert_chat_message`, `delete_chat_session`.                                                                                                                                          |


**db/repository/init.py** must re-export every **public** function (and any constant that external code might use) so that:

```python
from db import repository
repository.list_properties(conn)
repository.insert_turnover(conn, data)
# etc.
```

continues to work without any change in services, application, or tests.

## Implementation plan

### 1. Shared helpers

- **Create [db/repository/_helpers.py](db/repository/_helpers.py)**  
  - Add `import sqlite3` (for type hints used in other modules; _helpers itself may not need it).  
  - Move: `_row_to_dict`, `_rows_to_dicts`, `_inserted_id`, `TURNOVER_UPDATE_COLS`, `TASK_UPDATE_COLS`, `UNIT_UPDATE_COLS`.  
  - Keep logic and SQL (e.g. `SELECT last_insert_rowid()`) unchanged.  
  - Other modules will do `from db.repository._helpers import _row_to_dict, _rows_to_dicts, _inserted_id, TURNOVER_UPDATE_COLS` (or same for TASK/UNIT) as needed.

### 2. Entity modules

- **properties.py** — Move the 9 functions listed above. Import `_row_to_dict`, `_rows_to_dicts` from `_helpers`. Use `from db.errors import DatabaseIntegrityError` in `insert_property` only. Add `import sqlite3` for type hints. Do not change any SQL or signatures.
- **units.py** — Move the 10 functions. Import `_row_to_dict`, `_rows_to_dicts`, `_inserted_id`, `UNIT_UPDATE_COLS` from `_helpers`. Add `import sqlite3`.
- **turnovers.py** — Move the 9 functions. Import `_row_to_dict`, `_rows_to_dicts`, `_inserted_id`, `TURNOVER_UPDATE_COLS` from `_helpers`; use `datetime`, `json` for enrichment cache. Add `import sqlite3`.
- **tasks.py** — Move all task_template and task functions plus `DEFAULT_TASK_TYPES`. Import from `_helpers`: `_row_to_dict`, `_rows_to_dicts`, `_inserted_id`, `TASK_UPDATE_COLS`. `get_active_task_templates_by_phase` does a raw `conn.execute("SELECT property_id FROM phase ...")` and then calls `get_active_task_templates(conn, property_id=...)` — both stay in tasks.py. Add `import sqlite3`. If line count approaches 300, consider splitting task_template vs task into two files and re-exporting from tasks.py; otherwise keep in one.
- **notes.py** — Move the 5 functions. Import `_row_to_dict`, `_rows_to_dicts`, `_inserted_id` from `_helpers`. Add `import sqlite3`.
- **risks.py** — Move the 4 functions. `_ensure_confirmation_invariant` calls `upsert_risk(conn, ...)` and `insert_audit_log(conn, ...)`. Import `insert_audit_log` from `db.repository.imports` (or `.imports` relative) so that cross-module call still works. Import `_row_to_dict`, `_inserted_id` from `_helpers`. Use `datetime` for `now_iso`. Add `import sqlite3`.
- **imports.py** — Move the 5 functions. Import `_row_to_dict`, `_rows_to_dicts`, `_inserted_id` from `_helpers`. Add `import sqlite3`.
- **sla.py** — Move the 4 functions. Import `_row_to_dict`, `_inserted_id` from `_helpers`. Add `import sqlite3`.
- **chat.py** — Move the 7 functions. Import `_row_to_dict`, `_rows_to_dicts`, `_inserted_id` from `_helpers`. Add `import sqlite3`.

### 3. Re-export from **init**.py

- **Create [db/repository/init.py](db/repository/__init__.py)**  
  - Import every **public** function (and constants if any are part of the public API) from:
    - `.properties`
    - `.units`
    - `.turnovers`
    - `.tasks`
    - `.notes`
    - `.risks`
    - `.imports`
    - `.sla`
    - `.chat`
  - Do **not** export private names (e.g. `_ensure_confirmation_invariant`, `_row_to_dict`). If any caller outside the package ever needed them, they would have used `repository._ensure_confirmation_invariant`; grep shows no such use, so keep them internal.
  - Re-export so that `from db import repository` gives the same namespace as before: `repository.list_properties`, `repository.insert_turnover`, etc. Use either explicit `__all`__ or import list.

### 4. Remove old file and verify imports

- **Delete [db/repository.py](db/repository.py)** (the single file).  
  - In Python, `db/repository/` (package) and `db/repository.py` (module) cannot coexist; the package takes precedence. So once `db/repository/` exists with `__init__.py`, the old `db/repository.py` must be removed so the package is used.
- **Verification** — All existing call sites use `from db import repository` (or `from db import repository as db_repository`). No changes needed in:
  - [application/workflows/write_workflows.py](application/workflows/write_workflows.py)
  - [services/board_query_service.py](services/board_query_service.py), [services/import_service.py](services/import_service.py), [services/export_service.py](services/export_service.py), [services/turnover_service.py](services/turnover_service.py), [services/task_service.py](services/task_service.py), [services/note_service.py](services/note_service.py), [services/risk_service.py](services/risk_service.py), [services/sla_service.py](services/sla_service.py), [services/chat_service.py](services/chat_service.py), [services/ai_context_service.py](services/ai_context_service.py), [services/manual_availability_service.py](services/manual_availability_service.py), [services/unit_master_import_service.py](services/unit_master_import_service.py)
  - Tests under `tests/` that do `from db import repository`

Run the test suite after the refactor to confirm nothing is broken.

## Cross-module dependency

- **risks.py** depends on **imports.py**: `_ensure_confirmation_invariant` calls `insert_audit_log`. Resolve by: `from db.repository.imports import insert_audit_log` (or relative `from . import imports` then `imports.insert_audit_log`) inside risks.py. Do not change the logic or signature of `insert_audit_log`.

## Constraints (from prompt)

- Do not modify SQL queries.  
- Do not change function names or signatures.  
- Only relocate functions into the listed modules.  
- No repository module should exceed **300 lines**. (If tasks.py exceeds 300, split into e.g. task_templates.py and tasks.py and re-export from a single tasks namespace or from **init**.py.)  
- Existing services and tests must continue to work unchanged (no changes to `from db import repository` or to call patterns).

## Order of operations

1. Create `db/repository/` directory.
2. Add `_helpers.py` with shared helpers and constants.
3. Add `properties.py`, `units.py`, `turnovers.py`, `tasks.py`, `notes.py`, `risks.py`, `imports.py`, `sla.py`, `chat.py` in dependency order (imports before risks so risks can import insert_audit_log).
4. Add `__init__.py` that re-exports all public functions (and constants if needed).
5. Delete `db/repository.py`.
6. Run tests and fix any import or reference errors.

## File list


| Action | Path                        |
| ------ | --------------------------- |
| Create | db/repository/_helpers.py   |
| Create | db/repository/properties.py |
| Create | db/repository/units.py      |
| Create | db/repository/turnovers.py  |
| Create | db/repository/tasks.py      |
| Create | db/repository/notes.py      |
| Create | db/repository/imports.py    |
| Create | db/repository/risks.py      |
| Create | db/repository/sla.py        |
| Create | db/repository/chat.py       |
| Create | db/repository/**init**.py   |
| Delete | db/repository.py            |


