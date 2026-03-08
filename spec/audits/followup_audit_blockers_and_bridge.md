# Follow-Up Audit: Blockers First, Revised Migration, Schema

**Status:** Design only — no implementation.  
**Purpose:** Address DB reality check, parsing contract, UI filtering semantics, and compatibility bridge for hierarchy refactor.

---

## Blockers First

### A) DB reality check (blocker)

**1) Exact DB path in DB-mode**

- **Source:** `app_prototype_v2._get_db_path()` → `os.environ.get("COCKPIT_DB_PATH", os.path.join(os.path.dirname(__file__) or ".", "data", "cockpit.db"))`.
- **When `COCKPIT_DB_PATH` is set:** That value is used as the DB path.
- **When unset (default):** `os.path.join(os.path.dirname(__file__) or ".", "data", "cockpit.db")`. When the app is run as `streamlit run the-dmrb/app_prototype_v2.py` from repo root, `__file__` is the path to `app_prototype_v2.py`, so `dirname(__file__)` is the `the-dmrb` directory. The default path is therefore **`the-dmrb/data/cockpit.db`** relative to the process current working directory (typically repo root). Resolved at runtime, so it can be absolute if `__file__` is absolute.
- **Reference:** `app_prototype_v2.py:151–152`.

**2) Where schema initialization / migrations are executed**

- **Schema:** `db/connection.initialize_database(db_path, schema_path)` runs `schema.sql` via `executescript` **only when the DB file does not exist** (`if not os.path.isfile(db_path)`). The app **never** calls `initialize_database`. Only tests (e.g. `test_truth_safety`) build an in-memory DB from `schema.sql`; no production or dev path runs schema on startup.
- **Migrations:** There is **no** migration runner in the app or in a script. Migrations under `db/migrations/` (001, 002, 003) are applied only when run manually or by tests that reference them. The app does not execute any migration.
- **References:** `db/connection.py:17–28`; `app_prototype_v2.py` (no import or call of `initialize_database`); `tests/test_truth_safety.py:14–15, 23–24, 103, 119`.

**3) Why “no such table: turnover” occurs**

- **Cause:** The app opens the path from (1). `get_connection(db_path)` does **not** create tables; it only creates the **parent directory** if missing (`os.makedirs(parent, exist_ok=True)`) and then calls `sqlite3.connect(db_path)`. If the path does not exist, SQLite creates an **empty** database file. So:
  - First run with default path and no pre-created DB → `the-dmrb/data/` is created (if needed), `the-dmrb/data/cockpit.db` is created as an empty file → no tables.
  - If the user later unchecks “Use mock data,” the sidebar and/or board call `board_query_service.get_flag_bridge_rows` / `get_dmrb_board_rows` → `repository.list_open_turnovers` → `SELECT ... FROM turnover` → **OperationalError: no such table: turnover**.
- So the app is effectively pointing at a **new, empty SQLite file** whenever that file was never initialized with schema (and optionally migrations).

**4) Exact minimal startup sequence to guarantee tables exist before board_query_service runs**

- **Option A — Ensure schema + migrations before first query (recommended):**
  1. Resolve DB path (same as today: `COCKPIT_DB_PATH` or default `.../data/cockpit.db`).
  2. **Ensure schema:** If the DB file does not exist, call `initialize_database(db_path, path_to_schema.sql)`. If the DB file **does** exist, check that at least one core table exists (e.g. `SELECT 1 FROM sqlite_master WHERE type='table' AND name='turnover' LIMIT 1`). If the table is missing, run `schema.sql` (and optionally treat as “empty but existing file” and run schema anyway; current `initialize_database` does not handle “file exists but empty”).
  3. **Run migrations in order** on that connection (or a new one): 001, 002, 003 (each as `executescript` of the corresponding migration file). Use a simple version table or “migrations applied” list to avoid re-running.
  4. Only then allow any code path that calls `board_query_service` or repository queries against turnover/unit.

- **Option B — Lazy init on first connection:**
  1. On first `_get_conn()` when `use_mock=False`, after obtaining the connection, check for table existence (e.g. `turnover`). If missing, run schema + migrations, then commit. Then proceed with the request. This guarantees tables exist before any subsequent query on that run; same for next run because the file now has tables.

