# DB initialization and migration hardening — analysis and design

**Goal:** Guarantee that whenever DB-mode is enabled, the database is (1) present, (2) schema-initialized, (3) fully migrated, and (4) safe to query before any repository or service call runs.

**Scope:** No hierarchy refactor, no identity model change. Focus only on deterministic, safe DB bootstrap.

---

## 1) Current DB lifecycle audit

### Where `_get_conn()` is called

All call sites are in **`app_prototype_v2.py`**:

| Line | Context |
|------|--------|
| 170 | `_db_write(do_write)` — gets conn, then `do_write(conn)`, commit/rollback, close |
| 269 | Sidebar "Top Flags" — when `use_mock=False`: get flag bridge rows via `board_query_service.get_flag_bridge_rows(conn, ...)` |
| 365 | `_get_dmrb_rows()` — when not mock: `board_query_service.get_dmrb_board_rows(conn, ...)` |
| 624 | DMRB board "Save" — when `enable_db_writes` and status/task updates: turnover_service + task_service writes |
| 670 | `_get_flag_bridge_rows()` — when not mock: `board_query_service.get_flag_bridge_rows(conn, ...)` |
| 825 | Detail page unit search (backend path) — `board_query_service.get_dmrb_board_rows(conn, ...)` for unit lookup |
| 865 | Detail page — when not mock: `board_query_service.get_turnover_detail(conn, tid, ...)` |

`_get_conn()` itself (lines 154–162): if `_BACKEND_AVAILABLE`, calls `get_connection(_get_db_path())` and returns the connection; on any exception returns `None`. So the **first** successful call to `get_connection(db_path)` can create an empty DB file (see below).

### Whether any code path ensures schema.sql is executed

- **`db/connection.py`** defines `initialize_database(db_path, schema_path)` which runs `schema.sql` via `executescript` **only when** `not os.path.isfile(db_path)` (lines 20–25).
- **The app never calls `initialize_database`.** No import and no invocation in `app_prototype_v2.py` or any other app entrypoint.
- **Tests:** `tests/test_truth_safety.py` builds an in-memory DB from `schema.sql` in `_fresh_db()` and applies migration 002 manually in `test_migration_preserves_data`. No production or dev path runs schema on startup.

**Conclusion:** No application code path ensures schema is applied.

### Whether any migration runner exists

- **No migration runner** in the app or in a dedicated script. The files under `db/migrations/` (001, 002, 003) are only applied manually or in tests.
- Migrations are **not idempotent** if run twice: 001 and 003 use `ALTER TABLE ... ADD COLUMN` (would raise "duplicate column name"); 002 renames/drops tables (second run would fail on missing `risk_flag_old` or wrong schema). So a runner must record applied migrations and skip them.

**Conclusion:** No migration runner; migrations must be applied in order and only once per DB.

### Whether the app can accidentally create an empty SQLite file

- **Yes.** `get_connection(db_path)` in `db/connection.py` (lines 7–14):
  1. Creates parent directory if missing: `os.makedirs(parent, exist_ok=True)`.
  2. Calls `sqlite3.connect(db_path)`. If `db_path` does not exist, SQLite **creates an empty database file**.
- So the **first** backend request that calls `_get_conn()` (e.g. sidebar flags or DMRB board) can create `data/cockpit.db` as an empty file. Later, `initialize_database(db_path, schema_path)` would **not** run schema because `os.path.isfile(db_path)` is true.

**Conclusion:** The app can and does create an empty DB file on first use; schema is never applied in that scenario.

### Whether multiple DB paths could be used

- **Single logical path per run:** `_get_db_path()` returns `os.environ.get("COCKPIT_DB_PATH", default)` with default `os.path.join(os.path.dirname(__file__) or ".", "data", "cockpit.db")`. So either the env value or the default is used consistently for that process.
- **Risk:** If a user sets `COCKPIT_DB_PATH` to a path that does not exist, first `get_connection` creates an empty file there. No other path is used in the same run.

**Conclusion:** One DB path per run; that path can point to an empty file created by the app.

---

## 2) Minimal deterministic bootstrap design

### Principles

- **Single entry point:** One function `ensure_database_ready(db_path)` responsible for “DB exists, schema applied, migrations applied, safe to use.”
- **Schema when missing:** Run `schema.sql` if the DB file does not exist **or** if it exists but a required table (e.g. `turnover`) is missing.
- **Migrations in order:** Apply 001, 002, 003 in order; record applied version; skip already-applied.
- **No service-layer pollution:** Bootstrap lives in `db/` (e.g. `connection.py` or a small `db/bootstrap.py`). Services and repository receive an already-ready connection.
- **No manual CLI required:** App startup or first DB use performs bootstrap automatically.

