# Invariant Reconciliation Report

**Date:** 2025-02-25  
**Source files audited:** `db/schema.sql`, `db/repository.py`, `db/connection.py`, `domain/lifecycle.py`, `domain/risk_engine.py`, `domain/sla_engine.py`, `services/turnover_service.py`, `services/task_service.py`, `services/risk_service.py`, `services/sla_service.py`, `services/import_service.py`, `ui/mock_data_v2.py`, `app_prototype_v2.py`

---

## Section 1 — Hard Enforcement Matrix

Hard enforcement = schema CHECK constraints, UNIQUE indexes, or service-layer precondition checks that **reject invalid operations** (raise error or fail INSERT/UPDATE).

| # | Invariant | Enforcement Mechanism | Code Location |
|---|-----------|----------------------|---------------|
| H1 | **One open turnover per unit** | Partial unique index: `UNIQUE(unit_id) WHERE closed_at IS NULL AND canceled_at IS NULL` | `schema.sql:64-66` |
| H2 | **move_out_date NOT NULL** | `CHECK(move_out_date IS NOT NULL)` | `schema.sql:60` |
| H3 | **Closed and canceled are mutually exclusive** | `CHECK(NOT (closed_at IS NOT NULL AND canceled_at IS NOT NULL))` | `schema.sql:61` |
| H4 | **source_turnover_key uniqueness** | `TEXT NOT NULL UNIQUE` | `schema.sql:41` |
| H5 | **Unit code not empty** | `CHECK(unit_code_norm <> '')` | `schema.sql:31` |
| H6 | **Unit uniqueness per property** | `UNIQUE(property_id, unit_code_norm)` | `schema.sql:30` |
| H7 | **execution_status enum** | `CHECK(execution_status IN ('NOT_STARTED','SCHEDULED','IN_PROGRESS','VENDOR_COMPLETED','NA','CANCELED'))` | `schema.sql:108` |
| H8 | **confirmation_status enum** | `CHECK(confirmation_status IN ('PENDING','CONFIRMED','REJECTED','WAIVED'))` | `schema.sql:109` |
| H9 | **VENDOR_COMPLETED requires vendor_completed_at** | `CHECK(execution_status != 'VENDOR_COMPLETED' OR vendor_completed_at IS NOT NULL)` | `schema.sql:111` |
| H10 | **CONFIRMED requires vendor_completed_at** | `CHECK(confirmation_status != 'CONFIRMED' OR vendor_completed_at IS NOT NULL)` | `schema.sql:112` |
| H11 | **CONFIRMED requires manager_confirmed_at** | `CHECK(confirmation_status != 'CONFIRMED' OR manager_confirmed_at IS NOT NULL)` | `schema.sql:113` |
| H12 | **One task per type per turnover** | `UNIQUE(turnover_id, task_type)` | `schema.sql:110` |
| H13 | **No self-referencing task dependency** | `CHECK(task_id <> depends_on_task_id)` | `schema.sql:123` |
| H14 | **No self-referencing template dependency** | `CHECK(template_id <> depends_on_template_id)` | `schema.sql:92` |
| H15 | **manual_ready_status enum** | `CHECK(manual_ready_status IN ('Vacant ready','Vacant not ready','On notice') OR manual_ready_status IS NULL)` | `schema.sql:45` |
| H16 | **risk_type enum** | `CHECK(risk_type IN ('SLA_BREACH','QC_RISK','WD_RISK','CONFIRMATION_BACKLOG','EXECUTION_OVERDUE','DATA_INTEGRITY','DUPLICATE_OPEN_TURNOVER'))` | `schema.sql:157` |
| H17 | **One active risk per type per turnover** | Partial unique: `UNIQUE(turnover_id, risk_type) WHERE resolved_at IS NULL` | `schema.sql:164-166` |
| H18 | **One open SLA breach per turnover** | Partial unique: `UNIQUE(turnover_id) WHERE breach_resolved_at IS NULL` | `schema.sql:178-180` |
| H19 | **Import checksum uniqueness** | `UNIQUE(checksum)` on import_batch | `schema.sql:204` |
| H20 | **Confirm requires VENDOR_COMPLETED (service)** | `task_service.confirm_task` raises ValueError if `execution_status != 'VENDOR_COMPLETED'` | `task_service.py:60-61` |
| H21 | **Reject requires CONFIRMED (service)** | `task_service.reject_task` raises ValueError if `confirmation_status != 'CONFIRMED'` | `task_service.py:84-85` |
| H22 | **Boolean fields constrained to 0/1** | CHECK constraints on all boolean INTEGER columns (has_carpet, has_wd_expected, is_active, expedited_flag, wd_present, wd_supervisor_notified, wd_installed, required, blocking, auto_resolve, conflict_flag) | `schema.sql` (multiple lines) |
| H23 | **Repository UPDATE whitelist** | `TURNOVER_UPDATE_COLS`, `TASK_UPDATE_COLS`, `UNIT_UPDATE_COLS` frozensets silently drop any field not in list | `repository.py:4-19` |
| H24 | **audit_log source enum** | `CHECK(source IN ('manual','import','system'))` | `schema.sql:194` |
| H25 | **import_batch status enum** | `CHECK(status IN ('SUCCESS','NO_OP','FAILED'))` | `schema.sql:207` |
| H26 | **severity enum** (note, risk_flag) | `CHECK(severity IN ('INFO','WARNING','CRITICAL'))` | `schema.sql:145, 158` |
| H27 | **FK enforcement at runtime** | `PRAGMA foreign_keys = ON` in `connection.get_connection()` | `connection.py:12` |

