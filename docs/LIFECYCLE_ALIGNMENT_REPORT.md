# Lifecycle Alignment Report

**Purpose:** Align current repository behavior and Report Operations features with the intended real-world lifecycle workflow.  
**Scope:** Read-only analysis; no code or file modifications.  
**Target model:** Turnover operational only when move_out_date exists; Report Operations for reconciliation, diagnostics, and report-based workflows; manual correction as first-class; board for active turnovers only.

**Date:** 2025-03-11

---

## Target Lifecycle Rules (Reference)

1. **A turnover becomes operational only when move_out_date exists.**
2. **Units referenced by reports without a move_out_date are exceptions, not active turnovers.**
3. **Reports may arrive in any order.**
4. **Available Units is the strongest validator of live vacancy/readiness data.**
5. **Move-In rows without move-out must go to a repair workflow, not the main board.**
6. **Manual correction is part of the intended system, not an edge case.**
7. **The board is for active turnovers.**
8. **Report Operations is for reconciliation, diagnostics, and report-based workflows.**

---

## 1. What Already Matches the Target Lifecycle

| Target rule | Current behavior | Evidence |
|-------------|------------------|----------|
| **Turnover operational only when move_out_date exists** | Creation paths require move_out_date; schema enforces NOT NULL. | MOVE_OUTS skips rows with missing Move-Out Date (diagnostic MOVE_OUT_DATE_MISSING, no insert). Manual Add Availability requires `move_out_date: date`. `db/schema.sql`: `turnover.move_out_date TEXT NOT NULL`, `CHECK(move_out_date IS NOT NULL)`. `insert_turnover` uses `data["move_out_date"]`. |
| **Units without move_out_date = exceptions** | No turnover is created without move_out_date. Exceptions are written to import_row with conflict_reason. | MOVE_OUTS: invalid row, no turnover. PENDING_MOVE_INS / AVAILABLE_UNITS / DMRB / PENDING_FAS: when no open turnover, row is CONFLICT/IGNORED (e.g. MOVE_IN_WITHOUT_OPEN_TURNOVER, NO_OPEN_TURNOVER_FOR_READY_DATE); no insert_turnover. |
| **Reports may arrive in any order** | Each report type is applied independently; no enforced sequence. | Orchestrator `import_report_file` dispatches by report_type; no dependency on other report types. MOVE_OUTS creates turnover; others only update existing open turnover. Idempotency is per-batch (checksum), not cross-report. |
| **Manual correction is first-class** | Manual overrides are stored, respected by imports, and clearable when import matches. | `turnover`: move_out_manual_override_at, ready_manual_override_at, move_in_manual_override_at, status_manual_override_at. Domain: effective_move_out_date prioritizes manual override. Imports: when override set and value differs → SKIPPED_OVERRIDE; when match → override cleared + audit. Turnover detail UI: date/status edits and “Clear override.” |
| **Board is for active turnovers** | Board is turnover-centric; only open turnovers (closed_at/canceled_at NULL) are loaded. | `list_open_turnovers` → `get_dmrb_board_rows` → flat rows per turnover. No unit appears without an open turnover. |
| **Report Operations for reconciliation/diagnostics** | Missing Move-Out queue and FAS Tracker exist; resolve flow creates turnover with move_out_date. | `report_operations_service`: get_missing_move_out_queue (MOVE_IN_WITHOUT_OPEN_TURNOVER, MOVE_OUT_DATE_MISSING), resolve_missing_move_out (add_manual_availability), get_fas_tracker_rows, upsert_fas_note. UI: tabs “Missing Move-Out”, “FAS Tracker”. |
| **Lifecycle handles missing move_out for display** | Domain/enrichment support move_out_date None without assuming it exists. | `domain/lifecycle.derive_lifecycle_phase`: move_out_date is None → NOTICE. `domain/enrichment.derive_phase`: move_out None → NOTICE_SMI or NOTICE. effective_move_out_date returns Optional[date]. |

---

## 2. What Still Conflicts With the Target Lifecycle

