# Lifecycle Control Points Analysis

**Purpose:** Targeted discovery for designing a Pre-Turn guardrail and Missing Move-Out exception queue.  
**Scope:** Identify where the system (1) creates/activates turnovers, (2) instantiates tasks, and (3) generates rows for the operational board.  
**No implementation or code changes.**  
**Date:** 2025-03-11

---

## 1. Turnover Activation

### 1.1 Every place where a turnover becomes active

A turnover becomes “active” when it is inserted as an open turnover (`closed_at IS NULL`, `canceled_at IS NULL`) and is thereafter eligible for board display, task work, and SLA/risk reconciliation. The only two code paths that **create** new turnovers are below. All other import types (PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS, DMRB) only **update** existing open turnovers; they do not create turnovers.

---

#### Location A: MOVE_OUTS import (new turnover per row when unit has no open turnover)

| Item | Detail |
|------|--------|
| **File path** | `services/imports/move_outs.py` |
| **Function name** | `apply_move_outs` |
| **Trigger condition** | Import of a MOVE_OUTS report; for each row: unit exists (via `_ensure_unit`), unit has **no** open turnover (`get_open_turnover_by_unit` returns None), and **row has a non-null move_out_date** (see below). |
| **Fields required to activate** | From the row: `unit_id` (via normalized unit), `move_out_date` (required; rows with missing move-out date are **skipped** and not turned into turnovers). From context: `property_id`, `batch_id`, `now_iso`. Insert payload: `property_id`, `unit_id`, `source_turnover_key` (includes `move_out_iso`), `move_out_date`, `move_in_date` (None), `report_ready_date` (None), `created_at`, `updated_at`, `last_seen_moveout_batch_id`, `missing_moveout_count`, `scheduled_move_out_date`. |

**Activation context:** MOVE_OUTS import only. Rows with missing “Move-Out Date” are treated as invalid: diagnostic is appended, import row is written with `validation_status` INVALID and `conflict_reason` `MOVE_OUT_DATE_MISSING`, and the loop **continues** without creating a turnover or unit. So **activation occurs only when `move_out_date` is present** for that row.

---

#### Location B: Manual turnover creation (Add Availability)

| Item | Detail |
|------|--------|
| **File path** | `services/manual_availability_service.py` |
| **Function name** | `add_manual_availability` |
| **Trigger condition** | User adds a single unit availability from Admin UI; unit exists (by property/phase/building/unit number), unit has **no** open turnover. |
| **Fields required to activate** | `property_id`, `phase_code`, `building_code`, `unit_number`, **`move_out_date`** (required positional/keyword; no default). Optional: `move_in_date`, `report_ready_date`, `today`, `actor`. The service builds `source_turnover_key` and calls `turnover_service.create_turnover_and_reconcile`, which calls `repository.insert_turnover` with `move_out_date` set from the argument. |

**Activation context:** Manual turnover creation only. The function signature **requires** `move_out_date: date`; there is no path to create a turnover without it.

---

### 1.2 Whether activation occurs during MOVE_OUTS import, manual creation, or other workflows

- **MOVE_OUTS import:** Yes. This is the only import type that creates new turnovers. Rows with a valid unit and no open turnover and a **present** move-out date result in `repository.insert_turnover` in `apply_move_outs`.
- **Manual turnover creation:** Yes. Invoked from Admin → Add Unit via `create_turnover_workflow` → `add_manual_availability` → `turnover_service.create_turnover_and_reconcile` → `repository.insert_turnover`.
- **Other workflows:** No. PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS, and DMRB only update existing open turnovers (dates, status, legal confirmation, etc.). They never call `insert_turnover`.

### 1.3 Does the code assume move_out_date always exists when the turnover is created?

