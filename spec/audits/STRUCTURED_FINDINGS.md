# Structured Findings — DMRB Project & Database Schema

Read-only analysis. No modifications. No refactors. No recommendations.

---

## SECTION 1 — Database Schema Mapping

### Tables (canonical schema + migrations 001–008)

| Table | Primary key | Unique constraints | Foreign keys | Move-in | Move-out | Availability / ready | Timestamps | Source indicators |
|-------|-------------|--------------------|--------------|---------|----------|----------------------|------------|-------------------|
| **property** | property_id | (none) | (none) | — | — | — | — | — |
| **unit** | unit_id | UNIQUE(property_id, unit_code_norm); after 004: UNIQUE(property_id, unit_identity_key); CHECK(unit_code_norm <> '') | property_id → property; (007) phase_id → phase, building_id → building | — | — | — | — | — |
| **turnover** | turnover_id | UNIQUE(source_turnover_key); partial UNIQUE(unit_id) WHERE closed_at IS NULL AND canceled_at IS NULL | property_id, unit_id, last_seen_moveout_batch_id → import_batch | move_in_date | move_out_date (NOT NULL) | report_ready_date, manual_ready_status, manual_ready_confirmed_at | created_at, updated_at; wd_notified_at, wd_installed_at; closed_at, canceled_at | source_turnover_key (format: import `{prop}:{unit_norm}:{date}` or manual `manual:{prop}:{key}:{date}`); last_seen_moveout_batch_id |
| **task_template** | template_id | UNIQUE(property_id, task_type, is_active); after 008: UNIQUE(phase_id, task_type, is_active) | property_id → property; (008) phase_id → phase | — | — | — | — | — |
| **task_template_dependency** | (template_id, depends_on_template_id) | PK | template_id, depends_on_template_id → task_template | — | — | — | — | — |
| **task** | task_id | UNIQUE(turnover_id, task_type) | turnover_id → turnover | — | — | — | scheduled_date, vendor_due_date, vendor_completed_at, manager_confirmed_at | — |
| **task_dependency** | (task_id, depends_on_task_id) | PK | task_id, depends_on_task_id → task | — | — | — | — | — |
| **turnover_task_override** | (turnover_id, task_type) | PK | turnover_id → turnover | — | — | — | — | — |
| **note** | note_id | (none) | turnover_id → turnover | — | — | — | created_at, resolved_at | — |
| **risk_flag** | risk_id | Partial UNIQUE(turnover_id, risk_type) WHERE resolved_at IS NULL | turnover_id → turnover | — | — | — | triggered_at, resolved_at | — |
| **sla_event** | sla_event_id | Partial UNIQUE(turnover_id) WHERE breach_resolved_at IS NULL | turnover_id → turnover | — | — | — | breach_started_at, breach_resolved_at | — |
| **audit_log** | audit_id | (none) | (none) | — | — | — | changed_at | source TEXT NOT NULL CHECK(source IN ('manual', 'import', 'system')) |
| **import_batch** | batch_id | UNIQUE(checksum) | (none) | — | — | — | imported_at | report_type, source_file_name |
| **import_row** | row_id | (none) | batch_id → import_batch | move_in_date (payload) | move_out_date (payload) | (none) | (none) | validation_status, conflict_flag, conflict_reason |
| **schema_version** | singleton | CHECK(singleton=1) | (none) | — | — | — | — | — |
| **phase** (005) | phase_id | UNIQUE(property_id, phase_code) | property_id → property | — | — | — | — | — |
| **building** (005) | building_id | UNIQUE(phase_id, building_code) | phase_id → phase | — | — | — | — | — |

### Column details (date/availability/timestamps/source)

- **turnover**
  - Move-in: `move_in_date` (TEXT, nullable).
  - Move-out: `move_out_date` (TEXT NOT NULL).
  - Availability/ready: `report_ready_date` (TEXT), `manual_ready_status` (TEXT, CHECK: 'Vacant ready' | 'Vacant not ready' | 'On notice' or NULL), `manual_ready_confirmed_at` (TEXT).
  - Timestamps: `created_at`, `updated_at` (NOT NULL); `wd_notified_at`, `wd_installed_at`; `closed_at`, `canceled_at`.
  - Source: `source_turnover_key` (NOT NULL UNIQUE); `last_seen_moveout_batch_id` (FK to import_batch).
  - Migration 003: `wd_present_type` (TEXT, nullable).

- **import_row**
  - Move-in/move-out: `move_out_date`, `move_in_date` (payload from file; nullable).
  - Source/validation: `validation_status`, `conflict_flag`, `conflict_reason`.

- **task**
  - Timestamps: `scheduled_date`, `vendor_due_date`, `vendor_completed_at`, `manager_confirmed_at`.

- **audit_log**
  - Timestamp: `changed_at`.
  - Source: `source` CHECK ('manual', 'import', 'system').

