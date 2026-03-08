# POST-CLEANUP CODEBASE HEALTH STATUS — THE-DMRB

**Read-only health report after cleanup. No files modified.**

---

## SECTION 1 — Repo Map (Post-cleanup)

### 1) Top-level tree

**Repo root:**
```
.
├── AGENTS.md
├── blueprint.md
├── backups/
│   ├── db/
│   └── frontend/
├── refecerence_context/
├── the-dmrb/
└── (.pytest_cache, .DS_Store)
```

**the-dmrb/:**
```
the-dmrb/
├── README.md
├── app.py
├── requirements.txt
├── data/
│   ├── VERIFY_IMPORT.md
│   ├── cockpit.db, cockpit_BACKUP_PHASE0.db, test_imports/*.csv
├── db/
│   ├── connection.py
│   ├── repository.py
│   ├── schema.sql
│   └── migrations/
│       └── 001_add_report_ready_date.sql … 009_add_legal_and_availability_columns.sql
├── docs/
│   └── *.md
├── domain/
│   ├── enrichment.py, lifecycle.py, risk_engine.py, sla_engine.py, unit_identity.py
├── scripts/
│   ├── analyze_units_csv.py
│   └── verify_stage2_dual_write.py
├── services/
│   ├── board_query_service.py, import_service.py, manual_availability_service.py,
│   ├── note_service.py, risk_service.py, sla_service.py, task_service.py,
│   ├── turnover_service.py, unit_master_import_service.py
├── spec/
│   └── (architecture, audits, import_ops, ui, *.md)
├── tests/
│   └── test_*.py (enrichment_harness, manual_availability, truth_safety, unit_identity, unit_master_import)
└── ui/
    ├── __init__.py
    ├── mock_data.py
    └── mock_data_v2.py
```

### 2) Single entrypoint

- **Entrypoint:** `the-dmrb/app.py`
- **Run:** From repo root: `streamlit run the-dmrb/app.py`. DB path: `COCKPIT_DB_PATH` or default `the-dmrb/data/cockpit.db`.

### 3) Mock/prototype files

- **Removed (not in tree):** `app_prototype.py`, `app_prototype_v2.py`, `parsers/`, `utils/`, `ui/components/`.
- **Still present but not used by app:** `ui/mock_data.py`, `ui/mock_data_v2.py` — no import in `app.py`. Referenced only by:
  - `tests/test_enrichment_harness.py` (imports and uses `mock_data_v2`)
  - Comments in `services/board_query_service.py` (“Mirrors mock_data_v2…”).
- **Conclusion:** Mock/prototype **entrypoints** are gone and not referenced. Mock **data modules** remain as test/artifact dependencies only.

---

## SECTION 2 — Runtime Path (Backend Only)

### Exact modules imported at startup (app.py)

1. **Stdlib:** `copy`, `os`, `sqlite3`, `date` (from `datetime`), `Optional` (from `typing`).
2. **Third-party:** `pandas`, `streamlit`.
3. **Backend (inside try):**  
   `db.connection` (`get_connection`, `ensure_database_ready`),  
   `db.repository` (as `db_repository`),  
   `services.board_query_service`,  
   `services.import_service` (as `import_service_mod`),  
   `services.manual_availability_service` (as `manual_availability_service_mod`),  
   `services.note_service` (as `note_service_mod`),  
   `services.task_service` (as `task_service_mod`),  
   `services.turnover_service` (as `turnover_service_mod`),  
   `services.unit_master_import_service` (as `unit_master_import_service_mod`).

On **any** exception in that try block: `_BACKEND_AVAILABLE = False`, `_BACKEND_ERROR = _e`, service/repo refs set to `None`.

### Try/except and backend failures

- **Import-time:** Failure is **not** masked. After `st.set_page_config`, `if not _BACKEND_AVAILABLE: st.error(...); st.stop()`.
- **DB init:** `ensure_database_ready(_get_db_path())` is run once after session init; on exception: `st.error(...); st.stop()`.
- **Runtime connection:** `_get_conn()` catches `Exception` from `get_connection(db_path)` and returns `None`. So **connection failures at runtime are masked** (no exception propagated); callers see `None` and show `st.error("Database not available")` or empty data. The **underlying exception** is not shown to the user.

### DB path and open

