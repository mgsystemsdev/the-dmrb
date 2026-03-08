# PHASE 0 — Baseline Freeze & Safety Snapshot

Read-only baseline. No code/schema/migration changes. No implementation.

---

## 1) Runtime entry points

**Commands that start the app:**

- From repo root: `streamlit run the-dmrb/app.py`
- From repo root: `streamlit run the-dmrb/app_prototype_v2.py`
- From `the-dmrb/`: `streamlit run app.py` or `streamlit run app_prototype_v2.py`

**Main entry point files:**

| File path | Invocation |
|-----------|------------|
| `the-dmrb/app.py` | `streamlit run the-dmrb/app.py` (primary; docstring line 3–4) |
| `the-dmrb/app_prototype_v2.py` | `streamlit run the-dmrb/app_prototype_v2.py` (docstring line 3–4) |

**Other entry points (non-Streamlit):**

- `the-dmrb/app_prototype.py` — exits immediately with message "v1 prototype is disabled. Use app.py instead." (line 7).
- `the-dmrb/scripts/analyze_units_csv.py` — CLI script; `if __name__ == "__main__":` calls `main()`.

**Documented run (AGENTS.md):** `streamlit run the-dmrb/app.py` from repo root; or `streamlit run app.py` from `the-dmrb/`.

---

## 2) Database file(s) and location

**Where the SQLite DB path is configured:**

- **App:** `the-dmrb/app.py` and `the-dmrb/app_prototype_v2.py` define:
  - `def _get_db_path(): return os.environ.get("COCKPIT_DB_PATH", os.path.join(os.path.dirname(__file__) or ".", "data", "cockpit.db"))`
  - File path: `the-dmrb/app.py` lines 156–157; `the-dmrb/app_prototype_v2.py` lines 156–157.

**Resolution:**

- If **COCKPIT_DB_PATH** is set: that value is used.
- If **unset (default):** `os.path.join(os.path.dirname(__file__) or ".", "data", "cockpit.db")`. When run as `streamlit run the-dmrb/app.py` from repo root, `__file__` is the path to `app.py`, so the default is **`the-dmrb/data/cockpit.db`** (relative to process CWD, typically repo root). Directory `data` is created on first connection if missing (`db/connection.py` `get_connection`).

**Location type:** In repo under `the-dmrb/data/` by default; overridable via env var. File is created on first use if it does not exist (SQLite creates it when `sqlite3.connect(db_path)` is called); schema/migrations are applied by `ensure_database_ready` when backend is used.

**Multiple DBs (dev/test):** No separate dev/test DB path in app code. Tests (`the-dmrb/tests/test_unit_master_import.py`, `the-dmrb/tests/test_manual_availability.py`, etc.) use ephemeral DBs via `tempfile.mkstemp(suffix=".db")` and pass that path to `ensure_database_ready(path)` and `get_connection(path)`.

**Import service backup:** `services/import_service.py` `import_report_file` accepts optional `db_path` and `backup_dir`; when both are provided, after a successful import it calls `db_connection.backup_database(db_path, backup_dir, batch_id)`. The app does not pass these when invoking import (Import panel is mock); callers that run real import (e.g. a future wired Import page or scripts) would pass them.

---

## 3) Migration / bootstrap mechanism

**Is ensure_database_ready used? Where is it called?**

- **Yes.** Implemented in `the-dmrb/db/connection.py` as `ensure_database_ready(db_path: str)` (lines 276–338).
- **Called from:**
  - `the-dmrb/app.py`: when `_BACKEND_AVAILABLE` and not `st.session_state.use_mock`, in a block that runs before any DB read (lines 162–164): `ensure_database_ready(_get_db_path())` inside try/except; on exception sets `st.session_state.db_init_failed` and falls back to mock.
  - `the-dmrb/app_prototype_v2.py`: same pattern (lines 162–164).
  - Tests: `the-dmrb/tests/test_unit_master_import.py` (e.g. lines 62, 89), `the-dmrb/tests/test_manual_availability.py` (e.g. lines 51, 80, 122, 169, 189), `the-dmrb/tests/test_unit_identity.py` (e.g. 139, 177).

**Where migrations are stored:**