- **Concrete minimal sequence (no new API):**
  - **At app startup** (e.g. once per process when backend is available and use_mock is False), or **on first use of DB** (first `_get_conn()` that succeeds):  
    (1) `conn = get_connection(db_path)`.  
    (2) Cursor: `SELECT name FROM sqlite_master WHERE type='table' AND name='turnover'`.  
    (3) If no row: run `open(schema_path).read()` and `conn.executescript(schema_sql)`; then for each migration in order (001, 002, 003), `conn.executescript(migration_sql)`; `conn.commit()`.  
    (4) Close conn.  
  - Thereafter, all `_get_conn()` callers get a DB that already has tables (and migrations applied). No change to `board_query_service` call sites; the guarantee is “tables exist before any query.”

- **Gap in current `initialize_database`:** It only runs schema when `not os.path.isfile(db_path)`. So if an empty file was created earlier by `get_connection`, `initialize_database` will not run schema. The minimal startup must either (i) run schema when the file exists but `turnover` is missing, or (ii) ensure the file is never created without immediately running schema (e.g. a dedicated “init” entrypoint that creates the file only via `initialize_database`).

---

### B) Parsing contract (blocker)

**Canonical unit identity parsing contract**

- **Authority:** A single module (e.g. `domain/unit_identity.py` or `services/import_service` with exported helpers) must define the **canonical** parse and normalization. All consumers (import, manual entry, board display, backfill) must use the same rules so that (phase_code, building_code, unit_number) and unit_code_norm never diverge.

**Accepted input formats for unit_code_raw / unit_code_norm**

- **unit_code_raw:** Free text from reports or UI. Accepted: any string that, after normalization, yields a non-empty unit_code_norm. Leading/trailing whitespace, optional `"UNIT "` prefix (case-insensitive), internal spaces collapsed to single space, case normalized to uppercase for comparison.
- **unit_code_norm:** Output of canonical normalize(raw): strip, remove optional `"UNIT "` prefix, uppercase, collapse whitespace. Stored in DB; used for identity today as (property_id, unit_code_norm). Must satisfy `unit_code_norm <> ''` (schema).

**Exact parse rules to extract phase_code, building_code, unit_number**

- **Input:** unit_code_norm (or unit_code_raw normalized first).
- **Split:** On the single delimiter `"-"` (hyphen). Parts = `norm.split("-")`, each part stripped of whitespace.
- **Rules:**
  - **≥3 segments:** `phase_code = parts[0]`, `building_code = parts[1]`, `unit_number = parts[2]` (or `parts[-1]` if convention is “last is unit”). Current code uses `parts[1], parts[2]` for (building, unit_number) and first segment as phase in _phase_from_norm; so canonical: `phase_code = parts[0].strip()`, `building_code = parts[1].strip()`, `unit_number = parts[2].strip()`.
  - **2 segments:** `phase_code = parts[0].strip()`, `building_code = ""`, `unit_number = parts[1].strip()`.
  - **1 segment:** `phase_code = ""`, `building_code = ""`, `unit_number = parts[0].strip()`.
- **Type:** phase_code and building_code are strings (e.g. "5", "18"); unit_number is string (e.g. "101", "0206"). No coercion to int for identity.
- **Empty after strip:** If unit_number is empty after strip, treat as malformed (see below).

**Handling malformed inputs**

- **Reject as conflict vs fallback bucket:**
  - **Reject (report as conflict / invalid):** (a) Normalized string is empty. (b) Parse yields empty unit_number (e.g. single segment that is empty, or "5--" with empty unit_number). (c) phase_code not in allowed set when phase is required (e.g. VALID_PHASES 5,7,8 for import). (d) Optional: building_code or unit_number contains invalid characters (if a contract is defined, e.g. alphanumeric only).
  - **Fallback bucket:** For **backfill only**, rows that do not parse to a valid (phase_code, building_code, unit_number) can be assigned to a single “unknown” bucket: e.g. phase_code = `"UNK"`, building_code = `""`, unit_number = full unit_code_norm (or a hashed/sanitized value) so that (building_id, unit_number) remains unique. New imports must **reject** malformed units (write import_row with validation_status=CONFLICT or INVALID, conflict_reason e.g. "UNIT_CODE_UNPARSEABLE") and not create a unit. So: **reject on import**; **fallback bucket only for backfill** of existing nonconforming rows.

**Backfill strategy for nonconforming existing rows**

