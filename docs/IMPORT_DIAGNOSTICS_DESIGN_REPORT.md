# Import Diagnostics Design Report

Design for a new **Import Diagnostics** tab on the existing **Report Operations** page. This tab is purely observational: it exposes raw import outcomes (ignored, conflicted, invalid) from `import_row` and `import_batch` without modifying lifecycle, board, turnover, or enrichment logic.

---

## 1. Source Tables and Fields

### 1.1 `import_row`

| Column             | Type    | Description |
|--------------------|---------|-------------|
| `row_id`           | INTEGER | Primary key. |
| `batch_id`         | INTEGER | FK to `import_batch(batch_id)`. |
| `raw_json`         | TEXT    | Raw payload (e.g. unit, dates) as JSON. |
| `unit_code_raw`    | TEXT    | Unit code as in the file. |
| `unit_code_norm`   | TEXT    | Normalized unit code. |
| `move_out_date`    | TEXT    | Nullable; from report when applicable. |
| `move_in_date`     | TEXT    | Nullable; from report when applicable. |
| `validation_status`| TEXT    | One of: `OK`, `CONFLICT`, `INVALID`, `IGNORED`, `SKIPPED_OVERRIDE`. |
| `conflict_flag`    | INTEGER | 0 or 1. |
| `conflict_reason`  | TEXT    | Nullable; reason code when conflict/invalid/ignored. |

**Schema locations:** `db/schema.sql` (lines 247–257), `db/postgres_schema.sql` (lines 234–245).

Diagnostics-relevant fields: `unit_code_raw`, `unit_code_norm`, `validation_status`, `conflict_flag`, `conflict_reason`, `move_out_date`, `move_in_date`, `batch_id`, `raw_json`.

### 1.2 `import_batch`

| Column            | Type    | Description |
|-------------------|---------|-------------|
| `batch_id`        | INTEGER | Primary key. |
| `report_type`     | TEXT    | e.g. `MOVE_OUTS`, `PENDING_MOVE_INS`, `PENDING_FAS`, `AVAILABLE_UNITS`, `DMRB`. |
| `checksum`        | TEXT    | UNIQUE. |
| `source_file_name`| TEXT    | Original file name. |
| `record_count`    | INTEGER | Row count. |
| `status`          | TEXT    | `SUCCESS`, `NO_OP`, or `FAILED`. |
| `imported_at`     | TEXT    | Timestamp of import. |

**Note:** `import_batch` does **not** have a `property_id` column. Property is only known at import time (passed into `import_report_file`) and is not persisted on the batch. Filtering by “active property” for diagnostics must be done by joining to `unit` on `unit_code_norm` and `property_id` in the service layer (see §3 and §4).

**Schema locations:** `db/schema.sql` (lines 234–241), `db/postgres_schema.sql` (lines 46–53).

Diagnostics-relevant fields: `report_type`, `source_file_name`, `imported_at`.

### 1.3 Join

- **Relationship:** One batch has many rows. `import_row.batch_id` → `import_batch.batch_id`.
- **Join for diagnostics:**  
  `FROM import_row r JOIN import_batch b ON r.batch_id = b.batch_id`  
  so each row carries `report_type`, `source_file_name`, and `imported_at` from its batch.

---

## 2. Diagnostic Categories

Rows are classified for the diagnostics tab using `validation_status` and `conflict_flag`.

| Category        | Condition(s) | Meaning |
|----------------|--------------|--------|
| **Ignored**    | `validation_status = 'IGNORED'` | Row was not applied (e.g. no open turnover for FAS/ready-date). |
| **Conflict**   | `conflict_flag = 1` (or `validation_status = 'CONFLICT'`) | Row conflicted with current state (e.g. move-in without open turnover, move-out date mismatch). |
| **Invalid**    | `validation_status = 'INVALID'` | Row failed validation (e.g. missing move-out date, parse error). |

Recommended UI classification logic:

