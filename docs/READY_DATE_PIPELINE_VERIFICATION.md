# Ready Date — Full Pipeline Verification (All 8 Prompts)

Single run of the [Debugging Field Disappearance](DEBUGGING_FIELD_DISAPPEARANCE.md) playbook for **Ready Date** (Move-In Ready Date). Field: `report_ready_date`. Source: Available Units report column **"Move-In Ready Date"**. Target: **Ready Date** column on the DMRB board.

---

## Prompt 1 — Trace the Field Lifecycle

| Step | Where | File | Function | Line(s) | Field / key |
|------|--------|------|----------|--------|-------------|
| 1. Parse | CSV column "Move-In Ready Date" | `services/imports/available_units.py` | `_parse_available_units()` | 304, 309–310 | `r["Move-In Ready Date"]` → `report_ready_date` (date) in row dict |
| 2. Internal name | Row dict passed to apply | same | `apply_available_units()` | 353 | `row.get("report_ready_date")` → `ready_iso` |
| 3. DB write | Turnover update/insert | same | `apply_available_units()` + `repository.update_turnover_fields()` | 441–444, 529, 561; `db/repository/turnovers.py` 193–206 | `report_ready_date` (ISO string) in `update_fields` |
| 4. DB column | SQLite table | schema | `turnover.report_ready_date` | — | Column: `report_ready_date` |
| 5. Query load | Open turnovers | `db/repository/turnovers.py` | `list_open_turnovers()` | 99–123 | `SELECT * FROM turnover` → includes `report_ready_date` |
| 6. Row build | Flat row from turnover | `services/board_query_service.py` | `_build_flat_row()` | 84, 97 | `report_ready_date = turnover.get("report_ready_date")` → key `"report_ready_date"` in row |
| 7. Row key | Flat dict | same | same | 97 | `"report_ready_date"` |
| 8. UI read | Board table | `ui/screens/board.py` | (board render) | 271 | `row.get("report_ready_date")` for column "Ready Date" |

**Conclusion:** No drop or rename in the pipeline. Single name `report_ready_date` from parse through DB to UI.

---

## Prompt 2 — Inspect Row Construction

**Function:** `services/board_query_service.py` → `_build_flat_row()` (lines 50–120).

**DB fields read for this field:** `turnover.get("report_ready_date")` only (line 84).

**Key written:** `"report_ready_date"` (line 97). Also `"available_date"` is written separately from `turnover.get("available_date")` (line 98).

**Computed or derived:** No. Direct pass-through:

```python
# Ready Date = Move-In Ready Date only. Do not derive from available_date (vacancy).
report_ready_date = turnover.get("report_ready_date")
...
"report_ready_date": report_ready_date,
```

**Fallback/merge logic:** None. No `field_a OR field_b` for readiness. The previous fallback (`report_ready_date or available_date`) was removed.

**Effect on display:** Ready Date on the board is exactly the DB `report_ready_date`; if NULL, column is blank.

---

## Prompt 3 — Verify UI Column Mapping

**Component:** `ui/screens/board.py` (board table).

**Column label:** `"Ready Date"` (e.g. lines 271, 328, 349, 358).

**Row key read:** `row.get("report_ready_date")` (line 271). No other key used for this column in the main info table.

**Fallback in render:** None. `parse_date(row.get("report_ready_date"))` — no `or row.get("ready_date")` or similar.

**Consistency:** UI expects `report_ready_date`; board query service puts `report_ready_date` in the row. Mapping is consistent.

---

## Prompt 4 — Verify Database Write Path

**Table:** `turnover`. **Column:** `report_ready_date`.

**Source column:** Available Units report **"Move-In Ready Date"** (parsed in `_parse_available_units()` → `report_ready_date` in row; then in `apply_available_units()` as `row.get("report_ready_date")`).

**Code paths that write `report_ready_date`:**

| Context | File | Function | Lines | What’s written |
|---------|------|----------|-------|----------------|
| Backfill (reconcile) | `services/imports/available_units.py` | backfill from raw rows | 269–277 | `ready_iso` only when parsed `ready_date` is not None (no `available_date` fallback) |
| New turnover from availability row | same | `apply_available_units()` | 440–449 | `ready_iso_from_row = _to_iso_date(row.get("report_ready_date"))` only |
| Update open turnover (override clear) | same | same | 529–530 | `ready_iso` (from row’s Move-In Ready Date) |
| Update open turnover (no override) | same | same | 559–562 | `ready_iso` only when present |

**Fallback writing another field into `report_ready_date`:** None. Lifecycle rule: only the parsed **Move-In Ready Date** is written to `report_ready_date`; **Available Date** is written only to `available_date`.

**Conditions that skip writing the field:**

- **Override:** If `ready_manual_override_at` is set and incoming ready date differs, update is skipped (e.g. `_write_skip_audit_if_new` for `report_ready_date`).
- **Validation / ignore:** Row can be IGNORED (e.g. `NO_OPEN_TURNOVER_FOR_READY_DATE`) or INVALID; then no turnover update runs.
- **Missing turnover:** If there is no open turnover for the unit, the importer does not update any turnover (or creates one only in the “new turnover” path with `report_ready_date` from row only).

