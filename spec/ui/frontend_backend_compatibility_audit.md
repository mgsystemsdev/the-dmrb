# Frontend–Backend Compatibility Audit

**Document Class:** Architectural Alignment Report & Schema Compatibility Audit  
**Date:** 2025-02-25  
**Scope:** Finalized frontend (`app_prototype_v2.py` + `mock_data_v2.py`) vs backend (`schema.sql`, `repository.py`, `domain/`, `services/`)  
**Objective:** Achieve 100% schema alignment before any integration/wiring work begins

---

## 1. Frontend–Backend Compatibility Assessment

### 1.1 Overall Compatibility Score

| Layer | Compatibility | Status |
|-------|--------------|--------|
| Schema ↔ Frontend Data Model | **~82%** | ⚠️ Gaps exist |
| Repository ↔ Frontend Operations | **~65%** | ❌ Multiple missing functions |
| Services ↔ Frontend Actions | **~70%** | ⚠️ Partial coverage |
| Domain ↔ Frontend Enrichment | **~50%** | ❌ Significant divergence (by design) |
| **Overall** | **~67%** | ❌ **Not ready for integration** |

**Integration must not proceed until all Critical and High gaps documented below are resolved.**

### 1.2 Entity-Level Compatibility Matrix

#### 1.2.1 `unit` Table

| Frontend Field | Schema Column | Status | Notes |
|----------------|---------------|--------|-------|
| `unit_id` | `unit_id` (PK) | ✅ Aligned | |
| `property_id` | `property_id` (FK) | ✅ Aligned | Used as Phase identifier (5, 7, 8) |
| `unit_code_raw` | `unit_code_raw` (TEXT) | ✅ Aligned | Format: `"5-1-101"` |
| `unit_code_norm` | `unit_code_norm` (TEXT) | ✅ Aligned | |
| `has_carpet` | `has_carpet` (BOOLEAN) | ✅ Aligned | |
| `has_wd_expected` | `has_wd_expected` (BOOLEAN) | ✅ Aligned | |
| `is_active` | `is_active` (BOOLEAN) | ✅ Aligned | |

**Verdict: ✅ 100% compatible. No changes needed.**

#### 1.2.2 `turnover` Table

| Frontend Field | Schema Column | Status | Notes |
|----------------|---------------|--------|-------|
| `turnover_id` | `turnover_id` (PK) | ✅ Aligned | |
| `unit_id` | `unit_id` (FK) | ✅ Aligned | |
| `property_id` | `property_id` (FK) | ✅ Aligned | |
| `move_out_date` | `move_out_date` (TEXT) | ✅ Aligned | Editable in detail via `st.date_input` |
| `move_in_date` | `move_in_date` (TEXT) | ✅ Aligned | Editable in detail via `st.date_input` |
| `report_ready_date` | `report_ready_date` (TEXT) | ✅ Aligned | Added via migration 001 |
| `manual_ready_status` | `manual_ready_status` (TEXT) | ✅ Aligned | CHECK matches frontend: `Vacant ready / Vacant not ready / On notice` |
| `manual_ready_confirmed_at` | `manual_ready_confirmed_at` (TEXT) | ✅ Aligned | Not directly exposed in UI, used for SLA |
| `wd_present` | `wd_present` (BOOLEAN) | ✅ Aligned | |
| `wd_supervisor_notified` | `wd_supervisor_notified` (BOOLEAN) | ✅ Aligned | |
| `wd_notified_at` | `wd_notified_at` (TEXT) | ✅ Aligned | |
| `wd_installed` | `wd_installed` (BOOLEAN) | ✅ Aligned | |
| `wd_installed_at` | `wd_installed_at` (TEXT) | ✅ Aligned | |
| `closed_at` | `closed_at` (TEXT) | ✅ Aligned | |
| `canceled_at` | `canceled_at` (TEXT) | ✅ Aligned | |
| **`wd_present_type`** | **—** | ❌ **GAP** | Frontend uses `"No" / "Yes" / "Yes stack"` dropdown. Schema only has boolean `wd_present`. Needs new column or encoding convention. |
| — | `source_turnover_key` | Not used | See §3 |
| — | `expedited_flag` | Not used | See §3 |
| — | `cancel_reason` | Not used | See §3 |
| — | `last_seen_moveout_batch_id` | Not used | See §3 |
| — | `missing_moveout_count` | Not used | See §3 |
| — | `created_at`, `updated_at` | Not used | See §3 |

**Verdict: ⚠️ One schema gap (`wd_present_type`). See §2.2 for required migration.**

#### 1.2.3 `task` Table

