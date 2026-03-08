# Canonical Unit Identity — Findings (current truth)

Findings from repo scan; all references are to code/schema/tests.

---

## 1) Schema/migrations auto-initialization

**Yes.** The app initializes schema and migrations automatically when backend is used.

- **Where:** `app_prototype_v2.py` lines 152–161: when `_BACKEND_AVAILABLE` and not `use_mock`, it calls `ensure_database_ready(_get_db_path())` before any DB read path.
- **Implementation:** `db/connection.py` `ensure_database_ready(db_path)` (lines 62–218): opens DB, checks for `turnover` table; if missing runs `schema.sql`, ensures `schema_version` exists, then applies migrations 001–004 in order (including migration 004 backfill and unit table recreation).

---

## 2) Places unit identity is (property_id, unit_code_norm)

### Schema constraints

- **db/schema.sql** line 30: `UNIQUE(property_id, unit_code_norm)` on `unit`.
- **db/schema.sql** line 31: `CHECK(unit_code_norm <> '')`.

(After migration 004, `unit` also has `UNIQUE(property_id, unit_identity_key)` and NOT NULL on `phase_code`, `building_code`, `unit_number`, `unit_identity_key`.)

### Repository

- **db/repository.py** lines 30–34: `get_unit_by_norm(conn, *, property_id, unit_code_norm)` — `SELECT * FROM unit WHERE property_id = ? AND unit_code_norm = ?`.
- **db/repository.py** lines 53–67: `insert_unit(conn, data)` — inserts `property_id`, `unit_code_norm` (and after 004: `phase_code`, `building_code`, `unit_number`, `unit_identity_key`).
- **db/repository.py** lines 38–44: `get_unit_by_identity_key(conn, *, property_id, unit_identity_key)` — lookup by new identity key (added with this work).

### import_service

- **services/import_service.py** lines 186–206: `_ensure_unit(conn, property_id, unit_raw, unit_norm)` uses `repository.get_unit_by_norm(conn, property_id=..., unit_code_norm=unit_norm)`; on insert uses `unit_identity.parse_unit_parts` / `compose_identity_key` and passes identity columns to `insert_unit`.
- **services/import_service.py** lines 439, 482, 526: report-type handlers call `repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=row["unit_norm"])` for unit lookup.
- **services/import_service.py** lines 44–52: `_normalize_unit(raw)` returns `(raw_clean, unit_code_norm)` and now uses `unit_identity.normalize_unit_code(raw)` for the norm.

### Board filters / UI

- **services/board_query_service.py** lines 119, 158–159: `filter_phase` documented as "property_id as string ('5', '7', '8')"; filter uses `str(u.get("property_id")) != str(filter_phase)`.
- **app_prototype_v2.py** lines 420–422, 715–717: Phase dropdown options `["All", "5", "7", "8"]`; `st.session_state.filter_phase` passed to board queries.
- **app_prototype_v2.py** lines 906–910: Detail header derives `phase_id`, `building`, `unit_number` from `(u.get("unit_code_raw") or "").split("-")` (display only).

---

## 3) Where unit_code_norm / unit_code_raw is parsed (phase/building/unit)

| Location | Input | Effect | Reference |
|----------|--------|--------|-----------|
| **import_service._normalize_unit** | raw | **Persistence** — produces `unit_code_norm` stored and used for get_unit_by_norm / insert. | `import_service.py:44–52` |
| **import_service._phase_from_norm** | unit_norm | **Filter only** — first segment as int; filters rows to VALID_PHASES (5,7,8); not stored. | `import_service.py:55–68` |
| **board_query_service._parse_unit_code** | unit_code_raw | **Display only** — (building, unit_number) for flat row; not persistence. | `board_query_service.py:28–36, 48–49` |
| **ui/mock_data_v2.parse_unit_code** | unit_code_raw | **Display only** — (building, unit_number). | `mock_data_v2.py:228–236, 250–251` |
| **app_prototype_v2 (detail)** | unit_code_raw | **Display only** — `_uc_parts = (...).split("-")`; phase_id, building, unit_number for header. | `app_prototype_v2.py:906–910` |

---

## Implementation plan (executed)

1. **Canonical module** — Added `domain/unit_identity.py`: `normalize_unit_code`, `parse_unit_parts`, `compose_identity_key` with strict rules and rejection on empty unit_number.
2. **Migration 004** — `db/migrations/004_add_unit_identity_columns.sql` adds nullable `phase_code`, `building_code`, `unit_number`, `unit_identity_key`. In `ensure_database_ready`, after 004.sql: backfill from `unit_code_norm` via canonical module; detect duplicates and fail loudly; recreate `unit` table with NOT NULL and `UNIQUE(property_id, unit_identity_key)`.
3. **Repository** — `insert_unit` extended to accept and insert the four identity columns; `get_unit_by_identity_key` added; `UNIT_UPDATE_COLS` extended.
4. **Import** — `_ensure_unit` uses `unit_identity.parse_unit_parts` and `compose_identity_key` when inserting; `_normalize_unit` delegates norm to `unit_identity.normalize_unit_code`.
5. **Tests** — `tests/test_unit_identity.py`: normalization, parsing, compose, idempotency, uniqueness enforcement, import regression.
6. **Docs** — `docs/UNIT_IDENTITY.md` (examples and rejection cases), `docs/MIGRATIONS_NOTE.md` (how migrations run).
