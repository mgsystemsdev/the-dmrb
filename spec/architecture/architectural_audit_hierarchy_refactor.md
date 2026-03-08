# Full-Repository Architectural Audit + Structured Hierarchy Refactor Plan (Design Only)

**Status:** Design only — no implementation.  
**Goal:** Upgrade from flattened identity (property_id as “phase” → unit by property_id+unit_code_norm → turnover) to normalized hierarchy (property → phase → building → unit → turnover), with unit attributes, without breaking invariants or import idempotency.

---

## 1) Current Identity & Coupling Audit

### 1.1 Where property_id is assumed to represent phase

| Location | Usage | File reference |
|----------|--------|----------------|
| **Import service** | `VALID_PHASES = (5, 7, 8)`; `_phase_from_norm(unit_norm)` parses first segment of unit_norm as integer and filters rows to that set. Import does **not** store phase in a table; it uses a single `property_id` parameter (default 1) for the whole batch. Phase is **inferred from unit string** (first segment). | `services/import_service.py:26, 55–68` |
| **Board query service** | `filter_phase` docstring: "property_id as string ('5', '7', '8')". Filter: `str(u.get("property_id")) != str(filter_phase)`. So **phase filter = property_id filter**; values 5, 7, 8 are treated as phases. | `services/board_query_service.py:119, 158–159` |
| **App (UI)** | Phase dropdown options `["All", "5", "7", "8"]`; `st.session_state.filter_phase` passed as `filter_phase` to board queries. Display: `"Phase": str(row.get("property_id", ""))` and detail header `phase_id = _uc_parts[0]` from unit_code_raw or fallback `u.get("property_id")`. | `app_prototype_v2.py:406–408, 502, 894, 911` |
| **Mock data** | Units/turnovers use `property_id: 5 | 7 | 8`; comment "property_id 5, 7, 8 for Phase filter". | `ui/mock_data_v2.py:47, 65–69, 78–118` |
| **Schema** | No `phase` table. `property` has `property_id`; `unit` and `turnover` have `property_id` FK. So **property_id is the only “phase” axis** in the schema. | `db/schema.sql:14–17, 24, 39` |

**Conclusion:** Phase is not a first-class entity. It is conflated with `property_id`, and for filters/display the code assumes property_id values 5, 7, 8 are “phases.” Import infers a phase-like value from the unit string (first segment) only for row filtering, not for storage.

---

### 1.2 Modules that depend on UNIQUE(property_id, unit_code_norm)

| Module | Dependency | How |
|--------|------------|-----|
| **db/repository.py** | Unit identity | `get_unit_by_norm(conn, property_id=..., unit_code_norm=...)`; `insert_unit` with same columns. Uniqueness enforced by schema. | `repository.py:30–33, 52–66` |
| **services/import_service.py** | Unit lookup/ensure | `_ensure_unit(conn, property_id, unit_raw, unit_norm)` calls `repository.get_unit_by_norm(conn, property_id=property_id, unit_code_norm=unit_norm)` and optionally `insert_unit` with that (property_id, unit_code_norm). All unit resolution in MOVE_OUTS, PENDING_MOVE_INS, etc. uses this. | `import_service.py:186–199, 384, 439, 482, 526` |
| **spec/manual_entry_design.md** | Design contract | Manual entry uses same identity: (property_id, unit_code_norm) for get-or-create unit. | `spec/manual_entry_design.md` (references) |

No other modules call `get_unit_by_norm` directly; they receive unit rows by `unit_id` (from turnover or batch lookups). So the **only producer of unit identity** is import (and the designed manual entry), both keyed by (property_id, unit_code_norm).

---

### 1.3 Where unit identity is resolved from string parsing