---

## Section 2 — Soft Intelligence Matrix

Soft intelligence = deterministic predicates, computed flags, or risk evaluations that **surface signals** but do not reject operations.

| # | Rule | Backend Implementation | Frontend Implementation | Notes |
|---|------|----------------------|------------------------|-------|
| S1 | **Lifecycle phase derivation** | `domain/lifecycle.derive_lifecycle_phase()` — 8 phases from dates + closed/canceled | `mock_data_v2.derive_phase()` — same 8 phases | Minor divergence: see §4-C1 |
| S2 | **N/V/M classification** | Not implemented | `mock_data_v2.derive_nvm()` — maps phase → N/V/M | Frontend only |
| S3 | **Days Vacant (DV)** | Not computed anywhere | `mock_data_v2.compute_facts()` — `business_days(move_out, today)` | Frontend only, uses business days |
| S4 | **Days To Be Ready (DTBR)** | Not computed anywhere | `mock_data_v2.compute_facts()` — `business_days(today, move_in)` | Frontend only, uses business days |
| S5 | **QC Risk** | `risk_engine.evaluate_risks()` — move_in ≤ 3 days + QC not CONFIRMED → QC_RISK | Not computed as separate risk flag. QC status used in `is_ready_for_moving` | Different scope: see §4-C4 |
| S6 | **WD Risk** | `risk_engine.evaluate_risks()` — move_in ≤ 7 days + wd_present=False + notified≠True → WD_RISK | Not computed as separate risk flag | Backend only |
| S7 | **Confirmation Backlog** | `risk_engine.evaluate_risks()` — vendor_completed_date IS NOT NULL + manager_confirmed_at IS NULL + age > 2 | Not computed | Backend only |
| S8 | **Execution Overdue** | `risk_engine.evaluate_risks()` — vendor_due_date < today + status ≠ VENDOR_COMPLETED | Not computed | Backend only |
| S9 | **SLA Breach (backend)** | `sla_engine.evaluate_sla_state()` — calendar_days(move_out, today) > 10 AND manual_ready_confirmed_at IS NULL | Different definition: see S12 | Tracked via `sla_event` table |
| S10 | **Exposure Risk** | `risk_engine.evaluate_risks()` — report_ready_date passed + manual_ready_confirmed_at IS NULL → EXPOSURE_RISK | Different definition: see S15 | **Blocked by H16** — schema rejects insert |
| S11 | **Data Integrity risk** | `risk_engine.evaluate_risks()` — `has_data_integrity_conflict` flag → DATA_INTEGRITY | Not computed | Caller-provided flag |
| S12 | **SLA Breach (frontend)** | Not implemented | `mock_data_v2.compute_sla_breaches()` — `is_vacant AND NOT is_unit_ready AND business_days(dv) > 10` | Frontend only |
| S13 | **Inspection SLA Breach** | Not implemented | `compute_sla_breaches()` — `is_vacant AND NOT insp_done AND dv > 1` | Frontend only |
| S14 | **SLA MoveIn Breach** | Not implemented | `compute_sla_breaches()` — `is_move_in_present AND NOT is_ready_for_moving AND days_to_move_in ≤ 2` | Frontend only |
| S15 | **Plan Breach** | Not implemented (related: Exposure Risk S10) | `compute_sla_breaches()` — `report_ready_date passed AND NOT is_unit_ready` | Frontend only |
| S16 | **Is_Unit_Ready** | Not computed | `compute_intelligence()` — `status == "Vacant ready" AND task_state == "All Tasks Complete"` | Frontend only |
| S17 | **Is_Ready_For_Moving** | Not computed | `compute_intelligence()` — `is_unit_ready AND is_move_in_present AND is_qc_done` | Frontend only |
| S18 | **Operational State** (8 states) | Not implemented | `compute_intelligence()` — state machine: On Notice, Move-In Risk, QC Hold, Work Stalled, In Progress, Pending Start, Apartment Ready, Out of Scope | Frontend only |
| S19 | **Attention Badge** | Not implemented | `compute_intelligence()` — emoji badge derived from Operational State | Frontend only |
| S20 | **Task Stall Detection** | Not implemented | `compute_facts()` — `TASK_EXPECTED_DAYS` per task type, stalled if `dv > expected + 1` | Frontend only |
| S21 | **Auto-close eligibility** | `turnover_service.attempt_auto_close()` — today > move_in + 14 days AND no CRITICAL risks | Not implemented | Backend only, never called by UI |
| S22 | **Move-Out Disappearance** | `import_service` — `missing_moveout_count` incremented per MOVE_OUTS import; auto-cancel at ≥ 2 | Not implemented | Backend only |
| S23 | **Risk auto-resolution** | `risk_service.reconcile_risks_for_turnover()` — resolves risks whose predicate becomes false | Not implemented — static mock risks | Backend only |
| S24 | **Duplicate Open Turnover risk** | `risk_engine.evaluate_risks()` — `has_duplicate_open_turnover` flag → DUPLICATE_OPEN_TURNOVER | Not computed | Caller-provided flag |
| S25 | **Manual-authoritative field protection** | `import_service` never overwrites `manual_ready_status`, `wd_present`, `wd_supervisor_notified`, `wd_installed` | Not relevant (no import) | Implicit in import code |