- Directory: `the-dmrb/db/migrations/`
- Files (order applied):  
  `001_add_report_ready_date.sql`, `002_add_exposure_risk_type.sql`, `003_add_assignee_blocking_wd_type.sql`, `004_add_unit_identity_columns.sql`, `005_add_phase_building.sql`, `006_add_unit_attrs.sql`, `007_add_unit_hierarchy_fk.sql`, `008_task_template_phase_id.sql`

**How they are applied:**

- `ensure_database_ready(db_path)` in `the-dmrb/db/connection.py`:
  1. Opens connection via `get_connection(db_path)`.
  2. If table `turnover` is missing: runs `the-dmrb/db/schema.sql` via `executescript`, commits, sets `schema_version.version = 3` (so migrations 1–3 are considered already applied by schema.sql content).
  3. If table `schema_version` is missing: creates it and inserts `(singleton=1, version=0)`.
  4. Reads current `version` from `schema_version`.
  5. For each entry in `_MIGRATIONS` (1–8), if `current < n`: reads SQL from `the-dmrb/db/migrations/<filename>`, runs `executescript`, then for n=4 runs `_backfill_unit_identity(conn)`, for n=7 runs `_backfill_hierarchy(conn)`, for n=8 runs `_backfill_task_template_phase_id(conn)`, updates `schema_version.version = n`, commits.
  6. Closes connection.

Schema path resolved as `os.path.join(os.path.dirname(__file__), "schema.sql")` and migrations dir as `os.path.join(os.path.dirname(__file__), "migrations")` inside `db/connection.py` (so relative to `the-dmrb/db/`).

---

## 4) Baseline schema & invariants snapshot

**Current turnover table DDL**

Base from `the-dmrb/db/schema.sql` (section 3. turnover), plus column added by migration 003:

```sql
-- schema.sql (turnover) + migration 003 adds wd_present_type
CREATE TABLE turnover (
  turnover_id INTEGER PRIMARY KEY,
  property_id INTEGER NOT NULL REFERENCES property(property_id),
  unit_id INTEGER NOT NULL REFERENCES unit(unit_id),
  source_turnover_key TEXT NOT NULL UNIQUE,
  move_out_date TEXT NOT NULL,
  move_in_date TEXT,
  report_ready_date TEXT,
  manual_ready_status TEXT CHECK(manual_ready_status IN ('Vacant ready', 'Vacant not ready', 'On notice') OR manual_ready_status IS NULL),
  manual_ready_confirmed_at TEXT,
  expedited_flag INTEGER NOT NULL DEFAULT 0 CHECK(expedited_flag IN (0, 1)),
  wd_present INTEGER CHECK(wd_present IN (0, 1)),
  wd_supervisor_notified INTEGER CHECK(wd_supervisor_notified IN (0, 1)),
  wd_notified_at TEXT,
  wd_installed INTEGER CHECK(wd_installed IN (0, 1)),
  wd_installed_at TEXT,
  closed_at TEXT,
  canceled_at TEXT,
  cancel_reason TEXT,
  last_seen_moveout_batch_id INTEGER REFERENCES import_batch(batch_id),
  missing_moveout_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(move_out_date IS NOT NULL),
  CHECK(NOT (closed_at IS NOT NULL AND canceled_at IS NULL))
);
-- Migration 003:
ALTER TABLE turnover ADD COLUMN wd_present_type TEXT;
```

**All indexes on turnover**

- `CREATE UNIQUE INDEX idx_one_open_turnover_per_unit ON turnover(unit_id) WHERE closed_at IS NULL AND canceled_at IS NULL;` (schema.sql lines 64–66) — **one open turnover per unit**.
- `CREATE INDEX idx_turnover_unit_id ON turnover(unit_id);` (schema.sql line 228)
- `CREATE INDEX idx_turnover_move_out_date ON turnover(move_out_date);` (schema.sql line 229)
- `CREATE INDEX idx_turnover_move_in_date ON turnover(move_in_date);` (schema.sql line 230)

**CHECK constraints on turnover**

- `manual_ready_status`: IN ('Vacant ready', 'Vacant not ready', 'On notice') OR NULL
- `expedited_flag`: IN (0, 1)
- `wd_present`, `wd_supervisor_notified`, `wd_installed`: IN (0, 1) or NULL
- `move_out_date IS NOT NULL`
- `NOT (closed_at IS NOT NULL AND canceled_at IS NULL)`

