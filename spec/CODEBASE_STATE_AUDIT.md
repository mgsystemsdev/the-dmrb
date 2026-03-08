# CODEBASE STATE AUDIT — HARD TRUTH (READ ONLY)

Findings from full repo read. No files were modified during this audit.

---

## SECTION A — What is failing right now (blocking runtime)

### 1. SyntaxError in `the-dmrb/services/import_service.py` (line 507)

- **Exact error:** `SyntaxError: invalid syntax` at the `else:` keyword.
- **Cause:** The `else:` at line 506 is indented one level too deep. It sits inside the `if open_turnover is None:` block (lines 498–505). In Python, an `else` cannot appear as a second statement inside an `if` block; it must align with its `if`.
- **Downstream impact:**
  - `python3 -m py_compile the-dmrb/services/import_service.py` fails.
  - `from services import turnover_service` fails (because `turnover_service` imports `import_service`).
  - The top-level try in `app.py` (lines 19–31) that does `from services import turnover_service` (and related services) raises, so `_BACKEND_AVAILABLE = False` and `_BACKEND_ERROR = <the exception>`.
  - **Result:** Backend mode never loads. The app always runs with backend disabled. Even if the user unchecks "Use mock data", the app has no DB path for report imports and the Import page never calls `import_service.import_report_file` (see Section A.2).

### 2. Import page does not call the backend (fake success)

- **File:** `the-dmrb/app.py`, function `render_import()` (lines 1642–1650).
- **Behavior:** "Run import" button always shows a hardcoded success message:  
  `st.success("Batch ID: 1 | Status: SUCCESS | Records: 42 | Conflicts: 2 | Applied: 38")` and conflicts from `mock_data_v2.MOCK_CONFLICTS_V2`.
- **Missing:** No call to `import_service.import_report_file()`, no `get_connection`, no commit/rollback. So report types (MOVE_OUTS, AVAILABLE_UNITS, PENDING_FAS, etc.) are never ingested; DB stays at 0 turnovers from report imports.
- **Conclusion:** Even after fixing the syntax error, the Import page must be wired to `import_service.import_report_file()` and a real DB connection for Track 1 (backend restoration) to succeed.

### 3. Zero turnovers in DB

- **Observation:** `sqlite3 the-dmrb/data/cockpit.db "SELECT COUNT(*) FROM turnover;"` returns **0**.
- **Reason:** No code path in the app currently runs `import_service.import_report_file()` for MOVE_OUTS (or any report type). Unit Master Import only touches `unit` (and phase/building); it does not create turnovers. So verification scripts (e.g. `verify_stage2_dual_write.py`) that expect at least one turnover cannot succeed until at least one report import is run (e.g. MOVE_OUTS).

---

## SECTION B — What must remain (core execution spine)

Minimum required for backend mode end-to-end (app → services → repository → sqlite):

| Layer | File / module | Purpose |
|-------|----------------|---------|
| Entry | `the-dmrb/app.py` | Single entrypoint; session state; backend/mock switch; UI; must eventually call `import_service.import_report_file` for report imports. |
| DB | `the-dmrb/db/connection.py` | `get_connection`, `ensure_database_ready`, schema init, migrations. |
| DB | `the-dmrb/db/repository.py` | All reads/writes: turnover, unit, task, import_batch, import_row, audit_log, etc. |
| Services | `the-dmrb/services/import_service.py` | Report ingestion (MOVE_OUTS, PENDING_FAS, AVAILABLE_UNITS, etc.), idempotency, dual-write columns, task instantiation; used by `turnover_service` and (when wired) by Import page. |
| Services | `the-dmrb/services/turnover_service.py` | Turnover create/update; calls `import_service.instantiate_tasks_for_turnover`. |
| Services | `the-dmrb/services/board_query_service.py` | Board rows for UI from DB. |
| Services | `the-dmrb/services/task_service.py`, `note_service.py`, `manual_availability_service.py`, `unit_master_import_service.py` | In-app writes and Unit Master Import. |
| Domain | `the-dmrb/domain/lifecycle.py`, `risk_engine.py`, `sla_engine.py`, `unit_identity.py`, `enrichment.py` | Pure logic; used by services. |
| Schema | `the-dmrb/db/schema.sql` | Canonical DDL. |
| Scripts | `the-dmrb/scripts/verify_stage2_dual_write.py` | Stage 2D verification (run after imports; requires turnover_id). |

Dependencies: `app.py` → (when backend) `db.connection`, `db.repository`, `board_query_service`, `turnover_service`, …; `turnover_service` → `import_service`; so **fixing `import_service.py` is required** for any backend load.

---

## SECTION C — What should be removed or quarantined (and why)