---

## Section 3 — Category-by-Category Gaps

### 3.1 Identity & Lifecycle Integrity

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| One open turnover per unit | **A) Backend enforced** | Schema partial unique index `idx_one_open_turnover_per_unit` |
| move_out_date required | **A) Backend enforced** | Schema CHECK |
| Closed/canceled mutual exclusion | **A) Backend enforced** | Schema CHECK |
| source_turnover_key stable | **A) Backend enforced** | Schema UNIQUE, generated as `{prop}:{unit_norm}:{mo_iso}` by import |
| Lifecycle phase derivation | **C) Partially implemented** | Backend: `lifecycle.py`. Frontend: `mock_data_v2.derive_phase()`. Both exist but with behavioral divergence on `move_out_date IS NULL` (see §4-C1) |
| Auto-close after stabilization | **A) Backend only** | `turnover_service.attempt_auto_close()` — exists but is never invoked by any caller. Dead code. |

### 3.2 Task Dependency Integrity

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| Dependency stored at template + task level | **A) Backend enforced** | Schema tables `task_template_dependency`, `task_dependency` with self-ref CHECK |
| Dependencies instantiated on turnover creation | **A) Backend enforced** | `import_service._instantiate_tasks_for_turnover()` copies template deps to task deps |
| **Dependency order enforced during execution** | **D) Missing entirely** | No code anywhere checks task dependencies before allowing execution status changes. `mark_vendor_completed()` does not verify that dependent tasks are completed. Frontend allows arbitrary execution status changes on any task. |

