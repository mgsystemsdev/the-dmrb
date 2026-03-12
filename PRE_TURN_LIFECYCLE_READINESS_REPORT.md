# Pre-Turn Lifecycle Readiness Report

**Date:** 2025-03-11  
**Purpose:** Prepare the system for the lifecycle rule: *A turnover becomes operational only after move_out_date exists. Units referenced by reports but missing move_out_date must remain pre-turn exceptions, not active turnovers.*  
**Scope:** Read-only audit; no files were modified.

---

## 1. Turnover Activation Points

### 1.1 MOVE_OUTS import (creates new turnover)

| Item | Detail |
|------|--------|
| **File path** | `services/imports/move_outs.py` |
| **Function name** | `apply_move_outs` |
| **Conditions required** | Unit resolved via `_ensure_unit`; no open turnover for unit (`get_open_turnover_by_unit` returns None); **move_out_date must be present** (parsed from "Move-Out Date" column). |
| **move_out_date must exist?** | **Yes.** Rows with missing Move-Out Date are rejected before any turnover creation: diagnostic `MISSING_REQUIRED_FIELD` / `MOVE_OUT_DATE_MISSING`, `_write_import_row` with `validation_status=INVALID`, `invalid_count` incremented, `continue` (no `insert_turnover`). |
| **Activation** | Only when `move_out_date` is non-None: `repository.insert_turnover(conn, {..., "move_out_date": move_out_iso, "scheduled_move_out_date": move_out_iso, ...})` then `_instantiate_tasks_for_turnover_impl(conn, turnover_id, ...)`. |

### 1.2 Manual turnover creation (Add Availability)

| Item | Detail |
|------|--------|
| **File path** | `services/manual_availability_service.py` → `services/turnover_service.py` |
| **Function names** | `add_manual_availability`, `create_turnover_and_reconcile` |
| **Conditions required** | Unit exists (by property/phase/building/unit_number); no open turnover for unit; **move_out_date is a required parameter** (type `date`, not Optional). |
| **move_out_date must exist?** | **Yes.** `CreateTurnover` command has `move_out_date: date`; UI in `ui/screens/admin.py` uses `st.date_input("Move out", ...)` and passes it to `create_turnover_workflow` → `add_manual_availability(..., move_out_date=move_out_date, ...)` → `create_turnover_and_reconcile(..., move_out_date=move_out_date, ...)`. |
| **Activation** | `repository.insert_turnover(conn, {..., "move_out_date": move_out_iso, ...})` then `import_service.instantiate_tasks_for_turnover(...)`, then SLA and risk reconciliation. |

### 1.3 Other workflows

- **PENDING_MOVE_INS, AVAILABLE_UNITS, DMRB, PENDING_FAS:** Do **not** create turnovers. They only update existing open turnovers (move_in_date, report_ready_date, availability, FAS confirmation). When no open turnover exists they write to `import_row` with conflict/ignored reasons and do not call `insert_turnover`.

### 1.4 Summary: Can any path activate a turnover without move_out_date?

**No.**  

- **MOVE_OUTS:** Explicitly skips creation when `move_out_date` is None; only creates turnover with `move_out_iso`.  
- **Manual:** `move_out_date` is required by type and UI.  
- **Repository:** `insert_turnover` uses `data["move_out_date"]` (required key).  
- **Schema:** `turnover.move_out_date` is `TEXT NOT NULL` in both `db/schema.sql` and `db/postgres_schema.sql` (and `CHECK(move_out_date IS NOT NULL)` in SQLite schema). So even if code passed None, the DB would reject it.

**Conclusion:** Activation occurs only during (1) MOVE_OUTS import when the row has a valid Move-Out Date, and (2) manual turnover creation with a chosen move-out date. No current path activates a turnover without move_out_date.

---

## 2. Task Instantiation Triggers

### 2.1 Trigger locations