| Frontend Field | Schema Column | Status | Notes |
|----------------|---------------|--------|-------|
| `task_id` | `task_id` (PK) | ✅ Aligned | |
| `turnover_id` | `turnover_id` (FK) | ✅ Aligned | |
| `task_type` | `task_type` (TEXT) | ✅ Aligned | 9 types: Insp, CB, MRB, Paint, MR, HK, CC, FW, QC |
| `required` | `required` (BOOLEAN) | ✅ Aligned | Editable in detail via checkbox |
| `blocking` | `blocking` (BOOLEAN) | ✅ Aligned | |
| `vendor_due_date` | `vendor_due_date` (TEXT) | ✅ Aligned | Editable in detail via `st.date_input` |
| `vendor_completed_at` | `vendor_completed_at` (TEXT) | ✅ Aligned | |
| `manager_confirmed_at` | `manager_confirmed_at` (TEXT) | ✅ Aligned | |
| `execution_status` | `execution_status` (TEXT) | ✅ Aligned | CHECK values match frontend labels exactly |
| `confirmation_status` | `confirmation_status` (TEXT) | ✅ Aligned | CHECK values match frontend labels exactly |
| **`assignee`** | **—** | ❌ **CRITICAL GAP** | Frontend assigns per-task. Each task has an `assignee` field. Schema has no `assignee` column on `task`. |
| **`blocking_reason`** | **—** | ❌ **GAP** | Frontend has blocking reason dropdown per task (`"Not Blocking" / "Key Delivery" / "Vendor Delay" / "Parts on Order" / "Permit Required" / "Other"`). Schema only has boolean `blocking`. |
| — | `scheduled_date` | Not used | Frontend edits `vendor_due_date` directly; `scheduled_date` unused |

**Verdict: ❌ Two critical gaps (`assignee`, `blocking_reason`). See §2.2.**

#### 1.2.4 `note` Table

| Frontend Field | Schema Column | Status | Notes |
|----------------|---------------|--------|-------|
| `note_id` | `note_id` (PK) | ✅ Aligned | |
| `turnover_id` | `turnover_id` (FK) | ✅ Aligned | |
| `note_type` | `note_type` (TEXT) | ✅ Aligned | Frontend uses "blocking", "info" |
| `blocking` | `blocking` (BOOLEAN) | ✅ Aligned | |
| `severity` | `severity` (TEXT) | ✅ Aligned | Schema CHECK: INFO/WARNING/CRITICAL |
| `description` | `description` (TEXT) | ✅ Aligned | |
| `resolved_at` | `resolved_at` (TEXT) | ✅ Aligned | Frontend sets on "Resolve" button |
| — | `created_at` (TEXT) | ⚠️ Partial | Schema requires it (NOT NULL), frontend mock data doesn't provide it. Frontend must supply `created_at` on insert. |

**Verdict: ⚠️ Compatible with minor adjustment (supply `created_at` on note creation).**

#### 1.2.5 `risk_flag` Table

| Frontend Field | Schema Column | Status | Notes |
|----------------|---------------|--------|-------|
| `risk_id` | `risk_id` (PK) | ✅ Aligned | |
| `turnover_id` | `turnover_id` (FK) | ✅ Aligned | |
| `risk_type` | `risk_type` (TEXT) | ⚠️ Partial | Schema CHECK does not include `EXPOSURE_RISK`. See §2.2. |
| `severity` | `severity` (TEXT) | ✅ Aligned | |
| `triggered_at` | `triggered_at` (TEXT) | ✅ Aligned | |
| `resolved_at` | `resolved_at` (TEXT) | ✅ Aligned | |
| — | `auto_resolve` (BOOLEAN) | Not used | Frontend doesn't display this |

**Verdict: ⚠️ One CHECK constraint gap (`EXPOSURE_RISK`).**

### 1.3 Execution / Confirmation Status Value Alignment

| Domain | Frontend Labels | Schema CHECK Values | Mapping |
|--------|----------------|---------------------|---------|
| Execution | `"Not Started", "Scheduled", "In Progress", "Done", "N/A", "Canceled"` | `'NOT_STARTED', 'SCHEDULED', 'IN_PROGRESS', 'VENDOR_COMPLETED', 'NA', 'CANCELED'` | ✅ Exact 1:1 mapping via `EXEC_LABEL_TO_VALUE` |
| Confirmation | `"Pending", "Confirmed", "Rejected", "Waived"` | `'PENDING', 'CONFIRMED', 'REJECTED', 'WAIVED'` | ✅ Exact 1:1 mapping via `CONFIRM_LABEL_TO_VALUE` |
| Manual Status | `"Vacant ready", "Vacant not ready", "On notice"` | CHECK: same strings | ✅ Exact match |

### 1.4 Task Type Alignment

