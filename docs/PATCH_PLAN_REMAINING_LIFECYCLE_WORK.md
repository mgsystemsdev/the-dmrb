# Full Patch Plan: Remaining Lifecycle Work

**Purpose:** File-by-file patch plan for all remaining work to fully align the system with the intended lifecycle. Assumes Report Operations page, Missing Move-Out tab, FAS Tracker tab, Import Diagnostics design, existing turnover lifecycle engine, and existing task/board pipeline are already in place.  
**Scope:** Planning only; no code changes.  
**Date:** 2025-03-11

---

## Assumptions (Already Implemented)

- Report Operations page exists and is routed.
- Missing Move-Out tab: queue load, resolve (create turnover with move_out_date) implemented.
- FAS Tracker tab: PENDING_FAS rows load, note upsert implemented.
- Import Diagnostics design: docs/IMPORT_DIAGNOSTICS_DESIGN_REPORT.md defines query, service, and UI.
- Turnover lifecycle engine: domain/lifecycle, enrichment, effective move-out, phases.
- Task creation: instantiate_tasks_for_turnover called from MOVE_OUTS and manual creation.
- Board pipeline: list_open_turnovers → get_dmrb_board_rows → enrichment → UI.

---

## Must Build Now

### 1. Import Diagnostics — repository query

| Item | Detail |
|------|--------|
| **Feature name** | Import Diagnostics: get_import_diagnostics |
| **File path** | `db/repository/imports.py` |
| **Exact function to add or modify** | **Add** `get_import_diagnostics(conn, since_imported_at=None) -> list[dict]`. Implement per IMPORT_DIAGNOSTICS_DESIGN_REPORT §3.2–3.4: SELECT from import_row r JOIN import_batch b WHERE r.validation_status != 'OK', optional b.imported_at >= since_imported_at, deduplicated by (unit_code_norm, report_type) using ROW_NUMBER() OVER (PARTITION BY ... ORDER BY b.imported_at DESC, r.row_id DESC) WHERE rn = 1; return _rows_to_dicts. For SQLite < 3.25 use fallback GROUP BY / MAX query from design doc. |
| **Why this file** | All import_row/import_batch read functions live here (get_import_rows_by_batch, get_missing_move_out_exceptions, get_import_rows_pending_fas). Single place for diagnostics query. |
| **Risk level** | Medium — SQL differs for SQLite vs Postgres and SQLite version; window vs fallback must be correct. |
| **Additive or behavioral** | Additive. New function only; no existing callers changed. |

### 2. Import Diagnostics — repository export

| Item | Detail |
|------|--------|
| **Feature name** | Import Diagnostics: export get_import_diagnostics |
| **File path** | `db/repository/__init__.py` |
| **Exact function to add or modify** | **Modify** imports block: add `get_import_diagnostics` to the list imported from `db.repository.imports` and re-export. |
| **Why this file** | Central re-export for `from db import repository`; all repository imports are declared here. |
| **Risk level** | Low. |
| **Additive or behavioral** | Additive. New export only. |

### 3. Import Diagnostics — service layer

| Item | Detail |
|------|--------|
| **Feature name** | Import Diagnostics: get_import_diagnostics_queue |
| **File path** | `services/report_operations_service.py` |
| **Exact function to add or modify** | **Add** `get_import_diagnostics_queue(conn, property_id, since_imported_at=None) -> list[dict]`. Call repository.get_import_diagnostics(conn, since_imported_at=since_imported_at). For each row, resolve unit via repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=row['unit_code_norm']); include row only if unit exists (so row belongs to active property). Return list of dicts with keys for UI: unit_code (raw or norm), report_type, validation_status, conflict_reason, imported_at, source_file_name, optionally move_out_date, move_in_date. |
| **Why this file** | Report Operations service already owns get_missing_move_out_queue, get_fas_tracker_rows, resolve_missing_move_out. Same layer for diagnostics; property filtering belongs here (batch has no property_id). |
| **Risk level** | Low. N get_unit_by_norm calls for N rows; acceptable for moderate N; can optimize later. |
| **Additive or behavioral** | Additive. New function only. |

### 4. Import Diagnostics — UI tab and table

| Item | Detail |
|------|--------|
| **Feature name** | Import Diagnostics: third tab and render |
| **File path** | `ui/screens/report_operations.py` |
| **Exact function to add or modify** | **Modify** `render()`: add third tab "Import Diagnostics" alongside "Missing Move-Out" and "FAS Tracker". **Add** `_get_import_diagnostics_queue()` — get_conn(), get_active_property(), call report_operations_service.get_import_diagnostics_queue(conn, property_id=active["property_id"], since_imported_at=...) (optional date from filter). **Add** `_render_import_diagnostics_tab(active_property)` — subheader, caption (observational; no state change), optional filters (Report Type, Status, date range via st.selectbox / st.date_input), build DataFrame from queue with columns Unit, Report Type, Status, Conflict Reason, Import Time, Source File, st.dataframe(df, use_container_width=True, hide_index=True). |
| **Why this file** | Report Operations screen already has two tabs and the same pattern (helper to load data, render tab with table). Third tab in same screen keeps reconciliation workspace in one place. |
| **Risk level** | Low. Additive UI. |
| **Additive or behavioral** | Additive. New tab and helpers only. |