### 3.3 Data Model Integrity

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| Enum constraints (execution, confirmation, status) | **A) Backend enforced** | Schema CHECKs on all enum columns |
| Confirmation requires vendor completion | **A) Backend enforced** | Schema CHECK (H10) + service precondition (H20) |
| Reject requires confirmed state | **A) Backend enforced** | Service precondition (H21) |
| One task per type per turnover | **A) Backend enforced** | Schema UNIQUE |
| Boolean integrity | **A) Backend enforced** | Schema CHECK on every boolean INTEGER column |
| **Append-only tables (audit_log, sla_event, import_batch, import_row)** | **C) Partially enforced** | No schema-level trigger prevents UPDATE/DELETE. Enforced only by convention — repository functions for these tables only have INSERT functions, no UPDATE or DELETE (except `close_sla_event` which UPDATEs `breach_resolved_at`). |

### 3.4 Import Idempotency

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| Same (report_type, checksum) = NO_OP | **A) Backend enforced** | `import_service.import_report_file()` checks `get_import_batch_by_checksum()` first. Schema UNIQUE on checksum. |
| Every import row recorded | **A) Backend enforced** | `_write_import_row()` called for every row: OK, CONFLICT, INVALID, IGNORED |
| No silent merges (conflicts visible) | **A) Backend enforced** | Weak matches produce `conflict_flag=1` with specific `conflict_reason` |
| Backup after successful import | **A) Backend enforced** | `backup_database()` called at end of `import_report_file()` if `db_path` and `backup_dir` provided |
| Phase filter (5/7/8 only) | **A) Backend enforced** | `_filter_phase()` with `VALID_PHASES = (5, 7, 8)` — hardcoded |

### 3.5 Cancellation Rules

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| Move-out disappearance auto-cancel at count ≥ 2 | **A) Backend enforced** | `import_service` lines 580-589: increments `missing_moveout_count`, cancels with reason at ≥ 2 |
| Canceled turnover cannot also be closed | **A) Backend enforced** | Schema CHECK (H3) |
| Manual cancellation | **D) Missing entirely** | No service function for manual cancellation. No UI for it. Only auto-cancel via import exists. |

### 3.6 QC Risk

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| QC_RISK flagged when move_in ≤ 3 days + QC not confirmed | **A) Backend enforced** | `risk_engine.evaluate_risks()` lines 44-52, persisted via `risk_service` |
| Severity escalation (WARNING at 3, CRITICAL at ≤ 2) | **A) Backend enforced** | `risk_engine.py:52` |
| Auto-resolution when QC confirmed | **A) Backend enforced** | `risk_service.reconcile_risks_for_turnover()` resolves when predicate false |
| **Risk reconciliation triggered after QC task changes** | **D) Missing** | `task_service.confirm_task()` does NOT call `reconcile_risks_for_turnover()`. QC_RISK persists in DB until next turnover-level action triggers reconciliation. |