| Location | What is parsed | Assumption |
|----------|----------------|------------|
| **import_service._normalize_unit(raw)** | Strip, optional "UNIT " prefix, upper, collapse spaces → `(raw_clean, unit_code_norm)`. | Single string; no structural hierarchy. |
| **import_service._phase_from_norm(unit_norm)** | `unit_norm.split("-")`; first part as integer → “phase.” Used only to **filter** rows to VALID_PHASES (5,7,8). | Phase is **inferred from unit string**, not stored. Import still uses a single **batch-level** `property_id` (default 1) when calling `_ensure_unit` and `insert_turnover`. So currently **all** imported units are stored under that one property_id; the first segment of unit_norm is not written to a phase column. |
| **board_query_service._parse_unit_code(unit_code_raw)** | Split on "-"; if ≥3 parts → (parts[1], parts[2]) as (building, unit_number); else ( "", parts[1] or parts[0]). | Display only; not used for identity or persistence. |
| **ui/mock_data_v2.parse_unit_code** | Same logic: (building, unit_number) from unit_code_raw. | Display only. |
| **app_prototype_v2 (detail)** | `_uc_parts = (u.get("unit_code_raw") or "").split("-")`; phase_id = parts[0], building = parts[1], unit_number = parts[-1]. | Display only; fallback phase from `u.get("property_id")`. |

**Critical:** In import, **unit identity stored** is (property_id, unit_code_norm). The **phase** (first segment of unit_norm) is used only to filter which rows are processed; it is **not** used to set a phase_id or different property_id per row. So today “Phase 5” in the UI is really “property_id = 5”; if import runs with property_id=1, all units get property_id=1 and would not show under Phase 5 filter unless the data was seeded with property_id 5/7/8. Mock data and many tests use property_id 1 or 5/7/8 explicitly.

---

### 1.4 source_turnover_key construction and assumptions

| Location | Format | Assumptions |
|----------|--------|-------------|
| **import_service (MOVE_OUTS)** | `f"{property_id}:{row['unit_norm']}:{move_out_iso}"` | Uniqueness per (property_id, unit_norm, move_out_date). No phase/building in key; unit_norm is full string (e.g. "5-1-101"). | `import_service.py:417` |
| **spec/manual_entry_design.md** | Manual: `manual:{property_id}:{unit_norm}:{move_out_iso}` | Same components; prefix avoids collision with import. | Design doc |
| **repository** | Not constructed; only stored. | `insert_turnover` accepts `data["source_turnover_key"]`. | `repository.py:171` |
| **Tests** | Literal keys e.g. `'k'`, `'test:101:mo'`. | No structural assumption in tests. | `tests/test_truth_safety.py:75, 108, 41` |

**Assumptions encoded:** (1) Key is globally unique (UNIQUE in schema). (2) Import idempotency is by batch checksum + open turnover by **unit_id**, not by key lookup. (3) Key format is not queried elsewhere; only stored. So changing the key format is possible if migration and import resolver are updated together.

---

### 1.5 Tests that encode current identity assumptions

| Test / file | Assumption |
|-------------|------------|
| **test_truth_safety.py** | `property(property_id=1)`, `unit(unit_id=1, property_id=1, unit_code_raw='101', unit_code_norm='101')`, `turnover(property_id=1, unit_id=1, source_turnover_key='...')`. Single property; unit identity (1, '101'). | `test_truth_safety.py:29–45, 71–76, 105–110` |
| **test_enrichment_harness.py** | Uses mock_data_v2 units/turnovers with `property_id` 5/7/8 and `unit_code_norm` like "5-1-101". Asserts enriched fields (dv, phase, nvm, operational_state, etc.); **phase** here is lifecycle phase from domain.enrichment (NOT property_id). No direct assertion on property_id or unit_code_norm. | `test_enrichment_harness.py` |
| **test_migration (test_truth_safety)** | Old schema + migration; inserts property_id=1, unit with unit_code_norm, turnover. | `test_truth_safety.py:90–116` |

So: **test_truth_safety** encodes single-property, single-unit identity (property_id, unit_code_norm). **test_enrichment_harness** encodes mock structure (property_id 5/7/8, unit_code strings) and enrichment output, but not repository identity.

---

## 2) Dependency Impact Map

For each module, what breaks or must change under TARGET hierarchy (property → phase → building → unit → turnover).

### schema.sql

- **Breaks / changes:**
  - **unit:** Today `UNIQUE(property_id, unit_code_norm)`. Target: unit scoped to building → `UNIQUE(building_id, unit_number)` (or equivalent). So unit table gets `building_id` FK; identity becomes (building_id, unit_number). Columns like `unit_code_raw` / `unit_code_norm` may remain as derived/display or be deprecated in favor of phase_code + building_code + unit_number.
  - **turnover:** Today has `property_id` + `unit_id`. Target: turnover stays with `unit_id` only; property_id can be dropped from turnover (derived via unit → building → phase → property) or kept as denormalized for performance.
  - **task_template:** Today `property_id` FK and `UNIQUE(property_id, task_type, is_active)`. Target: template scope could stay property, or move to phase (so “Phase 5” has its own templates). Decision: scope by **phase** (e.g. phase_id) so multiple properties can share phase codes; then task_template references phase_id.
  - **New tables:** phase (FK property), building (FK phase), and unit (FK building). property remains; unit no longer has property_id FK.