- **unit**
  - No move-in, move-out, availability, or ready date columns. No created_at/updated_at. Identity: `unit_code_norm`, `unit_identity_key` (004), `phase_code`, `building_code`, `unit_number` (004); hierarchy: `phase_id`, `building_id` (007).

---

## SECTION 2 — Entity Identity & Relationships

### 1. Core identity entity

**Unit** is the core identity entity for physical dwellings. Uniqueness is by `(property_id, unit_code_norm)` and, after migration 004, also by `(property_id, unit_identity_key)` (phase_code, building_code, unit_number).

**Turnover** is the lifecycle entity: one open turnover per unit (enforced by partial unique index). Identity for turnover row: `turnover_id` (PK); business key: `source_turnover_key` (UNIQUE).

### 2. One row per unit?

**Unit:** Yes — one row per unit per property. UNIQUE(property_id, unit_code_norm) and UNIQUE(property_id, unit_identity_key) enforce one row per logical unit.

**Turnover:** No — a unit can have many turnovers over time, but at most one *open* (closed_at IS NULL AND canceled_at IS NULL) at a time. Historical turnovers are retained (closed_at or canceled_at set).

### 3. Historical records

- **Turnover:** Historical records are stored. Rows are not deleted; turnover is “ended” via `closed_at` or `canceled_at`. Open state is “no closed_at and no canceled_at.”
- **Task, note, risk_flag, sla_event:** Append/update in place; resolved/closed state via resolved_at, breach_resolved_at, etc. No table is “current state only” with history discarded.
- **audit_log, import_batch, import_row:** Append-only; no UPDATE/DELETE in v1.

### 4. UNIQUE constraints involving unit + date, unit + resident, unit + status

- **unit + date:** None. There is no UNIQUE(unit_id, date) or (unit_id, move_out_date). The partial unique is (unit_id) WHERE open only — i.e. one open turnover per unit.
- **unit + resident:** No “resident” entity in schema. No such constraint.
- **unit + status:** No UNIQUE(unit_id, status). Only partial UNIQUE(unit_id) WHERE closed_at IS NULL AND canceled_at IS NULL (one open turnover per unit).

---

## SECTION 3 — Import Logic Mapping

### 1. Turnover/operational imports — `services/import_service.py`

- **File path:** `the-dmrb/services/import_service.py`
- **Report types:** MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS, DMRB. Input: CSV (MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS) or Excel sheet "DMRB " (DMRB).
- **Matching to existing records:**
  - Unit: by normalized unit code → `get_unit_by_norm(conn, property_id, unit_code_norm)` or, for MOVE_OUTS, `_ensure_unit` (get or create via phase/building/unit_number/unit_identity_key).
  - Turnover: by unit → `get_open_turnover_by_unit(conn, unit_id)` (at most one open per unit).
- **Mode:** **Diff-based / conditional update.** Not full replace, not delete+insert. Per report type:
  - **MOVE_OUTS:** If no open turnover → insert new turnover + tasks; if open turnover exists and same move_out_date → update last_seen_moveout_batch_id, missing_moveout_count; if open exists and different move_out_date → conflict (write import_row only, no update). After processing all rows, open turnovers not seen in this batch get missing_moveout_count incremented; if ≥ 2, turnover is canceled.
  - **PENDING_MOVE_INS:** Open turnover must exist; update turnover.move_in_date if different.
  - **AVAILABLE_UNITS / DMRB:** Open turnover must exist; update turnover.report_ready_date if different.
  - **PENDING_FAS:** No write to turnover; validation only (compare mo_cancel_date to open turnover move_out_date); write import_row with CONFLICT or OK.
- **Record identity (turnover):** For new turnover: `source_turnover_key = f"{property_id}:{unit_norm}:{move_out_iso}"`. Existing turnover identified by unit_id + “open” (no closed_at, no canceled_at).
- **Conflict resolution:** Conflicts do not overwrite. Rows with CONFLICT or INVALID are written to import_row with conflict_flag=1 and conflict_reason; turnover is not updated (e.g. MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER, MOVE_IN_WITHOUT_OPEN_TURNOVER, PENDING_FAS_MOVE_OUT_MISMATCH).
- **Latest-update wins:** When there is no conflict, import overwrites the field (e.g. move_in_date, report_ready_date) with the value from the file. No timestamp comparison; the current import run’s value is applied.

**Idempotency:** Same file content → same checksum; `get_import_batch_by_checksum` returns existing batch → NO_OP, no changes.

---

### 2. Unit Master import — `services/unit_master_import_service.py`