- **Ignored:** `validation_status == 'IGNORED'`
- **Conflict:** `conflict_flag == 1` (or `validation_status == 'CONFLICT'`)
- **Invalid:** `validation_status == 'INVALID'`

**Additional statuses in the codebase:**

- **OK** (`validation_status = 'OK'`): Row was applied successfully. Exclude from the diagnostics tab (tab shows only non-OK outcomes).
- **SKIPPED_OVERRIDE** (`validation_status = 'SKIPPED_OVERRIDE'`): Row skipped due to manual override. Can be treated as a fourth category or grouped (e.g. “Skipped”); for minimal scope, can be included as “Other” or under a “Status” filter that lists all statuses.

**Conflict reasons** observed in code (for reference; display as-is in Conflict Reason column):  
`MOVE_OUT_DATE_MISSING`, `MOVE_IN_WITHOUT_OPEN_TURNOVER`, `MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER`, `NO_OPEN_TURNOVER_FOR_READY_DATE`, `NO_OPEN_TURNOVER_FOR_VALIDATION`, `UNIT_NOT_FOUND_STRICT`, plus parse-error strings from unit master import.

---

## 3. Repository Query

### 3.1 Constraint: no `property_id` on batch

`import_batch` has no `property_id`. So:

- **Repository:** Returns diagnostic rows (optionally filtered by time only).
- **Service:** Optionally restricts to “active property” by resolving `unit_code_norm` to `unit` with `unit.property_id = :property_id` and only including rows whose unit belongs to that property. Rows whose unit is not in the DB or is in another property can be omitted when “active property” filter is on.

### 3.2 Proposed repository function

**Name:** `get_import_diagnostics(conn, since_imported_at=None)`

**Behavior:**

- Select rows from `import_row` joined to `import_batch` where the row is **not** “OK” (i.e. diagnostic outcomes only).
- Optional filter: `b.imported_at >= since_imported_at` (e.g. last 30 days); if `since_imported_at` is `None`, return all such rows.
- Order by `b.imported_at DESC, r.row_id` so latest imports appear first.
- **For the Import Diagnostics tab:** use the **deduplicated** query in §3.3 so only the most recent diagnostic row per unit per report type is returned (avoids redundant entries when imports are run multiple times per day).

**SQL (conceptual):**

```sql
SELECT
  r.row_id,
  r.batch_id,
  r.unit_code_raw,
  r.unit_code_norm,
  r.move_out_date,
  r.move_in_date,
  r.validation_status,
  r.conflict_flag,
  r.conflict_reason,
  b.report_type,
  b.imported_at,
  b.source_file_name
FROM import_row r
JOIN import_batch b ON r.batch_id = b.batch_id
WHERE r.validation_status != 'OK'
  AND (b.imported_at >= ? OR ? IS NULL)
ORDER BY b.imported_at DESC, r.row_id
```

Parameterize `since_imported_at` (e.g. ISO string); for “no date filter” pass `None` and use a condition that is always true for the date part (e.g. `(? IS NULL OR b.imported_at >= ?)`).

**File:** `db/repository/imports.py`  
**Export:** Add to `db/repository/__init__.py`.

### 3.3 Duplicate rows and deduplication (most recent per unit per report type)

**Can multiple rows exist for the same unit within a short time window?**

Yes. The pipeline is append-only and idempotent only at the **batch** level (same file checksum → `NO_OP`, no new rows). Each time a **different** file is imported (e.g. re-export of the same report, or an updated report), a **new** batch is created and one `import_row` is inserted per file line. So:

- The same unit (e.g. `unit_code_norm = '5-A-101'`) can appear in many batches of the same `report_type` (e.g. MOVE_OUTS run at 9:00 and again at 14:00 with a new file → two batches, two rows for that unit).
- Within a single batch, each unit appears at most once per row (one line per unit in the file).

So **duplicates are common** when imports are run multiple times per day: the same unit can have many diagnostic rows (e.g. CONFLICT or IGNORED) across batches. Showing all of them in the Import Diagnostics tab would be redundant; the manager usually cares about the **latest** outcome per unit per report type.