- **Detection:** Query all units; for each, run canonical parse on unit_code_norm. If parse yields empty unit_number, or phase_code not in allowed set, or (phase_code, building_code, unit_number) would be ambiguous (e.g. duplicate (building_id, unit_number) after resolving phase/building), mark as nonconforming. Count: `SELECT COUNT(*) FROM unit WHERE ...` plus application-side parse; or a one-off script that reads all units and applies parse, then reports rows where `unit_number == ""` or phase_code not in (5,7,8) or duplicate (phase_code, building_code, unit_number) per property.
- **How many:** Run the script; report N nonconforming. No schema change required for detection.
- **Strategy:** (1) Backfill conforming rows first: set phase_id, building_id, unit_number from parse. (2) For nonconforming, either assign to fallback phase/building (e.g. property_id=1, phase_code="UNK", building_code="", unit_number=unit_code_norm or a safe substitute) so they retain a single open turnover and can be corrected later, or leave phase_id/building_id NULL and unit_number NULL and handle in UI as “legacy unit” until manual fix. Prefer fallback bucket so that no row is left with NULL identity columns that break UNIQUE(building_id, unit_number).

---

### C) UI filtering semantics (blocker)

**Multiple properties can have Phase 5**

- So “Phase 5” is ambiguous: it could be phase_id=1 under property A and phase_id=2 under property B. The UI must therefore select a **phase in context of a property**, or select a **phase_id** directly (so that phase_id is globally unique).

**Definition: how UI selects a phase**

- **Option 1 — (property_id, phase_code):** UI shows two controls: Property (e.g. dropdown) and Phase (e.g. 5, 7, 8). Backend receives `property_id` and `phase_code`; resolution to phase_id is done in service/repository. Pro: matches “multiple properties, each with Phase 5.” Con: two parameters.
- **Option 2 — phase_id only:** Phase table has phase_id as PK. Each phase belongs to one property. UI shows a single dropdown of “phases” with labels like “Prop A – Phase 5”, “Prop B – Phase 5”, and value is phase_id. Then the UI selects a single phase_id. Pro: one parameter; no ambiguity. Con: dropdown can be long if many properties × phases.
- **Recommendation:** Use **phase_id** as the single filter value for “Phase” in the board. So the UI holds `filter_phase_id` (integer or None for “All”). Options for the dropdown: either (i) list all phases (e.g. from `list_phases(conn)` or from a join property+phase) with label `f"{property_name} – {phase_code}"` and value `phase_id`, or (ii) if single-property deployment, list phase_codes with value = phase_id (so backend still receives phase_id). No (property_id, phase_code) in the UI contract; backend can derive property from phase_id when needed.

**Board query service filter signature**

- **Current:** `filter_phase: Optional[str] = None` (values "5", "7", "8" or "All"), compared to `str(u.get("property_id"))`. So filter is effectively “property_id as string.”
- **Target (blocker fix):** `filter_phase_id: Optional[int] = None`. When not None, filter rows where the turnover’s unit belongs to that phase: i.e. join unit → building → phase and `WHERE phase.phase_id = filter_phase_id`. So signature becomes:
  - `get_dmrb_board_rows(conn, *, property_ids=None, filter_phase_id=None, search_unit=..., filter_status=..., ...)`  
  - If `filter_phase_id` is not None, include in the query (or in the post-join filter) “unit’s phase_id = filter_phase_id.” Drop or repurpose `filter_phase` (string) so there is no duplicate concept.
- **Interim (before hierarchy exists):** Keep `filter_phase: Optional[str]` but document that it is “property_id as string (legacy); will become filter_phase_id when phase table exists.” Once phase table and unit→building→phase exist, add `filter_phase_id` and deprecate `filter_phase`.

---

### D) Compatibility bridge (blocker)

**Staged identity migration so old and new resolution coexist**

- **Stage 1 — Pre-hierarchy (current):** Only (property_id, unit_code_norm) exists. Repository: `get_unit_by_norm(conn, property_id, unit_code_norm)`, `insert_unit(conn, data)` with property_id + unit_code_norm. No phase/building tables. Import and manual entry use _ensure_unit / get_unit_by_norm.
- **Stage 2 — Add hierarchy, dual write/read:** New tables phase, building; unit gets phase_id, building_id, unit_number (nullable). Backfill fills these from canonical parse of unit_code_norm. **Repository:**
  - **Old (still supported):** `get_unit_by_norm(conn, property_id, unit_code_norm)` — returns unit row (unchanged). Used by import and manual entry during transition.
  - **New:** `get_unit_by_building_and_number(conn, building_id, unit_number)` — returns unit row. Used by new import path or internal use.
  - **Resolver (new):** `resolve_unit_via_hierarchy(conn, property_id, phase_code, building_code, unit_number)` → get_or_create phase, building, unit by (building_id, unit_number); optionally update unit_code_norm on unit for display. Import can call this when “new path” is enabled; manual entry same.
  - **Insert:** `insert_unit` still accepts (property_id, unit_code_norm) for legacy; **and** a new `insert_unit_hierarchy(conn, building_id, unit_number, unit_code_raw=None, unit_code_norm=None, ...)` for new path. So both exist.