| Item | Safe to delete now? | Prerequisite / note |
|------|----------------------|----------------------|
| `the-dmrb/app_prototype.py` | **Yes** | Already exits immediately with "v1 prototype is disabled. Use app.py instead." No unique behavior; uses old `mock_data`. |
| `the-dmrb/app_prototype_v2.py` | **After Track 1** | Near-copy of `app.py` (same backend try/except, same pages). Keep until backend is proven; then remove once `app.py` is the single entrypoint (Cleanup Stage B). |
| `the-dmrb/ui/mock_data.py` | **After Track 1** | Only referenced by `app_prototype.py`. Once prototype is removed, safe to delete (Cleanup Stage C). |
| `the-dmrb/ui/mock_data_v2.py` | **After Track 1, and only when mock path is removed** | Heavily used by `app.py` for session state init, dropdowns, and all mock branches. Remove only when Cleanup Stage C (remove mock mode) is executed; until then it is part of the "must remain" set for the app to run. |
| `the-dmrb/parsers/` | **Yes** | Empty directory (0 files). Safe to remove as dead folder. |
| `the-dmrb/utils/` | **Yes** | Empty directory (0 files). Safe to remove as dead folder. |
| `the-dmrb/ui/components/` | **Yes** | Empty directory (0 files). Safe to remove as dead folder. |

**Silent fallback to mock:** In `app.py`, when backend imports fail (line 28–31), `_BACKEND_AVAILABLE = False` and the app still runs; `use_mock` defaults to `True` (line 150–151), so the user sees a working UI with mock data. That is "fake success" in the sense that no error is shown and no backend is used. After fixing the syntax error, backend will load and the sidebar "Use mock data" will actually switch to DB; the next step is to wire Import to `import_service.import_report_file()` and run a test import so turnover count > 0.

---

## SECTION D — Proposed cleanup sequence (no code)

Staged plan; each step includes scope, verification command, and rollback note.

1. **Stage -1: Fix backend blocker**  
   - **Scope:** `the-dmrb/services/import_service.py` only — fix indentation of the `else` block (lines 506–543) so it aligns with `if open_turnover is None:`; add `continue` after the `_write_import_row` in the `if open_turnover is None` branch so control flow is correct.  
   - **Verification:**  
     - `python3 -m py_compile the-dmrb/services/import_service.py`  
     - `cd the-dmrb && python3 -c "from services import turnover_service; print('OK')"`  
   - **Rollback:** Revert the single file; re-run compile to confirm syntax error reappears.

2. **Stage 0: Prove backend writes**  
   - **Scope:** Wire Import page (or a one-off script) to call `import_service.import_report_file()` for one test MOVE_OUTS file; run app in backend mode with DB writes enabled; run import.  
   - **Verification:**  
     - `sqlite3 the-dmrb/data/cockpit.db "SELECT COUNT(*) FROM turnover;"` → count > 0.  
     - Optional: `SELECT turnover_id, move_out_date, scheduled_move_out_date FROM turnover ORDER BY turnover_id DESC LIMIT 5;`  
   - **Rollback:** Delete or restore DB from backup; re-run import if needed.

3. **Stage 2D: Verify dual-write**  
   - **Scope:** Import test files for MOVE_OUTS, AVAILABLE_UNITS, PENDING_FAS; run existing verify script.  
   - **Verification:**  
     - `python the-dmrb/scripts/verify_stage2_dual_write.py the-dmrb/data/cockpit.db <turnover_id>`  
   - **Rollback:** Not applicable (read-only checks).

4. **Cleanup A: Backup + quarantine**  
   - **Scope:** Create `backups/` at repo root; copy `the-dmrb/data/cockpit.db` → `backups/db/cockpit_BACKUP_PHASE0.db`; optionally snapshot UI state in `backups/ui/`.  
   - **Verification:** Files exist under `backups/`.  
   - **Rollback:** None; additive only.

5. **Cleanup B: One entrypoint**  
   - **Scope:** Remove `app_prototype.py` and `app_prototype_v2.py` after confirming no unique code vs `app.py`.  
   - **Verification:** `streamlit run the-dmrb/app.py` from repo root; all pages and backend mode work.  
   - **Rollback:** Restore from version control.

6. **Cleanup C: Remove mock mode**  
   - **Scope:** Remove mock data path and fallback in `app.py`; require backend; app must fail loudly if backend fails.  
   - **Verification:** App runs only with `COCKPIT_DB_PATH` and backend; no "Use mock data" checkbox; no `mock_data_v2` usage for data path.  
   - **Rollback:** Restore from version control; large diff.

7. **Cleanup D: Remove empty/dead folders**  
   - **Scope:** Delete empty directories: `the-dmrb/parsers/`, `the-dmrb/utils/`, `the-dmrb/ui/components/` (if confirmed unused).  
   - **Verification:** `ls`/glob shows directories gone; app and tests still run.  
   - **Rollback:** Recreate empty dirs if any tooling expects them.

---

**Summary:** The single blocking issue for backend is the **SyntaxError in `import_service.py`**. Fixing it (Stage -1) unblocks backend load. The Import page must then be wired to `import_service.import_report_file()` and a real DB so that at least one MOVE_OUTS import can create turnovers (Stage 0). Cleanup (A–D) must follow after Track 1 is green.
