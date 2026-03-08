# Schema Evolution — Coupling & Migration Risk Findings

Read-only analysis. No code. No implementation. No schema changes.

Planned evolution: scheduled vs confirmed move-out; legal_confirmation_source ('fas' | 'manual'); available_date and availability_status; import writing to scheduled_*; derived legal_vacancy_confirmed; manual legal override; main grid unchanged; small legal indicator in grid.

---

## SECTION 1 — Current Coupling Analysis

### 1.1 move_out_date — every read

| File path | Function / context | Exact column usage |
|-----------|-------------------|---------------------|
| the-dmrb/app_prototype.py | (inline filter) | `t.get("move_out_date")` — age > 10 days check |
| the-dmrb/app_prototype.py | render_control_board_1, render_control_board_2, render_turnover_detail | `t.get("move_out_date")`, `row.get("move_out_date")` — display only |
| the-dmrb/app_prototype_v2.py | _fmt_date / grid, date editors | `row.get("move_out_date")`, `t.get("move_out_date")` — display and date input |
| the-dmrb/app.py | (same as app_prototype_v2) | `row.get("move_out_date")`, `t.get("move_out_date")` — display and update_turnover_dates |
| the-dmrb/services/import_service.py | import_report_file (MOVE_OUTS) | `row.get("move_out_date")` (parsed); `open_turnover["move_out_date"]` (compare); insert_turnover `move_out_date`; source_turnover_key uses move_out_iso |
| the-dmrb/services/import_service.py | import_report_file (PENDING_FAS) | `open_turnover["move_out_date"]` — compare to FAS mo_cancel_date |
| the-dmrb/services/manual_availability_service.py | add_manual_availability | Pass-through to turnover_service; source_turnover_key uses move_out_iso |
| the-dmrb/db/repository.py | TURNOVER_UPDATE_COLS, insert_turnover | Column in allowed set and INSERT list |
| the-dmrb/services/turnover_service.py | create_turnover_and_reconcile | `move_out_date` param → insert; passed to reconcile_sla_for_turnover, reconcile_risks_for_turnover |
| the-dmrb/services/turnover_service.py | set_manual_ready_status, confirm_manual_ready, update_wd_panel, update_turnover_dates, reconcile_after_task_change, attempt_auto_close | `row["move_out_date"]` or `_parse_iso_date(row["move_out_date"])` — passed to SLA and risk reconciliation |
| the-dmrb/services/board_query_service.py | _build_flat_row | `turnover.get("move_out_date")` — flat row for grid |
| the-dmrb/domain/lifecycle.py | derive_lifecycle_phase | `move_out_date` param — all phase logic (VACANT, SMI, NOTICE, etc.) |
| the-dmrb/domain/enrichment.py | derive_phase, compute_facts | `t.get("move_out_date")`, `row.get("move_out_date")` — phase, dv (business days since move-out) |
| the-dmrb/domain/sla_engine.py | evaluate_sla_state | `move_out_date` param — breach_active = days_since_move_out > 10 |
| the-dmrb/services/sla_service.py | reconcile_sla_for_turnover | Passes turnover move_out_date to evaluate_sla_state |
| the-dmrb/domain/risk_engine.py | evaluate_risks | `move_out_date` param — not used in current risk rules (only move_in_date, report_ready_date, tasks, wd, etc.) |
| the-dmrb/services/risk_service.py | reconcile_risks_for_turnover | Passes move_out_date from turnover_service callers |
| the-dmrb/tests/test_manual_availability.py | multiple tests | Assertions on `row["move_out_date"]` |

### 1.2 move_in_date — every read