- **Stage 3 — New identity authoritative, old deprecated:** All new writes go through resolve_unit_via_hierarchy and insert_unit_hierarchy. `get_unit_by_norm` is kept for read-only backward compatibility (e.g. for backfill or legacy reports). List/filter by phase_id; `list_open_turnovers(conn, phase_id=...)` or join unit→building→phase. No new writes use (property_id, unit_code_norm) for identity.
- **Stage 4 — Drop legacy uniqueness:** Unit table drops UNIQUE(property_id, unit_code_norm); only UNIQUE(building_id, unit_number). get_unit_by_norm can remain as a **read** that joins unit→building→phase→property and matches (property_id, unit_code_norm) for legacy data only, or be removed once no caller remains.

**Repository functions per stage**

| Stage | Old resolution (property_id, unit_code_norm) | New resolution (phase/building/unit_number) |
|-------|----------------------------------------------|---------------------------------------------|
| 1     | get_unit_by_norm, insert_unit                | —                                           |
| 2     | get_unit_by_norm, insert_unit (legacy)       | get_unit_by_building_and_number; resolve_unit_via_hierarchy; insert_unit_hierarchy |
| 3     | get_unit_by_norm (read-only)                 | resolve_unit_via_hierarchy, get_unit_by_building_and_number, insert_unit_hierarchy; list_open_turnovers(phase_id=...) |
| 4     | get_unit_by_norm optional / removed          | Same as 3; UNIQUE(property_id, unit_code_norm) dropped |

---

## Revised Migration Plan

1. **DB startup guarantee (no hierarchy yet):** Before any board_query_service or repository query that touches turnover/unit, ensure schema + migrations have been run (see §A.4). Add a single entry point (e.g. `ensure_db_initialized(db_path)`) that checks for table `turnover` and if missing runs schema + 001, 002, 003; call it on first use of DB or at app startup when backend is enabled.
2. **Add phase and building tables** (migration 004): CREATE phase, CREATE building; no change to unit yet.
3. **Backfill phase/building from existing units:** One-off script or migration 005: parse each unit_code_norm with canonical parse; insert phase (property_id, phase_code) and building (phase_id, building_code); record mapping (unit_id → phase_id, building_id, unit_number). Detect nonconforming (see §B); assign fallback bucket or leave for manual fix.
4. **Add unit hierarchy columns** (migration 006): ALTER unit ADD phase_id, building_id, unit_number (nullable). Backfill from step 3. Application enforces “new reads can use building_id + unit_number” while still supporting get_unit_by_norm for writes.
5. **Dual resolution (Stage 2):** Implement resolve_unit_via_hierarchy and get_unit_by_building_and_number; import and manual entry can optionally use new path. source_turnover_key can stay as-is or add new format; idempotency still by unit_id.
6. **Switch list/filter to phase_id:** board_query_service accepts filter_phase_id; UI passes phase_id from dropdown. list_open_turnovers joins unit→building→phase when filter_phase_id is set (or denormalize phase_id on unit for speed).
7. **Drop turnover.property_id** (optional): Derive from unit→building→phase→property; or keep and backfill. Then drop column in a later migration if desired.
8. **Stage 3–4:** All writes via hierarchy; drop UNIQUE(property_id, unit_code_norm) and optionally remove get_unit_by_norm when no callers remain.

---

## Schema Changes (summary)

- **Existing (unchanged for blocker):** property, unit (property_id, unit_code_norm), turnover, task_template (property_id), etc. No schema change required for “guarantee tables exist”; only runtime startup sequence.
- **For hierarchy (already in main audit):** phase (phase_id, property_id, phase_code, UNIQUE(property_id, phase_code)); building (building_id, phase_id, building_code, UNIQUE(phase_id, building_code)); unit gains building_id, phase_id, unit_number, and eventually UNIQUE(building_id, unit_number); turnover may drop property_id. task_template gains phase_id (or keeps property_id until phase is stable).
- **Parsing/backfill:** No schema change; only application contract and backfill script for phase_id, building_id, unit_number.

---

**End of follow-up audit. No implementation.**