- **Hidden coupling:** None beyond FKs and unique constraints already listed.

### db/repository.py

- **Breaks:**
  - `get_unit_by_norm(conn, property_id, unit_code_norm)` — no longer valid; unit identity is (building_id, unit_number) or (phase_id, building_code, unit_number). Replace with e.g. `get_unit_by_building_and_number(conn, building_id, unit_number)` or a resolver that takes (property_id, phase_code, building_code, unit_number).
  - `insert_unit`: signature and uniqueness change; must accept building_id (and possibly phase_id/property_id for creation path), unit_number, optional unit_code_raw/unit_code_norm for display.
  - `list_open_turnovers(property_ids=...)` and `list_open_turnovers_by_property(property_id)` — if filtering by “phase” in UI, need either to keep turnover.property_id denormalized or to join unit → building → phase and filter by phase_id/phase_code. Same for any list that filters by property.
- **Changes:** All unit lookups used by import and board_query must go through new resolver (see §5). TURNOVER_UPDATE_COLS may drop property_id if turnover no longer stores it; or keep it as cached.

### import_service

- **Breaks:**
  - `_ensure_unit(conn, property_id, unit_raw, unit_norm)` — current contract is (property_id, unit_norm). Under hierarchy, must resolve (property, phase, building, unit) from the same string. So replace with a **structured resolver**: parse unit string → (phase_code, building_code, unit_number); then resolve_property (if single-property, trivial); resolve_phase(property_id, phase_code); resolve_building(phase_id, building_code); resolve_unit(building_id, unit_number). Create missing entities as needed.
  - `_phase_from_norm` is currently used only to filter rows; under target, phase becomes a real entity and should be resolved from parsed phase_code.
  - `source_turnover_key`: currently `{property_id}:{unit_norm}:{move_out_iso}`. Options: (a) keep same logical meaning with new identity, e.g. `{property_id}:{phase_code}:{building_code}:{unit_number}:{move_out_iso}` or (b) keep `{property_id}:{unit_norm}:{move_out_iso}` during transition by still storing/computing a “display” unit_norm from phase+building+unit for backward compatibility. Idempotency still relies on get_open_turnover_by_unit(unit_id), not key lookup.
- **Changes:** All call sites of `_ensure_unit` and `get_unit_by_norm` use the new resolver. `_instantiate_tasks_for_turnover` today takes `property_id` for task_template lookup; under target, templates are per phase → pass phase_id (or property_id if templates stay per property).

### turnover_service

- **Breaks:** Minimal. It uses `get_turnover_by_id`, `get_turnover_by_id` + unit via repository, and `update_turnover_fields`. No direct use of property_id or unit_code_norm for identity. If turnover loses property_id column, any code that writes property_id to turnover must stop (repository already allows it in TURNOVER_UPDATE_COLS).
- **Changes:** None if turnover keeps unit_id only and property_id is derived or dropped. Risk/SLA reconciliation use turnover and unit rows; as long as unit still has the needed attributes (and possibly phase/building for reporting), no change. If turnover_service ever needed “phase” for logic, it would get it via unit → building → phase.

### task_service

- **Breaks:** None. Uses task_id and turnover_id; no unit or property identity.
- **Changes:** None.

### risk_engine (domain)

- **Breaks:** None. Inputs are dates, tasks, wd flags, etc. No property/phase/unit identity.
- **Changes:** None.

### sla_engine (domain)

- **Breaks:** None. Inputs are move_out_date, manual_ready_confirmed_at, today, open_breach_exists. No identity.
- **Changes:** None.

### board_query_service