| File path | Function name | Event that triggers task creation | Depends on turnover creation? | Checks lifecycle state? |
|----------|---------------|-----------------------------------|------------------------------|-------------------------|
| `services/imports/tasks.py` | `instantiate_tasks_for_turnover`, `_instantiate_tasks_for_turnover_impl` | Called after a **new** turnover is created (by MOVE_OUTS or manual). | Yes — receives `turnover_id` and creates tasks for that turnover. | No — no check for move_out_date or lifecycle. |
| `services/imports/move_outs.py` | `apply_move_outs` | Right after `repository.insert_turnover(...)` for a new turnover. | Yes. | No — row already validated for move_out_date before this branch. |
| `services/turnover_service.py` | `create_turnover_and_reconcile` | After `repository.insert_turnover(...)`; calls `import_service.instantiate_tasks_for_turnover(...)`. | Yes. | No — move_out_date is required by caller. |
| `services/turnover_service.py` | `reconcile_missing_tasks` (and similar reconcile flows) | When updating an existing turnover; adds **missing** tasks from templates. | Yes — operates on existing turnover. | No lifecycle check. |

### 2.2 Task creation logic (summary)

- `_instantiate_tasks_for_turnover_impl` loads task templates by phase (or property), filters by unit attributes, then `repository.insert_task(conn, {"turnover_id": turnover_id, ...})` for each template. Comment in code: *"ensure the turnover gets tasks as soon as it has a move-out date"* — meaning current design assumes the turnover already has move_out_date when this runs (which is true today because turnover creation only happens with move_out_date).

### 2.3 Could tasks ever be created before move_out_date is known?

**Under current code:** No. The only callers of task instantiation are (1) MOVE_OUTS after creating a turnover with move_out_date, and (2) manual availability / `create_turnover_and_reconcile`, which require move_out_date. There is no path that creates a turnover without move_out_date and then creates tasks.

**If** a future change introduced a “pre-turn” turnover (e.g. unit referenced by a report but move_out_date NULL), and that path still called `_instantiate_tasks_for_turnover_impl`, then tasks **could** be created before move_out_date is known unless that call is guarded.

---

## 3. Board Rendering Pipeline

### 3.1 Flow: database query → enrichment → board rendering

1. **Database query**  
   - **Functions:** `repository.list_open_turnovers(conn, phase_ids=...)` or `repository.list_open_turnovers(conn, property_ids=...)` (in `db/repository/turnovers.py`).  
   - Returns all open turnovers (`closed_at IS NULL AND canceled_at IS NULL`). No filter on move_out_date.

2. **Batch load**  
   - **Function:** `services/board_query_service.get_dmrb_board_rows` (and same data path for flag bridge / risk radar).  
   - Loads: turnover_ids → units via `repository.get_units_by_ids`, tasks via `repository.get_tasks_for_turnover_ids`, notes via `repository.get_notes_for_turnover_ids`, optional enrichment cache via `repository.get_enrichment_cache_for_turnover_ids`.

3. **Flat row build**  
   - **Function:** `_build_flat_row(turnover, unit, tasks_for_turnover, notes_for_turnover)` in `board_query_service.py`.  
   - One row per turnover; includes `move_out_date`, `move_in_date`, task dicts, etc.

4. **Enrichment**  
   - **Function:** `domain.enrichment.enrich_row(row, today)` (or use cached payload).  
   - **Lifecycle derivation:** `domain.enrichment.derive_phase` → `domain.lifecycle.derive_lifecycle_phase` (and `effective_move_out_date`).  
   - Adds: phase, nvm, dv, dtbr, operational_state, attention_badge, SLA flags, risk fields, etc.

5. **Filtering (in-memory)**  
   - In `get_dmrb_board_rows`: search_unit, filter_phase, filter_status, filter_nvm, filter_assignee, filter_qc. No filter on “has move_out_date” or “pre-turn”.

6. **Sort**  
   - `_sort_move_in`: by (move_in present, move_in date, -dv).

7. **Board UI entry points**  
   - **DMRB Board:** `ui/screens/board.py` → `_get_dmrb_rows()` → `cached_get_dmrb_board_rows` → `board_query_service.get_dmrb_board_rows`.  
   - **Flag Bridge:** `ui/screens/flag_bridge.py` → `cached_get_flag_bridge_rows` → `board_query_service.get_flag_bridge_rows` (same rows, optional breach filter).  
   - **Risk Radar:** `ui/screens/risk_radar.py` → `cached_get_risk_radar_rows` → `board_query_service.get_risk_radar_rows` (same rows, risk filter/sort).  
   - **Cache layer:** `ui/data/cache.py` — `cached_get_dmrb_board_rows`, `cached_get_flag_bridge_rows`, `cached_get_risk_radar_rows` call the service with `get_conn()`.