- **File path:** `the-dmrb/services/unit_master_import_service.py`
- **Input:** CSV (e.g. Units.csv), skip 4 rows; columns Unit, Floor Plan, Gross Sq. Ft.
- **Matching:** Unit by `(property_id, unit_identity_key)` (from parse of Unit → phase_code, building_code, unit_number → compose_identity_key). strict_mode: lookup only (get_unit_by_identity_key). Non-strict: get-or-create via `resolve_unit(..., phase_code, building_code, unit_number, ...)`.
- **Mode:** **Upsert.** Get or create unit; then update unit fields (floor_plan, gross_sq_ft, unit_code_raw) only if value differs. No delete; no full replace.
- **Record identity:** Unit: (property_id, unit_identity_key). Unit Master does not touch turnover/task.
- **Conflict resolution:** strict_mode: if unit not found → CONFLICT, conflict_reason UNIT_NOT_FOUND_STRICT. Parse errors → INVALID, conflict_reason = parse_error. No overwrite of manual vs import at schema level.
- **Latest-update wins:** For unit attributes (floor_plan, gross_sq_ft, unit_code_raw), the import row value is applied when different from current; no timestamp-based resolution.

**Idempotency:** Checksum of file; duplicate checksum → NO_OP.

---

## SECTION 4 — Manual Edit Handling

### 1. Where manual edits are written

- **Same tables as imports.** Manual edits write to:
  - **turnover:** `repository.update_turnover_fields` (manual_ready_status, manual_ready_confirmed_at, wd_present, wd_present_type, wd_supervisor_notified, wd_notified_at, wd_installed, wd_installed_at, move_out_date, move_in_date, report_ready_date, etc.).
  - **task:** `repository.update_task_fields` (execution_status, confirmation_status, vendor_completed_at, manager_confirmed_at, assignee, blocking_reason, etc.).
  - **note:** `repository.insert_note`, `repository.update_note_resolved`.
- **No separate overlay table.** There is no “manual_overlay” or “user_override” table; manual and import both read/write the same turnover and task rows.

### 2. Metadata distinguishing manual vs import

- **At row level:** No column on turnover or task indicating “last changed by manual” vs “by import.” Same row holds both kinds of updates.
- **In audit_log:** Yes. Every manual change that goes through turnover_service or task_service (and note_service) writes to `audit_log` with `source = 'manual'`. Import writes with `source = 'import'`. System actions use `source = 'system'`. So distinction is in audit_log only, not on the entity row.
- **Turnover origin:** `source_turnover_key`: manual entries use prefix `manual:{property_id}:{unit_identity_key}:{move_out_iso}`; import uses `{property_id}:{unit_norm}:{move_out_iso}`. So manual-created vs import-created turnover can be inferred from that key; edits to the same row are not distinguished at the row level.

### 3. Timestamps and conflict resolution

- **updated_at:** turnover has `updated_at`; it is set when import or manual updates the row (e.g. import_service sets updated_at to now when applying move_in_date, report_ready_date, or last_seen_moveout_batch_id; turnover_service update_turnover_dates and similar paths update fields but repository.update_turnover_fields does not automatically set updated_at unless the caller passes it). So updated_at is not consistently used to decide “manual vs import wins.”
- **Conflict resolution:** Import does not compare timestamps to decide whether to overwrite. It applies import data when there is no business-rule conflict (e.g. same move_out for open turnover, or unit has open turnover for PENDING_MOVE_INS/AVAILABLE_UNITS). Manual edits can be overwritten by a later import of the same field (e.g. move_in_date, report_ready_date) because there is no “manual-authoritative” guard on those columns in the import logic. AGENTS.md states “Manual-authoritative fields must never be overwritten by imports” — policy; the code does not currently mark which fields are manual-authoritative or skip them during import.

---

## SECTION 5 — Date Authority Structure

### 1. Move-out dates

- **Single column:** One column: `turnover.move_out_date` (TEXT NOT NULL).
- **Scheduled vs confirmed:** No separate “scheduled move-out” vs “confirmed move-out” columns. Only `move_out_date`.
- **FAS data:** PENDING_FAS import supplies “MO / Cancel Date” from the file. It is not stored in a separate column or table. It is used only to validate: if it differs from the open turnover’s move_out_date, the row is written as CONFLICT (PENDING_FAS_MOVE_OUT_MISMATCH). So FAS is validation-only, not a separate stored move-out source.

### 2. Move-in dates

- **Where stored:** `turnover.move_in_date` (TEXT, nullable). Only on turnover.
- **Tied to:** Turnover (and thus unit via unit_id). No separate lease or application table; move-in is a date on the open turnover.

### 3. Availability

- **Availability status:** Stored on turnover: `manual_ready_status` (TEXT, CHECK: 'Vacant ready', 'Vacant not ready', 'On notice' or NULL). No separate “availability” table.
- **Available date:** There is no column named “available date.” The closest is:
  - **report_ready_date** (turnover): report-authoritative “ready” date (e.g. from Available Units “Move-In Ready Date” or DMRB “Ready_Date”).
- **Ready date:** Same as above: `turnover.report_ready_date` for report-driven ready date; `manual_ready_status` and `manual_ready_confirmed_at` for manual QC readiness. So:
  - **Available date:** Not stored as a distinct column (Available Units CSV has “Available Date” but import uses “Move-In Ready Date” → report_ready_date).
  - **Ready date:** `turnover.report_ready_date` (from reports) and manual readiness via `manual_ready_status` + `manual_ready_confirmed_at`.

---

End of structured findings.