### 3.7 WD Risk

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| WD_RISK flagged when move_in ≤ 7 days + wd_present=False + not notified | **A) Backend enforced** | `risk_engine.evaluate_risks()` line 54 |
| Severity escalation (WARNING at ≤ 7, CRITICAL at ≤ 3) | **A) Backend enforced** | `risk_engine.py:55` |
| Risk reconciliation after WD panel changes | **A) Backend enforced** | `turnover_service.update_wd_panel()` calls `reconcile_risks_for_turnover()` |
| wd_notified_at stamped on notification | **A) Backend enforced** | `turnover_service.update_wd_panel()` sets `wd_notified_at = now_iso` when `wd_supervisor_notified=True` |
| **wd_installed not handled by service** | **C) Partially implemented** | `update_wd_panel()` accepts `wd_present` and `wd_supervisor_notified` but NOT `wd_installed`. Frontend sets `wd_installed` directly on session state dict. No audit trail for wd_installed changes via service layer. |

### 3.8 Confirmation Backlog

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| Flagged when vendor done + not confirmed + age > 2 days | **A) Backend enforced** | `risk_engine.evaluate_risks()` lines 57-69 |
| Severity escalation (WARNING at 3-4 days, CRITICAL at ≥ 5) | **A) Backend enforced** | `risk_engine.py:64-67` |
| **Risk reconciliation after task confirmation** | **D) Missing** | `task_service.confirm_task()` does NOT call `reconcile_risks_for_turnover()`. CONFIRMATION_BACKLOG risk persists until next turnover-level action. |

### 3.9 SLA Breach

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| Backend: calendar days > 10 since move_out + not confirmed → breach | **A) Backend enforced** | `sla_engine.evaluate_sla_state()`, tracked via `sla_event` table |
| SLA event open/close with audit | **A) Backend enforced** | `sla_service.reconcile_sla_for_turnover()` |
| SLA reconciliation after manual ready confirmation | **A) Backend enforced** | `turnover_service.confirm_manual_ready()` calls `reconcile_sla_for_turnover()` |
| **SLA reconciliation triggered on every relevant change** | **C) Partially implemented** | Called by `confirm_manual_ready()` only. NOT called by `set_manual_ready_status()` or after task changes. SLA breach could be stale. |
| Frontend SLA breach | **B) Frontend only** | Uses business days, tests `is_unit_ready` (all tasks done + status), not `manual_ready_confirmed_at` |

### 3.10 Execution Overdue

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| Flagged when vendor_due_date < today + not completed | **A) Backend enforced** | `risk_engine.evaluate_risks()` lines 71-78, severity=WARNING |
| **Risk reconciliation after task execution changes** | **D) Missing** | `task_service.mark_vendor_completed()` does NOT call `reconcile_risks_for_turnover()`. EXECUTION_OVERDUE risk persists. |

### 3.11 Move-Out Disappearance

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| Counter incremented per MOVE_OUTS import for unseen turnovers | **A) Backend enforced** | `import_service.py:569-594` |
| Auto-cancel at missing_moveout_count ≥ 2 | **A) Backend enforced** | `import_service.py:581-589`, sets `canceled_at` + `cancel_reason` |
| Counter reset when seen in import | **A) Backend enforced** | `import_service.py:573-578`, sets `missing_moveout_count=0` |
| Audit trail for auto-cancel | **A) Backend enforced** | Two audit entries: `canceled_at` and `cancel_reason` |

### 3.12 Exposure Risk

| Sub-invariant | Status | Detail |
|---------------|--------|--------|
| EXPOSURE_RISK predicate: report_ready_date passed + not manually confirmed | **C) Partially implemented** | `risk_engine.evaluate_risks()` lines 85-91 computes it. `risk_service.reconcile_risks_for_turnover()` passes the required fields. **BUT schema CHECK (H16) does not include `EXPOSURE_RISK` in the allowed risk_type values.** The INSERT will fail with a constraint violation at runtime. |
| Frontend Plan Breach | **B) Frontend only** | `compute_sla_breaches()`: `report_ready_date passed AND NOT is_unit_ready` — different condition than backend |

---