### 5. reconcile_missing_tasks move_out_date guard

| Item | Detail |
|------|--------|
| **Feature name** | Guard: no task backfill without move_out_date |
| **File path** | `services/turnover_service.py` |
| **Exact function to add or modify** | **Modify** `reconcile_missing_tasks(conn) -> int`. After the existing SELECT that returns (turnover_id, unit_id, property_id) for open turnovers with zero tasks, filter to rows where the turnover has move_out_date IS NOT NULL. Options: (a) add AND t.move_out_date IS NOT NULL to the SQL, or (b) fetch full turnover rows and filter in Python. Prefer (a) for single query. Only call instantiate_tasks_for_turnover for those filtered rows. |
| **Why this file** | reconcile_missing_tasks is defined here and is the only backfill path for missing tasks; guard must live where the backfill runs. |
| **Risk level** | Low. Current data all have move_out_date NOT NULL; behavior unchanged for existing DBs. Defensive for future or legacy edge cases. |
| **Additive or behavioral** | Behavioral. Changes which turnovers get backfilled (excludes any with NULL move_out_date). Additive with respect to current data. |

---

## Should Build Next

### 6. Task instantiation guard (safety net)

| Item | Detail |
|------|--------|
| **Feature name** | Guard: no tasks when turnover has no move_out_date |
| **File path** | `services/imports/tasks.py` |
| **Exact function to add or modify** | **Modify** `_instantiate_tasks_for_turnover_impl(conn, turnover_id, unit_row, property_id)`. At start, load turnover with repository.get_turnover_by_id(conn, turnover_id). If turnover is None or turnover.get("move_out_date") is None or (str(turnover.get("move_out_date")) or "").strip() == "", return without creating tasks. Otherwise proceed as today. |
| **Why this file** | Single implementation of task instantiation; all callers (MOVE_OUTS, manual creation, reconcile_missing_tasks) go through this. Defense-in-depth. |
| **Risk level** | Low. Callers today always pass turnovers with move_out_date; no behavior change for current paths. |
| **Additive or behavioral** | Behavioral (early return in edge case). Additive for all current callers. |

### 7. Repair workflow caption (Report Operations)

| Item | Detail |
|------|--------|
| **Feature name** | Repair workflow naming in UI |
| **File path** | `ui/screens/report_operations.py` |
| **Exact function to add or modify** | **Modify** `_render_missing_move_out_tab`: update st.caption (or subheader) to state that this is the repair workflow for move-in-without-move-out, e.g. “Move-in rows without move-out are repaired here by adding a move-out date and creating the turnover; they do not appear on the main board until resolved.” |
| **Why this file** | Missing Move-Out tab is the repair workflow surface; caption is the right place for workflow explanation. |
| **Risk level** | Low. Copy only. |
| **Additive or behavioral** | Additive. Text only. |

### 8. Board operational filter (defensive)

| Item | Detail |
|------|--------|
| **Feature name** | Board: only show turnovers with move_out_date |
| **File path** | `db/repository/turnovers.py` **or** `services/board_query_service.py` |
| **Exact function to add or modify** | **Option A (repository):** In `list_open_turnovers` and `list_open_turnovers_by_property`, add to WHERE clause: AND t.move_out_date IS NOT NULL (and for list_open_turnovers_by_property, same for turnover table). **Option B (service):** In `get_dmrb_board_rows`, after fetching turnovers, filter: turnovers = [t for t in turnovers if (t.get("move_out_date") or "").strip()]. Prefer Option A for single place. |
| **Why this file** | list_open_turnovers is the single source for “what’s on the board”; adding the filter here keeps “operational = open and has move_out_date” in one place. Alternatively board_query_service owns the pipeline and can filter after load. |
| **Risk level** | Low. Redundant today (schema enforces NOT NULL); no current data change. |
| **Additive or behavioral** | Behavioral (would exclude NULL move_out_date rows if any existed). Additive for current data. |

---

## Later Improvements

### 9. Import Diagnostics — optional filters (UI)

| Item | Detail |
|------|--------|
| **Feature name** | Import Diagnostics: Report Type / Status / date filters |
| **File path** | `ui/screens/report_operations.py` |
| **Exact function to add or modify** | **Modify** `_render_import_diagnostics_tab`: add st.selectbox for Report Type (All, MOVE_OUTS, PENDING_MOVE_INS, …), for Status (All, IGNORED, CONFLICT, INVALID, SKIPPED_OVERRIDE), and optional date range (e.g. “Last 30 days” or date picker). Store in session_state; filter the DataFrame (or pass since_imported_at to service) before display. |
| **Why this file** | Same tab that renders the diagnostics table; filters are standard pattern in this app (e.g. Flag Bridge). |
| **Risk level** | Low. Additive. |
| **Additive or behavioral** | Additive. |