### Proposed `ensure_database_ready(db_path)` contract

- **Input:** `db_path: str` (same path used by `get_connection`).
- **Side effect:** Ensures the file at `db_path` exists and contains schema + all migrations. Creates file and/or applies schema/migrations only when needed.
- **Output:** None. Raises on unrecoverable failure (e.g. schema file missing, migration script missing, or SQL error during init/migrate).
- **Idempotent:** Safe to call on every startup or before first use; repeated calls no-op once DB is ready.

### Where to call it

- **Recommended: at app startup, when backend is enabled.** In `app_prototype_v2.py`, once per run when `use_mock` is False (or when backend may be used), call `ensure_database_ready(_get_db_path())` before any `_get_conn()` or board_query_service/repository usage. That way the first and every subsequent request sees an already-ready DB.
- **Alternative: on first `_get_conn()`.** Before returning the connection, call `ensure_database_ready(db_path)` (or a “ensure ready” check that runs schema+migrations if needed). This avoids touching the DB when user stays in mock mode, but couples bootstrap to the first backend request and requires care so the first request does not get a connection before ensure completes.
- **Recommendation:** Call at **startup** when backend is available (e.g. right after session state init, when `not st.session_state.use_mock` or unconditionally when `_BACKEND_AVAILABLE` so that switching to backend in the same session does not require a refresh). If desired, “startup” can be “first time we need DB” by using a module-level or session-state flag “db_ensured” and calling ensure once on first `_get_conn()` and setting the flag—but startup is simpler and more predictable.

### Detecting missing schema safely

- **Option A (recommended):** Open connection with `get_connection(db_path)`. Query `SELECT 1 FROM sqlite_master WHERE type='table' AND name='turnover' LIMIT 1`. If no row, schema is missing (empty DB or partial/corrupt). Then run schema + migrations (see below). Use the same connection for applying schema/migrations so no second connection races.
- **Option B:** If `not os.path.isfile(db_path)`, run schema + migrations (creating the file via the first `get_connection` inside ensure). If file exists, still check for table `turnover`; if missing, run schema + migrations. This handles both “no file” and “empty file created by earlier get_connection”.
- **Avoid:** Relying only on “file exists” to skip schema (current `initialize_database` bug).

### Tracking migration version

- **Table:** Add a small table used only by bootstrap, e.g. `schema_version` or `cockpit_migrations`:
  - `schema_version (version INTEGER PRIMARY KEY)` with a single row storing the highest applied migration number (e.g. 0 = only schema, 1 = schema+001, 2 = schema+001+002, 3 = schema+001+002+003).
- **Where it lives:** Either (1) in `schema.sql` so every new DB has it from the start, or (2) created by the bootstrap code before running migrations if it doesn’t exist. Option (1) is cleaner: add to `schema.sql`:
  - `CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL DEFAULT 0);`
  - `INSERT OR IGNORE INTO schema_version (version) VALUES (0);` (single row, version 0 after schema).
- **Bootstrap logic:** After ensuring schema is present (by running schema.sql if `turnover` was missing), read current version: `SELECT version FROM schema_version LIMIT 1`. For each migration 001..003, if current < 1 apply 001 and set version=1; if current < 2 apply 002 and set version=2; if current < 3 apply 003 and set version=3. Use a single transaction per migration (or one transaction for all pending migrations) and update `schema_version` at the end of each step so partial failure leaves a consistent version.

### Guaranteeing atomic behavior

- **Per migration:** Run each migration in a transaction: `BEGIN; ... migration SQL ...; UPDATE schema_version SET version = N; COMMIT;` (or equivalent). On failure, rollback so the DB is not left half-migrated.
- **Schema application:** Run `schema.sql` in a single transaction; commit only after full success. If schema fails, do not update version; next run will again see missing `turnover` and retry schema.
- **Single connection:** Use one connection for the whole ensure flow (open once, check table existence, apply schema if needed, apply migrations in order, commit each step, close). Avoid opening a second connection for “normal” use until ensure has finished.
- **SQLite:** `executescript` in Python runs multiple statements; it does not auto-commit between statements if you are inside an explicit transaction. Migration 002 uses `BEGIN TRANSACTION; ... COMMIT;` inside the script; that is compatible. For 001 and 003, wrap in `BEGIN; ... executescript(...); UPDATE schema_version; COMMIT;` in Python so version is updated atomically with the migration.