| File path | Function / context | Exact column usage |
|-----------|-------------------|---------------------|
| the-dmrb/app_prototype.py | render_dashboard, render_control_board_*, render_turnover_detail | `t.get("move_in_date")` — display; wd_risk count |
| the-dmrb/app_prototype_v2.py, app.py | grid, date editors, _parse_date | `row.get("move_in_date")`, `t.get("move_in_date")` — display and update_turnover_dates |
| the-dmrb/services/import_service.py | PENDING_MOVE_INS | `row.get("move_in_date")`; `open_turnover["move_in_date"]`; update_turnover_fields move_in_date |
| the-dmrb/db/repository.py | insert_turnover, TURNOVER_UPDATE_COLS | In INSERT and allowed update set |
| the-dmrb/services/manual_availability_service.py | add_manual_availability | Pass-through to turnover_service |
| the-dmrb/services/turnover_service.py | create_turnover_and_reconcile, set_manual_ready_status, confirm_manual_ready, update_wd_panel, update_turnover_dates, reconcile_after_task_change, attempt_auto_close | Read from row or params; passed to risk/SLA; attempt_auto_close: close if today > move_in_date + 14 and no CRITICAL risks |
| the-dmrb/services/board_query_service.py | _build_flat_row, _sort_move_in | `turnover.get("move_in_date")`; sort key for grid |
| the-dmrb/domain/lifecycle.py | derive_lifecycle_phase | `move_in_date` — SMI, STABILIZATION, MOVE_IN_COMPLETE, NOTICE_SMI |
| the-dmrb/domain/enrichment.py | derive_phase, compute_facts, compute_sla_breaches | `row.get("move_in_date")` — phase, dtbr, days_to_move_in, sla_movein_breach |
| the-dmrb/domain/risk_engine.py | evaluate_risks | `move_in_date` — QC_RISK, WD_RISK by days_to_move_in |
| the-dmrb/tests/test_manual_availability.py | tests | Assertions on `row["move_in_date"]` |

### 1.3 report_ready_date — every read

| File path | Function / context | Exact column usage |
|-----------|-------------------|---------------------|
| the-dmrb/app_prototype.py | render_control_board_1 | `t.get("report_ready_date")` — display |
| the-dmrb/app_prototype_v2.py, app.py | grid, date editors | `row.get("report_ready_date")`, `t.get("report_ready_date")` — display and update_turnover_dates |
| the-dmrb/services/import_service.py | AVAILABLE_UNITS, DMRB | `row.get("report_ready_date")`; `open_turnover["report_ready_date"]`; update_turnover_fields report_ready_date |
| the-dmrb/db/repository.py | insert_turnover, TURNOVER_UPDATE_COLS | In INSERT and allowed set |
| the-dmrb/services/manual_availability_service.py | add_manual_availability | Pass-through |
| the-dmrb/services/turnover_service.py | create_turnover_and_reconcile, update_turnover_dates | Write path; risk_service reads from turnover row |
| the-dmrb/services/board_query_service.py | _build_flat_row | `turnover.get("report_ready_date")` |
| the-dmrb/domain/enrichment.py | compute_facts, compute_sla_breaches | `row.get("report_ready_date")` — is_ready_declared; plan_breach (today >= report_ready_date and not is_unit_ready) |
| the-dmrb/domain/risk_engine.py | evaluate_risks | report_ready_date + manual_ready_confirmed_at — EXPOSURE_RISK |
| the-dmrb/services/risk_service.py | reconcile_risks_for_turnover | Reads turnover_row["report_ready_date"] for risk_engine |

### 1.4 status (manual_ready_status) — every read

| File path | Function / context | Exact column usage |
|-----------|-------------------|---------------------|
| the-dmrb/app_prototype.py | _update_turnover_status, render_*, render_turnover_detail | `t.get("manual_ready_status")`, `row.get("manual_ready_status")` — compare and display |
| the-dmrb/app_prototype_v2.py, app.py | _update_turnover_status, grid, detail, set_manual_ready_status call | `row.get("manual_ready_status")`, `t.get("manual_ready_status")` — display, filter, status selectbox |
| the-dmrb/db/repository.py | insert_turnover, TURNOVER_UPDATE_COLS | data.get("manual_ready_status") in INSERT |
| the-dmrb/services/turnover_service.py | set_manual_ready_status | row["manual_ready_status"] old value; update to new |
| the-dmrb/services/board_query_service.py | _build_flat_row, filter | `turnover.get("manual_ready_status")` or "Vacant not ready"; filter_status compared to row |
| the-dmrb/domain/enrichment.py | compute_intelligence | `(row.get("manual_ready_status") or "").lower() == "vacant ready"` — is_unit_ready |
| the-dmrb/ui/mock_data.py, mock_data_v2.py | MOCK_TURNOVERS, get_dmrb_board_rows, filter | manual_ready_status in mock rows and filter logic |
| the-dmrb/tests/test_truth_safety.py | test_set_manual_ready_status_triggers_sla | set_manual_ready_status call |