| Frontend `TASK_TYPES_ALL` | Template Required? | Notes |
|--------------------------|-------------------|-------|
| `Insp` | ❌ No template row | Must seed `task_template` |
| `CB` | ❌ No template row | Must seed `task_template` |
| `MRB` | ❌ No template row | Must seed `task_template` |
| `Paint` | ❌ No template row | Must seed `task_template` |
| `MR` | ❌ No template row | Must seed `task_template` |
| `HK` | ❌ No template row | Must seed `task_template` |
| `CC` | ❌ No template row | Must seed `task_template` |
| `FW` | ❌ No template row | Must seed `task_template` |
| `QC` | ❌ No template row | Must seed `task_template` |

**All 9 task types need `task_template` rows seeded** with correct `sort_order`, `required`, `blocking`, and `applies_if_*` filters to match frontend `DEFAULT_TASK_ASSIGNEES` and `TASK_TYPES_SEQUENCE`.

---

## 2. Schema & Database Adjustments

### 2.1 Elements to Remove or Deprecate

No schema columns need to be removed. All existing schema elements serve a purpose in the backend lifecycle (import reconciliation, audit, SLA). However, the following are **not surfaced in the frontend** and should be documented as backend-only:

| Schema Element | Reason Not in Frontend | Action |
|---------------|----------------------|--------|
| `turnover.source_turnover_key` | Import-internal identifier | Keep — used by import_service for idempotency |
| `turnover.expedited_flag` | Not in any frontend view | **Evaluate:** Either add UI toggle or deprecate |
| `turnover.cancel_reason` | Frontend has no cancellation flow | Keep — used by auto-cancel in import_service |
| `turnover.last_seen_moveout_batch_id` | Import tracking | Keep — backend-only |
| `turnover.missing_moveout_count` | Import disappearance tracking | Keep — backend-only |
| `turnover.created_at`, `updated_at` | Backend audit timestamps | Keep — required for INSERT |
| `task.scheduled_date` | Frontend uses `vendor_due_date` only | **Evaluate:** Merge semantics or keep both |
| `turnover_task_override` table | Not used by frontend or any service | **Candidate for removal** — entire table is unused |

### 2.2 Elements to Add or Modify

#### CRITICAL — Blocks integration

| # | Change | Table | Migration SQL | Rationale |
|---|--------|-------|--------------|-----------|
| 1 | **Add `assignee` column** | `task` | `ALTER TABLE task ADD COLUMN assignee TEXT;` | Frontend assigns per-task (Detail: assignee selectbox per task row; DMRB Board: "Assignee" column = MR task assignee). This is per-task, NOT per-turnover. |
| 2 | **Add `blocking_reason` column** | `task` | `ALTER TABLE task ADD COLUMN blocking_reason TEXT;` | Frontend has blocking reason dropdown: `"Not Blocking" / "Key Delivery" / "Vendor Delay" / "Parts on Order" / "Permit Required" / "Other"`. Current schema only has boolean `blocking`. |
| 3 | **Add `wd_present_type` column** | `turnover` | `ALTER TABLE turnover ADD COLUMN wd_present_type TEXT CHECK(wd_present_type IN ('No', 'Yes', 'Yes stack') OR wd_present_type IS NULL);` | Frontend W/D panel has 3-way dropdown: No, Yes, Yes stack. Boolean `wd_present` cannot represent "Yes stack". |
| 4 | **Add `EXPOSURE_RISK` to CHECK** | `risk_flag` | Requires table recreation (SQLite limitation). Add `'EXPOSURE_RISK'` to `risk_type` CHECK constraint. | `risk_engine.py` emits EXPOSURE_RISK but schema CHECK rejects it on INSERT. |

#### HIGH — Needed for full functionality

| # | Change | Table | Migration SQL | Rationale |
|---|--------|-------|--------------|-----------|
| 5 | **Seed 9 `task_template` rows** | `task_template` | INSERT statements for Insp, CB, MRB, Paint, MR, HK, CC, FW, QC with correct `sort_order`, `required`, `blocking` | Import service instantiates tasks from templates. Without templates, no tasks are created on turnover creation. |
| 6 | **Update `TASK_UPDATE_COLS`** | `repository.py` | Add `'assignee'` and `'blocking_reason'` to `TASK_UPDATE_COLS` frozenset | Repository whitelist prevents updating new columns. |
| 7 | **Update `TURNOVER_UPDATE_COLS`** | `repository.py` | Add `'wd_present_type'` to `TURNOVER_UPDATE_COLS` frozenset | Same — whitelist prevents updates. |

### 2.3 Inconsistencies Between Frontend Data Model and Backend Schema