## Section 4 — Conflicts Between Frontend and Backend

### C1. Lifecycle Phase: move_out_date IS NULL handling

| Layer | Behavior | Code |
|-------|----------|------|
| **Backend** | `move_out_date is None` → always returns `NOTICE` | `lifecycle.py:22-23` |
| **Frontend** | `move_out is None` → returns `NOTICE_SMI` if `move_in` exists, else `NOTICE` | `mock_data_v2.py:333-334` |

**Impact:** A turnover with no move_out but with a move_in would be classified differently. In practice, schema enforces `move_out_date IS NOT NULL` (H2), so this divergence cannot occur with real data. However, it reveals the frontend code was written without relying on that constraint.

### C2. SLA Breach: Different definition

| Layer | Predicate | Day Type | "Ready" Signal |
|-------|-----------|----------|----------------|
| **Backend** | `today - move_out_date > 10 days` AND `manual_ready_confirmed_at IS NULL` | Calendar days | `manual_ready_confirmed_at` (manager stamp) |
| **Frontend** | `is_vacant` AND `NOT is_unit_ready` AND `dv > 10` | Business days | `status == "Vacant ready" AND all 8 exec tasks VENDOR_COMPLETED` |

**Impact:** A turnover vacant for 11 calendar days (including a weekend) might be 9 business days — backend shows breach, frontend does not. A turnover with `manual_ready_confirmed_at` set but tasks incomplete — backend shows no breach, frontend shows breach. These are semantically different signals.

### C3. QC Confirm: Precondition bypass

| Layer | Behavior | Code |
|-------|----------|------|
| **Backend** | `confirm_task()` REQUIRES `execution_status == 'VENDOR_COMPLETED'`. Raises `ValueError` otherwise. | `task_service.py:60-61` |
| **Frontend** | QC confirm button calls `_update_task(task_id, confirm_status="CONFIRMED")` with no execution_status check. Also sets confirm directly from any state via Detail selectbox. | `app_prototype_v2.py:677-680, 831-835` |

**Impact:** Frontend allows confirming a QC task that hasn't been vendor-completed. When wired to backend, this will raise ValueError. Schema CHECK (H10) would also reject the raw UPDATE (confirmed requires vendor_completed_at).

### C4. SLA MoveIn Breach vs QC_RISK: Overlapping but different

| Layer | Predicate | Scope |
|-------|-----------|-------|
| **Backend QC_RISK** | move_in ≤ 3 days + QC task confirmation_status ≠ CONFIRMED | Only QC task |
| **Frontend sla_movein_breach** | move_in ≤ 2 days + NOT is_ready_for_moving (= is_unit_ready + is_move_in_present + is_qc_done) | All tasks + status + QC |

**Impact:** Backend flags QC_RISK even if all other tasks are done and unit is status "Vacant ready". Frontend only flags sla_movein_breach when full readiness is unmet. Backend triggers at 3 days, frontend at 2 days.

### C5. Plan Breach vs EXPOSURE_RISK: Different conditions

| Layer | Predicate |
|-------|-----------|
| **Backend EXPOSURE_RISK** | `report_ready_date ≤ today` AND `manual_ready_confirmed_at IS NULL` |
| **Frontend plan_breach** | `report_ready_date ≤ today` AND `NOT is_unit_ready` (all tasks done + status) |

**Impact:** Backend resolves EXPOSURE_RISK when manager confirms (regardless of task completion). Frontend resolves plan_breach when all tasks are actually done and status is "Vacant ready" (regardless of confirmation stamp).

### C6. Task status changes: No audit, no risk reconciliation

| Layer | Behavior on task status change |
|-------|-------------------------------|
| **Backend** | `mark_vendor_completed()` → audit + timestamp. `confirm_task()` → audit + timestamp + precondition. `reject_task()` → audit + resets execution to IN_PROGRESS. **None of these call `reconcile_risks_for_turnover()`.** |
| **Frontend** | `_update_task()` → direct dict mutation. No audit. No risk reconciliation. No precondition checks. Allows any execution_status → any execution_status and any confirmation_status → any confirmation_status. |