### 1.5 Turnover queried for grid display

| File path | Function name | What is read (turnover columns) |
|-----------|----------------|---------------------------------|
| the-dmrb/services/board_query_service.py | list_open_turnovers | phase_ids or property_ids → list_open_turnovers |
| the-dmrb/services/board_query_service.py | get_dmrb_board_rows | turnovers from list_open_turnovers; for each: unit_id, then _build_flat_row(turnover, unit, tasks, notes) → move_out_date, move_in_date, report_ready_date, manual_ready_status, closed_at, canceled_at, wd_* |
| the-dmrb/services/board_query_service.py | get_flag_bridge_rows | Calls get_dmrb_board_rows; filters by breach keys from enriched row |
| the-dmrb/services/board_query_service.py | get_turnover_detail | get_turnover_by_id → full turnover row; _build_flat_row for enriched_fields |
| the-dmrb/db/repository.py | list_open_turnovers | SELECT * FROM turnover WHERE (phase_ids or property_ids) AND closed_at IS NULL AND canceled_at IS NULL |
| the-dmrb/db/repository.py | list_open_turnovers_by_property | Same filter by property_id |
| the-dmrb/app.py, app_prototype_v2.py | render_dmrb_board | Rows from board_query_service.get_dmrb_board_rows (or mock); columns displayed include Move-Out, Ready Date, Move-In, Status (manual_ready_status) |
| the-dmrb/app_prototype.py | _get_filtered_turnovers, render_dashboard, render_control_board_1, render_control_board_2 | mock_data.get_turnovers_for_dashboard(session_state.turnovers); table columns include move_out_date, move_in_date, report_ready_date, manual_ready_status |

---

## SECTION 2 — Import Logic Impact

### MOVE_OUTS

1. **Where the write to turnover is performed**
   - **Existing open turnover, same move_out_date:** `repository.update_turnover_fields(conn, open_turnover["turnover_id"], { "last_seen_moveout_batch_id": batch_id, "missing_moveout_count": 0, "updated_at": now_iso })`. No write to move_out_date.
   - **No open turnover:** `repository.insert_turnover(conn, { ..., "move_out_date": move_out_iso, "move_in_date": None, "report_ready_date": None, ... })`. Then `_instantiate_tasks_for_turnover_impl`.

2. **Other fields indirectly updated**
   - last_seen_moveout_batch_id, missing_moveout_count, updated_at (when matching).
   - **Post-loop:** For every open turnover *not* in seen_unit_ids_move_outs: missing_moveout_count incremented; if >= 2, turnover gets canceled_at, cancel_reason, updated_at, and audit.

3. **Assumptions about move_out_date being singular**
   - **Single authoritative move_out_date:** Open turnover is matched by unit only; then `existing_move_out = open_turnover["move_out_date"]` is compared to file move_out_iso. If different → CONFLICT (no update). So the design assumes one move-out date per open turnover.
   - **New turnover key:** `source_turnover_key = f"{property_id}:{row['unit_norm']}:{move_out_iso}"` — move_out date is part of the unique business key. Splitting scheduled vs confirmed would require a decision: does key stay on scheduled, confirmed, or something else?
   - **Cancel logic:** “Move-out disappeared from report twice” uses missing_moveout_count only; it does not re-read move_out_date.

### PENDING_MOVE_INS (move-in)

1. **Where the write to turnover is performed**
   - When unit exists and has open turnover: `repository.update_turnover_fields(conn, open_turnover["turnover_id"], { "move_in_date": move_in_iso, "updated_at": now_iso })` when value changed; audit on move_in_date.

2. **Other fields indirectly updated**
   - updated_at; audit_log (field_name move_in_date, source import).

3. **Assumptions about move_out_date**
   - None directly. Open turnover is found by unit; move_in_date is the only date written. move_out_date is not read or written in this branch.

### AVAILABLE_UNITS / DMRB (availability / ready date)