### 3.2 Where the board decides which units appear

- **Inclusion:** Any row that passes the query and in-memory filters appears. The only “gate” is `list_open_turnovers` (open = not closed, not canceled). There is **no** exclusion of rows where move_out_date is missing, because the schema and all creation paths currently ensure every open turnover has move_out_date.
- **Exclusion:** Units with no turnover never appear (board is turnover-centric). Units whose turnover is closed/canceled are excluded by the open-turnover query.

---

## 4. Units Referenced Without Turnovers

### 4.1 Move-in import (PENDING_MOVE_INS)

| Behavior | Detail |
|---------|--------|
| **When** | Row references a unit (by norm) but unit has no open turnover. |
| **Detection** | `repository.get_open_turnover_by_unit(conn, unit_id)` is None. |
| **Logic location** | `services/imports/move_ins.py`, `apply_pending_move_ins`. |
| **What happens** | Diagnostic `UNKNOWN_UNIT_REFERENCE` / "No open turnover found for pending move-in row."; `_write_import_row(..., validation_status="CONFLICT", conflict_flag=1, conflict_reason="MOVE_IN_WITHOUT_OPEN_TURNOVER", move_out_date=None, move_in_date=...)`; `conflict_count += 1`; **no turnover created**. |

### 4.2 Availability import (AVAILABLE_UNITS)

| Behavior | Detail |
|---------|--------|
| **When** | Unit not found or unit has no open turnover. |
| **Detection** | `get_unit_by_norm` None or `get_open_turnover_by_unit` None. |
| **Logic location** | `services/imports/available_units.py`, `apply_available_units`. |
| **What happens** | Diagnostic "No open turnover found for ready-date import row."; `_write_import_row(..., validation_status="IGNORED", conflict_reason="NO_OPEN_TURNOVER_FOR_READY_DATE", move_out_date=None, move_in_date=None)`; **no turnover created**. |

### 4.3 DMRB import

| Behavior | Detail |
|---------|--------|
| **When** | Unit not found or no open turnover. |
| **Logic location** | `services/imports/dmrb.py`, `apply_dmrb`. |
| **What happens** | Same pattern: diagnostic, `_write_import_row(..., validation_status="IGNORED", conflict_reason="NO_OPEN_TURNOVER_FOR_READY_DATE", ...)`; **no turnover created**. |

### 4.4 PENDING_FAS import

| Behavior | Detail |
|---------|--------|
| **When** | Unit not found or no open turnover. |
| **Logic location** | `services/imports/pending_fas.py`, `apply_pending_fas`. |
| **What happens** | Diagnostic; `_write_import_row(..., validation_status="IGNORED", conflict_reason="NO_OPEN_TURNOVER_FOR_VALIDATION", ...)`; **no turnover created**. |

### 4.5 MOVE_OUTS: missing move-out date

| Behavior | Detail |
|---------|--------|
| **When** | Row has unit but "Move-Out Date" is missing/invalid. |
| **Logic location** | `services/imports/move_outs.py`, `apply_move_outs`. |
| **What happens** | Diagnostic `MISSING_REQUIRED_FIELD` / `MOVE_OUT_DATE_MISSING`; `_write_import_row(..., validation_status=INVALID, conflict_flag=1, conflict_reason="MOVE_OUT_DATE_MISSING", move_out_date=None, ...)`; **no turnover created**. |

### 4.6 Summary

- **Report references unit but no turnover:** Handled by PENDING_MOVE_INS, AVAILABLE_UNITS, DMRB, PENDING_FAS — row is written to `import_row` with conflict/ignored reason; no turnover is created.  
- **Report references unit but move_out_date missing (MOVE_OUTS):** Treated as invalid; row written to `import_row` with `MOVE_OUT_DATE_MISSING`; no turnover created.  
- **Logic lives in:** `services/imports/move_ins.py`, `available_units.py`, `dmrb.py`, `pending_fas.py`, `move_outs.py`; shared `_write_import_row` in `services/imports/common.py` → `db/repository/imports.py` `insert_import_row`.

---

## 5. Lifecycle State Calculation

### 5.1 Where lifecycle state is computed