**CHECK constraints on task**

From `the-dmrb/db/schema.sql` (task table); migrations 003 add columns only, no CHECK change:

- `execution_status` IN ('NOT_STARTED', 'SCHEDULED', 'IN_PROGRESS', 'VENDOR_COMPLETED', 'NA', 'CANCELED')
- `confirmation_status` IN ('PENDING', 'CONFIRMED', 'REJECTED', 'WAIVED')
- `required`, `blocking` IN (0, 1)
- `execution_status != 'VENDOR_COMPLETED' OR vendor_completed_at IS NOT NULL`
- `confirmation_status != 'CONFIRMED' OR vendor_completed_at IS NOT NULL`
- `confirmation_status != 'CONFIRMED' OR manager_confirmed_at IS NOT NULL`

---

## 5) Baseline import behavior snapshot

Report types and where they are parsed, columns read, turnover columns written, and conflicts emitted. Source: `the-dmrb/services/import_service.py`.

| Report type        | Parsed in (function)   | Report columns read (file format) | Turnover columns written | Conflicts / validation status emitted |
|--------------------|------------------------|------------------------------------|--------------------------|----------------------------------------|
| **MOVE_OUTS**      | `_parse_move_outs`     | CSV: skip 6 rows; columns `Unit`, `Move-Out Date` | New turnover: property_id, unit_id, source_turnover_key, move_out_date, move_in_date=None, report_ready_date=None, created_at, updated_at, last_seen_moveout_batch_id, missing_moveout_count=0. Existing (match): last_seen_moveout_batch_id, missing_moveout_count=0, updated_at. Post-pass (not seen): missing_moveout_count+=1 or canceled_at, cancel_reason, updated_at. | MOVE_OUT_DATE_MISSING (invalid); MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER (conflict) |
| **PENDING_MOVE_INS** | `_parse_pending_move_ins` | CSV: skip 5 rows; columns `Unit`, `Move In Date` | move_in_date, updated_at (on existing open turnover) | MOVE_IN_WITHOUT_OPEN_TURNOVER (conflict) when unit missing or no open turnover |
| **AVAILABLE_UNITS** | `_parse_available_units` | CSV: skip 5 rows; columns `Unit`, `Status`, `Available Date`, `Move-In Ready Date` | report_ready_date, updated_at (on existing open turnover) | IGNORED: NO_OPEN_TURNOVER_FOR_READY_DATE when unit missing or no open turnover |
| **DMRB**            | `_parse_dmrb`          | Excel sheet "DMRB "; columns `Unit`, `Ready_Date`, `Move_out`, `Move_in`, `Status`; dedup by unit_code_norm | report_ready_date, updated_at (on existing open turnover) | IGNORED: NO_OPEN_TURNOVER_FOR_READY_DATE when unit missing or no open turnover |
| **PENDING_FAS**     | `_parse_pending_fas`    | CSV: skip 4 rows; rename "Unit Number"→"Unit"; columns `Unit`, `MO / Cancel Date` | No turnover columns written; import_row only | PENDING_FAS_MOVE_OUT_MISMATCH (conflict) when mo_cancel_date != turnover move_out_date; IGNORED: NO_OPEN_TURNOVER_FOR_VALIDATION when unit missing or no open turnover |

All parsers filter rows by phase derived from normalized unit code: `_filter_phase(rows)` keeps only rows where `_phase_from_norm(unit_norm)` is in `VALID_PHASES = (5, 7, 8)`.

Idempotency: before parsing, `repository.get_import_batch_by_checksum(conn, checksum)` is used; if a batch exists with that checksum, the function returns immediately with status NO_OP (checksum only; report_type not part of key).

---

## 6) Baseline UI contract snapshot (what must not change)

**Main board/grid (DMRB Board) — columns shown**

Source: `the-dmrb/app.py` `render_dmrb_board`: `table_data.append({...})`, `column_order`, `column_config`. Column order and identity:

1. ▶ (checkbox, for navigation to detail)
2. Unit
3. Status
4. Move-Out
5. Ready Date
6. DV
7. Move-In
8. DTBR
9. N/V/M
10. Inspection
11. Carpet Bid
12. Make Ready Bid
13. Paint
14. Make Ready
15. Housekeeping
16. Carpet Clean
17. Final Walk
18. Assignee
19. W/D
20. Quality Control
21. Phase
22. Building
23. Unit #
24. Alert
25. Notes

**Editable inline (not in disabled_cols)**

- **Status** (selectbox; maps to turnover `manual_ready_status`)
- **Inspection, Carpet Bid, Make Ready Bid, Paint, Make Ready, Housekeeping, Carpet Clean, Final Walk** (selectboxes; map to task `execution_status` for the corresponding task type)
- **Quality Control** (selectbox; maps to QC task `confirmation_status`)

**Read-only (disabled) columns**

- Unit, Move-Out, Ready Date, DV, Move-In, DTBR, N/V/M, Assignee, W/D, Phase, Building, Unit #, Notes, Alert

Same column set and editability are used when backend is used (session state is replaced by board_query_service + turnover_service/task_service for writes when enable_db_writes is on).

---

## 7) Golden dataset proposal (for regression testing later)

Minimal set of scenarios (5–10 units) to exercise key behaviors. No files created; scenarios only.

1. **Move-out updates**  
   Unit A: open turnover exists with move_out_date D1. Import MOVE_OUTS with same unit, move_out_date D1 → last_seen_moveout_batch_id and missing_moveout_count=0 updated; no new turnover.

2. **Move-in updates**  
   Unit B: open turnover, move_in_date NULL. Import PENDING_MOVE_INS with unit B, move_in_date D2 → turnover.move_in_date set to D2, audit written.

3. **Availability / ready date**  
   Unit C: open turnover, report_ready_date NULL. Import AVAILABLE_UNITS (or DMRB) with unit C and a Move-In Ready Date / Ready_Date D3 → turnover.report_ready_date set to D3, audit written.

4. **FAS appears then disappears**  
   Unit D: open turnover. Import MOVE_OUTS without unit D → missing_moveout_count=1. Second MOVE_OUTS import again without unit D → missing_moveout_count=2, turnover canceled (canceled_at, cancel_reason set). Reappearance: unit D in a later MOVE_OUTS → if implemented, would reset count (currently next MOVE_OUTS with D resets missing_moveout_count and last_seen_moveout_batch_id).

5. **Manual date edit overwritten by next import**  
   Unit E: open turnover, move_in_date set manually to D4. Import PENDING_MOVE_INS with unit E, move_in_date D5 → turnover.move_in_date overwritten to D5 (report-authoritative).

6. **Manual / legal override case (FAS missing)**  
   Unit F: open turnover; manager keeps it open despite FAS (PENDING_FAS) not showing the unit (or MO/Cancel date mismatch). Import PENDING_FAS with unit F and different MO/Cancel date → conflict row (PENDING_FAS_MOVE_OUT_MISMATCH); turnover not auto-canceled. Optional: unit F not in two consecutive MOVE_OUTS → after two MOVE_OUTS imports without F, turnover canceled (move-out disappearance policy).

7. **New turnover creation**  
   Unit G: no open turnover. Import MOVE_OUTS with unit G, move_out_date D6 → new turnover created, source_turnover_key set, tasks instantiated, import_row OK.

8. **Move-in without turnover (conflict)**  
   Unit H: no open turnover (or unit H not in unit table). Import PENDING_MOVE_INS with unit H → conflict MOVE_IN_WITHOUT_OPEN_TURNOVER; no turnover created.

9. **Move-out date mismatch (conflict)**  
   Unit I: open turnover with move_out_date D7. Import MOVE_OUTS with unit I, move_out_date D8 (exact mismatch) → conflict MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER; turnover unchanged.

10. **Invalid row (missing move-out date)**  
    Unit J: any. Import MOVE_OUTS with unit J, Move-Out Date empty/invalid → import_row INVALID, conflict_reason MOVE_OUT_DATE_MISSING; no turnover created/updated.

These scenarios cover move-out updates, move-in updates, ready date updates, FAS disappearance and cancellation, report overwrite of manual date, FAS mismatch (no auto-merge), new turnover creation, move-in-without-turnover conflict, move-out mismatch conflict, and invalid row handling.