1. **Where the write to turnover is performed**
   - When unit has open turnover and row has report_ready_date: `repository.update_turnover_fields(conn, open_turnover["turnover_id"], { "report_ready_date": ready_iso, "updated_at": now_iso })`; audit report_ready_date.

2. **Other fields indirectly updated**
   - updated_at; audit_log (report_ready_date, source import).

3. **Assumptions about move_out_date**
   - None. Matching is by unit → open turnover. No move_out_date read or write. (AVAILABLE_UNITS CSV has “Status” and “Available Date” but import only maps “Move-In Ready Date” → report_ready_date; Status is not written to turnover.)

### PENDING_FAS

1. **Where the write to turnover is performed**
   - **Nowhere.** No update to turnover. Only import_row is written with validation_status OK or CONFLICT (PENDING_FAS_MOVE_OUT_MISMATCH when mo_cancel_date != turnover_move_out).

2. **Other fields indirectly updated**
   - None.

3. **Assumptions about move_out_date being singular**
   - `turnover_move_out = open_turnover["move_out_date"]` is compared to FAS mo_cancel_date. Single move-out field is assumed. If FAS were to *write* to turnover (e.g. confirmed_move_out_date or legal_confirmation_source), that would be a new write path and must define how it interacts with existing move_out_date and any new scheduled/confirmed split.

---

## SECTION 3 — Constraints & Index Risks

### 3.1 All UNIQUE constraints

- **turnover:** `source_turnover_key` TEXT NOT NULL UNIQUE.
- **turnover (partial):** `idx_one_open_turnover_per_unit` UNIQUE(unit_id) WHERE closed_at IS NULL AND canceled_at IS NULL.
- **unit:** UNIQUE(property_id, unit_code_norm); after 004 UNIQUE(property_id, unit_identity_key).
- **task_template:** UNIQUE(property_id, task_type, is_active); after 008 UNIQUE(phase_id, task_type, is_active).
- **task:** UNIQUE(turnover_id, task_type).
- **import_batch:** UNIQUE(checksum).
- **phase:** UNIQUE(property_id, phase_code).
- **building:** UNIQUE(phase_id, building_code).

### 3.2 Partial indexes

- **turnover:** idx_one_open_turnover_per_unit ON turnover(unit_id) WHERE closed_at IS NULL AND canceled_at IS NULL.
- **risk_flag:** idx_one_active_risk_per_type ON risk_flag(turnover_id, risk_type) WHERE resolved_at IS NULL.
- **sla_event:** idx_one_open_sla_breach ON sla_event(turnover_id) WHERE breach_resolved_at IS NULL.

### 3.3 Foreign keys (turnover-relevant)

- turnover.property_id → property; turnover.unit_id → unit; turnover.last_seen_moveout_batch_id → import_batch.
- task.turnover_id → turnover; note, risk_flag, sla_event → turnover.

### 3.4 CHECK constraints (turnover)

- move_out_date IS NOT NULL.
- NOT (closed_at IS NOT NULL AND canceled_at IS NULL).
- manual_ready_status IN ('Vacant ready', 'Vacant not ready', 'On notice') OR NULL.
- expedited_flag, wd_*, INTEGER 0/1 checks.

### 3.5 Queries depending on open turnover state

- **list_open_turnovers**, **list_open_turnovers_by_property:** WHERE closed_at IS NULL AND canceled_at IS NULL (and property/phase filter).
- **get_open_turnover_by_unit:** WHERE unit_id = ? AND closed_at IS NULL AND canceled_at IS NULL.
- **idx_one_open_turnover_per_unit:** Enforces at most one row per unit with closed_at IS NULL AND canceled_at IS NULL.

### 3.6 Would new columns conflict?

- **scheduled_move_out_date, confirmed_move_out_date, legal_confirmation_source:** Adding nullable columns does not conflict with existing UNIQUE or partial indexes. The partial index is on (unit_id) and open state only; no date or source column is part of it.
- **One open turnover per unit:** Unchanged. The partial unique index remains on unit_id + closed_at/canceled_at. New date/source columns do not affect it.
- **source_turnover_key:** Today it is built from property_id, unit_norm, and move_out_iso (import) or manual:... (manual). If move_out is split:
  - Key could stay on scheduled (or on “effective” for display), or key could include which date is used. Changing the key format could affect idempotency (same file re-import) and manual/import reconciliation; must be defined so one-open-per-unit and key uniqueness still hold.
