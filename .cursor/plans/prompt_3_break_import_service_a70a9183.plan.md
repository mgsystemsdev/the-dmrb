---
name: Prompt 3 Break Import Service
overview: Refactor the 920-line services/import_service.py into a package services/imports/ with modules for validation, parsing and apply logic per report type (move_outs, move_ins, available_units, pending_fas, dmrb), shared helpers, task instantiation, and an orchestrator that exposes the same public API so existing "from services import import_service" usage continues to work via a thin shim.
todos: []
isProject: false
---

# Prompt 3 — Break the Import Service

## Current state

- Single file [services/import_service.py](services/import_service.py) (~920 lines) containing:
  - **Constants:** MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS, DMRB; APP_SETTINGS, VALID_PHASES; OUTCOME_APPLIED, OUTCOME_SKIPPED_OVERRIDE, OUTCOME_CONFLICT.
  - **Validation/normalization helpers:** _validation_status_from_outcome, _sha256_file, _now_iso, _to_iso_date, _normalize_date_str, _normalize_status, _row_to_dict, _normalize_unit, _phase_from_norm, _filter_phase.
  - **Parsers (CSV/Excel -> rows):** _parse_move_outs, _parse_pending_move_ins, _parse_available_units, _parse_pending_fas, _parse_dmrb.
  - **Shared write/audit helpers:** _ensure_unit, _write_import_row, _append_diagnostic, _audit, _get_last_skipped_value, _write_skip_audit_if_new.
  - **Task instantiation:** _apply_template_filter, instantiate_tasks_for_turnover, _instantiate_tasks_for_turnover_impl (used by move-outs when creating new turnover, and by turnover_service / manual_availability).
  - **Main entry:** import_report_file (validates, parses by report_type, inserts batch, runs per-report apply loop, post-MOVE_OUTS reconciliation, backup, returns result dict).
- **Public API** used by callers:
  - `import_service.import_report_file(...)` — used by app/UI and tests.
  - `import_service.instantiate_tasks_for_turnover(conn, turnover_id, unit_row, property_id)` — used by [services/turnover_service.py](services/turnover_service.py) and [application/workflows/write_workflows.py](application/workflows/write_workflows.py) (via manual_availability which uses it).
- Callers use `from services import import_service`; no direct imports of internal names.

## Target structure

