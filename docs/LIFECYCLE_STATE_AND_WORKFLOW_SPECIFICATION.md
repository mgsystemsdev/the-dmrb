# Full Lifecycle State and Workflow Specification

**Document type:** Implementation-ready system specification  
**Purpose:** Single source of truth for lifecycle entry states, lifecycle states, operational layers, report rules, guardrails, exception workflows, and end-to-end manager workflows. Drives implementation without ambiguity.  
**Scope:** No code changes; specification only.  
**Date:** 2025-03-11

---

## 1. Entry States

Entry states describe **where a unit (or unit+report row) sits** before or outside the active turnover execution layer. They are mutually exclusive per unit at a point in time.

| Entry state | Definition | Where it lives | Can transition to |
|-------------|------------|----------------|-------------------|
| **Unit master only** | Unit exists in `unit` (and property/phase/building hierarchy). No turnover. No recent report row referencing it, or report row was applied to another state. | `unit` only. | Report referenced but no turnover (when a report row references the unit and no turnover exists); Move-out known (when MOVE_OUTS row with move_out_date is applied). |
| **Report referenced but no turnover** | Unit exists. At least one `import_row` references the unit (by unit_code_norm) with a non-OK outcome (CONFLICT, INVALID, IGNORED, SKIPPED_OVERRIDE). No row in `turnover` for this unit with closed_at IS NULL and canceled_at IS NULL. | `unit` + `import_row` (and `import_batch`). | Move-in without move-out; Move-out known; Unit master only (if exception is cleared or aged out). |
| **Move-in without move-out** | Subcase of Report referenced but no turnover. Unit has a report row that implies move-in (e.g. PENDING_MOVE_INS with move_in_date) or readiness (AVAILABLE_UNITS, DMRB) but **no** turnover exists because move_out_date was never supplied. conflict_reason in (MOVE_IN_WITHOUT_OPEN_TURNOVER, MOVE_OUT_DATE_MISSING). | `unit` + `import_row` with conflict_reason MOVE_IN_WITHOUT_OPEN_TURNOVER or MOVE_OUT_DATE_MISSING. | Move-out known (when manager resolves by supplying move_out_date and a turnover is created). |
| **Move-out known** | Unit has exactly one **open** turnover (closed_at IS NULL, canceled_at IS NULL) and that turnover has move_out_date set (NOT NULL). This is the only entry state that is **operational** for the board and task execution. | `turnover` (one row per unit with open turnover and move_out_date set). | Active turnover (same as move-out known; “active turnover” is the execution view of this state); Closed/Canceled (when turnover is closed or canceled). |
| **Active turnover** | Same as Move-out known: one open turnover per unit with move_out_date present. Used to mean “this unit is on the board and in the execution loop.” | `turnover` (open, move_out_date NOT NULL). | Closed (attempt_auto_close when move_in_date + 14 days passed and no critical risks); Canceled (e.g. post_process_after_move_outs after move-out disappeared twice). |

**Invariants (implementation must enforce):**

- At most one open turnover per unit (unique index `idx_one_open_turnover_per_unit`).
- Every open turnover row has `move_out_date` NOT NULL (schema + creation paths).
- Units in “Report referenced but no turnover” or “Move-in without move-out” **never** appear on the main board; they appear only in Report Operations (Missing Move-Out queue, Import Diagnostics, or FAS context).

---

## 2. Lifecycle States (Phase / NVM)

Lifecycle states are **derived** from turnover row data and `today`. They drive display (phase label, N/V/M), SLA, and risk. They are computed by `domain/lifecycle.derive_lifecycle_phase` and `domain/enrichment.derive_phase` (when move_out is None, enrichment returns NOTICE or NOTICE_SMI).