### Suggested bootstrap algorithm (pseudocode)

```
ensure_database_ready(db_path):
    schema_path = resolve path to db/schema.sql
    migrations_dir = resolve path to db/migrations/
    conn = get_connection(db_path)
    try:
        # 1) Ensure schema
        cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='turnover' LIMIT 1")
        if cur.fetchone() is None:
            with open(schema_path) as f:
                conn.executescript(f.read())
            conn.commit()

        # 2) Ensure schema_version table and current version
        # (If schema.sql was just run, schema_version already exists. If we add it to schema.sql, we're good.)
        cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        current = row[0] if row else 0

        # 3) Apply migrations in order
        for n, name in [(1, "001_add_report_ready_date.sql"), (2, "002_add_exposure_risk_type.sql"), (3, "003_add_assignee_blocking_wd_type.sql")]:
            if current >= n:
                continue
            path = os.path.join(migrations_dir, name)
            with open(path) as f:
                sql = f.read()
            conn.executescript(sql)
            conn.execute("UPDATE schema_version SET version = ?", (n,))
            conn.commit()
            current = n

    finally:
        conn.close()
```

- **Schema and schema_version:** Add `schema_version` to `schema.sql` (one table, one row, version 0). Then “run schema” creates that table; migration tracking is always available after schema apply.
- **Resolution of paths:** Pass schema_path and migrations_dir as arguments, or resolve relative to `db/` (e.g. `os.path.join(os.path.dirname(__file__), "schema.sql")` inside `db/connection.py`). App calls `ensure_database_ready(_get_db_path())` and does not need to know schema/migration paths.

### Clean architecture compliance

