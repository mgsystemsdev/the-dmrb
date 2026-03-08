# UI Design Plan v2 vs Backend — Compatibility Analysis

Systematic comparison of every UI column, action, enrichment pipeline stage, and
page against the actual backend (schema, repository, services, domain engines).

**Verdict format:** ✅ Ready | ⚠️ Partial (works with caveats) | ❌ Gap (needs backend work)

---

## 1. DMRB Board Columns — Field-by-Field

### 1.1 Identity & Dates

| UI Column | Backend Source | Verdict | Notes |
|-----------|---------------|---------|-------|
| **Unit** | `unit.unit_code_raw` | ⚠️ Partial | Schema has the field. **But** `repository.py` has no `get_unit_by_id(conn, unit_id)`. Only `get_unit_by_norm`. To display unit_code for a turnover, you need to look up by unit_id. **Gap: add `get_unit_by_id`.** |
| **Status** | `turnover.manual_ready_status` | ✅ Ready | Schema CHECK allows `'Vacant ready', 'Vacant not ready', 'On notice'` — matches UI options exactly. `turnover_service.set_manual_ready_status` exists. |
| **Move-Out** | `turnover.move_out_date` | ✅ Ready | TEXT ISO date, NOT NULL. Stored and queryable. |
| **Ready** | `turnover.report_ready_date` | ✅ Ready | Added via migration `001_add_report_ready_date.sql`. Import service writes it. |
| **Move-In** | `turnover.move_in_date` | ✅ Ready | Nullable TEXT. Import PENDING_MOVE_INS writes it. |
| **P** | `unit.property_id` | ✅ Ready | Integer. Available on unit row and turnover row. |
| **B** (Building) | Parsed from `unit.unit_code_raw` | ✅ Ready | No dedicated column — parsed at display time (e.g., `"5-18-0206"` → B=`"18"`). Pure UI logic, no backend needed. |
| **U** (Unit #) | Parsed from `unit.unit_code_raw` | ✅ Ready | Same as B — parse at display time. |

### 1.2 Computed Columns

| UI Column | Computation | Verdict | Notes |
|-----------|-------------|---------|-------|
| **DV** (Days Vacant) | `business_days(move_out_date, today)` | ✅ Ready | Pure computation from `move_out_date` (available in schema). Uses `numpy.busday_count` or equivalent. No backend storage needed. |
| **DTBR** (Days To Be Ready) | `business_days(today, move_in_date)` | ✅ Ready | Pure computation from `move_in_date`. Same approach. |
| **N/V/M** | Derived from lifecycle phase | ⚠️ Partial | Backend has `domain.lifecycle.derive_lifecycle_phase()` which returns NOTICE, VACANT, SMI, etc. UI plan maps these to N/V/M. **However**, the Excel pipeline derives N/V/M from the raw `N/V/M` column in the spreadsheet, while the backend derives phase from dates. The mapping is compatible but not identical — backend phase `NOTICE_SMI` has no direct Excel equivalent. **Resolution:** N/V/M = map from `derive_lifecycle_phase()` output. Works, but lifecycle.py returns 8 phases; the Excel has 3 buckets (N/V/M). The UI plan's `derive_nvm()` function handles this mapping correctly. |
| **Alert** (Attention Badge) | Operational State → Badge | ❌ Gap | This is the **biggest gap**. The backend has NO concept of Operational State or Attention Badge. These come entirely from the Excel Intelligence Engine (Stage 2). The backend has `risk_engine.evaluate_risks()` and `sla_engine.evaluate_sla_state()`, but neither produces `Operational_State` or `Attention_Badge`. **Must be implemented as pure UI-layer computation** in the mock data layer (and later as a new domain function). See §4 for full analysis. |

### 1.3 Task Columns (Insp, Paint, MR, HK, CC, QC)

| UI Column | Backend Source | Verdict | Notes |
|-----------|---------------|---------|-------|
| **Insp** | `task` WHERE `task_type = 'Insp'` | ⚠️ Partial | Schema supports any `task_type TEXT`. **But** the current system uses `task_template` to define which task types exist per property. No templates for "Insp", "MR", "HK" exist yet. The import service instantiates tasks from templates. **Gap: seed `task_template` rows for Insp/Paint/MR/HK/CC/QC with correct sort_order.** |
| **Paint** | `task` WHERE `task_type = 'Paint'` | ⚠️ Partial | Same as Insp. Template seeding needed. |
| **MR** | `task` WHERE `task_type = 'MR'` | ⚠️ Partial | Same. |
| **HK** | `task` WHERE `task_type = 'HK'` | ⚠️ Partial | Same. |
| **CC** | `task` WHERE `task_type = 'CC'` | ⚠️ Partial | Same. |
| **QC** | `task` WHERE `task_type = 'QC'` | ⚠️ Partial | Same. Additionally, the UI shows QC as `confirmation_status` (Pending/Confirmed/Rejected/Waived), while Insp–CC show `execution_status`. Backend supports both fields on every task row — this distinction is purely UI-layer. |

**Task execution_status values:**
- UI plan: `["—", "Not Started", "Scheduled", "In Progress", "Done", "N/A", "Canceled"]`
- Schema CHECK: `('NOT_STARTED', 'SCHEDULED', 'IN_PROGRESS', 'VENDOR_COMPLETED', 'NA', 'CANCELED')`
- ✅ **Compatible.** UI label map works: Done → VENDOR_COMPLETED, N/A → NA, etc.

**Task confirmation_status values:**
- UI plan: `["Pending", "Confirmed", "Rejected", "Waived"]`
- Schema CHECK: `('PENDING', 'CONFIRMED', 'REJECTED', 'WAIVED')`
- ✅ **Compatible.**

**Task date + status dual columns (Excel: `Insp` date + `Insp_status`):**
- Backend stores `vendor_due_date`, `vendor_completed_at`, `scheduled_date` per task.
- The Excel "Insp" date column maps to `vendor_completed_at` (when done) or `vendor_due_date` (when scheduled).
- ✅ **Compatible** — the backend has the date fields; UI just needs to pick the right one to display.

### 1.4 Other Columns

| UI Column | Backend Source | Verdict | Notes |
|-----------|---------------|---------|-------|
| **Assign** | `turnover.assignee` | ❌ Gap | **No `assignee` column in the turnover table.** The schema has no assignee field. The mock data has `assignee` as a mock-only key. **Must add `assignee TEXT` column to turnover table** (schema migration + repository update cols). |
| **W/D** | `turnover.wd_present`, `wd_supervisor_notified`, `wd_installed` | ✅ Ready | All three boolean fields exist in schema. `turnover_service.update_wd_panel` handles updates. UI derives icon (✅/⚠/—) from these — pure display logic. |
| **Notes** | `note` table | ⚠️ Partial | Schema has `note` table with `turnover_id`, `description`, `blocking`, `severity`, `resolved_at`. **But** repository.py has **no note query functions** — no `get_notes_by_turnover`, `insert_note`, `resolve_note`. **Gap: add note CRUD to repository.** |
| **▶** (Open detail) | Navigation | ✅ Ready | Pure UI — sets `session_state.selected_turnover_id`. |

---

## 2. Flag Bridge — Breach Flags

### 2.1 The Four SLA Flags vs Backend

| UI Breach Flag | Backend Equivalent | Verdict | Notes |
|----------------|-------------------|---------|-------|
| **Inspection_SLA_Breach** | *None* | ❌ Gap | The backend has **no concept** of Inspection SLA breach. `risk_engine.evaluate_risks()` does not check whether inspection was done within 1 business day. `sla_engine.evaluate_sla_state()` only checks the global 10-day SLA. **This is an Excel-only computation.** Must be implemented as UI-layer logic or added to risk_engine. |
| **SLA_Breach** | `sla_engine.evaluate_sla_state()` + `risk_flag` table (`SLA_BREACH`) | ⚠️ Partial | The backend SLA breach is: `today - move_out_date > 10 days AND manual_ready_confirmed_at IS NULL`. The Excel SLA_Breach is: `Vacant + not ready + aging > 10 biz days`. **Difference:** backend uses calendar days (timedelta > 10), Excel uses **business days** (numpy.busday_count > 10). Backend doesn't check `Is_Unit_Ready` (task completion); it only checks `manual_ready_confirmed_at`. These are semantically different — the backend breach closes when the manager confirms ready, the Excel breach closes when all tasks are actually done. **Resolution:** For the UI prototype (mock data), use the Excel definition. When wiring, either (a) add business-day SLA to domain, or (b) accept the calendar-day difference. |
| **SLA_MoveIn_Breach** | `risk_engine.evaluate_risks()` → `QC_RISK` (partial) | ⚠️ Partial | The Excel definition: `Has move-in + not ready for moving + ≤ 2 days to move-in`. The backend `QC_RISK` is: `move-in ≤ 3 days + QC not confirmed`. These overlap but are NOT the same. QC_RISK only checks QC task, not full readiness. SLA_MoveIn_Breach checks full readiness (`Is_Unit_Ready_For_Moving`). **Resolution:** Implement SLA_MoveIn_Breach as UI-layer computation — it requires `Is_Unit_Ready_For_Moving` which the backend doesn't compute. |
| **Plan_Breach** | `risk_engine.evaluate_risks()` → `EXPOSURE_RISK` (close match) | ⚠️ Partial | Excel Plan_Breach: `Ready_Date passed + not actually ready`. Backend EXPOSURE_RISK: `report_ready_date passed + manual_ready_confirmed_at IS NULL`. **Difference:** Excel checks `Is_Unit_Ready` (all tasks done + status = Vacant Ready). Backend checks only `manual_ready_confirmed_at`. A unit could have EXPOSURE_RISK resolved (manager confirmed) but Plan_Breach still active (tasks not done). **Resolution:** For UI prototype, use the Excel Plan_Breach definition. The backend EXPOSURE_RISK is a related but different signal. |

### 2.2 Backend Risk Types NOT in Flag Bridge

The backend `risk_engine.evaluate_risks()` produces these risk types that the Flag Bridge does NOT show:

| Backend Risk Type | In Flag Bridge? | In UI at all? |
|-------------------|-----------------|---------------|
| `QC_RISK` | No (folded into Attention Badge as "QC Hold") | Yes — Detail view risks panel |
| `WD_RISK` | No (folded into W/D column icon) | Yes — Detail view risks + WD panel |
| `CONFIRMATION_BACKLOG` | No | Yes — could be a metric or Detail risks |
| `EXECUTION_OVERDUE` | No | Yes — Detail view risks panel |
| `DATA_INTEGRITY` | No | Yes — Import conflicts |
| `DUPLICATE_OPEN_TURNOVER` | No | Yes — Import conflicts |
| `EXPOSURE_RISK` | No (related to Plan_Breach but different) | Partially — Detail view risks |

**This is by design.** The Flag Bridge shows the 4 **SLA breach flags** from the Excel pipeline. The backend risk_flag system covers a broader set. Both systems can coexist — the Flag Bridge uses the Excel SLA definitions, the Detail view shows the backend risk_flags.

### 2.3 EXPOSURE_RISK Schema Constraint

| Issue | Verdict |
|-------|---------|
| `risk_engine.py` emits `EXPOSURE_RISK` | ❌ Gap |
| `schema.sql` CHECK: `risk_type IN ('SLA_BREACH', 'QC_RISK', 'WD_RISK', 'CONFIRMATION_BACKLOG', 'EXECUTION_OVERDUE', 'DATA_INTEGRITY', 'DUPLICATE_OPEN_TURNOVER')` | Does NOT include `EXPOSURE_RISK` |
| `risk_service.reconcile_risks_for_turnover()` calls `evaluate_risks()` which returns `EXPOSURE_RISK` | INSERT will fail with CHECK constraint violation |

**Fix needed:** Schema migration to add `'EXPOSURE_RISK'` to the `risk_flag.risk_type` CHECK constraint.

---

## 3. Enrichment Pipeline vs Backend Domain

### 3.1 Stage 1 (Fact Engine) — What the backend covers

| Enrichment Field | Backend Coverage | Verdict |
|------------------|-----------------|---------|
| `Aging_Business_Days` | No built-in business day calc | ❌ Gap — backend uses calendar days everywhere. UI must compute business days independently. |
| `Is_Vacant` / `Is_SMI` / `Is_On_Notice` | `lifecycle.derive_lifecycle_phase()` returns VACANT, SMI, NOTICE, etc. | ✅ Ready — derive from lifecycle phase, then map. |
| `Is_MoveIn_Present` | `turnover.move_in_date IS NOT NULL` | ✅ Ready |
| `Is_Ready_Declared` | `turnover.report_ready_date IS NOT NULL` | ✅ Ready |
| `Is_QC_Done` | `task.confirmation_status == 'CONFIRMED'` WHERE `task_type = 'QC'` | ✅ Ready |
| `Has_Assignment` | `turnover.assignee` | ❌ Gap — no assignee column |
| `Note_Category` | `note.description` + pattern extraction | ⚠️ Partial — note table exists but no repo functions. Category extraction is UI-layer logic. |
| `Task_State` | Computed from all task execution_statuses | ✅ Ready — can be computed from `task` rows: all VENDOR_COMPLETED = "All Tasks Complete", all NOT_STARTED = "Not Started", else "In Progress". |
| `Task_Completion_Ratio` | Count tasks with `execution_status = 'VENDOR_COMPLETED'` / total | ✅ Ready |
| `Table_Current_Task` / `Table_Next_Task` | First task in sequence not VENDOR_COMPLETED | ✅ Ready — requires knowing task sort order. `task_template.sort_order` provides this. |
| `Is_Task_Stalled` | Vacant + task not done + aging > expected days | ⚠️ Partial — backend has no task stall concept. The expected-days-per-task constants (Insp=1, Paint=2, MR=3, HK=6, CC=7) exist only in the Excel code. **Must be hardcoded in UI layer or added to task_template as a new column.** |

### 3.2 Stage 2 (Intelligence Engine) — NOT in backend

| Enrichment Field | Backend Coverage | Verdict |
|------------------|-----------------|---------|
| `Status_Norm` | Trivial lowercase — UI layer | ✅ Ready |
| `Is_Unit_Ready` | Status == "Vacant Ready" AND all tasks done | ❌ Gap — backend has no single "unit ready" computation. `manual_ready_confirmed_at` is the closest signal, but it's manager-asserted, not task-computed. **Must be UI-layer computation.** |
| `Is_Unit_Ready_For_Moving` | Ready + has move-in + QC done | ❌ Gap — same, UI-layer. |
| `In_Turn_Execution` | Vacant + not ready | ❌ Gap — UI-layer. |
| `Operational_State` | Full state machine (8 states) | ❌ Gap — **entirely missing from backend.** The backend has no concept of "Move-In Risk", "QC Hold", "Work Stalled", "Pending Start", "Apartment Ready". This is the Excel intelligence engine's core value-add. **Must be implemented as UI-layer domain function.** |
| `Prevention_Risk_Flag` | In execution + has hold/no assignment/etc. | ❌ Gap — UI-layer. |
| `Attention_Badge` | Emoji badge from Operational State | ❌ Gap — UI-layer. |

### 3.3 Stage 3 (SLA Engine) — Partial backend coverage

| Enrichment Field | Backend Coverage | Verdict |
|------------------|-----------------|---------|
| `Days_To_MoveIn` | `(move_in_date - today).days` | ✅ Ready — trivial computation. |
| `Inspection_SLA_Breach` | Not in backend | ❌ Gap — UI-layer computation. |
| `SLA_Breach` | `sla_engine.evaluate_sla_state()` (calendar days, not business days) | ⚠️ Partial — different definition. |
| `SLA_MoveIn_Breach` | Partially covered by QC_RISK (different scope) | ❌ Gap — UI-layer computation. |
| `Plan_Breach` | Partially covered by EXPOSURE_RISK (different scope) | ⚠️ Partial — related but different trigger. |

---

## 4. Service Layer Coverage for UI Actions

### 4.1 Inline Edit Actions

| UI Action | Service Call | Verdict | Notes |
|-----------|-------------|---------|-------|
| Change Status dropdown | `turnover_service.set_manual_ready_status()` | ✅ Ready | Exists, audits, reconciles risks. |
| Change task exec status (Insp/Paint/MR/HK/CC) | `task_service.mark_vendor_completed()` for Done; `repository.update_task_fields()` for others | ⚠️ Partial | `mark_vendor_completed` only handles the Done transition (sets VENDOR_COMPLETED + timestamps). For other transitions (Not Started → Scheduled → In Progress), only raw `update_task_fields` exists — **no service function, no audit trail, no risk reconciliation.** |
| Change QC confirmation | `task_service.confirm_task()` / `reject_task()` | ⚠️ Partial | `confirm_task` and `reject_task` exist. But `reject_task` requires current state == CONFIRMED (can't reject from PENDING). No service for setting WAIVED. No service for going from CONFIRMED → PENDING. **Gap: need `set_task_execution_status` and `set_task_confirmation_status` general-purpose service functions.** |
| Confirm QC (one-click) | `task_service.confirm_task()` | ⚠️ Partial | Works only if `execution_status == 'VENDOR_COMPLETED'`. If QC task isn't vendor-completed, confirm fails. UI must handle this constraint. |

### 4.2 Detail Page Actions

| UI Action | Service Call | Verdict | Notes |
|-----------|-------------|---------|-------|
| Mark WD Notified | `turnover_service.update_wd_panel(wd_supervisor_notified=True)` | ✅ Ready | |
| Mark WD Installed | `turnover_service.update_wd_panel()` | ⚠️ Partial | `update_wd_panel` accepts `wd_present` and `wd_supervisor_notified` but NOT `wd_installed`. **Gap: add `wd_installed` support to `update_wd_panel`.** The field exists in schema and in TURNOVER_UPDATE_COLS, but the service function doesn't handle it. |
| Resolve Note | Note repository | ❌ Gap | No `resolve_note` or `update_note_resolved_at` in repository. No note_service. |
| Create Note | Note repository | ❌ Gap | No `insert_note` in repository. |
| Back button | UI navigation | ✅ Ready | |

### 4.3 Risk Reconciliation After Task Changes

| Scenario | Current Behavior | Verdict |
|----------|-----------------|---------|
| After `set_manual_ready_status` | `turnover_service` calls `reconcile_risks_for_turnover` | ✅ Ready |
| After `confirm_manual_ready` | `turnover_service` calls both `reconcile_sla` and `reconcile_risks` | ✅ Ready |
| After `update_wd_panel` | `turnover_service` calls `reconcile_risks` | ✅ Ready |
| After `mark_vendor_completed` | `task_service` does NOT call `reconcile_risks` | ❌ Gap |
| After `confirm_task` | `task_service` does NOT call `reconcile_risks` | ❌ Gap |
| After `reject_task` | `task_service` does NOT call `reconcile_risks` | ❌ Gap |

**Impact:** After any task status change, risk flags (QC_RISK, CONFIRMATION_BACKLOG, EXECUTION_OVERDUE) won't auto-update until the next turnover-level action.

**Fix options:**
1. Add `reconcile_risks` calls to `task_service` functions (requires task_service to depend on risk_service — currently doesn't).
2. Have the UI call `risk_service.reconcile_risks_for_turnover()` after every task action (requires UI to build the args that turnover_service currently builds internally).
3. Create a new `turnover_service.reconcile_after_task_change(turnover_id)` wrapper.

---

## 5. Repository Layer Gaps

| Missing Function | Needed By | Priority |
|------------------|-----------|----------|
| `get_unit_by_id(conn, unit_id)` | Dashboard: show unit_code for each turnover | **Critical** |
| `get_notes_by_turnover(conn, turnover_id)` | Detail: notes panel; DMRB Board: Notes column | **Critical** |
| `insert_note(conn, data)` | Detail: create note | High |
| `resolve_note(conn, note_id, resolved_at)` | Detail: resolve note | High |
| `get_import_rows_with_conflicts(conn, limit)` | Import: conflict viewer | Medium |
| `get_import_batches_recent(conn, limit)` | Import: history | Low |
| Batch query: `get_units_by_ids(conn, unit_ids)` | Dashboard: avoid N+1 | Medium |
| Batch query: `get_all_tasks_for_turnover_ids(conn, ids)` | Dashboard: avoid N+1 | Medium |
| Batch query: `get_all_risks_for_turnover_ids(conn, ids)` | Dashboard: avoid N+1 | Medium |

---

## 6. Schema Gaps

| Gap | Table | Fix |
|-----|-------|-----|
| No `assignee` column | `turnover` | `ALTER TABLE turnover ADD COLUMN assignee TEXT;` |
| `EXPOSURE_RISK` not in CHECK | `risk_flag` | Recreate table or add `EXPOSURE_RISK` to the CHECK. SQLite doesn't support `ALTER TABLE ... ALTER CONSTRAINT`, so this requires table recreation in a migration. |
| No `expected_business_days` on task_template | `task_template` | Optional: `ALTER TABLE task_template ADD COLUMN expected_business_days INTEGER;` — for task stall detection. Alternative: hardcode in UI layer. |

---

## 7. Two Divergent Risk/Breach Systems

This is the most important architectural finding. The UI plan merges two different systems:

### System A: Backend Risk Engine (risk_flag table)

- **Stored in DB** as `risk_flag` rows with `risk_type` and `severity`
- **Risk types:** SLA_BREACH, QC_RISK, WD_RISK, CONFIRMATION_BACKLOG, EXECUTION_OVERDUE, DATA_INTEGRITY, DUPLICATE_OPEN_TURNOVER, EXPOSURE_RISK
- **Lifecycle:** Auto-resolve when predicate becomes false; upsert/resolve pattern
- **Uses calendar days** for all thresholds
- **SLA definition:** `today - move_out_date > 10 calendar days AND manual_ready_confirmed_at IS NULL`
- **Does NOT compute:** Is_Unit_Ready, Operational_State, Task_Stalled, business days

### System B: Excel Enrichment Pipeline (UI-layer computation)

- **Not stored** — computed on every render from base data
- **Breach flags:** Inspection_SLA_Breach, SLA_Breach, SLA_MoveIn_Breach, Plan_Breach
- **Intelligence:** Operational_State, Attention_Badge, Is_Unit_Ready, Prevention_Risk_Flag
- **Uses business days** for all thresholds
- **SLA definition:** `business_days(move_out, today) > 10 AND NOT Is_Unit_Ready`
- **Computes:** Full task pipeline state, stall detection, readiness assessment

### How They Coexist

For the **prototype** (mock data, no backend):
- All computation is UI-layer. No conflict. Implement the Excel pipeline logic.

For **wired mode** (real backend):
- **Flag Bridge** uses System B (Excel SLA breach definitions, computed at render time)
- **Detail view risks panel** uses System A (backend risk_flag rows)
- **Attention Badge** uses System B (Operational State, computed at render time)
- **Risk reconciliation after edits** uses System A (backend risk_service)

This means the UI will compute breach flags independently of the backend risk_flag table. The backend risk_flags are authoritative for audit/history/resolution tracking. The Excel-derived breach flags are authoritative for the Flag Bridge display. They answer slightly different questions:

- Backend: "Does this turnover have an active risk that needs attention?" (audit trail)
- Excel: "Is this turnover in SLA breach right now?" (operational display)

**Recommendation:** Accept the dual system. The backend risk_flag system is needed for audit, persistence, and auto-resolution. The Excel-derived breaches are needed for the Flag Bridge display. They're complementary. Don't try to merge them — they serve different purposes.

---

## 8. Filter Compatibility

| UI Filter | Backend Support | Verdict |
|-----------|----------------|---------|
| Search unit | `unit.unit_code_raw` / `unit_code_norm` LIKE | ✅ Ready — `get_unit_by_norm` exists; for substring search, add `WHERE unit_code_norm LIKE ?`. |
| Phase (P = 5/7/8) | `unit.property_id` or `turnover.property_id` | ✅ Ready |
| Status (VR/VNR/ON) | `turnover.manual_ready_status` | ✅ Ready |
| N/V/M | Derived from lifecycle phase | ✅ Ready — compute in UI layer. |
| Assign | `turnover.assignee` | ❌ Gap — column doesn't exist. |
| QC (Done/Not Done) | `task.confirmation_status WHERE task_type='QC'` | ✅ Ready — query per turnover. |
| Flag Bridge breach filter | Computed breach flags | ✅ Ready — UI-layer computation on each row. |

---

## 9. Import Page Compatibility

| Feature | Backend Support | Verdict |
|---------|----------------|---------|
| File upload | `import_service.import_report_file()` | ✅ Ready |
| Report type selection | Constants: MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS, DMRB | ✅ Ready |
| Run import | `import_service.import_report_file()` returns result dict | ✅ Ready |
| Summary display | Result dict: status, applied_count, conflict_count, invalid_count | ✅ Ready |
| Conflict list | `import_row` table with `conflict_flag` | ⚠️ Partial — table exists, **but no repository function to query conflicts.** Gap: add `get_import_rows_with_conflicts`. |

---

## 10. Summary: All Gaps Ranked by Priority

### Critical (blocks wiring to backend)

| # | Gap | Location | Fix |
|---|-----|----------|-----|
| 1 | **No `get_unit_by_id`** | `repository.py` | Add 3-line function |
| 2 | **No `assignee` column** | `turnover` schema | Migration: ADD COLUMN |
| 3 | **EXPOSURE_RISK not in CHECK** | `risk_flag` schema | Migration: recreate table with updated CHECK |
| 4 | **No note CRUD** | `repository.py` | Add `get_notes_by_turnover`, `insert_note`, `resolve_note` |
| 5 | **No risk reconciliation after task changes** | `task_service.py` | Add reconcile_risks calls or wrapper |

### High (needed for full functionality)

| # | Gap | Location | Fix |
|---|-----|----------|-----|
| 6 | **No general `set_task_execution_status` service** | `task_service.py` | Add service function covering all transitions with audit |
| 7 | **`update_wd_panel` missing `wd_installed`** | `turnover_service.py` | Add wd_installed handling (3 lines) |
| 8 | **No conflict query** | `repository.py` | Add `get_import_rows_with_conflicts` |
| 9 | **Task templates not seeded** for Insp/Paint/MR/HK/CC/QC | `task_template` data | Seed script or migration |

### Low (can defer; UI-layer workaround exists)

| # | Gap | Location | Fix |
|---|-----|----------|-----|
| 10 | Business days vs calendar days | Domain layer | Either accept difference or add business_days utility |
| 11 | Batch queries to avoid N+1 | `repository.py` | Add `get_units_by_ids`, `get_all_tasks_for_turnover_ids` |
| 12 | `expected_business_days` on task_template | Schema | Optional column or hardcode |

### Not a Gap (UI-layer only, by design)

| Item | Why it's not a gap |
|------|-------------------|
| Operational State / Attention Badge | Intentionally UI-layer computation, like the Excel Intelligence Engine |
| Inspection_SLA_Breach | Excel-derived breach, computed at render time |
| SLA_MoveIn_Breach | Excel-derived breach, computed at render time |
| Plan_Breach | Excel-derived breach (different from EXPOSURE_RISK, by design) |
| Is_Unit_Ready / Is_Task_Stalled / Prevention_Risk_Flag | Computed from base data at render time |
| DV / DTBR / N/V/M | Pure display computations |

---

## 11. Prototype Impact

For the **mock data prototype** (no backend), none of the gaps above matter.
All computation is UI-layer. The mock data provides the base fields, and the
enrichment pipeline runs as pure functions.

**When wiring to real backend**, address gaps #1–#9 in that order.
The dual breach system (§7) is intentional and doesn't need resolution.