- **Yes, at creation time.**  
  - **Schema:** `db/schema.sql` defines `turnover.move_out_date TEXT NOT NULL` and `CHECK(move_out_date IS NOT NULL)`. So the database enforces presence on insert.  
  - **Repository:** `db/repository/turnovers.py` `insert_turnover` uses `data["move_out_date"]` (required key); no default for move_out_date.  
  - **MOVE_OUTS:** Rows with `row.get("move_out_date") is None` are skipped and never reach `insert_turnover`.  
  - **Manual:** `add_manual_availability` requires `move_out_date: date`; `create_turnover_and_reconcile` passes it through to `insert_turnover`.  
- **Downstream (lifecycle/enrichment):** The domain tolerates missing effective move-out for **display** purposes: `domain/enrichment.py` `derive_phase` explicitly handles `move_out is None` (returns NOTICE_SMI or NOTICE). `domain/lifecycle.py` `effective_move_out_date` can return `None` if no override/scheduled/legal/legacy date is set. So the board and enrichment can show rows without a move-out date (e.g. NOTICE phase, no DV), but **creation** of a turnover is currently only possible when move_out_date is supplied and stored.

---

## 2. Task Instantiation

### 2.1 All code paths that create maintenance tasks

Tasks are created only via the shared implementation in `services/imports/tasks.py` (`_instantiate_tasks_for_turnover_impl`), which is exposed as `instantiate_tasks_for_turnover` (from `services.imports.tasks` and re-exported by `services/import_service`). Callers pass `(conn, turnover_id, unit_row, property_id)` so tasks are always associated with a `turnover_id`.

---

#### Path 1: Immediately after turnover creation in MOVE_OUTS import

| Item | Detail |
|------|--------|
| **File path** | `services/imports/move_outs.py` |
| **Function name** | `apply_move_outs` |
| **Trigger condition** | Right after `repository.insert_turnover(...)` for a new turnover (no open turnover for that unit, valid move_out_date). |
| **Association with turnover_id** | `turnover_id` is the return value of `insert_turnover`; passed directly to `_instantiate_tasks_for_turnover_impl(conn, turnover_id, unit_row, property_id)`. |

---

#### Path 2: Immediately after turnover creation in manual availability

| Item | Detail |
|------|--------|
| **File path** | `services/turnover_service.py` |
| **Function name** | `create_turnover_and_reconcile` |
| **Trigger condition** | After `repository.insert_turnover(...)` for the new turnover. |
| **Association with turnover_id** | `turnover_id` from `insert_turnover`; then `import_service.instantiate_tasks_for_turnover(conn, turnover_id, unit_row, property_id)`. |

---

#### Path 3: Backfill (reconciliation) for open turnovers with zero tasks

| Item | Detail |
|------|--------|
| **File path** | `services/turnover_service.py` |
| **Function name** | `reconcile_missing_tasks` |
| **Trigger condition** | Invoked at app startup from `app.py`: after `ensure_database_ready`, if backend is available, `reconcile_missing_tasks(conn)` runs once. It selects open turnovers (closed_at IS NULL, canceled_at IS NULL) that have **no** tasks and for each calls `import_service.instantiate_tasks_for_turnover(conn, turnover_id, unit_dict, property_id)`. |
| **Association with turnover_id** | Reads `(turnover_id, unit_id, property_id)` from the DB; looks up unit row; passes `turnover_id` into `instantiate_tasks_for_turnover`. |

---

### 2.2 Summary: when tasks are created

- **Immediately after turnover creation:** Yes, for both MOVE_OUTS and manual creation. In both cases, task instantiation runs in the same flow right after `insert_turnover`.
- **Through a separate scheduler:** No. There is no cron or scheduled job for task creation.
- **Through reconciliation/backfill:** Yes. `reconcile_missing_tasks` runs once per app startup and creates tasks for any open turnover that has zero tasks.

### 2.3 Check for move_out_date before task creation