**Low-level writer:** `db/repository/turnovers.py` → `update_turnover_fields()` (193–207). Accepts `report_ready_date` in `fields`; it is in `TURNOVER_UPDATE_COLS` (`db/repository/_helpers.py`).

---

## Prompt 5 — Validate End-to-End Consistency

| Layer | Name used | Alias? |
|-------|-----------|--------|
| Database column | `report_ready_date` | — |
| Repository (SELECT) | `report_ready_date` (in `SELECT *`) | — |
| Row construction | `report_ready_date` | — |
| Enrichment | `row.get("report_ready_date")` | — |
| UI rendering | `row.get("report_ready_date")` | — |

**Mismatches:** None. No alias like `ready_date` in the board path. Pipeline is internally consistent on `report_ready_date`.

---

## Prompt 6 — Identify Fallback / Merge Logic Impact

**Operational meaning:**

- **Available Date** = vacancy (resident moved out).
- **Move-In Ready Date** (`report_ready_date`) = unit ready for occupancy.

**Merge logic in codebase:** None in board or current importer. The previous pattern `report_ready_date OR available_date` was removed from:

- `services/board_query_service.py` → `_build_flat_row()`
- `services/imports/available_units.py` → backfill, new turnover, and open turnover update.

**Impact:** Using `available_date` as a fallback for readiness would be incorrect lifecycle semantics (vacancy ≠ readiness). Current code does not do that; Ready Date is purely Move-In Ready.

---

## Prompt 7 — Verify Record Selection

**Question:** Is the UI rendering the correct record (e.g. the right turnover when a unit has multiple turnovers)?

**How the board gets rows:**

1. `repository.list_open_turnovers(conn, phase_ids=...)` or `property_ids=...` (`services/board_query_service.py` 174–177).
2. Query: `closed_at IS NULL AND canceled_at IS NULL` and (with phase filter) `move_out_date IS NOT NULL` (`db/repository/turnovers.py` 99–123).
3. One row per **open** turnover; each such turnover is the single “open” turnover for that unit at query time (business rule: one open turnover per unit).

**Record chosen:** The **open** turnover for each unit (no `ORDER BY` in `list_open_turnovers`; if multiple open turnovers per unit were possible, order would be undefined—but the schema/invariants intend one open per unit). So the board shows the single open turnover’s `report_ready_date`.

**If the field appears missing:** Either (1) that open turnover has `report_ready_date` NULL in the DB, or (2) the unit has another (e.g. closed) turnover that has a date while the **open** one does not. The board is correct to show the open turnover only; the “missing” value would be on a different (non-open) record.

**Conclusion:** Record selection is by design (open turnover only). No bug from showing the wrong record; if Ready Date is blank, it is because the **open** turnover has no `report_ready_date`.

---

## Prompt 8 — Database Reality Check

Before assuming a code bug, confirm whether the value exists in the database for the record the board actually shows (the open turnover for the unit).

**Diagnostic query (by unit):**

```sql
SELECT
  t.turnover_id,
  t.unit_id,
  u.unit_code_norm,
  t.move_out_date,
  t.report_ready_date,
  t.available_date,
  t.closed_at,
  t.canceled_at
FROM turnover t
JOIN unit u ON u.unit_id = t.unit_id
WHERE u.unit_code_norm = ?   -- or WHERE t.unit_id = ?
ORDER BY t.created_at;
```

**By unit_id:**

```sql
SELECT
  turnover_id,
  unit_id,
  move_out_date,
  report_ready_date,
  available_date,
  closed_at,
  canceled_at
FROM turnover
WHERE unit_id = ?
ORDER BY created_at;
```

**How to use:** Run for the unit where Ready Date appears missing. Check the row with `closed_at IS NULL` and `canceled_at IS NULL` (the open turnover). If that row has `report_ready_date` NULL, the issue is upstream (import/backfill not writing it). If it has a date but the board is blank, then the bug is in query/row build/UI (current verification says pipeline is consistent).

---

## Summary Table (Five Categories)

| Category | Status | Evidence |
|----------|--------|----------|
| 1. Field never written to DB | Possible upstream | Importer writes only when Move-In Ready Date present; overrides can skip. Use Prompt 8 query. |
| 2. Field renamed in pipeline | No | Same name `report_ready_date` end to end. |
| 3. Field dropped in row construction | No | `_build_flat_row()` passes through `report_ready_date` only; no fallback. |
| 4. UI reading wrong key | No | Board uses `row.get("report_ready_date")`. |
| 5. UI showing wrong record | No | Board shows open turnover only; one open per unit. |

**Verdict:** Pipeline is aligned on `report_ready_date` with no fallback and no rename. Blank Ready Date on the board means the **open** turnover has NULL `report_ready_date` in the DB; confirm with the diagnostic query (Prompt 8) and then fix upstream (import/override rules) if needed.