- **Defined:** `_get_db_path()` in `app.py`: `os.environ.get("COCKPIT_DB_PATH", os.path.join(os.path.dirname(__file__) or ".", "data", "cockpit.db"))`.
- **Opened:** `db/connection.py` — `get_connection(db_path)` creates parent dirs, `sqlite3.connect(db_path)`, sets `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, `row_factory=sqlite3.Row`.

### ensure_database_ready on startup

- **Runs:** Yes, in `app.py` after `_init_session_state()`, before any page logic.
- **Behavior:** Opens DB, ensures `turnover` exists (else runs `schema.sql`, sets schema_version to 3), ensures `schema_version` table and row, then applies migrations 001–009 in order with per-migration commit. Raises on failure; app then shows error and `st.stop()`.

**Flow summary:**  
`app.py` → (backend try) → `db.connection` + `db.repository` + all listed services.  
Board/detail data: `app.py` → `board_query_service.get_dmrb_board_rows` / `get_turnover_detail` → `repository.list_open_turnovers`, `get_turnover_by_id`, units, tasks, notes → `domain.enrichment` (compute_facts, derive_phase, etc.) → `domain.lifecycle`, `sla_engine`, `risk_engine`.  
Writes: `app.py` → `turnover_service`, `task_service`, `note_service`, etc. → `repository.update_*`, `insert_*` → SQLite.

---

## SECTION 3 — Imports Health (import_service.py)

### Compilation

- **Syntax:** `python3 -m py_compile the-dmrb/services/import_service.py` → exit 0. No syntax errors.

### Report handlers and columns written

| Report type        | Matching key / logic | Turnover columns written | import_row status outcomes | Gaps |
|--------------------|----------------------|---------------------------|----------------------------|------|
| **MOVE_OUTS**      | Unit (norm) + open turnover or create | New: `move_out_date`, `source_turnover_key`, `created_at`, `updated_at`, `last_seen_moveout_batch_id`, `missing_moveout_count`, `scheduled_move_out_date`. Existing match: `last_seen_moveout_batch_id`, `missing_moveout_count`, `updated_at`, `scheduled_move_out_date`. New turnover: also 009 columns via `insert_turnover` (repository). | OK, CONFLICT (MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER), INVALID (MOVE_OUT_DATE_MISSING). All rows written with `conflict_reason` and `validation_status`. | None. |
| **PENDING_MOVE_INS** | Unit + open turnover | `move_in_date`, `updated_at`. | OK, CONFLICT (MOVE_IN_WITHOUT_OPEN_TURNOVER). `move_out_date`/`move_in_date` passed to `_write_import_row`. | None. |
| **AVAILABLE_UNITS** | Unit + open turnover | `report_ready_date`, `updated_at`, `available_date`, `availability_status` (009). | OK, IGNORED (NO_OPEN_TURNOVER_FOR_READY_DATE). | None. |
| **PENDING_FAS**    | Unit + open turnover; FAS date vs turnover move_out | `confirmed_move_out_date`, `legal_confirmation_source`, `legal_confirmed_at`, `updated_at` (009). | OK, CONFLICT (PENDING_FAS_MOVE_OUT_MISMATCH), IGNORED (NO_OPEN_TURNOVER_FOR_VALIDATION). | None. |
| **DMRB**           | Same as AVAILABLE_UNITS (unit + open turnover) | `report_ready_date`, `updated_at`, `available_date` (no `availability_status`). | Same as AVAILABLE_UNITS. | None. |

### import_batch / import_row and schema

- **import_batch:** Code uses `report_type`, `checksum`, `source_file_name`, `record_count`, `status`, `imported_at`. All exist in `schema.sql` (batch_id PK). No missing columns.
- **import_row:** Code writes `batch_id`, `raw_json`, `unit_code_raw`, `unit_code_norm`, `move_out_date`, `move_in_date`, `validation_status`, `conflict_flag`, `conflict_reason`. Schema has all of these. Every branch that records an outcome calls `_write_import_row` with `validation_status` and, where applicable, `conflict_reason`; conflict paths set `conflict_flag=1`.

---

## SECTION 4 — Authority & Drift Readiness (move_out_date)

Every place **move_out_date** is read as authority for lifecycle, DV, SLA, risks, or UI:

| File | Function / location | Use | If we switch to “effective move-out date” | Minimum set for Stage 3? |
|------|----------------------|-----|-------------------------------------------|---------------------------|
| **domain/lifecycle.py** | `derive_lifecycle_phase(move_out_date=...)` | Phase (NOTICE, VACANT, SMI, etc.). | Caller must pass effective date instead of row move_out_date. | Yes (single domain entrypoint). |
| **domain/enrichment.py** | `derive_phase(t, today)` → `t.get("move_out_date")`; `compute_facts(row, today)` → `row.get("move_out_date")` for DV and phase. | Phase and DV (business_days(move_out, today)). | Row must carry effective move-out (or caller passes it); derive_phase/compute_facts use it. | Yes (single enrichment entrypoint; callers pass row). |
| **domain/sla_engine.py** | `evaluate_sla_state(move_out_date=...)` | SLA breach (days since move-out > 10). | Caller must pass effective date. | Yes. |
| **domain/risk_engine.py** | `evaluate_risks(move_out_date=...)` | Risk evaluation (move_out_date is an input). | Caller must pass effective date. | Yes. |
| **services/turnover_service.py** | All call sites of `reconcile_sla_for_turnover` and `reconcile_risks_for_turnover` pass `move_out_date` from `row["move_out_date"]` (or `mo_eff` after update). | SLA and risk reconciliation after any turnover change. | Compute effective move-out (e.g. confirmed_move_out_date or move_out_date) once per row and pass it into both reconciles. | Yes (single service layer that calls SLA/risk). |
| **services/board_query_service.py** | `_build_flat_row()` → `"move_out_date": turnover.get("move_out_date")`. | Row passed to enrichment. | Flat row should include effective move-out (or enrichment reads it from turnover dict). | Yes (enrichment consumes this row). |
| **app.py** | Display `row.get("move_out_date")` in board; detail `t.get("move_out_date")` for date input and `turnover_service_mod.update_turnover_dates(move_out_date=...)`. | UI display and manual date edit. | Display effective (or keep move_out_date for “report” and show effective separately); edits may still write to move_out_date or to a dedicated effective field per product decision. | Optional (UI can show effective without changing authority until Stage 3). |

**Minimum set to change for Stage 3 (authority switch):**

1. **domain/lifecycle.py** — `derive_lifecycle_phase`: keep signature; callers pass effective date.
2. **domain/enrichment.py** — `derive_phase` and `compute_facts`: take effective move-out from row or explicit arg (row should carry it).
3. **domain/sla_engine.py** — `evaluate_sla_state`: callers pass effective date.
4. **domain/risk_engine.py** — `evaluate_risks`: callers pass effective date.
5. **services/turnover_service.py** — wherever `move_out_date` is read from row for SLA/risk, compute effective (e.g. `confirmed_move_out_date or move_out_date`) and pass that.
6. **services/board_query_service.py** — `_build_flat_row`: add effective move-out to row (or compute in enrichment from turnover dict).

---

## SECTION 5 — Data Reality Check (DB vs Code)

### Migration 009 and turnover columns

- **009 adds:** `scheduled_move_out_date`, `confirmed_move_out_date`, `legal_confirmation_source`, `legal_confirmed_at`, `legal_confirmation_note`, `available_date`, `availability_status`.
- **repository.py:** `TURNOVER_UPDATE_COLS` and `insert_turnover` include these. Schema after 009 matches code.

### One open turnover per unit

- **Constraint:** `CREATE UNIQUE INDEX idx_one_open_turnover_per_unit ON turnover(unit_id) WHERE closed_at IS NULL AND canceled_at IS NULL` (schema.sql).
- **Code:** `repository.get_open_turnover_by_unit(conn, unit_id)` and `list_open_turnovers` filter `closed_at IS NULL AND canceled_at IS NULL`. Import and manual add assume one open per unit. No code path creates a second open turnover for the same unit; constraint enforces it.

### schema_version and migration runner

- **Table:** `schema_version(singleton, version)`. connection.py ensures one row, version 0 initially.
- **Runner:** `ensure_database_ready` applies 001–009 in order; after each, `UPDATE schema_version SET version = n`. Migrations 4, 7, 8 run Python backfills after their SQL. Version is correct and runner behavior is as designed.

### Schema/code mismatches

- **Schema vs code:** No missing turnover/task/import_row columns used by code. Task: schema (base) has no assignee/blocking_reason; migration 003 adds them; repository `TASK_UPDATE_COLS` and updates use them. Consistent.
- **Constraint mismatch:** None identified. “One open turnover per unit” is both enforced and assumed by code.

---

## SECTION 6 — What’s Hurting You Right Now (Top 10)

1. **Runtime connection failures are invisible**  
   - **Why it hurts:** User sees “Database not available” but not the real error (e.g. permission, lock, path).  
   - **Where:** `app.py` `_get_conn()` catches Exception and returns None.  
   - **What breaks first:** Debugging production or CI DB issues.

2. **Mock data modules still in UI package**  
   - **Why it hurts:** Confusion; risk of accidental re-use; tests depend on production-looking module names.  
   - **Where:** `ui/mock_data.py`, `ui/mock_data_v2.py`.  
   - **What breaks first:** Onboarding or refactors that assume “ui/ = app runtime only.”

3. **No end-to-end test of Import → DB**  
   - **Why it hurts:** Regressions in import or repository not caught by app run alone.  
   - **Where:** Import page calls `import_service_mod.import_report_file()` but no pytest runs a full import and asserts on DB.  
   - **What breaks first:** Import or schema changes that break MOVE_OUTS/PENDING_FAS/AVAILABLE_UNITS.

4. **Lifecycle/SLA/risk all use move_out_date only**  
   - **Why it hurts:** Stage 3 (effective move-out) requires coordinated change; any missed call site keeps old authority.  
   - **Where:** Section 4 list (lifecycle, enrichment, sla_engine, risk_engine, turnover_service, board_query_service).  
   - **What breaks first:** Inconsistent behavior after partial “effective date” rollout.

5. **Phase filter still legacy property_id in places**  
   - **Why it hurts:** Filter uses phase_code/property_id string; hierarchy is phase_id-based. Drift between filter semantics and list_open_turnovers(phase_ids=).  
   - **Where:** app.py DMRB/Flag Bridge phase opts from `phase_id_by_code`; repository list_open_turnovers by phase_ids or property_ids.  
   - **What breaks first:** Wrong list when multiple properties or phase coding diverges.

6. **ensure_database_ready runs on every Streamlit rerun**  
   - **Why it hurts:** Repeated open/read/close and migration check on every request until version is 9.  
   - **Where:** app.py top-level after session init.  
   - **What breaks first:** Unnecessary load or lock risk under concurrency (if ever multi-user).

7. **Import page commits but caller owns transaction**  
   - **Why it hurts:** app.py calls `conn.commit()` after import_report_file; contract says “caller owns transaction.” Easy to double-commit or forget in other callers.  
   - **Where:** app.py render_import() vs import_service docstring.  
   - **What breaks first:** Script or other caller that doesn’t commit and assumes import committed.

8. **Operational state / attention badge not in backend**  
   - **Why it hurts:** UI derives from enrichment only; no single source of truth for “operational state” in DB or domain.  
   - **Where:** board_query_service + domain/enrichment; spec (ui_v2_backend_compatibility.md) notes gap.  
   - **What breaks first:** Reporting or audits that expect operational state to be queryable.

9. **Backup-on-import optional and not default**  
   - **Why it hurts:** Large imports can corrupt DB with no automatic backup.  
   - **Where:** import_service.import_report_file(..., db_path=, backup_dir=); app passes db_path but backup_dir is None.  
   - **What breaks first:** Accidental overwrite or bad file with no restore point.

10. **Tests depend on mock_data_v2 structure**  
    - **Why it hurts:** Changing mock_data_v2 for tests can break test_enrichment_harness; app no longer uses it so structure can drift from real row shape.  
    - **Where:** tests/test_enrichment_harness.py.  
    - **What breaks first:** Enrichment or repository changes that change row shape and don’t update mock_data_v2.

---

## SECTION 7 — Stage Progress Scoreboard

| Stage | Status | Evidence | Blocker if not done |
|-------|--------|----------|----------------------|
| **Stage -1 (backend restore)** | **DONE** | `import_service.py` compiles; `python3 -m py_compile the-dmrb/services/import_service.py` succeeds. No syntax error. | — |
| **Stage 0 (backend proof)** | **DONE** | Single entrypoint `app.py`; backend-only; `ensure_database_ready` on startup; app runs with DB. Import page calls `import_service_mod.import_report_file()` and commits. | — |
| **Stage 1 (migration 009)** | **DONE** | `db/migrations/009_add_legal_and_availability_columns.sql` exists; connection.py `_MIGRATIONS` includes (9, "009_..."); repository insert_turnover/update_turnover use 009 columns; import_service writes scheduled_move_out_date, confirmed_move_out_date, legal_*, available_date, availability_status. | — |
| **Stage 2 (dual-write)** | **DONE** | MOVE_OUTS and new turnover write both move_out_date and scheduled_move_out_date; PENDING_FAS writes confirmed_move_out_date, legal_confirmation_source, legal_confirmed_at; AVAILABLE_UNITS/DMRB write available_date (and availability_status for AVAILABLE_UNITS). | — |
| **Stage 2D (verification script)** | **DONE** | `scripts/verify_stage2_dual_write.py` exists; STAGE2D_VERIFICATION.md documents run after MOVE_OUTS, AVAILABLE_UNITS, PENDING_FAS. | — |
| **Stage 3 (authority switch)** | **NOT DONE** | Lifecycle, DV, SLA, and risks still use move_out_date only (Section 4). No “effective move-out” derivation in code. | Need to implement effective move-out (e.g. confirmed_move_out_date or move_out_date) and pass it through lifecycle, enrichment, SLA, risk, and board row. |
| **Stage 4 (minimal UI indicator)** | **NOT DONE** | No UI showing “effective move-out” or authority source. | Stage 3 first; then add indicator in app.py (detail/board). |
| **Stage 5 (hardening)** | **NOT DONE** | No systematic backup-on-import, no E2E import test, connection errors still masked at runtime. | Product/ops priorities; Section 6 items. |

---

**End of report. No design, no refactoring suggestions, no implementation, no edits.**