- **Breaks:**
  - **Filter by “phase”:** Today compares `str(u.get("property_id")) != str(filter_phase)`. Under target, “phase” is a first-class concept: either (1) join unit → building → phase and filter by phase_id or phase_code, or (2) keep a denormalized phase_id/phase_code on unit for speed. So filter_phase must become “phase_code” or “phase_id” and comparison must use the new source.
  - **_parse_unit_code:** Still used for display (building, unit_number). Under target, building and unit number can come from tables (building_code, unit_number). So either keep _parse_unit_code for backward compatibility on legacy unit_code_raw or replace with columns from joined building/unit.
  - **_build_flat_row:** Today uses `unit.get("property_id")`, `unit.get("unit_code_raw")`, `unit.get("unit_code_norm")`, and _parse_unit_code for building/unit_number. Under target, row should get phase_code, building_code, unit_number (and optionally unit_code_display) from hierarchy; property_id can come from unit→building→phase→property or be dropped from row if UI no longer needs it.
- **Hidden coupling:** Assumption that “phase” filter is property_id; and that unit has unit_code_raw/norm for display.

### enrichment pipeline (domain/enrichment.py)

- **Breaks:** None. Uses dates, task dicts, and row fields; no property/phase/unit identity. `derive_phase` is **lifecycle** phase (VACANT, NOTICE, etc.), not structural phase.
- **Changes:** None.

### UI (app_prototype_v2, mock_data_v2)

- **Breaks:**
  - **Phase dropdown:** Still "All" / "5" / "7" / "8". Under target, options could remain phase_code (e.g. "5","7","8") but backend filter must be by phase_id or phase_code from new schema. If multiple properties have Phase 5, UI may need Property + Phase or a single “Phase” that means (property_id, phase_code) — product decision.
  - **Search unit:** Today substring on unit_code. Under target, can stay as substring on a display string (e.g. phase_code + building_code + unit_number) or on unit_code_raw if retained.
  - **Detail header:** Today phase_id from parsing unit_code_raw or property_id. Under target, from unit → building → phase (phase_code or name).
  - **Table column “Phase”:** Today `row.get("property_id")`. Under target, from joined phase (phase_code).
- **Hidden coupling:** UI assumes phase is a single dimension (5/7/8) and that it equals property_id. Under target, phase is per-property, so “Phase 5” could be phase_id 1 under property A and phase_id 2 under property B; UI may need to show “Phase 5” as label and pass phase_id for filter.

---

## 3) Recommended Target Schema (DDL-level outline)

### Tables (normalized hierarchy)

```text
property
  property_id INTEGER PRIMARY KEY
  name TEXT NOT NULL

phase
  phase_id INTEGER PRIMARY KEY
  property_id INTEGER NOT NULL REFERENCES property(property_id)
  phase_code TEXT NOT NULL   -- e.g. '5', '7', '8'
  UNIQUE(property_id, phase_code)

building
  building_id INTEGER PRIMARY KEY
  phase_id INTEGER NOT NULL REFERENCES phase(phase_id)
  building_code TEXT NOT NULL
  UNIQUE(phase_id, building_code)

unit
  unit_id INTEGER PRIMARY KEY
  building_id INTEGER NOT NULL REFERENCES building(building_id)
  unit_number TEXT NOT NULL   -- e.g. '101', '0206'
  unit_code_raw TEXT           -- optional display
  unit_code_norm TEXT          -- optional; derived or legacy
  has_carpet INTEGER NOT NULL DEFAULT 0
  has_wd_expected INTEGER NOT NULL DEFAULT 0
  is_active INTEGER NOT NULL DEFAULT 1
  square_footage INTEGER
  bed_count INTEGER
  bath_count INTEGER
  layout_code TEXT
  UNIQUE(building_id, unit_number)
  CHECK(unit_number <> '')

turnover
  turnover_id INTEGER PRIMARY KEY
  unit_id INTEGER NOT NULL REFERENCES unit(unit_id)
  source_turnover_key TEXT NOT NULL UNIQUE
  move_out_date TEXT NOT NULL
  ... (rest unchanged; property_id removed or kept as denormalized)
```

- **unit_code_norm:** Keep as optional. Use for backward compatibility during migration (e.g. computed from phase_code + building_code + unit_number) and for display/search. Identity for new data is (building_id, unit_number). No duplicate identity path: **authoritative** identity is (building_id, unit_number); unit_code_norm is derived/cached for import key and display until all consumers move to structured identity.
- **layout:** Keep as `layout_code TEXT` on unit (e.g. '2B2B', '1B1B'). Normalizing into a separate layout table is optional and not required for minimal refactor; can be added later if many shared layouts.
- **square_footage, bed_count, bath_count:** Unit columns (nullable INTEGER / TEXT as appropriate). No separate table needed for this refactor.

