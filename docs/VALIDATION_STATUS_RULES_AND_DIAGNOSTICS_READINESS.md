# Validation Status Rules and Why Diagnostics Are Not Open for Review Yet

This document answers two questions: **(1)** What rules produce validation status errors? **(2)** Why are those outcomes not yet open for review in the UI?

---

## 1. Rules That Produce Validation Status Errors

Validation happens in **three layers**. Only the first two can block the whole batch before any row is written; the third writes every row to `import_row` with a status.

### 1.1 File-level rules (pre-import; batch fails, no rows written)

**Location:** `imports/validation/file_validator.py` (and `services/imports/orchestrator.py` calls it before parsing).

| Rule | Condition | `error_type` | Outcome |
|------|-----------|--------------|---------|
| Unknown report type | `report_type` not in supported list | `UNKNOWN_REPORT_TYPE` | Batch not created; `ImportValidationError` raised. |
| Wrong file extension | Extension not in `SUPPORTED_EXTENSIONS[report_type]` (e.g. not `.csv` for AVAILABLE_UNITS) | `UNSUPPORTED_FILE_TYPE` | Batch not created; `ImportValidationError` raised. |
| Empty file | File missing or 0 bytes | `EMPTY_FILE` | Batch not created; `ImportValidationError` raised. |
| DMRB: unreadable Excel | Excel file cannot be opened | `UNREADABLE_FILE` | Batch not created; `ImportValidationError` raised. |
| DMRB: missing sheet | Required sheet name (e.g. `"DMRB "`) not in workbook | `MISSING_REQUIRED_SHEET` | Batch not created; `ImportValidationError` raised. |

**Supported extensions:** `services/imports/validation/file_validator.py`: MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS → `.csv`; DMRB → `.xlsx`, `.xls`.

---

### 1.2 Schema-level rules (pre-apply; batch fails, no rows written)

**Location:** `imports/validation/schema_validator.py`. Runs after file validation, before row apply. Uses `SCHEMA_RULES` and row-by-row checks.

**Required columns (header) and required fields (per row) by report type:**

| Report type | Required columns | Required fields (per row) | Date columns | Numeric columns |
|-------------|------------------|---------------------------|--------------|-----------------|
| MOVE_OUTS | Unit, Move-Out Date | Unit, Move-Out Date | Move-Out Date | — |
| PENDING_MOVE_INS | Unit, Move In Date | Unit, Move In Date | Move In Date | — |
| AVAILABLE_UNITS | Unit, Status, Available Date, Move-In Ready Date | Unit | Available Date, Move-In Ready Date | — |
| PENDING_FAS | Unit, MO / Cancel Date | Unit | MO / Cancel Date | — |
| DMRB | Unit, Ready_Date, Move_out, Move_in, Status | Unit | Ready_Date, Move_out, Move_in | — |

**Schema error types (all raise `ImportValidationError` before any row is applied):**

| Rule | `error_type` | When |
|------|--------------|------|
| Unknown report type | `UNKNOWN_REPORT_TYPE` | `report_type` not in `SCHEMA_RULES`. |
| Empty dataset | `EMPTY_DATASET` | No data rows after header/skip-rows. |
| Duplicate column | `DUPLICATE_COLUMN` | Same column name appears more than once in header. |
| Missing required column | `MISSING_REQUIRED_COLUMN` | A required column from `required_columns` is missing from the file. |
| Missing required field | `MISSING_REQUIRED_FIELD` | For a given row, a required field (e.g. Unit) is blank. |
| Invalid date format | `INVALID_DATE_FORMAT` | A value in a `date_columns` column cannot be parsed as a date. |
| Invalid numeric value | `INVALID_NUMERIC_VALUE` | A value in a `numeric_columns` column cannot be parsed as numeric. |

**CSV skip-rows (header offset):** MOVE_OUTS 6, PENDING_MOVE_INS 5, AVAILABLE_UNITS 5, PENDING_FAS 4. (`schema_validator.py`.)

If any of these fire, the orchestrator inserts a single `import_batch` row with `status = 'FAILED'`, `record_count = 0`, and **no** `import_row` rows. The UI shows the validation diagnostics from the exception.

---

### 1.3 Row-level rules (per report type; every row written to `import_row` with a status)

**Location:** `services/imports/` (e.g. `available_units.py`, `move_outs.py`, `move_ins.py`, `pending_fas.py`, `dmrb.py`). Each row is written to `import_row` with `validation_status` and, when applicable, `conflict_reason`.

**Possible `validation_status` values:** `OK`, `CONFLICT`, `INVALID`, `IGNORED`, `SKIPPED_OVERRIDE`.

**Conflict reasons (examples in code/docs):**  
`MOVE_OUT_DATE_MISSING`, `MOVE_IN_WITHOUT_OPEN_TURNOVER`, `MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER`, `NO_OPEN_TURNOVER_FOR_READY_DATE`, `NO_OPEN_TURNOVER_FOR_VALIDATION`, `UNIT_NOT_FOUND_STRICT`, plus parse-error messages from unit master import.

#### AVAILABLE_UNITS (`services/imports/available_units.py`)

- Unit not found or no open turnover → `validation_status = IGNORED`, `conflict_reason = NO_OPEN_TURNOVER_FOR_READY_DATE`.
- Unit has open turnover; manual override set and value differs → `SKIPPED_OVERRIDE`.
- Otherwise applied → `OK`.

#### MOVE_OUTS (`services/imports/move_outs.py`)