| # | Inconsistency | Frontend Behavior | Backend Behavior | Resolution |
|---|---------------|-------------------|------------------|------------|
| 1 | **Assignee scope** | Per-task (`task.assignee`) | No assignee anywhere | Add `assignee TEXT` to `task` table |
| 2 | **W/D type granularity** | 3-way: No / Yes / Yes stack | Binary: 0 / 1 | Add `wd_present_type` column; derive `wd_present` as `0 if type == 'No' else 1` |
| 3 | **Blocking reason** | Enum dropdown per task | Boolean only | Add `blocking_reason TEXT` to `task` table |
| 4 | **Business days vs calendar days** | Frontend uses business days for DV, DTBR, SLA thresholds | Backend `sla_engine` uses calendar days (`timedelta > 10`) | Accept dual system (§ below); backend SLA for audit, frontend for operational display |
| 5 | **"Unit ready" definition** | `manual_ready_status == "Vacant ready" AND all tasks VENDOR_COMPLETED` | `manual_ready_confirmed_at IS NOT NULL` | These are complementary signals, not contradictions. Frontend is operational, backend is audit-authoritative. |
| 6 | **Note `created_at`** | Mock data omits `created_at` | Schema: `NOT NULL` | Frontend must supply `datetime.utcnow().isoformat()` on note creation |
| 7 | **Risk computation** | Frontend computes 4 breach flags (Insp SLA, SLA, SLA MI, Plan) at render time | Backend computes 7 risk types and persists to `risk_flag` table | Dual system by design (see §2.4) |

### 2.4 The Dual Breach/Risk System (Architectural Decision)

The frontend and backend compute risk/breach indicators differently. **This is intentional and should be preserved.**

| Aspect | Frontend (System B) | Backend (System A) |
|--------|--------------------|--------------------|
| **Purpose** | Operational display (Flag Bridge, Alert badge) | Audit trail, auto-resolution, persistence |
| **Storage** | Computed at render time, not persisted | Persisted in `risk_flag` table |
| **Breach types** | `inspection_sla_breach`, `sla_breach`, `sla_movein_breach`, `plan_breach` | `SLA_BREACH`, `QC_RISK`, `WD_RISK`, `CONFIRMATION_BACKLOG`, `EXECUTION_OVERDUE`, `DATA_INTEGRITY`, `EXPOSURE_RISK` |
| **Day counting** | Business days | Calendar days |
| **"Ready" test** | All tasks complete + status = "Vacant ready" | `manual_ready_confirmed_at IS NOT NULL` |

**Rule:** Flag Bridge and Attention Badge use System B. Detail view risks panel uses System A. Both coexist.

---

## 3. Backend Features Not Utilized by the Frontend

### 3.1 Structured Inventory

#### 3.1.1 Schema Elements — Not Exposed in UI

| Backend Element | Description | Recommendation |
|----------------|-------------|----------------|
| `turnover.expedited_flag` | Boolean flag for expedited turnovers | **Integrate:** Add toggle in Detail view; useful for prioritization |
| `turnover.cancel_reason` | Text describing why turnover was canceled | **Integrate:** Show in Detail view when turnover is canceled |
| `turnover.source_turnover_key` | Stable import identity key | **Keep as-is:** Backend-only, used for import idempotency |
| `turnover.last_seen_moveout_batch_id` | Tracks last import batch that saw this unit | **Keep as-is:** Backend-only import tracking |
| `turnover.missing_moveout_count` | Disappearance counter (auto-cancel at 2) | **Keep as-is:** Backend-only, auto-cancel logic |
| `task.scheduled_date` | Separate from `vendor_due_date` | **Evaluate:** Frontend only edits `vendor_due_date`. Consider if `scheduled_date` adds value or should be merged |
| `turnover_task_override` table | Per-turnover overrides for task required/blocking | **Deprecate or integrate:** Entire table is unused by any code (neither services nor frontend). If task overrides are valuable, wire them; otherwise remove. |
| `task_template_dependency` + `task_dependency` | Task dependency chains | **Future integration:** Frontend shows tasks in sequence but doesn't enforce dependencies. Backend has the data model for it. |
| `risk_flag.auto_resolve` | Whether risk auto-resolves | **Keep as-is:** Backend-only flag, affects risk reconciliation |

#### 3.1.2 Domain Functions — Not Called by Frontend

| Backend Function | Module | Description | Recommendation |
|-----------------|--------|-------------|----------------|
| `derive_lifecycle_phase()` | `domain/lifecycle.py` | Derives NOTICE → VACANT → SMI → etc. | **Integrate:** Frontend reimplements this in `mock_data_v2.derive_phase()`. Should call backend function instead when wired. |
| `evaluate_risks()` | `domain/risk_engine.py` | Evaluates 7+ risk types | **Integrate:** Detail view risk panel should be populated by this engine. Frontend currently uses static mock risks. |
| `evaluate_sla_state()` | `domain/sla_engine.py` | SLA breach open/close logic | **Integrate:** Works with `sla_event` table for audit trail. Frontend SLA breach is render-time; backend SLA is persistent. Both needed. |