### task_template

- Scope by **phase** so “Phase 5” templates are per phase, not per property: `phase_id INTEGER NOT NULL REFERENCES phase(phase_id)`, `UNIQUE(phase_id, task_type, is_active)`. Migrate existing templates from property_id to phase_id (one-to-one mapping during backfill: property_id 5 → phase with phase_code '5' under that property).

### turnover

- Drop **property_id** from turnover (derive via unit → building → phase → property) **or** keep as denormalized for performance; recommend drop to avoid double source of truth. All list/filter by “phase” then go through unit → building → phase.

### Indexes

- Existing turnover/task/risk/note indexes unchanged.
- Add indexes as needed: phase(property_id), building(phase_id), unit(building_id); unique constraints already provide lookup.

---

## 4) Minimal Safe Migration Plan (SQLite-compatible)

SQLite does not support ADD CONSTRAINT for UNIQUE or FK on existing tables in all versions; typical approach is create new table, copy, drop old, rename, or add new columns and backfill, then add constraints via new table. Prefer **additive migrations** and **no downtime**.

### Phase 1: Add new hierarchy (no drop)

1. **Migration 004_add_phase_building**
   - CREATE TABLE phase (phase_id, property_id, phase_code, UNIQUE(property_id, phase_code)).
   - CREATE TABLE building (building_id, phase_id, building_code, UNIQUE(phase_id, building_code)).
   - No change to unit or turnover yet.

2. **Backfill phase and building from existing data**
   - One-time script or migration 005: For each distinct (property_id, unit_code_norm) in unit, parse unit_code_norm (e.g. split "-") to get (phase_code, building_code, unit_number). Insert phase for (property_id, phase_code) if not exists; insert building for (phase_id, building_code) if not exists. Store mapping (unit_id → phase_id, building_id) in a temp table or new columns on unit (phase_id, building_id nullable).

3. **Migration 006_add_unit_hierarchy_columns**
   - ALTER TABLE unit ADD COLUMN phase_id INTEGER REFERENCES phase(phase_id);
   - ALTER TABLE unit ADD COLUMN building_id INTEGER REFERENCES building(building_id);
   - ALTER TABLE unit ADD COLUMN unit_number TEXT;
   - (Optional) ALTER TABLE unit ADD COLUMN square_footage INTEGER; ADD COLUMN bed_count INTEGER; ADD COLUMN bath_count INTEGER; ADD COLUMN layout_code TEXT;
   - Backfill unit.phase_id, unit.building_id, unit.unit_number from backfill script (from parsed unit_code_norm). Ensure UNIQUE(phase_id, building_id, unit_number) or (building_id, unit_number) is enforced in application until schema can add it.

4. **Enforce uniqueness in application**
   - Do not add UNIQUE(building_id, unit_number) yet if unit still has old UNIQUE(property_id, unit_code_norm) and both are populated (could have duplicates during transition). Instead: ensure backfill is deterministic (one unit_number per building from one unit_code_norm); then add a **new** table `unit_v2` with UNIQUE(building_id, unit_number), migrate data, and switch reads/writes in a later step, **or** in SQLite add a unique index only after backfill and after dropping the old unique constraint in a separate migration.

### Phase 2: Switch identity and drop old constraint

5. **Repository and import use dual read**
   - New resolver: resolve_unit(conn, property_id, phase_code, building_code, unit_number) → unit_id (create phase/building/unit if missing). Import and manual entry call this. Keep reading unit by unit_id everywhere that currently does. For “get unit by legacy key,” add get_unit_by_property_and_norm(conn, property_id, unit_code_norm) that returns unit by matching existing unit_code_norm and property_id (or derived phase_id from phase_code) during transition.

6. **Migration 007_unit_identity_switch**
   - Make unit_number NOT NULL where backfilled.
   - Add UNIQUE(building_id, unit_number) (SQLite: CREATE UNIQUE INDEX idx_unit_building_number ON unit(building_id, unit_number)).
   - Stop using UNIQUE(property_id, unit_code_norm) for new writes: new code path uses (building_id, unit_number). Old get_unit_by_norm can remain for legacy reads until all data and callers are migrated.
   - When safe: drop old unique index on (property_id, unit_code_norm) (SQLite: create new table without it, copy, drop old, rename).