| File path | Function names | Inputs used |
|----------|----------------|------------|
| `domain/lifecycle.py` | `effective_move_out_date(row)`, `derive_lifecycle_phase(move_out_date, move_in_date, closed_at, canceled_at, today)` | Row dict (move_out_manual_override_at, move_out_date, legal_confirmation_source, confirmed_move_out_date, scheduled_move_out_date); move_in_date; closed_at; canceled_at; today. |
| `domain/enrichment.py` | `derive_phase(t, today)`, `compute_facts(row, today)` (calls `effective_move_out_date(row)`, `derive_phase`) | Flat row (move_out_date, move_in_date, closed_at, canceled_at, task_*, report_ready_date, etc.). |

### 5.2 Does lifecycle state assume move_out_date always exists?

- **`domain/lifecycle.derive_lifecycle_phase`:** Explicitly handles `move_out_date is None` → returns `NOTICE` (first branch). So the **domain** does **not** assume move_out_date always exists.  
- **`domain/enrichment.derive_phase`:** If `move_out` is None, returns `NOTICE_SMI` if move_in else `NOTICE`. So enrichment also supports missing move_out_date.  
- **`effective_move_out_date`:** Returns Optional[date]; can return None if no override, no legal confirmed, no scheduled, and no legacy move_out_date.  
- **Downstream:** `compute_facts` uses `move_out = effective_move_out_date(row)`; `dv = business_days(move_out, today) if move_out else None`; SLA breach logic uses `dv` and other flags. So when move_out_date is missing, dv is None and phase is NOTICE/NOTICE_SMI; the rest of the pipeline can still run.

**Conclusion:** Lifecycle state calculation does **not** assume move_out_date always exists; it has defined behavior for missing move_out_date (NOTICE/NOTICE_SMI, no dv). The schema and creation paths, however, currently ensure every stored turnover has move_out_date.

---

## 6. Database Constraints

### 6.1 move_out_date nullability

- **SQLite (`db/schema.sql`):** `turnover.move_out_date TEXT NOT NULL` and `CHECK(move_out_date IS NOT NULL)`.  
- **Postgres (`db/postgres_schema.sql`):** `turnover.move_out_date TEXT NOT NULL`.  
- **Migrations:** No migration was found that makes move_out_date nullable on turnover. Migration 009 adds scheduled_move_out_date, confirmed_move_out_date, etc.; it does not alter move_out_date nullability.

**Conclusion:** move_out_date is NOT NULL; turnovers cannot exist without move_out_date at the schema level.

### 6.2 Tasks and turnover existence

- **task table:** `turnover_id INTEGER NOT NULL REFERENCES turnover(turnover_id)`. Tasks depend on turnover existence; no task without a turnover.  
- There is no schema constraint that “tasks may only exist when turnover has move_out_date.”

### 6.3 Schema changes required for a pre-turn state

To support a pre-turn state (unit referenced by report, move_in_date possibly set, move_out_date missing, no tasks scheduled) while keeping the rule “operational only after move_out_date”:

- **Option A (pre-turn as a row in turnover):** Allow turnover rows with move_out_date NULL. That would require: (1) making `turnover.move_out_date` nullable (schema + migration), (2) relaxing or removing the CHECK on move_out_date, (3) ensuring task instantiation and board “operational” visibility only when move_out_date is not NULL (application/query logic).  
- **Option B (pre-turn outside turnover):** Keep turnover.move_out_date NOT NULL and represent “referenced but no move-out yet” in another structure (e.g. import_row only, or a dedicated pre_turn / exception table). Then no change to turnover nullability; “activation” would mean creating a turnover only when move_out_date is set.

The report does not recommend one option; it only states that **if** a pre-turn state must exist as a first-class entity with no move_out_date, the current schema does not allow it and would need one of the above directions.

---

## 7. Existing Exception Handling

### 7.1 Lifecycle / import anomaly handling