**Recommended behavior for the Import Diagnostics tab:** Return only the **most recent** diagnostic row per `(unit_code_norm, report_type)`, where “most recent” is defined by `b.imported_at DESC`, then `r.row_id DESC` as a tie-breaker.

**Proposed query (deduplicated):**

Use a CTE that ranks rows per `(unit_code_norm, report_type)` and keep only the first (most recent). Works in **PostgreSQL** and **SQLite 3.25+** (both support window functions).

```sql
WITH diag AS (
  SELECT
    r.row_id,
    r.batch_id,
    r.unit_code_raw,
    r.unit_code_norm,
    r.move_out_date,
    r.move_in_date,
    r.validation_status,
    r.conflict_flag,
    r.conflict_reason,
    b.report_type,
    b.imported_at,
    b.source_file_name,
    ROW_NUMBER() OVER (
      PARTITION BY r.unit_code_norm, b.report_type
      ORDER BY b.imported_at DESC, r.row_id DESC
    ) AS rn
  FROM import_row r
  JOIN import_batch b ON r.batch_id = b.batch_id
  WHERE r.validation_status != 'OK'
    AND (b.imported_at >= ? OR ? IS NULL)
)
SELECT
  row_id,
  batch_id,
  unit_code_raw,
  unit_code_norm,
  move_out_date,
  move_in_date,
  validation_status,
  conflict_flag,
  conflict_reason,
  report_type,
  imported_at,
  source_file_name
FROM diag
WHERE rn = 1
ORDER BY imported_at DESC, row_id
```

**Parameters:** Same as §3.2: bind `since_imported_at` twice (or `None` for no date filter).

**Implementation note:** Implement `get_import_diagnostics(conn, since_imported_at=None)` using this deduplicated query so the Import Diagnostics tab shows one row per unit per report type (the latest). If a “show all history” option is added later, a separate function or a `deduplicate=True` flag can call the non-deduplicated query from §3.2.

### 3.4 SQLite version verification and fallback

**Why:** The app may run in environments where the SQLite runtime is older than 3.25 (e.g. Python builds that ship an older bundled SQLite). Window functions (`ROW_NUMBER() OVER (...)`) were added in **SQLite 3.25.0** (September 2018). Using them on an older SQLite will raise an error and break the Import Diagnostics tab.

**Verification at runtime:**

- **PostgreSQL:** Always use the window-function query (§3.3); no version check needed.
- **SQLite:** Before running the deduplicated query, confirm that window functions are supported:
  1. Execute `SELECT sqlite_version();` on the connection (e.g. `conn.execute("SELECT sqlite_version()").fetchone()[0]`).
  2. Parse the result as a version string (e.g. `"3.35.2"`) and compare to `"3.25.0"` (e.g. `tuple(map(int, version.split(".")[:2])) >= (3, 25)`).
  3. If the version is **&lt; 3.25**, use the fallback query below instead of the `ROW_NUMBER()` query.

**Fallback query (no window functions):** Use `GROUP BY` plus `MAX(imported_at)` and then `MAX(row_id)` as a tie-breaker so that "most recent" matches §3.3 (one row per `(unit_code_norm, report_type)`). CTEs are supported in SQLite 3.8.3+, so this is safe on older SQLite.