**Impact:** When wired, task changes through the backend service layer will not auto-update risk flags (QC_RISK, CONFIRMATION_BACKLOG, EXECUTION_OVERDUE). Risks will be stale until next turnover-level action (status change, WD update) triggers reconciliation.

### C7. Reject flow: Frontend has no reject capability

| Layer | Behavior |
|-------|----------|
| **Backend** | `task_service.reject_task()` — sets confirmation=REJECTED, execution=IN_PROGRESS, clears manager_confirmed_at |
| **Frontend** | No reject button or flow. The confirmation selectbox can be set to "Rejected" but it only calls `_update_task(confirm_status="REJECTED")` — does NOT reset execution_status or clear manager_confirmed_at |

**Impact:** Frontend "Rejected" status change is incomplete. Backend reject also resets execution to IN_PROGRESS and clears timestamp. These will diverge when wired.

### C8. Risk display: Static vs dynamic

| Layer | Behavior |
|-------|----------|
| **Backend** | `risk_service.reconcile_risks_for_turnover()` dynamically evaluates all risk predicates, upserts/resolves in `risk_flag` table |
| **Frontend** | Detail view reads from `MOCK_RISKS_V2` — hardcoded static list. Risks do not change based on UI actions. |

**Impact:** In the frontend prototype, resolving a risk trigger (e.g., confirming QC or notifying WD) does not clear the risk from the risks panel. When wired, risks will auto-resolve through reconciliation.

---

## Section 5 — Recommendations Before Integration

### 5.1 Must Fix (will cause runtime errors)

| # | Issue | Action |
|---|-------|--------|
| 1 | **EXPOSURE_RISK blocked by schema CHECK (H16)** | Migration: recreate `risk_flag` table with `EXPOSURE_RISK` added to the `risk_type` CHECK constraint. Without this, `risk_service.reconcile_risks_for_turnover()` will crash with a constraint violation whenever the EXPOSURE_RISK predicate is true. |
| 2 | **Frontend QC confirm bypasses execution check (C3)** | Frontend must check `execution_status == 'VENDOR_COMPLETED'` before allowing QC confirmation. Otherwise, `task_service.confirm_task()` will raise ValueError and schema CHECK (H10) will reject the UPDATE. |
| 3 | **Frontend reject does not reset execution (C7)** | When wiring the confirmation selectbox, "Rejected" must call `task_service.reject_task()` which resets execution to IN_PROGRESS and clears `manager_confirmed_at`. Current frontend only changes `confirmation_status`. |

### 5.2 Must Fix (data integrity at risk)

| # | Issue | Action |
|---|-------|--------|
| 4 | **No risk reconciliation after task changes** | Add `reconcile_risks_for_turnover()` call to `task_service.mark_vendor_completed()`, `confirm_task()`, and `reject_task()`. This requires `task_service` to accept `turnover_id` context or create a `turnover_service.reconcile_after_task_change()` wrapper. Without this, QC_RISK, CONFIRMATION_BACKLOG, and EXECUTION_OVERDUE flags will be stale. |
| 5 | **SLA reconciliation only on confirm_manual_ready** | Add `reconcile_sla_for_turnover()` call to `set_manual_ready_status()`. Currently, changing status to "Vacant not ready" from "Vacant ready" does not close or re-evaluate the SLA breach. |
| 6 | **Task dependency order not enforced during execution** | Add dependency check to `mark_vendor_completed()`: verify all `depends_on_task_id` tasks have `execution_status == 'VENDOR_COMPLETED'` before allowing the transition. Currently, any task can be completed regardless of dependency chain. |
| 7 | **`wd_installed` not handled by turnover_service** | Add `wd_installed` parameter to `update_wd_panel()` with audit trail and `wd_installed_at` timestamp. Frontend currently sets this directly without audit. |