#### 3.1.3 Service Functions — Not Called by Frontend

| Backend Service | Function | Description | Recommendation |
|----------------|----------|-------------|----------------|
| `turnover_service` | `set_manual_ready_status()` | Audited status change + risk reconciliation | **Integrate:** Replace frontend's `_update_turnover_status()` (direct dict mutation) |
| `turnover_service` | `confirm_manual_ready()` | Stamps `manual_ready_confirmed_at` + SLA + risks | **Integrate:** Not exposed in frontend at all. Needed for SLA closure. |
| `turnover_service` | `update_wd_panel()` | Audited W/D changes + risk reconciliation | **Integrate:** Replace frontend's direct dict mutation |
| `turnover_service` | `attempt_auto_close()` | Auto-close turnover after stabilization | **Integrate:** Should run on a schedule or after certain actions |
| `task_service` | `mark_vendor_completed()` | Audited vendor completion with timestamp | **Integrate:** Replace frontend's `_update_task()` for "Done" transitions |
| `task_service` | `confirm_task()` | Audited confirmation with constraint checks | **Integrate:** Replace frontend's QC confirm button |
| `task_service` | `reject_task()` | Reopens task execution after rejection | **Integrate:** Frontend has no reject action currently. Add it. |
| `import_service` | `import_report_file()` | Full import pipeline with parsing, conflict detection, idempotency | **Integrate:** Frontend import page currently shows fake results. Wire to real service. |
| `risk_service` | `reconcile_risks_for_turnover()` | Upsert/resolve risk flags in DB | **Integrate:** Should run after every task/turnover change |
| `sla_service` | `reconcile_sla_for_turnover()` | Open/close SLA breach events | **Integrate:** Should run after status changes |

#### 3.1.4 Repository Functions — Available but Uncalled

| Repository Function | Description | Recommendation |
|--------------------|-------------|----------------|
| `list_open_turnovers_by_property()` | All open turnovers for property | **Integrate:** Replace `st.session_state.turnovers` iteration |
| `get_turnover_by_id()` | Single turnover lookup | **Integrate:** Replace `_find_turnover_by_id()` |
| `get_open_turnover_by_unit()` | Open turnover for unit | **Integrate:** For Detail view unit search |
| `get_tasks_by_turnover()` | All tasks for turnover | **Integrate:** Replace `_get_tasks_for_turnover()` |
| `get_active_risks_by_turnover()` | Active risk flags | **Integrate:** Detail view risks panel |
| `upsert_risk()` / `resolve_risk()` | Risk lifecycle | **Integrate:** Via risk_service |
| `insert_import_batch()` / `insert_import_row()` | Import audit trail | **Integrate:** Via import_service |
| `insert_audit_log()` | Audit trail for all changes | **Integrate:** Via services (automatic when using service layer) |
| `get_active_task_templates()` | Template lookup | **Integrate:** For task instantiation |
| `get_open_sla_event()` / `insert_sla_event()` / `close_sla_event()` | SLA event lifecycle | **Integrate:** Via sla_service |
| `backup_database()` | Post-import backup | **Integrate:** Wire backup into import flow |

#### 3.1.5 Infrastructure — Available but Unused

| Component | Description | Recommendation |
|-----------|-------------|----------------|
| `connection.get_connection()` | SQLite connection with WAL + FK | **Integrate:** App startup |
| `connection.initialize_database()` | Schema creation from DDL | **Integrate:** First-run setup |
| `connection.run_integrity_check()` | PRAGMA integrity_check | **Integrate:** App startup — block on failure per blueprint §15.2 |
| `connection.backup_database()` | DB file backup | **Integrate:** Post-import |
| `migrations/001_add_report_ready_date.sql` | Schema migration | **Integrate:** Migration runner needed |

### 3.2 Backend-Ready Systems for Immediate Frontend Consumption

These backend systems are **fully implemented and tested**, requiring only UI wiring:

| # | System | Backend Location | Frontend Wiring Needed |
|---|--------|-----------------|----------------------|
| 1 | **Import pipeline** (5 report types, idempotent, conflict detection) | `services/import_service.py` | Replace mock import with real file → `import_report_file()` |
| 2 | **Risk reconciliation** (auto-resolve, upsert, 7 risk types) | `services/risk_service.py` + `domain/risk_engine.py` | Call after every task/turnover change |
| 3 | **SLA breach tracking** (open/close events, audit) | `services/sla_service.py` + `domain/sla_engine.py` | Call after status changes |
| 4 | **Audit logging** (all changes tracked with actor, source, timestamp) | `repository.insert_audit_log()` via services | Automatic when using service layer |
| 5 | **Task lifecycle** (vendor complete, confirm, reject with constraints) | `services/task_service.py` | Replace direct dict mutations |
| 6 | **Turnover status management** (audited, with risk reconciliation) | `services/turnover_service.py` | Replace direct dict mutations |
| 7 | **DB integrity + backup** | `db/connection.py` | Startup check + post-import backup |