```sql
WITH base AS (
  SELECT
    r.row_id,
    r.batch_id,
    r.unit_code_raw,
    r.unit_code_norm,
    r.move_out_date,
    r.move_in_date,
    r.validation_status,
    r.conflict_flag,
    r.conflict_reason,
    b.report_type,
    b.imported_at,
    b.source_file_name
  FROM import_row r
  JOIN import_batch b ON r.batch_id = b.batch_id
  WHERE r.validation_status != 'OK'
    AND (b.imported_at >= ? OR ? IS NULL)
),
latest_imported AS (
  SELECT
    unit_code_norm,
    report_type,
    MAX(imported_at) AS max_imported_at
  FROM base
  GROUP BY unit_code_norm, report_type
),
latest_row AS (
  SELECT
    b.unit_code_norm,
    b.report_type,
    b.max_imported_at,
    MAX(base.row_id) AS max_row_id
  FROM latest_imported b
  JOIN base ON base.unit_code_norm = b.unit_code_norm
    AND base.report_type = b.report_type
    AND base.imported_at = b.max_imported_at
  GROUP BY b.unit_code_norm, b.report_type, b.max_imported_at
)
SELECT
  base.row_id,
  base.batch_id,
  base.unit_code_raw,
  base.unit_code_norm,
  base.move_out_date,
  base.move_in_date,
  base.validation_status,
  base.conflict_flag,
  base.conflict_reason,
  base.report_type,
  base.imported_at,
  base.source_file_name
FROM base
JOIN latest_row l
  ON base.unit_code_norm = l.unit_code_norm
  AND base.report_type = l.report_type
  AND base.imported_at = l.max_imported_at
  AND base.row_id = l.max_row_id
ORDER BY base.imported_at DESC, base.row_id
```

**Parameters:** Same as §3.3: bind `since_imported_at` twice (or `None` for no date filter).

**Implementation recommendation:** In `get_import_diagnostics(conn, since_imported_at=None)`, if the engine is SQLite, run the version check once per connection (or cache per process); if version &lt; 3.25, run the fallback query above; otherwise run the window-function query from §3.3. For Postgres, always use the §3.3 query. This keeps the deduplication behavior correct in every environment where the app runs.

---

## 4. Service Layer

**Location:** `services/report_operations_service.py`

**Proposed function:** `get_import_diagnostics_queue(conn, property_id, since_imported_at=None)`

**Behavior:**

1. Call `repository.get_import_diagnostics(conn, since_imported_at=since_imported_at)`.
2. If `property_id` is not `None`, filter rows to those where the unit belongs to the given property:  
   for each row, resolve `repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=row['unit_code_norm'])`; keep the row only if the unit exists (so that unit is in that property).  
   If `property_id` is `None`, return all rows (no property filter).
3. Transform to a list of dicts for the UI, e.g.:
   - `unit_code` → `unit_code_raw` or `unit_code_norm`
   - `report_type`, `validation_status`, `conflict_reason`, `imported_at`, `source_file_name`
   - Optionally `move_out_date`, `move_in_date` for extra context.

This keeps the repository free of property semantics and keeps “active property” filtering in one place.

---

## 5. UI Integration

**File:** `ui/screens/report_operations.py`

**Changes:**

- Add a **third tab** to the existing Report Operations page: **Import Diagnostics** (alongside “Missing Move-Out” and “FAS Tracker”).
- In the Import Diagnostics tab:
  - Use the same pattern as the other tabs: call a `_get_import_diagnostics_queue()` helper that uses `get_active_property()` and `report_operations_service.get_import_diagnostics_queue(conn, property_id=..., since_imported_at=...)`.
  - Display a table with columns:
    - **Unit** (unit code)
    - **Report Type**
    - **Status** (validation_status)
    - **Conflict Reason**
    - **Import Time** (imported_at)
    - **Source File** (source_file_name)
  - Use the same table component as elsewhere: `st.dataframe(df, use_container_width=True, hide_index=True)` so sorting (and any existing filtering) is consistent.

**Observational only:** No buttons or actions that change lifecycle, board, or turnover state.

---

## 6. Optional Filters

Suggested filters for the diagnostics table:

| Filter       | Implementation |
|-------------|----------------|
| **Report Type** | Dropdown (e.g. All, MOVE_OUTS, PENDING_MOVE_INS, PENDING_FAS, AVAILABLE_UNITS, DMRB). Filter the displayed dataframe by `report_type`. |
| **Status**      | Dropdown (e.g. All, IGNORED, CONFLICT, INVALID, SKIPPED_OVERRIDE). Filter by `validation_status`. |
| **Date range**   | Optional `since_imported_at` (e.g. “Last 30 days” or a date picker). Passed to `get_import_diagnostics(conn, since_imported_at=...)` and/or filter in UI on `imported_at`. |