### 10. Import Diagnostics — SQLite version fallback

| Item | Detail |
|------|--------|
| **Feature name** | get_import_diagnostics: SQLite < 3.25 fallback |
| **File path** | `db/repository/imports.py` |
| **Exact function to add or modify** | **Modify** `get_import_diagnostics`: detect SQLite (e.g. conn connection type or adapter); if SQLite, run SELECT sqlite_version() and parse version; if version < (3, 25), use the GROUP BY / MAX fallback query from IMPORT_DIAGNOSTICS_DESIGN_REPORT §3.4 instead of ROW_NUMBER() query. For Postgres always use window query. |
| **Why this file** | get_import_diagnostics is implemented here; version check and branch belong in the same function. |
| **Risk level** | Low. Fallback is specified in design doc. |
| **Additive or behavioral** | Behavioral (different query path on old SQLite). Additive for environments on 3.25+. |

### 11. Available Units as strongest validator

| Item | Detail |
|------|--------|
| **Feature name** | Prefer AVAILABLE_UNITS over DMRB for report_ready_date |
| **File path** | TBD — likely `services/imports/available_units.py`, `services/imports/dmrb.py`, and/or `services/imports/orchestrator.py` |
| **Exact function to add or modify** | **Deferred until product rule is specified.** Possible approaches: (a) store last_ready_date_source (e.g. report_type) and timestamp on turnover; when applying DMRB, skip overwriting report_ready_date if AVAILABLE_UNITS was applied more recently; (b) apply AVAILABLE_UNITS after DMRB when both files are imported in same run; (c) separate “readiness reconciliation” step that prefers AVAILABLE_UNITS. No patch detail until product confirms rule. |
| **Why this file** | Import apply logic and/or orchestrator; exact location depends on chosen approach. |
| **Risk level** | Medium. Changes when report_ready_date gets updated; could affect manual overrides or display. |
| **Additive or behavioral** | Behavioral. |

### 12. Report Operations tab counts

| Item | Detail |
|------|--------|
| **Feature name** | Tab labels with counts (e.g. “Import Diagnostics (12)”) |
| **File path** | `ui/screens/report_operations.py` |
| **Exact function to add or modify** | **Modify** `render()`: when building st.tabs, compute lengths of each queue (missing move-out, FAS rows, diagnostics) and use in tab labels, e.g. `st.tabs(["Missing Move-Out", "FAS Tracker", "Import Diagnostics"])` → `st.tabs([f"Missing Move-Out ({len(missing_rows)})", f"FAS Tracker ({len(fas_rows)})", f"Import Diagnostics ({len(diag_rows)})"])` (or equivalent). Requires loading all three datasets; may want to do so once and pass to tab renderers. |
| **Why this file** | Tab labels are part of the Report Operations screen layout. |
| **Risk level** | Low. Extra load of diagnostics if not already loaded for tab content. |
| **Additive or behavioral** | Additive. |

### 13. Repair workflow documentation

| Item | Detail |
|------|--------|
| **Feature name** | Document repair workflow in lifecycle docs |
| **File path** | `docs/LIFECYCLE_CONTROL_POINTS_ANALYSIS.md` or `docs/LIFECYCLE_STATE_AND_WORKFLOW_SPECIFICATION.md` |
| **Exact function to add or modify** | **Add** a short subsection or paragraph: “The repair workflow for move-in-without-move-out is: Report Operations → Missing Move-Out queue → Resolve (enter move-out date, Create turnover). Units do not appear on the main board until a turnover exists with move_out_date.” |
| **Why this file** | Lifecycle docs are the single place for workflow and control-point description. |
| **Risk level** | None. Doc only. |
| **Additive or behavioral** | Additive. |

### 14. Admin post-import hint for diagnostics

| Item | Detail |
|------|--------|
| **Feature name** | After import: hint to check Import Diagnostics when there are non-OK rows |
| **File path** | `ui/screens/admin.py` |
| **Exact function to add or modify** | **Modify** the block that runs after import_report_file returns: when result has conflict_count > 0 or invalid_count > 0, add st.info or st.caption suggesting “Check Report Operations → Import Diagnostics for details.” (or similar). |
| **Why this file** | Admin is where imports are triggered; post-import message is the right place to point to diagnostics. |
| **Risk level** | Low. Additive message. |
| **Additive or behavioral** | Additive. |

---

## Summary by Priority

| Priority | Patches | Purpose |
|----------|---------|---------|
| **Must build now** | 1–5 | Import Diagnostics end-to-end (repo, export, service, UI tab); reconcile_missing_tasks move_out_date guard. |
| **Should build next** | 6–8 | Task instantiation guard; repair caption; optional board move_out_date filter. |
| **Later improvements** | 9–14 | Diagnostics filters, SQLite fallback, Available Units authority, tab counts, repair doc, Admin hint. |

No code was modified; this document is planning only.