| File path | Function(s) | Conditions checked |
|-----------|-------------|---------------------|
| `services/imports/move_outs.py` | `apply_move_outs` | Missing Move-Out Date → invalid row, MOVE_OUT_DATE_MISSING; move-out date mismatch for existing open turnover → CONFLICT, MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER. |
| `services/imports/move_ins.py` | `apply_pending_move_ins` | Unit not found; no open turnover → MOVE_IN_WITHOUT_OPEN_TURNOVER. |
| `services/imports/available_units.py` | `apply_available_units` | Unit not found; no open turnover → NO_OPEN_TURNOVER_FOR_READY_DATE (IGNORED). |
| `services/imports/dmrb.py` | `apply_dmrb` | Unit not found; no open turnover → NO_OPEN_TURNOVER_FOR_READY_DATE (IGNORED). |
| `services/imports/pending_fas.py` | `apply_pending_fas` | Unit not found; no open turnover → NO_OPEN_TURNOVER_FOR_VALIDATION (IGNORED). |
| `services/imports/common.py` | `_append_diagnostic` | Builds list of diagnostics (row_index, column, error_type, error_message, suggestion). |
| `imports/validation/schema_validator.py` | Validation, file_validator | MISSING_REQUIRED_COLUMN, MISSING_REQUIRED_FIELD, INVALID_DATE_FORMAT, etc. |
| `db/repository/risks.py` | `_ensure_confirmation_invariant` | legal_confirmation_source set but confirmed_move_out_date NULL → invariant violation. |
| `services/turnover_service.py` | Various reconcile paths | has_data_integrity_conflict flag passed to risk evaluation. |
| `domain/risk_engine.py` | `evaluate_risks` | has_data_integrity_conflict → can affect risk evaluation. |

### 7.2 Ignored rows / conflicts storage

- **import_row:** Every applied, conflict, or invalid row is written via `_write_import_row` → `repository.insert_import_row` with validation_status, conflict_flag, conflict_reason, move_out_date, move_in_date. So “exceptions” (invalid/conflict/ignored) are already recorded per batch.  
- **Admin UI:** `ui/screens/admin.py` shows diagnostics after import; when a batch is selected, it loads `get_import_rows_by_batch(conn, batch_id)` and displays a table with validation_status, conflict_flag, conflict_reason. A “List conflicts here when a batch is selected (future)” caption indicates a dedicated conflict list is only partially implemented.

### 7.3 Could this support an exception queue?

- **Yes, in part.** import_row already acts as an exception log per batch (conflict_reason, validation_status, unit_code_norm, move_out_date, move_in_date). A “Missing Move-Out” or “Pre-Turn” queue could: (1) query import_row (and optionally other sources) for rows with e.g. MOVE_OUT_DATE_MISSING or a new pre-turn reason, or (2) if pre-turn becomes a first-class entity (e.g. turnover with move_out_date NULL), query that table. Existing diagnostics and conflict reasons are a good basis for filtering and labeling; no single “exception queue” aggregation exists yet.

---

## 8. UI Surfaces That Could Host an Exception Queue

### 8.1 Filtered unit/list surfaces

| File path | Component / area | Data query | Notes |
|-----------|-------------------|------------|--------|
| `ui/screens/admin.py` | Import console; batch selection; “Imported Rows” table | `get_import_rows_by_batch(conn, batch_id)` | Shows validation_status, conflict_flag, conflict_reason per row. Subheader “Conflicts” with caption about listing conflicts when batch selected (future). |
| `ui/screens/admin.py` | Add Availability (single unit) | Unit lookup; create_turnover_workflow | Single-unit form; not a list. |
| `ui/screens/board.py` | DMRB Board | `cached_get_dmrb_board_rows` → `get_dmrb_board_rows` | Turnover-centric list; filters (phase, status, nvm, assignee, qc). |
| `ui/screens/flag_bridge.py` | Flag Bridge | `cached_get_flag_bridge_rows` | Same rows as board; breach filter. |
| `ui/screens/risk_radar.py` | Risk Radar | `cached_get_risk_radar_rows` | Same rows; risk filter/sort. |
| `ui/screens/unit_import.py` | Unit Master Import | Unit master import service result | Shows conflict_count, error_count. |

### 8.2 Where a “Missing Move-Out” queue page could integrate

- **Admin / Import area:** Add a tab or section “Missing Move-Out” (or “Pre-Turn Exceptions”) that: (1) queries import_row (and optionally a future pre_turn table) for rows with e.g. `conflict_reason = 'MOVE_OUT_DATE_MISSING'` or a new pre-turn reason, optionally by property/batch, and (2) displays them in a table with unit, report type, date, suggestion, link to fix (e.g. re-import MOVE_OUTS or add move-out date). Uses existing `get_import_rows_by_batch` or a new query like “import_row WHERE conflict_reason IN (...)” grouped by batch or time.  
- **Minimal architectural change:** Reuse existing admin screen and repository (import_row); add one new query (or filter on existing batch/import_row data) and one new UI block (tab or expander). No change to board query or turnover list.