---

## 4. Inventory of Fully Utilized Backend Components

### 4.1 Components with Full Frontend Alignment

| Backend Component | Frontend Usage | Alignment Status |
|-------------------|---------------|-----------------|
| `turnover` schema (core fields) | DMRB Board, Flag Bridge, Detail view | ✅ All core fields (dates, status, W/D) are displayed and editable |
| `task` schema (core fields) | DMRB Board columns (9 task types), Detail task panel | ✅ `execution_status`, `confirmation_status`, `vendor_due_date` fully used |
| `unit` schema | Unit code parsing, Phase filter, Detail header | ✅ `unit_code_raw`, `property_id` used in all views |
| Execution status enum | DMRB Board task columns + Detail task rows | ✅ 6-value enum with bidirectional label mapping |
| Confirmation status enum | QC column + Detail task rows | ✅ 4-value enum with bidirectional label mapping |
| Manual status enum | Status column + Detail status dropdown | ✅ 3-value enum, exact string match with schema CHECK |
| Risk severity enum | Detail risks panel (icons by severity) | ✅ CRITICAL → 🔴, WARNING → 🟡, INFO → ⚪ |
| Note structure | Detail notes panel (description, blocking, resolve) | ✅ Data model aligned (minus `created_at` on insert) |

### 4.2 Redundancies and Inefficiencies in Active Components

| # | Issue | Impact | Resolution |
|---|-------|--------|------------|
| 1 | **Frontend reimplements `derive_lifecycle_phase()`** | `mock_data_v2.derive_phase()` duplicates `domain/lifecycle.py` with minor differences (MOVE_IN_COMPLETE logic varies slightly) | When wiring, delete `derive_phase()` from mock data; call `domain.lifecycle.derive_lifecycle_phase()` |
| 2 | **Frontend reimplements `derive_nvm()`** | Same mapping exists in mock_data_v2 and could exist in domain | Move `derive_nvm()` to `domain/lifecycle.py` as canonical source |
| 3 | **`_update_turnover_status()` bypasses service layer** | Frontend mutates session state directly; no audit trail, no risk reconciliation | When wiring, replace with `turnover_service.set_manual_ready_status()` |
| 4 | **`_update_task()` bypasses service layer** | Same — no audit, no constraint checks, no risk reconciliation | When wiring, replace with `task_service` functions |
| 5 | **Risk display uses static mock data** | Detail view risks panel shows `MOCK_RISKS_V2` (hardcoded), not dynamically computed | When wiring, call `repository.get_active_risks_by_turnover()` |
| 6 | **Import page is entirely fake** | "Run import" shows a hardcoded success message | When wiring, call `import_service.import_report_file()` |

---

## 5. Architectural Principle: Zero Logic in the Frontend

### 5.1 Current State Assessment

The frontend currently contains **significant transitional logic and mock data**. This is expected and documented as a prototype. The following inventory identifies all logic that must migrate to the backend before production.

### 5.2 Logic Currently in the Frontend

#### 5.2.1 Business Logic (Must Migrate to Backend)

| # | Logic | Frontend Location | Target Backend Location | Priority |
|---|-------|-------------------|------------------------|----------|
| 1 | **3-stage enrichment pipeline** (Fact → Intelligence → SLA) | `mock_data_v2.py`: `compute_facts()`, `compute_intelligence()`, `compute_sla_breaches()` | New `domain/enrichment.py` or distribute across `lifecycle.py`, `risk_engine.py`, `sla_engine.py` | **Critical** |
| 2 | **Lifecycle phase derivation** | `mock_data_v2.derive_phase()` | `domain/lifecycle.derive_lifecycle_phase()` (already exists, minor alignment needed) | High |
| 3 | **N/V/M derivation** | `mock_data_v2.derive_nvm()` | `domain/lifecycle.py` (add function) | High |
| 4 | **Operational State machine** (8 states: On Notice, Move-In Risk, QC Hold, Work Stalled, In Progress, Pending Start, Apartment Ready, Out of Scope) | `mock_data_v2.compute_intelligence()` | New `domain/intelligence.py` or `domain/operational_state.py` | **Critical** |
| 5 | **Attention Badge derivation** | `mock_data_v2.compute_intelligence()` badge_map | Same as above | **Critical** |
| 6 | **SLA breach computation** (4 breach flags) | `mock_data_v2.compute_sla_breaches()` | `domain/sla_engine.py` (extend or create parallel) | **Critical** |
| 7 | **Task stall detection** | `mock_data_v2.compute_facts()` (`is_task_stalled` with `TASK_EXPECTED_DAYS`) | `domain/lifecycle.py` or `domain/intelligence.py` | High |
| 8 | **"Unit ready" computation** | `mock_data_v2.compute_intelligence()` (`is_unit_ready = status == "Vacant ready" AND all tasks done`) | `domain/intelligence.py` | High |
| 9 | **"Ready for moving" computation** | `mock_data_v2.compute_intelligence()` (`is_ready_for_moving = ready + move-in + QC done`) | `domain/intelligence.py` | High |
| 10 | **Business day calculation** | `mock_data_v2.business_days()` | `domain/` or `utils/` shared utility | High |
| 11 | **W/D summary derivation** | `mock_data_v2._wd_summary()` | Backend enrichment | Medium |
| 12 | **Assign display derivation** | `mock_data_v2._assign_display()` (MR task assignee) | Backend enrichment | Medium |