- **CHECK(move_out_date IS NOT NULL):** If move_out_date is deprecated in favor of scheduled/confirmed, this CHECK must be relaxed or satisfied by a new NOT NULL column (e.g. effective_move_out_date or scheduled_move_out_date NOT NULL) to avoid breaking inserts.

---

## SECTION 4 — State Logic Dependencies

### 4.1 Logic inferring legal vacancy from move_out_date

- **domain/lifecycle.py:** `derive_lifecycle_phase` uses move_out_date (and move_in_date, closed_at, canceled_at, today). “Vacancy” in lifecycle terms is phase VACANT when today >= move_out_date and (move_in_date is None or today < move_in_date). There is no separate “legal vacancy” or FAS confirmation; vacancy is purely date-based from the single move_out_date.
- **domain/sla_engine.py:** `evaluate_sla_state` uses move_out_date for breach: breach_active when today > move_out_date and days_since_move_out > 10 and manual_ready_confirmed_at is None. No FAS or legal flag.
- **domain/enrichment.py:** derive_phase and compute_facts use move_out_date for phase and dv (business days since move-out). No legal or FAS distinction.

So: **legal vacancy is not currently inferred anywhere.** move_out_date is treated as the single operational move-out date for phase, SLA, and grid. Introducing legal_vacancy_confirmed or confirmed_move_out_date would require this logic to use “confirmed” (or effective) move-out where appropriate instead of the current single column.

### 4.2 Readiness from report_ready_date alone

- **domain/enrichment.py:** `is_ready_declared = row.get("report_ready_date") is not None`. Used in compute_facts. Then `is_unit_ready = (manual_ready_status == "vacant ready" and task_state == "All Tasks Complete")`. So “readiness” for display/state is manual_ready_status + tasks, not report_ready_date alone. report_ready_date drives:
  - **plan_breach:** report_ready_date is not None and today >= report_ready_date and not is_unit_ready.
  - **domain/risk_engine.py EXPOSURE_RISK:** report_ready_date set and today >= report_ready_date and manual_ready_confirmed_at is None.
- So: **Readiness (is_unit_ready) is not inferred from report_ready_date alone** — it’s manual_ready_status + tasks. report_ready_date is used for breach and exposure risk, not for “unit is ready” display.

### 4.3 Workflow state from absence of FAS

- **No logic infers workflow state from “FAS absent.”** PENDING_FAS import only validates (compare mo_cancel_date to move_out_date) and writes import_row. No turnover column is set from FAS. So there is no current dependency on “FAS has run” or “FAS confirmed” for any state; adding FAS as a writer (e.g. confirmed_move_out_date, legal_confirmation_source='fas') would be new behavior.

### 4.4 Closing turnover and move_out_date

- **attempt_auto_close (turnover_service):** Does not use move_out_date. It uses move_in_date only: if today > move_in_date + 14 days and no CRITICAL risks, set closed_at. So **closing does not depend on move_out_date**.
- **Cancel path (import MOVE_OUTS):** When missing_moveout_count >= 2, turnover is canceled (canceled_at, cancel_reason). No re-read of move_out_date.
- **Manual close:** Not shown in the reviewed code; only attempt_auto_close sets closed_at. So no other close logic depends on move_out_date.

---

## SECTION 5 — Migration Risk Surface

### 5.1 If move_out_date stops being authoritative

