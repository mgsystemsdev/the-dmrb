# Gap-to-Implementation Roadmap

**Purpose:** Staged implementation plan to align the system with the lifecycle specification. Minimal and realistic; reuses existing architecture.  
**Scope:** Planning only; no code changes.  
**Date:** 2025-03-11

---

## Stage 0 — Confirm and Preserve Current Stable Behavior

**Objective:** Lock in and document current stable behavior so later stages do not regress it. No production code changes; optional lightweight tests or checklist.

**Exact features included:**
- Define and document the “stable baseline”: board loads from open turnovers; all five report types import and write import_row with correct validation_status/conflict_reason; Missing Move-Out tab shows resolvable exceptions and resolve creates turnover; FAS Tracker shows PENDING_FAS rows and saves notes; manual overrides respected by imports; no turnover created without move_out_date.
- Optional: a short regression/smoke checklist (manual or automated) covering: one import per report type, board row count, Missing Move-Out resolve flow, FAS note save.
- No new features; no changes to repository, services, or UI logic.

**Exact files likely touched:**
- `docs/` — new or updated checklist/baseline doc (e.g. add section to LIFECYCLE_ALIGNMENT_REPORT or new STABLE_BASELINE.md).
- Optionally `tests/` — one smoke test that runs imports and board load (if not already covered).

**Risks:** None if no production code change. If adding tests, risk of flakiness or env-dependent failures.

**Dependencies:** None.

**What must not break:** N/A (no code change). After Stage 0, the baseline checklist must remain passable for all later stages.

---

## Stage 1 — Finish Report Reconciliation Workspace

**Objective:** Complete Report Operations as the single reconciliation workspace by adding the Import Diagnostics tab so all non-OK import outcomes are visible in one place.

**Exact features included:**
- Repository: `get_import_diagnostics(conn, since_imported_at=None)` — query import_row JOIN import_batch WHERE validation_status != 'OK', optional since_imported_at filter, deduplicated (most recent per unit_code_norm, report_type) via window function or fallback for SQLite < 3.25.
- Repository export: add `get_import_diagnostics` to `db/repository/__init__.py`.
- Service: `get_import_diagnostics_queue(conn, property_id, since_imported_at=None)` — call repo, filter rows to active property via get_unit_by_norm, return list of dicts for UI.
- UI: Third tab “Import Diagnostics” on Report Operations page; helper to fetch data; table columns: Unit, Report Type, Status, Conflict Reason, Import Time, Source File. Optional: filters (Report Type, Status, date range) via selectbox/session state.

**Exact files likely touched:**
- `db/repository/imports.py` — add get_import_diagnostics.
- `db/repository/__init__.py` — export get_import_diagnostics.
- `services/report_operations_service.py` — add get_import_diagnostics_queue.
- `ui/screens/report_operations.py` — add tab, _get_import_diagnostics_queue(), _render_import_diagnostics_tab(active_property).

**Risks:** SQLite version: window functions require 3.25+; older runtimes need fallback query (IMPORT_DIAGNOSTICS_DESIGN_REPORT §3.4). Property filter in service can be N lookups (get_unit_by_norm per row); acceptable for moderate row counts; can optimize later with batch resolve.

**Dependencies:** None. Existing Report Operations page and tabs; existing import_row/import_batch schema.

**What must not break:** Missing Move-Out tab, FAS Tracker tab, Admin import console, board load, any existing import or resolve flow.

---

## Stage 2 — Complete Lifecycle Exception Handling

**Objective:** Make exception handling and repair path explicit so managers know where to fix move-in-without-move-out and other non-OK outcomes.

**Exact features included:**
- UI copy: In Report Operations → Missing Move-Out tab, add or adjust caption to state that this is the “repair workflow” for move-in-without-move-out (e.g. “Move-in rows without move-out are repaired here by adding a move-out date and creating the turnover; they do not appear on the main board until resolved.”).
- Ensure Import Diagnostics (Stage 1) shows all validation_status and conflict_reason values used in the codebase (IGNORED, CONFLICT, INVALID, SKIPPED_OVERRIDE; MOVE_OUT_DATE_MISSING, MOVE_IN_WITHOUT_OPEN_TURNOVER, MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER, NO_OPEN_TURNOVER_FOR_READY_DATE, NO_OPEN_TURNOVER_FOR_VALIDATION, etc.) so no exception class is invisible.
- Optional: Short doc update (e.g. in LIFECYCLE_CONTROL_POINTS_ANALYSIS or LIFECYCLE_STATE_AND_WORKFLOW_SPECIFICATION) stating that the repair workflow is Report Operations → Missing Move-Out → Resolve.

**Exact files likely touched:**
- `ui/screens/report_operations.py` — caption text for Missing Move-Out tab.
- `docs/LIFECYCLE_CONTROL_POINTS_ANALYSIS.md` or `docs/LIFECYCLE_STATE_AND_WORKFLOW_SPECIFICATION.md` — optional paragraph on repair workflow.

**Risks:** Low. Copy-only and doc-only; no behavioral change.

**Dependencies:** Stage 1 (Import Diagnostics) recommended so “all exceptions” are visible in one place; not strictly required for caption change.

**What must not break:** Resolve flow, FAS Tracker, Import Diagnostics, board, imports.

---

## Stage 3 — Tighten Turnover Activation and Board Consistency