- **MOVE_OUTS:** Tasks are only created for turnovers that were just inserted with a non-null `move_out_date` (rows with missing move-out never create a turnover).
- **Manual:** Tasks are only created after a turnover is created with a required `move_out_date`.
- **reconcile_missing_tasks:** There is **no** check for `move_out_date` (or effective move-out) before calling `instantiate_tasks_for_turnover`. It only checks “open turnover with zero tasks.” So if an open turnover ever existed without a move_out_date (e.g. legacy data or a future code path), this path would still create tasks for it.

---

## 3. Board Row Generation

### 3.1 Full path from UI/API to rendered board

- **UI entry points:**  
  - DMRB Board: `app.py` → `render_current_page()` → `ui.screens.board` → `board.render()` → `_get_dmrb_rows()` → `cached_get_dmrb_board_rows(...)`.  
  - Flag Bridge: same router → `ui.screens.flag_bridge` → uses `cached_get_flag_bridge_rows(...)`.  
  - Sidebar “Top Flags”: `app.py` → `render_top_flags()` → `ui/components/sidebar_flags.py` → `cached_get_flag_bridge_rows(...)`.  
  - Risk Radar: `ui.screens.risk_radar` → `cached_get_risk_radar_rows(...)` (which delegates to the same board pipeline then filters/sorts).  
  - Turnover detail: `get_turnover_detail` used by detail screen; unit search on detail uses `cached_get_dmrb_board_rows`.

- **Cache layer:**  
  - **File:** `ui/data/cache.py`.  
  - **Functions:** `cached_get_dmrb_board_rows`, `cached_get_flag_bridge_rows`, `cached_get_risk_radar_rows`.  
  - **Behavior:** Get connection, call into `board_query_service.get_dmrb_board_rows` / `get_flag_bridge_rows` / `get_risk_radar_rows`, return list of dicts. TTL 5s.

- **Board query:**  
  - **File:** `services/board_query_service.py`.  
  - **Functions:**  
    - **get_dmrb_board_rows:** Loads open turnovers via `repository.list_open_turnovers(conn, phase_ids=...)` or `list_open_turnovers(conn, property_ids=...)`; batches units, tasks, notes by turnover_ids; for each turnover builds one flat row with `_build_flat_row(turnover, unit, tasks_for_turnover, notes_for_turnover)`; then enrichment (see below) and in-memory filters (status, nvm, assignee, qc); sorts by move-in and dv.  
    - **get_flag_bridge_rows:** Calls `get_dmrb_board_rows` then filters by breach key (BRIDGE_MAP).  
    - **get_risk_radar_rows:** Calls `get_dmrb_board_rows` then applies `score_enriched_turnover` and optional risk_level filter, sorts by risk.  
    - **get_turnover_detail:** Single turnover by id, same flat row + enrichment for `enriched_fields`.

- **Enrichment:**  
  - **File:** `domain/enrichment.py`.  
  - **Function:** `enrich_row(row, today)`.  
  - **Stages:** `compute_facts` → `compute_intelligence` → `compute_sla_breaches`; then `wd_summary`, `assign_display`, and `score_enriched_turnover`.  
  - **Lifecycle/phase:** `compute_facts` uses `effective_move_out_date(row)` (from `domain/lifecycle`) and `derive_phase(t, today)`. `derive_phase` uses `move_out_date` from the row; if `move_out is None`, returns NOTICE_SMI or NOTICE; otherwise calls `derive_lifecycle_phase(...)`. N/V/M and phase labels come from `derive_phase` and `_derive_nvm_short(phase)`.

- **Lifecycle derivation:**  
  - **File:** `domain/lifecycle.py`.  
  - **Functions:** `effective_move_out_date(row)`, `derive_lifecycle_phase(...)`, `derive_nvm(phase)`.  
  - **Usage:** Enrichment uses these to set `dv`, `phase`, `nvm`, and related flags (is_vacant, is_smi, etc.).