- **Lifecycle phase (domain/lifecycle, enrichment):** All phase and N/V/M logic uses move_out_date. If “authoritative” becomes confirmed_move_out_date (or an effective date), every caller that passes move_out_date into derive_lifecycle_phase, derive_phase, compute_facts must pass the new authoritative value (or a compatibility layer must expose “effective_move_out_date” = confirmed else scheduled).
- **SLA (sla_engine, sla_service):** evaluate_sla_state(move_out_date=...) is called with turnover’s move_out_date. If authority shifts to confirmed, SLA must use confirmed (or effective) for “days since move-out” and breach logic, or breach behavior will be wrong.
- **Import (import_service):** MOVE_OUTS compares and writes move_out_date; source_turnover_key embeds it. If imports write to scheduled_move_out_date only, then: (1) existing code reading move_out_date for phase/SLA/grid must read from scheduled or from a derived “effective” column; (2) key format may need to use scheduled date to preserve idempotency.
- **Grid and detail (board_query_service, app):** _build_flat_row and UI show move_out_date. If the grid is to stay unchanged, the column can continue to show “move out” as effective/confirmed or scheduled (product decision); backend must provide that single value from the new model (e.g. computed column or chosen column).
- **Risk engine:** move_out_date is passed in but not used in current evaluate_risks rules. Lower risk.
- **Repository and insert_turnover:** CHECK(move_out_date IS NOT NULL) and insert_turnover(data["move_out_date"]) would need to be updated if move_out_date is deprecated: e.g. allow NULL and require scheduled_move_out_date NOT NULL, or keep move_out_date as computed/default for backward compatibility during transition.

### 5.2 If FAS begins writing to turnover

- **New write path:** Today PENDING_FAS does not update turnover. Writing FAS data (e.g. confirmed_move_out_date, legal_confirmation_source='fas') would require: (1) matching open turnover by unit (and possibly scheduled date); (2) conflict rule when FAS date differs from existing confirmed or scheduled; (3) audit with source='import' and correlation to batch.
- **Conflict with manual:** If manual legal override can set confirmed_move_out_date or legal_confirmation_source='manual', then FAS write must respect “manual wins” or “last write wins” or timestamp; otherwise manual override could be overwritten by next FAS import.
- **Key and idempotency:** source_turnover_key today does not include FAS. If FAS only updates existing rows and does not create turnover, key uniqueness is unaffected. If FAS could create a turnover (currently it does not), key format would need to be defined.

### 5.3 If manual legal override is introduced

- **Override target:** e.g. confirmed_move_out_date and/or legal_confirmation_source='manual'. Same table as import; no overlay table today. So manual override would UPDATE turnover and audit with source='manual'.
- **Import overwrite:** Per Section 4 of STRUCTURED_FINDINGS, import can overwrite move_in_date and report_ready_date; there is no “manual-authoritative” guard. If manual legal override is authoritative, import (and FAS) must not overwrite confirmed_move_out_date or legal_confirmation_source when set by manual (e.g. skip update when legal_confirmation_source='manual' or when a manual_override_at timestamp is set).
- **SLA/risk:** Once confirmed_move_out_date or legal_vacancy_confirmed exists, SLA and risk logic that today use move_out_date must switch to using confirmed (or effective) for “legal vacancy” and breach; otherwise manual override would not affect SLA/risk behavior.

### 5.4 Background jobs, task triggers, SLA, risk

- **SLA:** reconcile_sla_for_turnover is called from turnover_service (create, set_manual_ready_status, confirm_manual_ready, update_wd_panel, update_turnover_dates, reconcile_after_task_change). It uses move_out_date and manual_ready_confirmed_at. No background job; all synchronous. If move_out_date is replaced by effective/confirmed, SLA must use that.
- **Risk:** reconcile_risks_for_turnover is called from the same turnover_service entry points; it loads report_ready_date and manual_ready_confirmed_at from the turnover row and receives move_in_date, move_out_date from caller. So risk already depends on turnover row + passed dates. Any switch to confirmed_move_out_date or legal_vacancy_confirmed must be reflected in what is passed and/or read from the row.
- **attempt_auto_close:** Not called by any code path (dead code). Uses move_in_date only. No move_out_date dependency for close.
- **No other background jobs or task triggers** that depend on move_out_date were found in the reviewed code.

---

## SECTION 6 — Recommended Migration Safeguards

### 6.1 What must be staged carefully