#### 5.2.2 Data Transformation (Must Migrate)

| # | Transformation | Frontend Location | Target |
|---|---------------|-------------------|--------|
| 1 | **DMRB Board row assembly** | `mock_data_v2.get_dmrb_board_rows()` — builds flat rows, enriches, filters, sorts | Backend query service that joins turnover + unit + tasks + notes, enriches, returns ready-to-display rows |
| 2 | **Flag Bridge row assembly** | `mock_data_v2.get_flag_bridge_rows()` — same + breach filter | Same backend query service |
| 3 | **Unit code parsing** | `mock_data_v2.parse_unit_code()` — splits `"5-1-101"` → building, unit | Utility function (can remain in shared utils) |
| 4 | **Date formatting** | `app_prototype_v2._fmt_date()` — ISO → MM/DD/YYYY | UI-layer only (acceptable) |

#### 5.2.3 Filtering Logic (Must Migrate)

| # | Filter | Frontend Location | Target |
|---|--------|-------------------|--------|
| 1 | Search by unit code | `get_dmrb_board_rows()` substring match | Backend query with `WHERE unit_code_norm LIKE ?` |
| 2 | Filter by phase | `get_dmrb_board_rows()` property_id match | Backend query with `WHERE property_id = ?` |
| 3 | Filter by status | `get_dmrb_board_rows()` manual_ready_status match | Backend query with `WHERE manual_ready_status = ?` |
| 4 | Filter by N/V/M | `get_dmrb_board_rows()` derived nvm match | Backend: compute phase → nvm, filter |
| 5 | Filter by assignee | `get_dmrb_board_rows()` checks all task assignees | Backend: JOIN task WHERE assignee = ? |
| 6 | Filter by QC | `get_dmrb_board_rows()` QC confirmation_status check | Backend: JOIN task WHERE task_type='QC' |
| 7 | Breach filter/value | `get_flag_bridge_rows()` breach_filter + value | Backend: compute breaches, filter |

#### 5.2.4 Mock Data (Must Be Removed)

| Mock Data Object | Location | Replacement |
|-----------------|----------|-------------|
| `MOCK_UNITS_V2` | `mock_data_v2.py` | `repository.get_units_by_property()` (to be added) |
| `MOCK_TURNOVERS_V2` | `mock_data_v2.py` | `repository.list_open_turnovers_by_property()` |
| `MOCK_TASKS_V2` | `mock_data_v2.py` | `repository.get_tasks_by_turnover()` per turnover |
| `MOCK_NOTES_V2` | `mock_data_v2.py` | `repository.get_notes_by_turnover()` (to be added) |
| `MOCK_RISKS_V2` | `mock_data_v2.py` | `repository.get_active_risks_by_turnover()` |
| `MOCK_CONFLICTS_V2` | `mock_data_v2.py` | `repository.get_import_rows_with_conflicts()` (to be added) |
| `DEFAULT_TASK_ASSIGNEES` | `mock_data_v2.py` | Configurable table or JSON config (not yet designed) |

#### 5.2.5 Frontend-Only Logic (Acceptable to Keep)

These items are **presentation-only** and should remain in the frontend:

| Logic | Reason |
|-------|--------|
| Date formatting (`_fmt_date`) | Display-only transformation |
| Column configuration for `st.data_editor` | Streamlit-specific rendering |
| Session state management (page, filters, selection) | UI navigation state |
| CSS styling (centering, alignment) | Presentation |
| Label maps (`EXEC_LABEL_TO_VALUE`, `CONFIRM_VALUE_TO_LABEL`) | UI display labels ↔ backend enum mapping |
| Sidebar flag rendering | UI layout |
| Dropdown Manager UI | UI configuration (though persistence needs backend) |

### 5.3 Migration Plan: Frontend Logic → Backend

