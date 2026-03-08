# Backend Enrichment Pipeline — Deliverables Summary

## Diff summary

### New files
- **domain/enrichment.py** — Pure enrichment: `_parse_date`, `business_days`, `derive_phase`, `compute_facts`, `compute_intelligence`, `compute_sla_breaches`, `_wd_summary`, `_assign_display`, `enrich_row`. Constants: `TASK_TYPES_SEQUENCE`, `TASK_EXPECTED_DAYS`. No Streamlit/DB; uses `domain.lifecycle.derive_lifecycle_phase` and `derive_nvm`.
- **domain/lifecycle.py** — Added `derive_nvm(phase)` as canonical N/V/M from phase.
- **db/migrations/003_add_assignee_blocking_wd_type.sql** — Adds `task.assignee`, `task.blocking_reason`, `turnover.wd_present_type`.
- **services/board_query_service.py** — `get_dmrb_board_rows`, `get_flag_bridge_rows`, `get_turnover_detail`; `_row_to_dict`, `_parse_date`, `_build_flat_row`; `BRIDGE_MAP`. Uses repository only; batch loads units, tasks, notes; runs `enrichment.enrich_row`.
- **tests/test_enrichment_harness.py** — `test_enrichment_matches_mock_board_rows`, `test_enrichment_no_exceptions` (compare domain enrichment vs mock_data_v2 output).
- **docs/BACKEND_ENRICHMENT_DELIVERABLES.md** — This file.

### Modified files
- **db/repository.py** — Added `get_unit_by_id`, `get_units_by_ids`, `get_notes_by_turnover`, `get_notes_for_turnover_ids`, `get_tasks_for_turnover_ids`, `list_open_turnovers(property_ids=None)`. Added `strict: bool = True` to `update_turnover_fields`, `update_task_fields`, `update_unit_fields` (raise `ValueError` on unknown keys). Extended `TURNOVER_UPDATE_COLS` with `wd_present_type`, `TASK_UPDATE_COLS` with `assignee`, `blocking_reason`.
- **app_prototype_v2.py** — Optional backend: `use_mock` session state and sidebar checkbox; `_get_conn()`, `_get_db_path()`; `_operational_state_to_badge`, `_get_attention_badge` (UI-only); `_get_dmrb_rows` and `_get_flag_bridge_rows` branch on `use_mock` (mock_data_v2 vs board_query_service); sidebar top flags use service when not mock; detail page branches on `use_mock` (session state vs `get_turnover_detail`); notes add/resolve only when `use_mock`. DB path from `COCKPIT_DB_PATH` or `the-dmrb/data/cockpit.db`.

---

## Behavior deltas

- **None** for enrichment logic: validation harness asserts same row count, order, and key fields (dv, phase, nvm, operational_state, has_violation, wd_summary, assign_display) vs mock.
- **Backend mode (use_mock=False):** Detail page unit search uses `get_dmrb_board_rows` to resolve unit code; notes are read-only (no add/resolve). Board/flag table edits do not persist (no repository update calls from UI in this phase).

---

## TODOs left

- **Task dependency enforcement** — Not implemented; task order/dependencies are not enforced in board_query_service or enrichment.
- **Persistence of edits in UI when use_mock=False** — Status, QC, task exec/assignee, and note add/resolve are not written to DB from the app; backend mode is view-only for edits.
- **insert_task** — Does not yet set `assignee` or `blocking_reason`; new tasks get NULL. Can extend when a service creates tasks with assignees.
- **Run migration 003** — New DBs or existing DBs must run `db/migrations/003_add_assignee_blocking_wd_type.sql` before using new columns.