| Lifecycle state (phase) | Constant | Condition (effective move_out, move_in, closed_at, canceled_at, today) | NVM label | Board visibility |
|--------------------------|----------|-----------------------------------------------------------------------|-----------|------------------|
| **NOTICE** | NOTICE | move_out_date is None, or today < move_out_date and no move_in yet. | N (Notice) | If on board (only when turnover has move_out_date): pre-move-out. |
| **NOTICE + SMI** | NOTICE_SMI | move_out_date is None and move_in_date is set; or today < move_out_date and move_in_date is set (scheduled). | N (Notice + SMI) | Same. |
| **VACANT** | VACANT | today >= move_out_date; move_in_date is None or today < move_in_date. | V (Vacant) | Yes. |
| **SMI** | SMI | today >= move_out_date and today < move_in_date (scheduled move-in in future). | M (SMI) | Yes. |
| **Move-In (complete)** | MOVE_IN_COMPLETE | move_in_date set and today >= move_in_date and today <= move_in_date + 14 days. | M (Move-In) | Yes. |
| **Move-In (stabilization)** | STABILIZATION | move_in_date set and today > move_in_date and today <= move_in_date + 14 days. | M (Move-In) | Yes. |
| **CLOSED** | CLOSED | closed_at IS NOT NULL. | — | No (excluded from list_open_turnovers). |
| **CANCELED** | CANCELED | canceled_at IS NOT NULL. | — | No (excluded from list_open_turnovers). |

**Effective move-out date (authority order for lifecycle/SLA):**

1. Manager manual override: if move_out_manual_override_at is set and move_out_date is set → use move_out_date.
2. Legal confirmed: if legal_confirmation_source is set → use confirmed_move_out_date.
3. Scheduled: scheduled_move_out_date.
4. Legacy: move_out_date.

**Closed/Canceled and post–move-in:**

- **closed_at:** Set by `attempt_auto_close` when move_in_date is set, today > move_in_date + 14 days, and no critical risks. Once set, turnover is excluded from open turnover list and board.
- **canceled_at:** Set by MOVE_OUTS post_process when unit was not seen in the last two consecutive MOVE_OUTS batches (missing_moveout_count >= 2); cancel_reason = "Move-out disappeared from report twice". Also excludable for other cancel reasons if added later.
- **Post–move-in (before close):** Phases MOVE_IN_COMPLETE and STABILIZATION; still open and on board until auto-close or manual close.

---

## 3. Operational Layers

Three layers define where work happens and what data they see.

| Layer | Purpose | Data scope | Key surfaces |
|-------|---------|------------|--------------|
| **Report Operations** | Reconciliation, diagnostics, report-based workflows. Fix exceptions before they become board work. | import_row (non-OK rows), import_batch; units with no open turnover; PENDING_FAS rows; optional deduplicated diagnostics (all non-OK outcomes). | Missing Move-Out queue, FAS Tracker, Import Diagnostics (to implement). Resolve = create turnover with move_out_date (Missing Move-Out) or add notes (FAS). |
| **Active turnover execution** | Day-to-day execution of turnovers that have move_out_date. Board, tasks, SLA, risk, dates, status. | Open turnovers only (closed_at IS NULL, canceled_at IS NULL); in practice always with move_out_date NOT NULL. | DMRB Board, Flag Bridge, Risk Radar, Turnover Detail. Task updates, date overrides, status, manual overrides, auto-close. |
| **Diagnostics / exception handling** | Observability and triage of why rows were not applied or were conflicted. | import_row joined to import_batch; filter validation_status != 'OK'. Optional: filter by conflict_reason, report_type, date. | Import Diagnostics tab (designed); Admin import console (batch + rows); Report Operations Missing Move-Out (subset of exceptions that are resolvable by adding move-out). |

**Rule:** The board and execution layer **must not** show units that do not have an open turnover with move_out_date. Pre-turn exceptions (move-in without move-out, missing move-out) **must** appear only in Report Operations and diagnostics, not on the main board.

---

## 4. Rules by Report Type

Each report type has deterministic rules. Reports may arrive in **any order**; idempotency is per-batch (checksum). All rows are written to `import_row` with validation_status and, when applicable, conflict_reason.

### 4.1 Available Units

- **Input:** CSV; columns Unit, Status, Available Date, Move-In Ready Date (used: Unit, Status, Move-In Ready Date).
- **Authority:** Treated as **strongest validator of live vacancy/readiness** (product intent). Implementation may enforce precedence over DMRB for report_ready_date/availability_status when both are present (e.g. prefer AVAILABLE_UNITS on conflict or by timestamp; current code does not yet enforce this).
- **When unit not found or no open turnover:** Write import_row with validation_status = IGNORED, conflict_reason = NO_OPEN_TURNOVER_FOR_READY_DATE. Do not create a turnover.
- **When unit has open turnover:** Update turnover: report_ready_date, available_date, availability_status. Respect ready_manual_override_at and status_manual_override_at: if set and incoming value differs → SKIPPED_OVERRIDE, do not overwrite; if set and incoming matches → clear override, apply, audit manual_override_cleared.
- **Outcomes:** OK, IGNORED, SKIPPED_OVERRIDE.