- **db/** owns persistence and bootstrap: `ensure_database_ready` lives in `db/connection.py` (or `db/bootstrap.py`). It uses `get_connection`, reads schema/migration files from the filesystem, and executes SQL. No UI or service logic.
- **App** only calls `ensure_database_ready(db_path)` once at startup (or first backend use) and then uses `_get_conn()` as today; services and repository remain unchanged.
- **No new dependencies.**

---

## 3) Failure modes

### Migration partially fails

- **Scenario:** e.g. 002 runs, commits, then 003 fails (file missing or SQL error). DB is at version 2; next run will apply only 003. If 002 had failed mid-way, transaction rollback (no commit) leaves version still at 1; next run retries 002.
- **Mitigation:** Run each migration in a single transaction; update `schema_version` in the same transaction; commit only after success. Do not commit between “half” of a migration and the rest.
- **002 note:** Migration 002 contains its own `BEGIN TRANSACTION; ... COMMIT;`. Run it as one script; then `UPDATE schema_version SET version = 2; COMMIT;` in the same connection so version and 002 are consistent. If 002’s script fails, the script’s transaction rolls back and we do not bump version.

### Corrupted state

- **Scenario:** Disk full, kill -9, or power loss during commit. SQLite is generally resilient (WAL, journal); worst case the DB file or WAL is inconsistent.
- **Mitigation:** (1) Do not expose “half-applied” schema_version: only commit when a full migration (and version update) succeeds. (2) Optional: after ensure, call existing `run_integrity_check(db_path)` and refuse to proceed (or surface error) if integrity check fails. That is a separate, optional hardening step.
- **Blocking writes until healthy:** If we run `ensure_database_ready` at startup and it raises, the app can show “Database initialization failed” and not call `_get_conn()` for normal operations (or `_get_conn()` returns None when ensure has not succeeded). So effectively “block” by not giving the app a connection until ensure has completed successfully. Optional: run integrity check after ensure and treat failure as “DB not ready.”

### Should writes be blocked until DB is healthy?

- **Yes, implicitly:** If `ensure_database_ready` is called before any use of the DB and it raises on failure, the app should not proceed to use the DB (e.g. show error and do not call repository/services). If ensure succeeds, all subsequent `_get_conn()` calls are safe for both read and write. So “healthy” means “ensure_database_ready completed without exception”; no separate “read-only until migrated” phase is required if we ensure once at startup.

---

## 4) Clean integration plan

### 4.1 Add `schema_version` to `schema.sql`

- At the end of `db/schema.sql` (after indexes), add:

```sql
-- ---------------------------------------------------------------------------
-- Bootstrap: migration version (managed by ensure_database_ready)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO schema_version (version) VALUES (0);
```

- Ensures every new DB created from schema has the table and version 0 (schema only, no migrations yet).

### 4.2 Implement `ensure_database_ready` in `db/connection.py`

- Add function `ensure_database_ready(db_path: str, schema_path: str | None = None, migrations_dir: str | None = None) -> None`.
- If `schema_path` is None, resolve to `os.path.join(os.path.dirname(__file__), "schema.sql")`. If `migrations_dir` is None, resolve to `os.path.join(os.path.dirname(__file__), "migrations")`.
- Logic:
  1. `conn = get_connection(db_path)`.
  2. Check for table `turnover`: `SELECT 1 FROM sqlite_master WHERE type='table' AND name='turnover' LIMIT 1`. If missing, run schema file via `executescript`, then `conn.commit()`.
  3. Ensure `schema_version` exists: if not (e.g. old DB created before we added the table), create it and insert 0 (only needed for legacy empty DBs; new schema.sql already has it).
  4. `SELECT version FROM schema_version LIMIT 1` → current.
  5. For n in 1, 2, 3 with corresponding filenames 001_..., 002_..., 003_..., if current < n: read file, `conn.executescript(sql)`, `conn.execute("UPDATE schema_version SET version = ?", (n,))`, `conn.commit()`.
  6. `conn.close()` in a `finally` block.
- On any exception (missing file, SQL error), propagate; no silent swallow. Caller can catch and show “Database initialization failed.”

### 4.3 Call `ensure_database_ready` from `app_prototype_v2.py`

- **Where:** Once at startup, after `_init_session_state()`, and only when backend will be used. Simplest: if `_BACKEND_AVAILABLE`, call ensure once before any page that might call `_get_conn()`. That implies calling it near the top of the script, after session state init, e.g.:

  - `if _BACKEND_AVAILABLE: from db.connection import ensure_database_ready; ensure_database_ready(_get_db_path())`
  - Or: call only when `not st.session_state.use_mock` so we don’t touch the DB in mock-only runs. Trade-off: if user switches from mock to backend mid-session, first backend request might trigger ensure (then you’d need “ensure on first backend use” with a flag). Recommended: **ensure unconditionally when _BACKEND_AVAILABLE** so that switching to backend never hits an uninitialized DB; the cost is one ensure per app load when backend is available.

- **Exception handling:** Wrap in try/except; on failure set a session-state flag e.g. `db_init_failed = True` and show a single message at top “Database initialization failed. Check logs and db/schema.sql, or use mock data.” and avoid calling `_get_conn()` for the rest of the run (or have `_get_conn()` return None when `db_init_failed`).

### 4.4 Migration directory usage

- **Existing files:** Keep `001_add_report_ready_date.sql`, `002_add_exposure_risk_type.sql`, `003_add_assignee_blocking_wd_type.sql` as-is. No change to migration content.
- **Order:** 001, 002, 003. Bootstrap applies only those three in order; future migrations (004, 005) would be added to the list in `ensure_database_ready` (or a small list constant) when implemented.
- **No CLI:** No new script required; app startup (or first-use) runs ensure. Optional: add a small `scripts/init_db.py` that only calls `ensure_database_ready(path)` for manual one-off init; not required for “no manual steps.”

### 4.5 Summary of file changes

| File | Change |
|------|--------|
| `db/schema.sql` | Append `schema_version` table and one row (version 0). |
| `db/connection.py` | Add `ensure_database_ready(db_path, schema_path=None, migrations_dir=None)`; keep `get_connection`, `initialize_database`, `run_integrity_check`, `backup_database` unchanged for now. Optionally deprecate or narrow `initialize_database` later (e.g. only “create from schema when file missing”) once ensure is the single entry point. |
| `app_prototype_v2.py` | After `_init_session_state()`, if `_BACKEND_AVAILABLE`, call `ensure_database_ready(_get_db_path())` in try/except; on failure set `st.session_state.db_init_failed = True` and show error + avoid backend paths. No change to hierarchy or identity. |

### 4.6 Optional follow-ups (out of scope for “minimal”)

- Run `run_integrity_check(db_path)` after `ensure_database_ready` and treat failure as init failure.
- Move “list of migrations” (001, 002, 003) to a constant or small config so adding 004 does not require editing the middle of `ensure_database_ready` logic.
- Remove or reduce duplicate “Database not initialized” warnings in the UI once ensure is guaranteed (they become rare/corruption-only).

---

**Definition of done for this design:** DB file is never used for repository/service calls until schema and migrations 001–003 are applied; bootstrap is automatic; no manual CLI; single entry point in `db/`; app integrates with one call at startup and optional init-failure handling.