---

## 9. Data Model Compatibility Check

**Hypothetical state:**

- Unit referenced by report  
- move_in_date exists (e.g. from PENDING_MOVE_INS)  
- move_out_date missing  
- No tasks scheduled  

**Can this state exist safely today?**

- **As a turnover row:** No. The schema requires `turnover.move_out_date NOT NULL`. So you cannot store this state in the turnover table.  
- **As “unit + import_row” only:** Partially. A unit can exist without a turnover. A report (e.g. PENDING_MOVE_INS) can reference that unit; the import will write an import_row with conflict_reason MOVE_IN_WITHOUT_OPEN_TURNOVER and will not create a turnover. So “unit referenced by report, no turnover” exists only as unit + import_row; there is no row with “move_in_date set, move_out_date missing” on turnover because no such turnover is created.  
- **If we allowed a turnover with move_in_date and NULL move_out_date:** That would require making move_out_date nullable and a code path that creates/updates such a turnover without creating tasks. Today no such path exists; the domain/lifecycle logic would treat NULL move_out_date as NOTICE/NOTICE_SMI and would not break, but the schema and creation paths do not support it.

**Conclusion:** The current schema and lifecycle logic do **not** support a first-class “turnover” state where move_out_date is missing and move_in_date exists and no tasks are scheduled. They do support “unit referenced by report with no turnover” as unit + import_row only; that is not a turnover row.

---

## 10. Integration Points for the Pre-Turn Guardrail

**Rule to enforce:** *Turnover tasks must not be scheduled until move_out_date exists.*

### 10.1 Potential interception layers

| Layer | Pros | Risks |
|-------|------|--------|
| **Import pipelines (MOVE_OUTS)** | Already validates move_out_date before creating turnover; single place for file-based creation. | Only affects MOVE_OUTS; manual and any future import types need the same rule elsewhere. |
| **Turnover creation functions** | `insert_turnover` or wrappers (`create_turnover_and_reconcile`, `apply_move_outs` branch that inserts): block or branch when move_out_date is missing. | If turnover is allowed with NULL move_out_date later, must ensure no task creation and no “operational” visibility until move_out_date is set. |
| **Task instantiation functions** | In `services/imports/tasks.py`, at start of `_instantiate_tasks_for_turnover_impl`: if turnover has no effective move_out_date, skip creating tasks (or no-op). | Clear and narrow: “no tasks without move_out_date.” Risk: callers might assume tasks exist; need to document and possibly expose “pre-turn” state in UI. |
| **Lifecycle enrichment** | Could mark rows as “pre-turn” when effective_move_out_date is None; board could filter or show in separate queue. | Does not prevent task creation; only affects display and downstream logic. Good for visibility, not for enforcing “no tasks.” |
| **Board query layer** | `list_open_turnovers` or `get_dmrb_board_rows` could filter out turnovers with no move_out_date (or put them in a separate “pre-turn” list). | Does not prevent task creation; only affects what appears on the operational board. Complements guardrail but is not the enforcement point. |

### 10.2 Recommended interception points (conceptual)

- **Enforcement (no tasks until move_out_date):**  
  - **Task instantiation:** In `_instantiate_tasks_for_turnover_impl` (and any other place that creates tasks for a new turnover), require that the turnover has an effective move_out_date (e.g. load turnover row and check `effective_move_out_date(turnover)` or raw move_out_date); if not, return without creating tasks.  
  - **Turnover creation:** Keep or add a rule at creation: “do not call task instantiation when move_out_date is missing.” Currently creation paths already only create when move_out_date exists; if a future path creates a “pre-turn” turnover with NULL move_out_date, that path must not call task instantiation.  

- **Visibility (pre-turn / exception queue):**  
  - **Board query / UI:** Optionally separate “operational” board (move_out_date present) from “pre-turn” or “exceptions” (e.g. move_out_date missing, or rows from import_row with MOVE_OUT_DATE_MISSING).  
  - **Import/Admin:** Use existing import_row diagnostics and conflict reasons to drive a “Missing Move-Out” or pre-turn queue page as in section 8.

No implementation is proposed in this report; only the locations and trade-offs are described.

---

*End of Pre-Turn Lifecycle Readiness Report.*