### 4.2 Move-Outs

- **Input:** CSV; columns Unit, Move-Out Date.
- **Only report type that can create a new turnover.** Creation requires: unit exists (or is created via _ensure_unit), unit has no open turnover, and row has a non-null move_out_date.
- **Missing move-out date:** Write import_row with validation_status = INVALID, conflict_flag = 1, conflict_reason = MOVE_OUT_DATE_MISSING. Do not create turnover or unit.
- **Unit has open turnover:** Match by unit. If move_out_date differs and no manual override → CONFLICT, conflict_reason = MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER. If manual override set and incoming matches → clear override, update scheduled_move_out_date, last_seen_moveout_batch_id, missing_moveout_count = 0. If manual override set and incoming differs → skip overwrite (SKIPPED_OVERRIDE).
- **New turnover:** insert_turnover with move_out_date, then instantiate_tasks_for_turnover. Record unit in seen_unit_ids for post_process.
- **Post-process:** For property, all open turnovers not in seen_unit_ids: increment missing_moveout_count; if missing_moveout_count >= 2, set canceled_at and cancel_reason = "Move-out disappeared from report twice".
- **Outcomes:** OK (APPLIED), INVALID, CONFLICT, SKIPPED_OVERRIDE.

### 4.3 Pending Move-Ins

- **Input:** CSV; columns Unit, Move In Date.
- **Never creates a turnover.** Only updates existing open turnover’s move_in_date.
- **Unit not found or no open turnover:** Write import_row with validation_status = CONFLICT, conflict_flag = 1, conflict_reason = MOVE_IN_WITHOUT_OPEN_TURNOVER. Do not create turnover. These rows feed the **repair workflow** (Missing Move-Out queue).
- **Unit has open turnover:** Update move_in_date. Respect move_in_manual_override_at: if set and incoming differs → skip overwrite; if set and incoming matches → clear override, apply.
- **Outcomes:** OK, CONFLICT.

### 4.4 Pending FAS

- **Input:** CSV; columns include Unit Number (as Unit), MO / Cancel Date (or equivalent).
- **Never creates a turnover.** Updates existing open turnover’s legal/confirmed move-out (confirmed_move_out_date, legal_confirmation_source, legal_confirmed_at) when applicable; or used for FAS tracking (notes).
- **Unit not found or no open turnover:** Write import_row with validation_status = IGNORED, conflict_reason = NO_OPEN_TURNOVER_FOR_VALIDATION. Do not create turnover.
- **Unit has open turnover:** Apply FAS confirmation logic (confirm move-out, set legal fields). FAS Tracker in Report Operations shows PENDING_FAS rows and allows notes per unit/fas_date.
- **Outcomes:** OK, IGNORED.

### 4.5 DMRB

- **Input:** Excel sheet "DMRB "; columns Unit, Ready_Date, Move_out, Move_in, Status. Used: Unit, Ready_Date (→ report_ready_date).
- **Never creates a turnover.** Only updates existing open turnover’s report_ready_date and available_date (no availability_status in DMRB).
- **Unit not found or no open turnover:** Write import_row with validation_status = IGNORED, conflict_reason = NO_OPEN_TURNOVER_FOR_READY_DATE.
- **Unit has open turnover:** Update report_ready_date, available_date. Respect ready_manual_override_at (same pattern as AVAILABLE_UNITS).
- **Outcomes:** OK, IGNORED, SKIPPED_OVERRIDE.

### 4.6 Manual creation (Add Availability)

- **Entry:** Admin → Add Unit (or Report Operations → Resolve Missing Move-Out). Input: property, phase_code, building_code, unit_number, move_out_date (required), optional move_in_date, report_ready_date.
- **Rule:** Unit must exist; unit must have no open turnover. move_out_date is required (no default).
- **Action:** create_turnover_and_reconcile → insert_turnover → instantiate_tasks_for_turnover → SLA and risk reconciliation. No import_row written for manual path.
- **Outcomes:** turnover_id or error (e.g. unit has open turnover).

---

## 5. Guardrails

Implementation must enforce the following. Existing code already enforces most; any gap must be closed as specified.