- **Domain and services:** lifecycle (derive_lifecycle_phase), sla_engine (evaluate_sla_state), enrichment (derive_phase, compute_facts, compute_sla_breaches) all take move_out_date. Introduce a single notion of “effective move-out date” (e.g. confirmed_move_out_date if set else scheduled_move_out_date) and pass that wherever move_out_date is currently used for phase, SLA, breach, and grid. Stage so that: (1) new columns exist and are populated (scheduled from current move_out_date, confirmed/FAS/manual as per product rules); (2) one release uses effective in domain/services but still writes move_out_date for backward compatibility; (3) then grid/API can switch to showing effective (or separate columns) and finally deprecate move_out_date.
- **Import:** MOVE_OUTS and PENDING_FAS. MOVE_OUTS: decide whether to write scheduled_move_out_date only and leave confirmed to FAS/manual, and whether source_turnover_key stays on scheduled date. PENDING_FAS: add write to turnover (confirmed_move_out_date, legal_confirmation_source='fas') only when product rules are clear (e.g. only when no manual override). Stage so that FAS write is additive (new columns) and does not overwrite manual override.
- **Manual legal override:** New UI and turnover_service API to set confirmed_move_out_date and/or legal_confirmation_source='manual'. Ensure audit_log and any “manual override” flag or timestamp so import can skip overwriting.

### 6.2 What must be dual-written temporarily

- **turnover:** During transition, keep writing move_out_date from existing code paths (import, manual availability, update_turnover_dates) so that readers that still use move_out_date do not break. New paths (scheduled_move_out_date, confirmed_move_out_date, legal_confirmation_source) should be written in parallel where applicable: e.g. MOVE_OUTS sets scheduled_move_out_date and, until deprecated, move_out_date = same value; FAS sets confirmed_move_out_date and legal_confirmation_source='fas'; manual override sets confirmed_move_out_date and legal_confirmation_source='manual'. So both old and new columns are populated until all readers use “effective” or new columns and move_out_date can be deprecated.
- **available_date / availability_status:** If these are added, any place that currently infers “availability” from report_ready_date or manual_ready_status may need to read from the new fields once they exist; during transition, dual-write from existing import (e.g. AVAILABLE_UNITS) and from manual status so that old and new semantics stay in sync.

### 6.3 What must remain backward compatible until switch

- **Repository and schema:** insert_turnover and update_turnover_fields today use move_out_date. Until all callers are migrated, keep move_out_date in INSERT/UPDATE and satisfy CHECK(move_out_date IS NOT NULL) (e.g. by defaulting move_out_date from scheduled_move_out_date when present). Backward compatibility: any code that only reads move_out_date continues to see a valid value (scheduled or effective).
- **Board query and grid:** _build_flat_row returns move_out_date, move_in_date, report_ready_date, manual_ready_status. To keep the main grid unchanged, keep these keys in the flat row; the values can be sourced from new columns (e.g. effective_move_out_date) so that grid code does not need to change. Detail and “legal indicator” can add new keys (e.g. legal_confirmation_source, legal_vacancy_confirmed) without removing existing ones.
- **Tests:** test_manual_availability and any test that asserts on move_out_date or insert_turnover shape must still pass; either keep move_out_date populated or add test-only compatibility (e.g. set move_out_date from scheduled in test fixtures) until tests are updated to assert on new columns.

### 6.4 Rollback hazards

- **Schema:** If a migration adds NOT NULL columns (e.g. scheduled_move_out_date) and backfills from move_out_date, rollback would require a reverse migration that either drops the new columns or nulls them. If application code already writes only to new columns and not to move_out_date, rolling back code without rolling back schema could leave move_out_date stale or NULL and break CHECK or readers.
- **Key format:** If source_turnover_key is changed to use scheduled (or confirmed) date, re-import of the same file could create a second row (different key) if rollback reverts key logic but not schema. So key format change should be done only after scheduled/confirmed are stable and idempotency is re-verified.
- **FAS write:** Once FAS writes to turnover, rollback of that write path without rolling back schema leaves confirmed_move_out_date and legal_confirmation_source in the DB; old code that does not read them is unaffected, but if new code is rolled back, those columns become unused until a later release. No data loss if rollback is code-only; if a migration is rolled back, FAS-written values could be lost unless a reverse migration copies them somewhere.
- **Manual override:** If manual override is implemented and then rolled back, any “manual wins” logic in import must be removed so that import does not skip updates incorrectly; otherwise behavior is inconsistent.

---

End of findings.