Create package **services/imports/** (note: directory name is `imports`, not `import_service`) with these modules:


| Module                 | Responsibility                      | Contents (relocate only; no logic/signature change)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ---------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **constants.py**       | Report types and outcome constants  | MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS, DMRB; OUTCOME_APPLIED, OUTCOME_SKIPPED_OVERRIDE, OUTCOME_CONFLICT; APP_SETTINGS, VALID_PHASES.                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| **validation.py**      | Validation helpers and schema usage | _validation_status_from_outcome, _normalize_date_str, _normalize_status. Optionally _sha256_file (checksum for batch). Uses constants.                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| **common.py**          | Shared helpers used by apply logic  | _row_to_dict, _to_iso_date, _now_iso, _normalize_unit, _phase_from_norm, _filter_phase, _ensure_unit, _write_import_row, _append_diagnostic, _audit, _get_last_skipped_value, _write_skip_audit_if_new. Imports: repository, constants, domain.unit_identity.                                                                                                                                                                                                                                                                                                                                                       |
| **move_outs.py**       | Move-out import logic               | _parse_move_outs (pandas CSV parse); apply_move_outs(conn, batch_id, rows, property_id, now_iso, actor, corr_id, today, ...) implementing the current MOVE_OUTS for-loop and the post-loop "missing move-out" reconciliation. Returns (applied_count, conflict_count, invalid_count, diagnostics, seen_unit_ids). Uses common, validation, constants; calls task instantiation when creating new turnover.                                                                                                                                                                                                          |
| **move_ins.py**        | Pending move-in processing          | _parse_pending_move_ins; apply_pending_move_ins(conn, batch_id, rows, property_id, now_iso, actor, corr_id, ...). Same pattern.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **available_units.py** | Available units import logic        | _parse_available_units; apply_available_units(conn, batch_id, rows, property_id, now_iso, actor, corr_id, ...) — only the branch for report_type == AVAILABLE_UNITS (ready date + availability_status).                                                                                                                                                                                                                                                                                                                                                                                                             |
| **pending_fas.py**     | Pending FA processing               | _parse_pending_fas; apply_pending_fas(conn, batch_id, rows, property_id, now_iso, actor, corr_id, today, ...). Uses effective_move_out_date, reconcile_sla_for_turnover.                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **dmrb.py**            | DMRB-specific transformations       | _parse_dmrb (Excel); apply_dmrb(conn, batch_id, rows, property_id, now_iso, actor, corr_id, ...) — ready-date-only branch (no availability_status).                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **tasks.py**           | Task instantiation for new turnover | _apply_template_filter, instantiate_tasks_for_turnover, _instantiate_tasks_for_turnover_impl. Used by move_outs and by orchestrator (re-export). Imports repository, common.                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| **orchestrator.py**    | Main entrypoint                     | import_report_file: checksum, get_import_batch_by_checksum, validate_import_file/validate_import_schema (from imports.validation package), parse via move_outs._parse_move_outs / move_ins._parse_pending_move_ins / etc., insert_import_batch, then dispatch to move_outs.apply_move_outs, move_ins.apply_pending_move_ins, pending_fas.apply_pending_fas, available_units.apply_available_units, dmrb.apply_dmrb; run post-MOVE_OUTS reconciliation (or call move_outs.post_process_missing_move_outs); backup_db if db_path/backup_dir; return result dict. Re-export instantiate_tasks_for_turnover from tasks. |


**Compatibility:** Keep [services/import_service.py](services/import_service.py) as a **thin shim** (single file) that does:

```python
from services.imports.orchestrator import import_report_file, instantiate_tasks_for_turnover
from services.imports.constants import MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS, DMRB
# Re-export so "from services import import_service" and import_service.import_report_file / .MOVE_OUTS etc. still work
```

So all existing callers (app, application.workflows, services.turnover_service, tests) remain unchanged.

## Implementation plan

### 1. Create services/imports/ package

- **constants.py** — Move the five report-type strings, three OUTCOME_* strings, APP_SETTINGS = get_settings(), VALID_PHASES. No logic.
- **validation.py** — Move _validation_status_from_outcome, _normalize_date_str, _normalize_status, *sha256_file. Import constants for OUTCOME** and VALID_PHASES if needed. Do not change behavior.
- **common.py** — Move _row_to_dict, _to_iso_date, _now_iso, _normalize_unit (_normalize_unit uses domain.unit_identity), _phase_from_norm, _filter_phase, _ensure_unit, _write_import_row, _append_diagnostic, _audit, _get_last_skipped_value, _write_skip_audit_if_new. These need db.repository and constants; common.py imports them. _ensure_unit and _audit use repository; _get_last_skipped_value uses conn.execute (raw SQL for audit_log). Keep signatures and SQL identical.
- **tasks.py** — Move _apply_template_filter, instantiate_tasks_for_turnover, _instantiate_tasks_for_turnover_impl. Import repository and common (for any helper used). Used by move_outs and by orchestrator.
- **move_outs.py** — Move _parse_move_outs (uses pandas, common._normalize_unit, common._filter_phase, constants.VALID_PHASES). Move the entire MOVE_OUTS branch from import_report_file into apply_move_outs(conn, batch_id, rows, property_id, now_iso, actor, corr_id, today, ...) and the post-loop block that updates missing_moveout_count / canceled_at into a function (e.g. post_process_after_move_outs). Return counts and diagnostics so orchestrator can aggregate. When creating a new turnover, call tasks._instantiate_tasks_for_turnover_impl (or import instantiate_tasks_for_turnover from tasks and use it). Keep pandas logic and repository calls unchanged.
- **move_ins.py** — Move _parse_pending_move_ins and the PENDING_MOVE_INS for-loop into apply_pending_move_ins(...). Same pattern.
- **available_units.py** — Move _parse_available_units and the AVAILABLE_UNITS-specific branch (report_ready_date + availability_status) into apply_available_units(...). The current code shares a loop with DMRB; split so that apply_available_units only handles rows for AVAILABLE_UNITS (ready date + status); orchestrator will call apply_available_units when report_type == AVAILABLE_UNITS and apply_dmrb when report_type == DMRB.
- **pending_fas.py** — Move _parse_pending_fas and the PENDING_FAS for-loop into apply_pending_fas(...). Uses domain.lifecycle.effective_move_out_date and services.sla_service.reconcile_sla_for_turnover; keep those imports in pending_fas.py.
- **dmrb.py** — Move _parse_dmrb and the DMRB-specific apply logic (ready date only, no availability_status) into apply_dmrb(...).
- **orchestrator.py** — Contains only import_report_file: compute checksum, check existing batch, call validate_import_file/validate_import_schema (from imports.validation), dispatch to *parse** from move_outs/move_ins/available_units/pending_fas/dmrb by report_type, insert_import_batch, then call apply_move_outs / apply_pending_move_ins / apply_pending_fas / apply_available_units / apply_dmrb as appropriate; call post_process_after_move_outs for MOVE_OUTS; backup if requested; return result. Re-export instantiate_tasks_for_turnover from tasks (so from services.imports.orchestrator import instantiate_tasks_for_turnover works).
- **init.py** — Re-export from orchestrator and constants so that `from services.imports import import_report_file, instantiate_tasks_for_turnover, MOVE_OUTS, ...` works if needed; and so the shim can do from services.imports.orchestrator import ... and from services.imports.constants import ...

### 2. Thin shim services/import_service.py

Replace the body of [services/import_service.py](services/import_service.py) with imports and re-exports only, e.g.:

- from services.imports.orchestrator import import_report_file, instantiate_tasks_for_turnover
- from services.imports.constants import MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS, DMRB

Re-export these so that existing code that does `from services import import_service` and then `import_service.import_report_file(...)` or `import_service.MOVE_OUTS` continues to work without modification.

### 3. Cross-module dependencies

- **common** is used by move_outs, move_ins, available_units, pending_fas, dmrb, and tasks. No circular dependency if common does not import move_outs/move_ins/etc.
- **tasks** is used by move_outs (when creating new turnover) and by orchestrator. **move_outs** imports tasks; **orchestrator** imports move_outs and tasks. So: orchestrator -> move_outs -> tasks, orchestrator -> tasks. No cycle.
- **pending_fas** imports sla_service and domain.lifecycle; that stays in pending_fas.py.
- **orchestrator** imports db.connection for backup_database; keep that in orchestrator.

### 4. Existing imports.validation package

The current import_service imports from **imports.validation.file_validator** and **imports.validation.schema_validator** (the top-level `imports` package under project root). Orchestrator should keep using those; do not move them into services.imports. So services/imports/validation.py only holds the small helpers (_validation_status_from_outcome, _normalize_date_str, _normalize_status, _sha256_file); the actual validate_import_file and validate_import_schema remain in imports.validation and are called from orchestrator.

## Constraints (from prompt)

- Do not modify business logic, pandas logic, or function signatures; only reorganize.
- No file over **250 lines**. If any module (e.g. move_outs or orchestrator) would exceed 250 lines, split further (e.g. move_outs parse vs apply, or extract post_process into a small function in the same file).
- All existing imports must still work: `from services import import_service` and import_service.import_report_file / import_service.instantiate_tasks_for_turnover / import_service.MOVE_OUTS etc.

## Order of operations

1. Create services/imports/ directory and constants.py, validation.py, common.py.
2. Create tasks.py (task instantiation).
3. Create move_outs.py, move_ins.py, available_units.py, pending_fas.py, dmrb.py (parsers + apply functions).
4. Create orchestrator.py (import_report_file and re-export of instantiate_tasks_for_turnover).
5. Create services/imports/**init**.py re-exporting public API and constants.
6. Replace services/import_service.py with the thin shim.
7. Run tests (test_import_validation, test_manual_override_protection, test_sla_import_confirmation_reconcile, test_legal_confirmation_invariant, test_task_creation, test_unit_master_import, etc.) and fix any import or reference errors.

## File list


| Action  | Path                                   |
| ------- | -------------------------------------- |
| Create  | services/imports/**init**.py           |
| Create  | services/imports/constants.py          |
| Create  | services/imports/validation.py         |
| Create  | services/imports/common.py             |
| Create  | services/imports/tasks.py              |
| Create  | services/imports/move_outs.py          |
| Create  | services/imports/move_ins.py           |
| Create  | services/imports/available_units.py    |
| Create  | services/imports/pending_fas.py        |
| Create  | services/imports/dmrb.py               |
| Create  | services/imports/orchestrator.py       |
| Replace | services/import_service.py (shim only) |