- Missing move-out date → `validation_status = INVALID`, `conflict_flag = 1`, `conflict_reason = MOVE_OUT_DATE_MISSING`.
- Unit has open turnover and move-out date differs (no override) → `CONFLICT`, `conflict_reason = MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER`.
- Manual override / applied → `OK` or `SKIPPED_OVERRIDE` as appropriate.

#### PENDING_MOVE_INS (`services/imports/move_ins.py`)

- Unit not found or no open turnover → `validation_status = CONFLICT`, `conflict_flag = 1`, `conflict_reason = MOVE_IN_WITHOUT_OPEN_TURNOVER`.
- Applied → `OK`.

#### PENDING_FAS (`services/imports/pending_fas.py`)

- Unit not found or no open turnover → `validation_status = IGNORED`, `conflict_reason = NO_OPEN_TURNOVER_FOR_VALIDATION`.
- Applied → `OK`.

#### DMRB (`services/imports/dmrb.py`)

- Unit not found or no open turnover → `validation_status = IGNORED`, `conflict_reason = NO_OPEN_TURNOVER_FOR_READY_DATE`.
- Manual override / applied → `OK` or `SKIPPED_OVERRIDE` as appropriate.

**Unit master import** (separate pipeline): Can write `import_row` with conflict/validation reasons such as `UNIT_NOT_FOUND_STRICT` or parse errors; same `import_row` table, so they would appear in diagnostics once that UI exists.

---

## 2. Why These Outcomes Are Not Open for Review Yet

**Short answer:** The **Import Diagnostics** experience is **designed and partially implemented** (repository and design doc), but the **UI that would expose it for review is not built yet**. Admin only shows “latest batch” tables and a placeholder for conflicts; there is no dedicated “list conflicts / diagnostics for a selected batch” or “Import Diagnostics tab” yet.

### 2.1 What exists today

- **Data model:** Every non-OK row is stored in `import_row` with `validation_status`, `conflict_flag`, `conflict_reason`, plus batch metadata in `import_batch`. So the **rules above are already producing** the data that would be “open for review.”
- **Repository:** `db/repository/imports.py` implements `get_import_diagnostics(conn, since_imported_at=None)` with a deduplicated query (latest row per `(unit_code_norm, report_type)`), SQLite version check, and Postgres support. So the **backend is ready** to serve diagnostics.
- **Design:** `docs/IMPORT_DIAGNOSTICS_DESIGN_REPORT.md` specifies the Import Diagnostics tab (data source, filters, deduplication, UI behavior). `docs/LIFECYCLE_STATE_AND_WORKFLOW_SPECIFICATION.md` (§6) describes exception workflows and states that the **Import Diagnostics tab is “to implement”** on Report Operations.
- **Admin Import:** Admin → Import shows per–report-type **“Latest import”** tables (batch metadata + rows from latest batch) and a **“Conflicts”** subheader with the caption: *“Conflict details are recorded in import_row for the batch. List conflicts here when a batch is selected (future).”* So the app explicitly states that **listing conflicts by batch is future work**.
- **Report Operations:** Missing Move-Out and FAS Tracker tabs exist and surface **subsets** of exceptions (e.g. MOVE_IN_WITHOUT_OPEN_TURNOVER, MOVE_OUT_DATE_MISSING, PENDING_FAS) with resolve actions. There is **no** general “Import Diagnostics” tab that shows all non-OK rows (or filtered by report type / status / date) for review.

### 2.2 What is missing (why they are “not open for review yet”)

1. **Import Diagnostics tab on Report Operations**  
   The design report and lifecycle spec both say: show `import_row` joined to `import_batch` where `validation_status != 'OK'`, with optional filters (report type, status, date range, property via unit), and deduplication (latest per unit per report type). That tab **has not been implemented** in the Report Operations UI, so users cannot yet “open” a single place to review all validation/conflict outcomes.

2. **Admin “Conflicts” section**  
   Admin currently has a placeholder: “List conflicts here when a batch is selected (future).” So there is **no** “select a batch → list conflicts for that batch” feature. Without that, Admin does not yet expose conflicts/diagnostics for review either.

3. **No batch selector for diagnostics**  
   Even though the latest-batch tables show one batch per report type, there is no control to “select a batch” and then show only the non-OK rows (or all rows) for that batch. So the “when a batch is selected” part of the Conflicts caption is not implemented.

### 2.3 Summary

- **Rules that produce validation status:** File-level and schema-level rules (file validator + schema validator) block the batch and surface errors in the UI without writing rows; row-level rules (per report type in `services/imports/*`) write every row to `import_row` with `validation_status` and optional `conflict_reason`. All of these are already in the codebase and documented above.
- **Why they are not open for review yet:** The data is stored and the repository supports diagnostics, but the **Import Diagnostics tab** (Report Operations) and the **Admin “Conflicts” list (when a batch is selected)** are not implemented. Until those UI pieces are built, validation status and conflict reasons are not exposed in a dedicated “open for review” flow—only indirectly via the latest-import tables and the existing Report Operations tabs (Missing Move-Out, FAS Tracker) for specific exception types.

**References:**  
- `docs/IMPORT_DIAGNOSTICS_DESIGN_REPORT.md`  
- `docs/LIFECYCLE_STATE_AND_WORKFLOW_SPECIFICATION.md` (§4 Rules by Report Type, §6 Exception Workflows)  
- `ui/screens/admin.py` (Conflicts caption)  
- `db/repository/imports.py` (`get_import_diagnostics`)  
- `imports/validation/file_validator.py`, `imports/validation/schema_validator.py`  
- `services/imports/available_units.py`, `move_outs.py`, `move_ins.py`, `pending_fas.py`, `dmrb.py`