- **Rendering:**  
  - **Files:** `ui/screens/board.py`, `ui/screens/flag_bridge.py`, `ui/screens/risk_radar.py`, `ui/components/sidebar_flags.py`.  
  - **Behavior:** Board screen builds pandas DataFrames from the list of enriched rows and renders with `st.data_editor` / metrics; Flag Bridge and sidebar filter/sort and render subsets; Risk Radar adds risk columns and sorts. No separate “rendering” service; rendering is in the UI layer using the enriched row dicts.

### 3.2 How units are selected for display

- Units are **not** selected directly. The board loads **open turnovers** first (`list_open_turnovers` by phase_ids or property_ids). Then it loads **units** (and tasks, notes) for those turnover_ids. So “units” on the board are exactly those that have an associated open turnover for the chosen property/phase. Selection is thus **by turnover**, then by unit_id from the turnover.

### 3.3 Whether the board queries turnovers or units directly

- The board **queries turnovers first** via `repository.list_open_turnovers(conn, phase_ids=...)` or `list_open_turnovers(conn, property_ids=...)`. Units (and tasks, notes) are then batch-fetched by the unit_ids and turnover_ids from those turnovers. So the primary query is over turnovers; units are joined in for display and enrichment.

### 3.4 How lifecycle phase and N/V/M state are attached to rows

- **Flat row:** `_build_flat_row` in `board_query_service.py` copies turnover fields (including `move_out_date`, `move_in_date`, etc.) and task/note data into a single dict per turnover.  
- **Enrichment:** For each row, either a cached enrichment payload is applied (`get_enrichment_cache_for_turnover_ids` / `upsert_turnover_enrichment_cache`) or `enrichment.enrich_row(row, today)` is called.  
- **Phase and N/V/M:** Inside `enrich_row` → `compute_facts`: `effective_move_out_date(row)` and `derive_phase(t, today)` are used; `derive_phase` uses the row’s move_out/move_in and closed/canceled state and calls `domain.lifecycle.derive_lifecycle_phase`. The result is stored as `row["phase"]`; `_derive_nvm_short(phase)` sets `row["nvm"]` (N/V/M). So lifecycle phase and N/V/M are **derived at enrichment time** (or from cache) and attached as keys on the same row dict that is used for display.

---

## 4. Data Flow Summary

High-level lifecycle with file paths:

1. **Report import**  
   - **Entry:** UI Admin → Import → `apply_import_row_workflow` (e.g. `ApplyImportRow`) → `services/import_service.py` (`import_report_file`).  
   - **Orchestrator:** `services/imports/orchestrator.py` (`import_report_file`): validate, parse by report type, then call report-specific apply (e.g. `apply_move_outs`).

2. **Turnover creation/update**  
   - **MOVE_OUTS (create):** `services/imports/move_outs.py` → `apply_move_outs` → for new turnover: `db/repository/turnovers.py` (`insert_turnover`).  
   - **Manual (create):** `application/workflows/write_workflows.py` (`create_turnover_workflow`) → `services/manual_availability_service.py` (`add_manual_availability`) → `services/turnover_service.py` (`create_turnover_and_reconcile`) → `db/repository/turnovers.py` (`insert_turnover`).  
   - **Other reports:** Same orchestrator → `apply_pending_move_ins`, `apply_available_units`, `apply_pending_fas`, `apply_dmrb` → only `repository.update_turnover_fields` (no insert).

3. **Task instantiation**  
   - **After MOVE_OUTS create:** `services/imports/move_outs.py` → `_instantiate_tasks_for_turnover_impl` (from `services/imports/tasks.py`).  
   - **After manual create:** `services/turnover_service.py` (`create_turnover_and_reconcile`) → `services/import_service.instantiate_tasks_for_turnover` → `services/imports/tasks.py` (`_instantiate_tasks_for_turnover_impl`).  
   - **Backfill:** `app.py` → `turnover_service.reconcile_missing_tasks` → same `instantiate_tasks_for_turnover` for open turnovers with zero tasks.

