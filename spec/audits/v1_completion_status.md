# Turnover Cockpit v1 — Completion Status

Based on **Canonical Master Blueprint v1** (§17 Definition of Complete, §16 UI Contract, §15 Backup/Startup) and the current codebase.

---

## 1. Blueprint §17 — Definition of Complete (checklist)

| Criterion | Status | Notes |
|-----------|--------|--------|
| Imports deterministic and idempotent | **Done** | `import_service.py`: checksum, NO_OP, SUCCESS/FAILED |
| Turnovers created/updated without duplicates | **Done** | Schema partial unique index + import logic |
| Template instantiation correct and stable | **Done** | Import creates tasks + dependencies from templates |
| One-open-turnover invariant enforced | **Done** | `idx_one_open_turnover_per_unit` |
| Task dependencies exist and are queryable | **Done** | `task_dependency` + repo `get_task_template_dependencies` |
| Execution + confirmation semantics enforced | **Done** | `task_service`: mark_vendor_completed, confirm_task |
| Reject behavior works per spec | **Done** | `task_service.reject_task` |
| SLA breach events open/close correctly | **Done** | `sla_service` + `sla_engine` |
| Risks appear and auto-resolve deterministically | **Partial** | risk_engine + risk_service exist; EXPOSURE_RISK not wired (see below) |
| Conflicts captured and visible, no silent merges | **Done** | import_service writes CONFLICT rows + conflict_reason |
| Audit log for all critical changes | **Done** | import + turnover/task/sla/risk services write audit_log |
| Backups created; restore path validated | **Partial** | `backup_database()` exists and is called after SUCCESS import; no restore UI/script |

---

## 2. What Exists Today

- **DB:** `schema.sql`, `connection.py` (get_connection, initialize_database, run_integrity_check, backup_database), `repository.py` (full CRUD for units, turnovers, tasks, templates, dependencies, import_batch/row, audit_log, risk_flag, sla_event), `migrations/001_add_report_ready_date.sql`.
- **Domain:** `lifecycle.py` (derive_lifecycle_phase), `risk_engine.py` (evaluate_risks including EXPOSURE_RISK), `sla_engine.py`.
- **Services:** `import_service.py`, `turnover_service.py`, `task_service.py`, `risk_service.py`, `sla_service.py`.
- **Spec:** `import_contract_v1.md`.
- **No:** Streamlit app, UI layer (`ui/`), `app.py`, tests, scripts (e.g. init DB, run migrations, restore from backup).

---

## 3. Gaps to Reach 100% Complete

### 3.1 Wire EXPOSURE_RISK in risk_service (small)

- **Issue:** `risk_engine.evaluate_risks` has parameters `report_ready_date` and `manual_ready_confirmed_at` for EXPOSURE_RISK, but `risk_service.reconcile_risks_for_turnover` does not pass them.
- **Action:** In `risk_service.reconcile_risks_for_turnover`, accept (or read from turnover row) `report_ready_date` and `manual_ready_confirmed_at`; pass them into `evaluate_risks(...)` so EXPOSURE_RISK is computed and upserted/resolved like other risks.

### 3.2 UI layer (large)

Blueprint §16:

- **Dashboard (§16.1):** Sort by risk severity, move-in proximity, SLA age; sections: Immediate Action (CRITICAL), Needs Confirmation, Execution Overdue, Blocking Notes, Conflicts.
- **Turnover detail (§16.2):** Unit search; task status changes; vendor complete / confirm / reject; WD toggles; QC confirm; notes.
- **Import panel (§16.3):** Upload file, run import, summary (applied, conflicts, no-op/failed), link to conflict list.

**Action:** Add Streamlit entrypoint (e.g. `app.py`) and implement the three areas above (no business logic in UI; call services/repository).

### 3.3 Startup integrity + restore path (§15.2)

- **Current:** `run_integrity_check(db_path)` exists; no app startup that runs it and blocks on failure.
- **Action:** On app startup, run integrity check; if failed, block and show restore instructions + list of backups. Optionally add a small script or UI to restore from `data/backups/`.

### 3.4 Tests (recommended)

- **Current:** No `tests/` or test files.
- **Action:** Add tests for: domain (lifecycle, risk_engine, sla_engine), import_service (parsing, idempotency, conflict/disappearance), key service flows (task confirm/reject, SLA, risk reconcile).

### 3.5 Scripts (optional)

- **Current:** No scripts in `scripts/`.
- **Action:** Optional: `scripts/init_db.py`, `scripts/run_migrations.py`, `scripts/restore_backup.py` for local/dev use.

---

## 4. Rough Completion %

| Area | Weight | Done | Remaining |
|------|--------|------|-----------|
| Schema + DB + migrations | 10% | 100% | — |
| Domain (lifecycle, SLA, risk) | 15% | 100% | — |
| Repository | 15% | 100% | — |
| Import service (idempotent, conflicts, no silent merges) | 20% | 100% | — |
| Other services (turnover, task, risk, SLA) | 15% | ~95% | Wire EXPOSURE_RISK in risk_service |
| Backup on import + integrity check | 5% | 90% | Startup run + restore path |
| UI (Dashboard, Detail, Import) | 20% | 0% | Full UI per §16 |
| Tests | — | 0% | Recommended |
| **Overall (excluding tests)** | **100%** | **~75–80%** | UI + EXPOSURE_RISK + startup/restore |

---

## 5. Recommended Order to Finish

1. **Wire EXPOSURE_RISK** in `risk_service.reconcile_risks_for_turnover` (pass `report_ready_date`, `manual_ready_confirmed_at` into `evaluate_risks`).
2. **Streamlit app:** Add `app.py`, then Dashboard, then Turnover detail, then Import panel; on startup run `run_integrity_check` and block with restore instructions on failure.
3. **Restore path:** Either a simple script that copies a backup over the active DB, or a minimal “Restore” section in the app.
4. **Tests:** Domain and import_service first, then critical service paths.

Once (1)–(3) are done, the system meets the blueprint “Definition of Complete” for v1; (4) validates it.