### Phase 3: Turnover and cleanup

7. **Turnover property_id**
   - If dropping turnover.property_id: add migration that adds a view or application-level derivation (unit → building → phase → property) for any query that still expects turnover.property_id. Update list_open_turnovers to filter by phase_id via join. Then ALTER turnover to drop property_id (SQLite 3.35.0+: DROP COLUMN; else new table, copy, drop, rename).
   - If keeping: backfill from unit → phase → property and keep as cached.

8. **Import idempotency**
   - Keep checksum-based batch skip. Keep “open turnover by unit_id” logic. source_turnover_key format can be updated to e.g. {property_id}:{phase_code}:{building_code}:{unit_number}:{move_out_iso} so it stays unique and readable; no need to look up by key for idempotency.

9. **Index recreation**
   - Any time a unique constraint is dropped or added, in SQLite you may need to recreate the table. Document order: create new table with desired constraints, INSERT INTO new SELECT from old, DROP old, ALTER TABLE new RENAME TO old. Application must support both old and new schema during a short window if doing table replacement.

### Avoiding breaking imports during transition

- **Dual-write not required** if migration is done in order: backfill hierarchy from existing unit_code_norm first, then add new columns, then switch import to “resolve (property, phase, building, unit) and create turnover” while still writing source_turnover_key in a format that includes the new identity (or legacy unit_code_norm) so keys remain unique. Old batches (checksum) still skip. New batches use new resolver; they create/find unit by (building_id, unit_number) and still enforce one open turnover per unit_id.

---

## 5) Import Refactor Strategy

### Structured resolver

- **resolve_property(conn, property_id: int)**  
  Return property row by property_id (or by name/code if you add it). For single-property deployments, may be trivial.

- **resolve_phase(conn, property_id: int, phase_code: str)**  
  Get or create phase: SELECT from phase WHERE property_id = ? AND phase_code = ?; if missing, INSERT (phase_code, property_id), return row. Ensures UNIQUE(property_id, phase_code).

- **resolve_building(conn, phase_id: int, building_code: str)**  
  Get or create building: SELECT from building WHERE phase_id = ? AND building_code = ?; if missing, INSERT, return row. Ensures UNIQUE(phase_id, building_code).

- **resolve_unit(conn, building_id: int, unit_number: str, unit_code_raw: str | None = None)**  
  Get or create unit: SELECT from unit WHERE building_id = ? AND unit_number = ?; if missing, INSERT (building_id, unit_number, unit_code_raw, unit_code_norm derived, has_carpet, has_wd_expected, is_active), return row. Ensures UNIQUE(building_id, unit_number).

### Parsing existing unit string

- **Safe parse:** Use same convention as today: `unit_norm` from _normalize_unit(raw). Then split on "-": parts[0] = phase_code, parts[1] = building_code (or "" if only two segments), parts[2] or parts[-1] = unit_number. Validate: phase_code in VALID_PHASES (or in phase table for property); building_code and unit_number non-empty when expected. If parsing fails (e.g. single segment "101"), treat as unit_number only and require phase_code/building_code from elsewhere or use a default (e.g. phase from batch, building "" or "MAIN") so that (phase_id, building_id, unit_number) is deterministic.

- **Validation:** After parse, resolve_phase and resolve_building must succeed (create if missing). unit_number must be non-empty. If unit_code_norm is kept, set it to e.g. f"{phase_code}-{building_code}-{unit_number}".strip("-") for consistency.

### Preventing duplicate unit creation

- All creates go through resolve_*: resolve_phase and resolve_building are get-or-create; resolve_unit is get-or-create. Use SELECT then INSERT only when not found, inside a transaction, so concurrent imports still see UNIQUE constraint or serialized transaction. No duplicate unit creation as long as (building_id, unit_number) is unique and all callers use the same resolver.

### Keeping import idempotency intact

- **Checksum:** Unchanged; same file + report_type → same checksum → NO_OP or skip reprocessing.
- **Open turnover by unit:** Still use get_open_turnover_by_unit(conn, unit_id). Unit_id is stable once unit is resolved. So re-running the same import again finds the same unit_id and same open turnover; no duplicate turnover.
- **source_turnover_key:** Still UNIQUE. New format e.g. `{property_id}:{phase_code}:{building_code}:{unit_number}:{move_out_iso}` or keep `{property_id}:{unit_norm}:{move_out_iso}` during transition by setting unit_code_norm on unit from parsed components. Idempotency does not depend on key lookup, only on (unit_id, open turnover).