**Existing UI patterns:** The app already uses `st.selectbox` and session state for filters (e.g. Flag Bridge: phase, status, N/V/M, assignee, bridge). The same pattern can be used: store filter values in `st.session_state` (e.g. `report_ops_diag_report_type`, `report_ops_diag_status`, `report_ops_diag_days`), render selectboxes/date inputs above the table, and filter the dataframe (or the service result) before displaying. No new infrastructure is required.

---

## 7. Performance Considerations

- **Table growth:** `import_row` is append-only and can grow large. Query uses `JOIN import_batch` and `WHERE r.validation_status != 'OK'` and optional `b.imported_at >= ?`.
- **Index usage:**
  - Existing: `idx_import_row_batch_id ON import_row(batch_id)` supports the join.
  - `import_batch.imported_at` is used in the optional date filter; there is no current index on `imported_at`. For large batches, an index on `import_batch(imported_at)` would reduce scan size when “last N days” is used.
  - Filtering by `validation_status != 'OK'` is a table scan on `import_row` unless an index exists. An index such as `idx_import_row_validation_status ON import_row(validation_status)` could help if the table is very large.
- **Recommendation:** Do not add indexes in the initial implementation. If the diagnostics query becomes slow as data grows, add:
  - `CREATE INDEX idx_import_batch_imported_at ON import_batch(imported_at);`
  - Optionally `CREATE INDEX idx_import_row_validation_status ON import_row(validation_status);`
- **Property filter:** Property filtering is done in the service layer by repeated `get_unit_by_norm` lookups. For a large number of diagnostic rows this could be N queries. If needed, this can be optimized later (e.g. batch resolve unit_ids by property, or add a single query that joins `import_row` → `unit` on `unit_code_norm` and `property_id` and returns only rows that match).

---

## 8. Patch Outline

Minimal file set; no changes to lifecycle, board, turnover, or enrichment logic.

| File | Change |
|------|--------|
| `db/repository/imports.py` | Add `get_import_diagnostics(conn, since_imported_at=None)` returning list of dicts (row + batch fields). |
| `db/repository/__init__.py` | Export `get_import_diagnostics`. |
| `services/report_operations_service.py` | Add `get_import_diagnostics_queue(conn, property_id, since_imported_at=None)`; call repo, optionally filter by property via `get_unit_by_norm`, return list of dicts for UI. |
| `ui/screens/report_operations.py` | Add third tab “Import Diagnostics”; add `_get_import_diagnostics_queue()` and `_render_import_diagnostics_tab(active_property)`; render table (Unit, Report Type, Status, Conflict Reason, Import Time, Source File). Optionally add filters (Report Type, Status, date range) using existing selectbox/session-state pattern. |

No changes to:

- `domain/`, `application/workflows/`, board query, turnover creation, enrichment, or import execution logic.

---

## 9. Goal

The Import Diagnostics tab will allow the manager to:

- See **why a unit was ignored** (e.g. no open turnover for FAS/ready-date).
- See **which rows conflicted** in recent imports (e.g. move-in without open turnover, move-out date mismatch).
- See **which units failed validation** (e.g. missing move-out date, parse error).

The feature is **purely observational** and does not modify lifecycle state, board, or turnover data.

---

## Summary: File Paths and Function Names

| Layer   | File | Function / change |
|--------|------|--------------------|
| Repository | `db/repository/imports.py` | `get_import_diagnostics(conn, since_imported_at=None)` |
| Repository | `db/repository/__init__.py` | Export `get_import_diagnostics` |
| Service    | `services/report_operations_service.py` | `get_import_diagnostics_queue(conn, property_id, since_imported_at=None)` |
| UI         | `ui/screens/report_operations.py` | Third tab “Import Diagnostics”; `_get_import_diagnostics_queue()`, `_render_import_diagnostics_tab(active_property)`; table columns: Unit, Report Type, Status, Conflict Reason, Import Time, Source File |