| Conflict | Detail |
|----------|--------|
| **Board does not explicitly filter by move_out_date** | Target: “Board is for active turnovers” (operational = has move_out_date). Current: Board shows all open turnovers; schema and creation already ensure every open turnover has move_out_date, so no conflict in practice. **If** schema were ever relaxed to allow NULL move_out_date, the board would still show those rows because `list_open_turnovers` has no `move_out_date IS NOT NULL` filter. |
| **reconcile_missing_tasks has no move_out_date guard** | Target: No tasks until turnover is operational (move_out_date exists). Current: `reconcile_missing_tasks` selects open turnovers with zero tasks and calls `instantiate_tasks_for_turnover` with no check for move_out_date. Today no open turnover can have NULL move_out_date, so this is a latent risk only; if a future path created “pre-turn” turnovers with NULL move_out_date, backfill would still create tasks. |
| **Move-in without move-out → “repair workflow”** | Target: “Move-In rows without move-out must go to a repair workflow, not the main board.” Current: Move-in-only rows (PENDING_MOVE_INS when unit has no open turnover) are written as CONFLICT MOVE_IN_WITHOUT_OPEN_TURNOVER and appear in Report Operations “Missing Move-Out” queue; resolving creates a turnover (with move_out_date) that then appears on the board. There is no separate **repair workflow** or **repair board**; the “repair” is “resolve via Report Operations by adding move-out date.” So the **destination** (not main board until move_out exists) is correct; the **workflow name** (“repair workflow”) is not a distinct feature—it’s the existing Missing Move-Out queue + resolve. |
| **Available Units as “strongest validator”** | Target: “Available Units is the strongest validator of live vacancy/readiness data.” Current: AVAILABLE_UNITS and DMRB both update report_ready_date (and AVAILABLE_UNITS also availability_status) on an existing open turnover. There is no precedence rule (e.g. “prefer AVAILABLE_UNITS over DMRB when both have data” or “last import wins by report type priority”). So “strongest validator” is **not** encoded as an authority rule; it’s at most a process guideline. |

---

## 3. Workflows Now Complete

| Workflow | Status | Notes |
|----------|--------|-------|
| **Turnover activation only with move_out_date** | Complete | MOVE_OUTS and manual creation only; both require move_out_date; schema NOT NULL. |
| **Exception handling for missing move-out** | Complete | MOVE_OUTS rows without date → INVALID, MOVE_OUT_DATE_MISSING. Other reports referencing unit with no turnover → CONFLICT/IGNORED with specific conflict_reason. |
| **Missing Move-Out queue (Report Operations)** | Complete | Queue shows units from import_row (MOVE_IN_WITHOUT_OPEN_TURNOVER, MOVE_OUT_DATE_MISSING) where unit exists and has no open turnover; resolve = add move-out date → create turnover. |
| **FAS Tracker (Report Operations)** | Complete | PENDING_FAS rows with unit/note; upsert_fas_note for reconciliation. |
| **Manual overrides** | Complete | Four override timestamps; import respects them (skip or clear); turnover detail allows set/clear. |
| **Board = open turnovers only** | Complete | list_open_turnovers → board rows; no unit without turnover. |
| **Report order independence** | Complete | No enforced order; each report type applied independently. |
| **Lifecycle phase with optional move_out** | Complete | Domain and enrichment handle move_out None (NOTICE/NOTICE_SMI); no assumption that move_out always exists. |

---

## 4. Workflows Still Missing

| Workflow | Gap |
|----------|-----|
| **Import Diagnostics tab** | Designed in `docs/IMPORT_DIAGNOSTICS_DESIGN_REPORT.md` but **not implemented**. Report Operations UI has only two tabs (Missing Move-Out, FAS Tracker). No `get_import_diagnostics` in repository; no `get_import_diagnostics_queue` in report_operations_service; no third tab in report_operations.py. |
| **Explicit “operational” filter for board** | No filter “only turnovers with move_out_date present” in board query or list_open_turnovers. Redundant today (schema enforces), but if pre-turn state is ever introduced (nullable move_out_date), board would need this filter and a separate exception view. |
| **Guard in task instantiation for move_out_date** | `_instantiate_tasks_for_turnover_impl` and `reconcile_missing_tasks` do not check move_out_date before creating tasks. Safety net only until/unless pre-turn turnovers exist. |
| **Available Units as strongest validator** | No rule that AVAILABLE_UNITS overrides or outranks DMRB (or other readiness sources) for report_ready_date / availability. Last write wins per field. |
| **Named “repair workflow”** | No separate UI or flow labeled “repair workflow.” Move-in-without-move-out is handled by Missing Move-Out queue + resolve; naming/documentation could present this explicitly as the repair path. |

---

## 5. Highest-Priority Missing Pieces

1. **Import Diagnostics tab** — Designed and specified; gives visibility into all non-OK import outcomes (ignored, conflict, invalid) and supports “Report Operations is for reconciliation, diagnostics, and report-based workflows.” High value, contained change set (repository, service, UI tab).
2. **reconcile_missing_tasks move_out_date guard** — Low code cost; prevents tasks on any future pre-turn turnover and aligns with “operational only when move_out_date exists.” Prevents latent bug if schema or creation paths ever allow NULL move_out_date.
3. **Board “operational” filter (move_out_date IS NOT NULL)** — Only needed if move_out_date becomes nullable; otherwise redundant. Priority: low unless pre-turn state is introduced.
4. **Available Units authority** — Clarify product intent: e.g. “when both AVAILABLE_UNITS and DMRB have been imported, prefer AVAILABLE_UNITS for report_ready_date” would require a precedence rule and possibly timestamp/versioning. Medium effort; product decision first.
5. **Repair workflow naming** — Documentation/UI copy: state that “Move-in without move-out” is resolved via Report Operations → Missing Move-Out → “Create turnover” with move-out date (i.e. the repair workflow is the existing queue + resolve). No code change required for naming.

---