### 5.3 Should Fix (behavioral divergence)

| # | Issue | Action |
|---|-------|--------|
| 8 | **Business days vs calendar days (C2)** | Decide on canonical day counting. Backend uses calendar days for SLA. Frontend uses business days for DV, DTBR, SLA. Either: (a) add `business_days()` to domain layer and use everywhere, or (b) document the divergence as intentional — backend SLA is audit-authoritative (calendar), frontend is operational display (business). |
| 9 | **"Ready" definition divergence (C2, C5)** | Backend: `manual_ready_confirmed_at IS NOT NULL`. Frontend: `status == "Vacant ready" AND all tasks complete`. These are complementary but different signals. Document which is authoritative for which purpose. Do not attempt to merge — they answer different questions. |
| 10 | **`attempt_auto_close()` is dead code** | This function exists in `turnover_service.py` but is never called by any other code. Either wire it to a periodic reconciliation loop or remove it. |

### 5.4 Undocumented Invariants Found in Code

These invariants are enforced by code but not documented in the blueprint or any spec:

| # | Invariant | Code Location | Documentation Status |
|---|-----------|--------------|---------------------|
| U1 | **Phase filter: only phases 5, 7, 8 are imported** | `import_service.VALID_PHASES = (5, 7, 8)` + `_filter_phase()` | Not documented |
| U2 | **source_turnover_key format: `{prop}:{unit_norm}:{mo_iso}`** | `import_service.py:417` | Not documented as stable contract |
| U3 | **Auto-close blocked by any CRITICAL risk** | `turnover_service.attempt_auto_close()` line 211 | Not documented |
| U4 | **Reject always resets to IN_PROGRESS** | `task_service.reject_task()` line 93 — hardcoded, not configurable | Not documented |
| U5 | **DMRB import deduplicates by unit_code_norm** | `import_service._parse_dmrb()` — `seen_norm` set skips duplicates | Not documented |
| U6 | **Repository silently drops unknown update fields** | `update_turnover_fields()` / `update_task_fields()` — fields not in whitelist are ignored without error | Not documented. Dangerous: caller may believe a field was updated when it was not. |
| U7 | **SLA_BREACH risk_type exists in schema CHECK but is never emitted** | `risk_engine.evaluate_risks()` never produces `SLA_BREACH`. SLA is tracked exclusively via `sla_event` table. The `SLA_BREACH` slot in `risk_flag.risk_type` CHECK is unused. | Not documented |
| U8 | **WD notification timestamp is one-way** | `update_wd_panel()` sets `wd_notified_at` when notifying but does NOT clear it when un-notifying. Setting `wd_supervisor_notified=False` leaves the old timestamp. | Not documented |
| U9 | **Manual-authoritative field protection** | Import never overwrites `manual_ready_status`, `wd_present`, `wd_supervisor_notified`, `wd_installed`. This is implicit — these fields simply aren't touched by any import branch. | Blueprint §1.6 states this rule but the enforcement is implicit, not explicit guard code. |
| U10 | **Frontend `is_unit_ready` is a compound predicate** | `status == "Vacant ready" AND task_state == "All Tasks Complete"`. The backend has no equivalent compound check. `manual_ready_confirmed_at` is the closest but semantically different. | Not documented as a formal invariant |
| U11 | **Frontend task stall uses hardcoded expected-days constants** | `TASK_EXPECTED_DAYS = {"Insp": 1, "CB": 2, "MRB": 2, "Paint": 2, "MR": 3, "HK": 6, "CC": 7, "FW": 8}` | Not in schema or backend config. Frontend-only magic numbers. |
| U12 | **Checksum includes report_type prefix** | `_sha256_file()` prepends `report_type + "\n"` to file bytes before hashing. Same file imported as different report types will produce different checksums. | Not documented |