| Guardrail | Rule | Enforcement point(s) |
|-----------|------|----------------------|
| **No operational turnover without move_out_date** | A turnover is operational (board, tasks, SLA) only when move_out_date is present. | Schema: turnover.move_out_date NOT NULL. Creation: MOVE_OUTS skips row when move_out_date is missing; manual creation requires move_out_date. Optional future: list_open_turnovers or get_dmrb_board_rows filter AND move_out_date IS NOT NULL if schema ever allows NULL. |
| **No task scheduling before turnover activation** | Tasks must not be created for a turnover that does not have move_out_date (operational). | MOVE_OUTS: tasks created only after insert_turnover (which already requires move_out_date). Manual: same. reconcile_missing_tasks: **must** filter to open turnovers where move_out_date IS NOT NULL before calling instantiate_tasks_for_turnover. Optional: at start of _instantiate_tasks_for_turnover_impl, load turnover and no-op if move_out_date is NULL. |
| **No duplicate open turnovers** | At most one open turnover per unit. | Unique partial index idx_one_open_turnover_per_unit (WHERE closed_at IS NULL AND canceled_at IS NULL). Creation paths check get_open_turnover_by_unit before insert. |
| **No board pollution from pre-turn exceptions** | Units that have no open turnover, or only report rows with CONFLICT/INVALID/IGNORED, must not appear on the main board. | Board data source is list_open_turnovers only (turnover-based). No turnover ⇒ unit not on board. Exceptions live only in import_row and are surfaced in Report Operations / Import Diagnostics, not on the board. |

---

## 6. Exception Workflows

Exception workflows are the prescribed ways to handle non-OK import outcomes and report-based follow-up.

| Exception workflow | Trigger / data source | Action | Surface |
|--------------------|------------------------|--------|---------|
| **Missing move-out** | import_row where conflict_reason IN (MOVE_IN_WITHOUT_OPEN_TURNOVER, MOVE_OUT_DATE_MISSING) and unit exists and has no open turnover. | Manager selects unit, enters move_out_date, clicks “Create turnover.” System calls add_manual_availability (same as manual creation). Turnover is created; unit appears on board. | Report Operations → Missing Move-Out tab. Resolve UI: select unit, date input, Create turnover. |
| **FAS tracking** | import_row from PENDING_FAS batches; unit exists. | View list of units/dates from PENDING_FAS; add or edit a note per (unit_id, fas_date). Notes stored in fas_tracker_note; persist across imports. | Report Operations → FAS Tracker tab. Edit note, Save. |
| **Import diagnostics** | import_row joined to import_batch where validation_status != 'OK'. Optional deduplication: latest row per (unit_code_norm, report_type). Optional filter: report_type, validation_status, date range, property (via unit). | Observational: view Unit, Report Type, Status, Conflict Reason, Import Time, Source File. No state change from this tab. | Report Operations → Import Diagnostics tab (to implement per IMPORT_DIAGNOSTICS_DESIGN_REPORT). |
| **Move-out date mismatch (open turnover)** | import_row with conflict_reason = MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER. | Manager resolves by either: (1) correcting the report and re-importing, or (2) using Turnover Detail to set manual move-out override to match report, then re-import to clear override; or (3) accepting manual override and leaving as-is. | Visible in Import Diagnostics (and Admin batch rows). No dedicated “resolve” button; resolution is data correction or manual override. |
| **No open turnover for ready date / validation** | import_row with NO_OPEN_TURNOVER_FOR_READY_DATE or NO_OPEN_TURNOVER_FOR_VALIDATION. | Unit may need a turnover first (e.g. resolve via Missing Move-Out if it also appears there with MOVE_OUT_DATE_MISSING or MOVE_IN_WITHOUT_OPEN_TURNOVER). Or unit is in error in the report. | Import Diagnostics; Admin. Resolve indirectly via Missing Move-Out if applicable. |
| **Skipped override** | import_row with validation_status = SKIPPED_OVERRIDE. | Informational: import value differed from manual override; system kept manual value. Manager can clear override in Turnover Detail and re-import to accept report value, or leave override. | Import Diagnostics; Admin batch rows. |
| **Invalid (e.g. parse error, missing required field)** | import_row with validation_status = INVALID (e.g. MOVE_OUT_DATE_MISSING, or schema validation failures). | Fix source data or required field; re-import. Missing move-out rows also appear in Missing Move-Out queue when unit exists and has no open turnover. | Import Diagnostics; Admin; Missing Move-Out (for MOVE_OUT_DATE_MISSING when resolvable). |
| **Unit master import exceptions** | Unit master import (Units.csv) may write conflict/validation reasons (e.g. UNIT_NOT_FOUND_STRICT or parse errors). | Separate from turnover lifecycle; fix unit hierarchy or file and re-import. | Unit Import screen; if stored in import_row, also visible in Import Diagnostics. |