4. **Lifecycle derivation**  
   - **Domain:** `domain/lifecycle.py` (`effective_move_out_date`, `derive_lifecycle_phase`, `derive_nvm`).  
   - **Enrichment:** `domain/enrichment.py` (`enrich_row` → `compute_facts` → `compute_intelligence` → `compute_sla_breaches`; uses lifecycle for phase/nvm and SLA/risk helpers).

5. **Board display**  
   - **Query:** `services/board_query_service.py` (`get_dmrb_board_rows`, `get_flag_bridge_rows`, `get_risk_radar_rows`, `get_turnover_detail`).  
   - **UI/cache:** `ui/data/cache.py` (`cached_get_dmrb_board_rows`, etc.) → `ui/screens/board.py`, `ui/screens/flag_bridge.py`, `ui/components/sidebar_flags.py`, `ui/screens/risk_radar.py`, turnover detail.

---

## 5. Guardrail Insertion Points

Rule to enforce: **A turnover should not become operational until move_out_date exists.**

Possible interception layers and pros/risks:

| Layer | File(s) / area | Pros | Risks |
|-------|----------------|------|------|
| **Import pipelines** | `services/imports/move_outs.py` (and optionally orchestrator) | Single place for MOVE_OUTS; already skips rows with missing move-out; easy to add “staging” or queue for missing move-out rows. | Only affects import; manual path and backfill are separate. |
| **Turnover creation logic** | `db/repository/turnovers.py` (`insert_turnover`), or `services/turnover_service.py` (`create_turnover_and_reconcile`), or `services/manual_availability_service.py` | DB/repo: enforces for all callers. Service layer: can block or redirect to “pending” state before insert. | Repo: schema currently NOT NULL; changing to allow NULL would require migration and all callers to handle “pending” state. Service: need to define what “not operational” means (e.g. not in list_open_turnovers until move_out_date set). |
| **Task instantiation logic** | `services/imports/tasks.py` (`_instantiate_tasks_for_turnover_impl` or `instantiate_tasks_for_turnover`) | Prevents tasks for turnovers without move_out_date. Good for “no work until date set.” | Backfill (`reconcile_missing_tasks`) would need to skip turnovers without move_out_date; otherwise inconsistent with “instantiate right after create.” If creation already requires move_out_date, this is a safety net only. |
| **Lifecycle enrichment** | `domain/enrichment.py` (`derive_phase`, `compute_facts`) | Already handles move_out None for display. Could add an explicit “pending move-out” state or badge. | Does not prevent creation or task creation; only affects how rows are labeled. Useful for visibility, not for blocking. |
| **Board query filtering** | `services/board_query_service.py` (`get_dmrb_board_rows`), or `db/repository/turnovers.py` (`list_open_turnovers`) | Hiding “no move_out_date” from the main board is easy (filter in query or after load). | Turnovers would still exist and have tasks; they would just be invisible on the main board. Need a dedicated “Missing Move-Out” or exception queue view; otherwise operators cannot see or fix them. |

**Suggested focus for design (no implementation):**

- **Pre-turn guardrail:** Enforce at **creation** (so no open turnover is created without move_out_date) and/or at **task instantiation** (no tasks until move_out_date exists). The safest single point that covers both import and manual is either (a) keeping the current contract and adding an explicit check in both `apply_move_outs` and `create_turnover_and_reconcile` before insert, or (b) introducing a “pending” turnover state (e.g. move_out_date NULL allowed, excluded from `list_open_turnovers`) and only promoting to “operational” when move_out_date is set—which would require schema and multiple call sites to change.
- **Missing Move-Out exception queue:** Can be implemented by (1) a **filter** in the board (or a dedicated view) that shows only open turnovers where effective move_out_date is null, and (2) optionally a **staging path** in MOVE_OUTS import that creates a placeholder or queue entry for rows with missing move-out instead of skipping them, so they can be completed later. The board query / list_open_turnovers layer is the right place to **define** “operational” (e.g. exclude null move_out_date from main board and expose them in an exception list).

---

*End of Lifecycle Control Points Analysis. No code was modified.*