**Phase 1 — Schema alignment (before any wiring)**
1. Run all migrations from §2.2 (add `assignee`, `blocking_reason`, `wd_present_type`, fix EXPOSURE_RISK CHECK)
2. Seed `task_template` rows for all 9 task types
3. Add missing repository functions (notes CRUD, unit by ID, conflict queries)

**Phase 2 — Domain enrichment engine (new backend code)**
1. Move `business_days()` to `domain/` or `utils/`
2. Move `derive_nvm()` to `domain/lifecycle.py`
3. Create `domain/enrichment.py` with `compute_facts()`, `compute_intelligence()`, `compute_sla_breaches()`, `enrich_row()`
4. Create backend query service that returns fully enriched rows for DMRB Board / Flag Bridge

**Phase 3 — Service layer completion**
1. Add general `set_task_execution_status()` and `set_task_confirmation_status()` to `task_service.py`
2. Add `wd_installed` support to `turnover_service.update_wd_panel()`
3. Add risk reconciliation calls after task changes
4. Add note service (`create_note`, `resolve_note`)

**Phase 4 — Frontend wiring**
1. Replace `st.session_state.turnovers/tasks` with real DB queries
2. Replace `_update_*` functions with service calls
3. Remove `mock_data_v2.py` entirely
4. Wire import page to `import_service.import_report_file()`
5. Wire Detail risks panel to `repository.get_active_risks_by_turnover()`

**Phase 5 — Validation**
1. All mock data removed
2. All business logic originates from backend
3. Frontend is purely presentational
4. All edits go through service layer (audit trail, risk reconciliation)
5. Import is functional end-to-end

---

## 6. Summary: All Required Actions (Ranked)

### Critical — Must complete before integration

| # | Action | Location | Effort |
|---|--------|----------|--------|
| 1 | Add `assignee TEXT` to `task` table | Schema migration | Small |
| 2 | Add `blocking_reason TEXT` to `task` table | Schema migration | Small |
| 3 | Add `wd_present_type TEXT` to `turnover` table | Schema migration | Small |
| 4 | Add `EXPOSURE_RISK` to `risk_flag.risk_type` CHECK | Schema migration (table recreation) | Medium |
| 5 | Seed 9 `task_template` rows | Data migration | Small |
| 6 | Add note CRUD to repository (`get_notes_by_turnover`, `insert_note`, `resolve_note`) | `repository.py` | Small |
| 7 | Add `get_unit_by_id()` to repository | `repository.py` | Small |
| 8 | Update `TASK_UPDATE_COLS` and `TURNOVER_UPDATE_COLS` with new columns | `repository.py` | Small |

### High — Needed for full feature parity

| # | Action | Location | Effort |
|---|--------|----------|--------|
| 9 | Add general `set_task_execution_status()` service | `task_service.py` | Medium |
| 10 | Add `wd_installed` to `turnover_service.update_wd_panel()` | `turnover_service.py` | Small |
| 11 | Add risk reconciliation after task changes | `task_service.py` | Medium |
| 12 | Create backend enrichment engine (`domain/enrichment.py`) | New file | Large |
| 13 | Add conflict query to repository | `repository.py` | Small |
| 14 | Add batch queries to avoid N+1 (`get_all_tasks_for_turnover_ids`, etc.) | `repository.py` | Medium |
| 15 | Create Dropdown Manager persistence (task assignee config) | New table + service | Medium |

### Medium — Can defer to post-integration refinement

| # | Action | Location | Effort |
|---|--------|----------|--------|
| 16 | Move `business_days()` to shared domain utility | `domain/` or `utils/` | Small |
| 17 | Evaluate `turnover_task_override` table — integrate or remove | Schema decision | Small |
| 18 | Evaluate `task.scheduled_date` — merge with `vendor_due_date` or keep | Schema decision | Small |
| 19 | Add `expedited_flag` toggle to Detail view | Frontend change | Small |
| 20 | Add startup integrity check + restore path | `app.py` startup | Medium |

---

## 7. Conclusion

The backend and frontend are **architecturally aligned** in their data model foundations (units, turnovers, tasks, notes, risks) but **not yet ready for integration**. The primary gaps are:

1. **Three missing schema columns** (`task.assignee`, `task.blocking_reason`, `turnover.wd_present_type`) that the frontend actively uses.
2. **Missing repository functions** for notes and unit lookup by ID.
3. **No backend enrichment engine** — the frontend's 3-stage pipeline (facts, intelligence, SLA breaches) must be mirrored in the backend before the frontend can drop its mock data.
4. **Service layer gaps** — general task status changes, note management, and post-task-change risk reconciliation.

The **dual breach/risk system** (frontend computed at render time vs backend persisted risk_flags) is an intentional architectural decision and should be preserved, not merged.

**Integration must not begin until items #1–#8 from §6 are complete.** Once schema alignment reaches 100%, the remaining work is service wiring (replacing mock data calls with real DB queries and service calls).