---

## 7. End-to-End Manager Workflow

Canonical patterns for how a manager uses the system across the day. Implementation must support these without requiring a fixed report order.

### 7.1 Morning imports

- **Intent:** Ingest latest reports (any subset: MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS, DMRB) to refresh turnover state and readiness.
- **Steps:** Admin → Import; select report type and file for each report. Each import runs independently (checksum idempotency per batch). No required sequence.
- **Outcomes:** New turnovers from MOVE_OUTS (with move_out_date); updates to move_in_date, report_ready_date, availability, FAS confirmation from other reports. Non-OK rows written to import_row.
- **Follow-up:** Check Report Operations → Missing Move-Out for units that need a move-out date; resolve as needed. Optionally check Import Diagnostics (when implemented) for other exceptions.

### 7.2 Midday imports

- **Intent:** Apply updated reports (e.g. revised Move-Outs, new Pending Move-Ins, updated Available Units).
- **Steps:** Same as morning: Admin → Import per report type. Idempotency by checksum; new batch if file changed.
- **Outcomes:** Same rules as morning. Manual overrides are preserved when import value differs; cleared when import matches.

### 7.3 End-of-day imports

- **Intent:** Final snapshot of the day; reconcile readiness and FAS.
- **Steps:** Same import flow. Optional: run exports (Final Report, DMRB Report, etc.) after imports for handoff or audit.

### 7.4 Repair loop

- **Intent:** Clear pre-turn exceptions so units can become active turnovers and appear on the board.
- **Trigger:** Report Operations → Missing Move-Out queue shows units with MOVE_IN_WITHOUT_OPEN_TURNOVER or MOVE_OUT_DATE_MISSING (unit exists, no open turnover).
- **Steps:** (1) Open Missing Move-Out tab. (2) Select unit. (3) Enter move_out_date. (4) Click “Create turnover.” (5) System creates turnover and tasks; unit appears on board. Repeat for other units.
- **Exit:** When no unresolved missing-move-out exceptions for the active property (or operator chooses to leave some for later).

### 7.5 Turnover execution loop

- **Intent:** Execute work on active turnovers (board), update tasks, dates, status, and close when done.
- **Trigger:** Board shows open turnovers (with move_out_date). Flag Bridge / Risk Radar filter by breach or risk.
- **Steps:** (1) View DMRB Board (or Flag Bridge / Risk Radar). (2) Open Turnover Detail for a unit. (3) Update task status, assignees, dates (move-out, ready, move-in), or manual status. (4) Clear or set manual overrides as needed. (5) When move-in is complete and past stabilization (e.g. move_in_date + 14 days, no critical risks), system may auto-close (attempt_auto_close) or manager closes. (6) Repeat across units; re-import as needed during the day.
- **Exit:** Turnover is closed or canceled; it disappears from the board. New turnover for same unit can appear only after MOVE_OUTS or manual creation with move_out_date.

---

## 8. Implementation Checklist (Summary)

- **Entry states:** Enforce at most one open turnover per unit; move_out_date NOT NULL on turnover; no board rows for units without open turnover.
- **Lifecycle states:** Use domain/lifecycle and domain/enrichment as specified; effective move-out priority; closed_at / canceled_at exclude from board.
- **Operational layers:** Report Operations (Missing Move-Out, FAS Tracker, Import Diagnostics); Board and detail for open turnovers only; diagnostics from import_row.
- **Report rules:** Apply per §4; respect manual overrides; no turnover creation except MOVE_OUTS and manual; post_process_after_move_outs for MOVE_OUTS.
- **Guardrails:** move_out_date required for creation and for task instantiation; reconcile_missing_tasks must filter move_out_date IS NOT NULL; unique open turnover per unit; board from list_open_turnovers only.
- **Exception workflows:** Missing Move-Out resolve → add_manual_availability; FAS Tracker notes; Import Diagnostics tab (implement get_import_diagnostics, get_import_diagnostics_queue, third tab); document other exception resolutions.
- **Manager workflow:** Support arbitrary report order; morning/midday/end-of-day imports; repair loop via Missing Move-Out; execution loop via Board and Detail; auto-close per attempt_auto_close.

This specification is implementation-ready and does not require code changes until implementation is authorized.