### Whether source_turnover_key should change

- **Recommendation:** Change to a structured format that reflects the new identity, e.g. `{property_id}:{phase_code}:{building_code}:{unit_number}:{move_out_iso}`, so that keys are unique and readable. No lookup by key in import; only uniqueness matters. Manual entry key can be `manual:{property_id}:{phase_code}:{building_code}:{unit_number}:{move_out_iso}`.

---

## 6) Risk Assessment

### What breaks first

1. **Repository get_unit_by_norm and insert_unit** — All callers (import, manual entry) assume (property_id, unit_code_norm). As soon as unit identity moves to (building_id, unit_number), those APIs break unless a compatibility layer is added (e.g. get_unit_by_norm that joins unit→building→phase→property and matches phase_code+building_code+unit_number from parsed unit_code_norm).
2. **Board query filter_phase** — Currently compares property_id. Once turnover or unit no longer has property_id (or it’s denormalized), filter must use join to phase. UI and board_query_service must be updated together.
3. **Tests** — test_truth_safety seeds property + unit with (property_id, unit_code_norm). Any test that assumes that identity will fail until tests are updated to seed phase, building, unit with (building_id, unit_number).

### Highest migration risk

- **Import pipeline:** It is the only producer of units and turnovers from external data. If the resolver is wrong (e.g. parse or create order), duplicate units or wrong phase/building can be created. Mitigation: run resolver in a transaction; add integration tests that run import twice and assert no duplicate units/turnovers and correct hierarchy; backfill script in a separate migration with validation (e.g. assert every unit_code_norm parses to exactly one (phase_code, building_code, unit_number)).
- **Backfill from unit_code_norm:** If parsing is ambiguous (e.g. "5-101" → phase 5, building "" or "101"?), backfill could assign wrong building. Mitigation: define parsing rules explicitly and document; validate backfill counts (e.g. distinct (phase_id, building_id, unit_number) = count of units).

### Invariants that could silently change

- **One open turnover per unit:** Unchanged; still keyed by unit_id. No risk if unit_id is stable.
- **Import idempotency (checksum):** Unchanged. Risk only if new code path creates different unit_id for “same” logical unit (e.g. different phase_code parsed) so that a re-run creates a second unit and then a second turnover. Mitigation: resolver must be deterministic (same raw string → same phase_code, building_code, unit_number).
- **SLA and risk reconciliation semantics:** No change; they use turnover and unit rows by id. Only if display or reporting expects “phase” to be property_id could reports change (e.g. “Phase” filter meaning phase_code instead of property_id). Product decision: phase filter should mean “phase_code” (or phase_id) under target.

### Mitigation summary

| Risk | Mitigation |
|------|------------|
| Duplicate units | Resolver get-or-create; UNIQUE(building_id, unit_number); tests that run import twice. |
| Wrong hierarchy on backfill | Explicit parse rules; validate backfill; one-off script with dry-run. |
| Filter “phase” breaks | Implement phase filter via join (unit→building→phase) or denormalized phase_id on unit; update UI to pass phase_id/phase_code. |
| Tests fail | Update test_truth_safety and enrichment harness to seed phase/building/unit with new schema; or add compatibility layer so get_unit_by_norm still works during transition. |
| Import creates two turnovers for same unit | Resolver must return same unit_id for same (property, phase, building, unit_number); open turnover check remains by unit_id. |

---

## Deliverables Summary

| Deliverable | Section |
|-------------|---------|
| **A) Dependency impact map** | §2 (per-module breaks and changes) |
| **B) Proposed normalized schema** | §3 (property, phase, building, unit, turnover; task_template; unit_code_norm, layout, attributes) |
| **C) Minimal migration sequence** | §4 (add phase/building, backfill, unit columns, identity switch, turnover cleanup; SQLite-safe) |
| **D) Import resolution design** | §5 (resolve_property, resolve_phase, resolve_building, resolve_unit; parse, validate, idempotency, source_turnover_key) |
| **E) Risk assessment** | §6 (what breaks first, highest risk, silent invariant changes, mitigations) |

No code has been implemented; this document is architectural and design-only.