## 6. File-by-File Map: Where Each Missing Piece Belongs

### 6.1 Import Diagnostics tab (full feature)

| Piece | File | Change |
|-------|------|--------|
| Repository query (deduplicated diagnostic rows) | `db/repository/imports.py` | Add `get_import_diagnostics(conn, since_imported_at=None)` per design (window or fallback query; exclude validation_status = 'OK'). |
| Repository export | `db/repository/__init__.py` | Export `get_import_diagnostics`. |
| Service (property filter, shape for UI) | `services/report_operations_service.py` | Add `get_import_diagnostics_queue(conn, property_id, since_imported_at=None)`; call repo; filter by property via get_unit_by_norm; return list of dicts. |
| UI tab and table | `ui/screens/report_operations.py` | Add third tab “Import Diagnostics”; helper `_get_import_diagnostics_queue()`; `_render_import_diagnostics_tab(active_property)`; table columns: Unit, Report Type, Status, Conflict Reason, Import Time, Source File. Optional: filters (Report Type, Status, date range). |

### 6.2 reconcile_missing_tasks move_out_date guard

| Piece | File | Change |
|-------|------|--------|
| Skip turnovers without move_out_date in backfill | `services/turnover_service.py` | In `reconcile_missing_tasks`, after selecting open turnovers with zero tasks, filter to those where `move_out_date IS NOT NULL` (or use effective_move_out_date if row is loaded). Only call instantiate_tasks_for_turnover for those. |

### 6.3 Task instantiation guard (safety net)

| Piece | File | Change |
|-------|------|--------|
| No tasks when turnover has no move_out_date | `services/imports/tasks.py` | At start of `_instantiate_tasks_for_turnover_impl`, optionally load turnover row and skip (return without creating tasks) if move_out_date is None. Callers today always pass turnovers with move_out_date; this is defensive only. |

### 6.4 Board “operational” filter (only if move_out_date becomes nullable)

| Piece | File | Change |
|-------|------|--------|
| Restrict main board to turnovers with move_out_date | `db/repository/turnovers.py` | In `list_open_turnovers` / `list_open_turnovers_by_property`, add `AND move_out_date IS NOT NULL` to WHERE. |
| Or filter in service | `services/board_query_service.py` | In `get_dmrb_board_rows`, after loading turnovers, filter to those with non-null move_out_date before building rows. |
| Exception / pre-turn view | New or existing Report Operations | If pre-turn turnovers exist, a dedicated list (e.g. “Pre-Turn” or “Missing Move-Out on Board”) could list open turnovers where move_out_date IS NULL; query in report_operations_service or new repo function. |

### 6.5 Available Units as strongest validator (product-defined)

| Piece | File | Change |
|-------|------|--------|
| Precedence or “source of truth” for readiness | `services/imports/available_units.py`, `services/imports/dmrb.py` | If product rule is “AVAILABLE_UNITS overwrites DMRB for report_ready_date when both exist,” could: (a) always apply AVAILABLE_UNITS after DMRB when both are imported, or (b) store “last_ready_date_source” and have a resolution step that prefers AVAILABLE_UNITS. Likely touches import orchestrator or a new reconciliation step. No change recommended until product specifies rule. |

### 6.6 Repair workflow naming (documentation / UI copy)

| Piece | File | Change |
|-------|------|--------|
| Caption / docs | `ui/screens/report_operations.py` | In Missing Move-Out tab caption, add that this is the “repair workflow” for move-in-without-move-out (e.g. “Move-in rows without move-out are repaired here by adding a move-out date and creating the turnover.”). |
| Docs | `docs/LIFECYCLE_CONTROL_POINTS_ANALYSIS.md` or new doc | State explicitly that the repair workflow for “Move-In rows without move-out” is: Report Operations → Missing Move-Out queue → Resolve (create turnover with move-out date); they do not go to the main board until resolved. |

---

## 7. Summary

- **Matches:** Turnover activation only with move_out_date, exceptions not as active turnovers, report order independence, manual correction first-class, board for open turnovers, Report Operations for Missing Move-Out and FAS Tracker, lifecycle handling of missing move_out.
- **Conflicts:** Board/reconcile have no explicit move_out_date guard (latent if schema changes); no “strongest validator” rule for Available Units; “repair workflow” is the existing queue+resolve but not named as such.
- **Complete workflows:** Activation, exception handling, Missing Move-Out queue, FAS Tracker, manual overrides, board scope, report order, lifecycle phase.
- **Missing:** Import Diagnostics tab (designed, not built), move_out_date guard in reconcile_missing_tasks and optionally in task instantiation, optional board filter and exception view if pre-turn state is added, Available Units authority rule, repair workflow naming.
- **Highest priority:** (1) Implement Import Diagnostics tab; (2) Add move_out_date guard to reconcile_missing_tasks; (3) Optional guard in task instantiation; (4) Board/exception filter only if move_out_date is made nullable; (5) Available Units precedence and repair naming per product/docs.

No code or files were modified; this document is analysis and alignment only.