**Objective:** Enforce guardrails so no tasks are created for turnovers without move_out_date and, optionally, board explicitly shows only “operational” turnovers (move_out_date present).

**Exact features included:**
- **reconcile_missing_tasks guard:** In `reconcile_missing_tasks`, after selecting open turnovers with zero tasks, filter to those where move_out_date IS NOT NULL; only for those call instantiate_tasks_for_turnover. (Today all open turnovers have move_out_date NOT NULL; this is defensive.)
- **Optional task-instantiation guard:** At start of `_instantiate_tasks_for_turnover_impl`, load turnover row; if move_out_date is None, return without creating tasks. Callers today always pass turnovers with move_out_date; additive safety net.
- **Optional board filter:** In `list_open_turnovers` / `list_open_turnovers_by_property` add AND move_out_date IS NOT NULL, or in `get_dmrb_board_rows` filter loaded turnovers to move_out_date non-null before building rows. Redundant with current schema but makes “operational only” explicit.

**Exact files likely touched:**
- `services/turnover_service.py` — reconcile_missing_tasks: add filter (e.g. in SQL or in Python after fetch) for move_out_date IS NOT NULL.
- `services/imports/tasks.py` — _instantiate_tasks_for_turnover_impl: optional load turnover, skip if move_out_date None.
- Optionally `db/repository/turnovers.py` — list_open_turnovers / list_open_turnovers_by_property add AND move_out_date IS NOT NULL.
- Optionally `services/board_query_service.py` — get_dmrb_board_rows: filter turnovers to move_out_date non-null before building rows.

**Risks:** reconcile_missing_tasks: if any open turnover ever had NULL move_out_date (e.g. legacy or future bug), they would no longer get backfilled tasks; current schema and creation paths prevent that. Low risk. Task guard: none. Board filter: none for current data.

**Dependencies:** None.

**What must not break:** Task creation for all existing open turnovers (all have move_out_date). Board row set must remain the same for current data. Startup backfill (reconcile_missing_tasks) must still backfill any valid open turnover with zero tasks.

---

## Stage 4 — Add Observability and Workflow Feedback

**Objective:** Give managers lightweight feedback that supports morning/midday/end-of-day and repair workflows (counts, success messages, or hints). Minimal scope.

**Exact features included:**
- Optional: Report Operations tab labels show counts (e.g. “Import Diagnostics (12)” when there are 12 rows) so managers see impact at a glance.
- Optional: After resolve in Missing Move-Out, success message already exists; optionally add “View board” or “Unit will appear on the board” reminder.
- Optional: Admin import result could briefly mention “Check Report Operations → Import Diagnostics for non-OK rows” when conflict_count or invalid_count > 0.
- No new backend APIs beyond what Stage 1 provides; only UI copy and optional count display.

**Exact files likely touched:**
- `ui/screens/report_operations.py` — tab labels with counts (if data already loaded); optional success-message tweak.
- Optionally `ui/screens/admin.py` — post-import message when diagnostics exist.

**Risks:** Low. Additive UI only.

**Dependencies:** Stage 1 (Import Diagnostics) for diagnostics count in tab; others independent.

**What must not break:** Resolve flow, FAS save, Import Diagnostics load, Admin import.

---

## Stage 5 — Cleanup and Consistency Pass

**Objective:** Align documentation, naming, and any small consistency items; defer or document product decisions (e.g. Available Units authority).

**Exact features included:**
- Document repair workflow and exception resolution paths in the main lifecycle/spec docs so implementation and support stay aligned.
- Add or update “What must not break” and baseline checklist after all stages.
- Note “Available Units as strongest validator” as product intent; implementation of precedence (e.g. over DMRB) deferred until product rule is specified; no code change in this stage.
- Remove dead code or redundant comments if any are found; consistent terminology (e.g. “operational turnover,” “Report Operations,” “repair workflow”) across docs.
- Optional: SQLite version check and fallback query for get_import_diagnostics if support for SQLite < 3.25 is required (could be done in Stage 1 instead).

**Exact files likely touched:**
- `docs/LIFECYCLE_STATE_AND_WORKFLOW_SPECIFICATION.md`, `docs/LIFECYCLE_ALIGNMENT_REPORT.md`, `docs/LIFECYCLE_CONTROL_POINTS_ANALYSIS.md` — short updates.
- Optional: `docs/STABLE_BASELINE.md` or similar.
- Code: only if dead code or comment cleanup; no behavior change.

**Risks:** Low. Doc and optional minor cleanup.

**Dependencies:** Stages 1–4 complete so docs reflect implemented behavior.

**What must not break:** Any existing behavior; docs are additive or clarifying.

---

## Summary Table

| Stage | Objective                         | Main deliverable                    | Breaks if…                          |
|-------|-----------------------------------|-------------------------------------|-------------------------------------|
| 0     | Confirm and preserve baseline     | Baseline checklist / doc            | N/A                                 |
| 1     | Finish report reconciliation      | Import Diagnostics tab              | Missing Move-Out/FAS/import break   |
| 2     | Complete exception handling       | Repair caption + exception visibility| Resolve or diagnostics break       |
| 3     | Tighten activation and board      | move_out_date guards (reconcile + optional task/board) | Tasks or board change for current data |
| 4     | Observability and feedback        | Tab counts, messages                | Report Ops or Admin import break    |
| 5     | Cleanup and consistency           | Docs, naming, defer Available Units | N/A                                 |

No code was modified; this document is planning only.
