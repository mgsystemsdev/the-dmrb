# Manual Entry Workflow — Design Recommendation

**Status:** Recommendation only (not implemented).  
**Context:** DB-backed SQLite, Streamlit UI, service layer authoritative. Units/turnovers are typically created via `import_service`; manual entry is for cases when import has not yet created the unit/turnover.

---

## 1. Recommended approach: **C) Create Unit + Create Turnover together (single form/workflow)**

### Rationale

- **A) Create Unit only** — Leaves the user waiting for import to create the turnover, or forces a separate “create turnover” step. Poor UX and doesn’t solve “no turnover yet.”
- **B) Create Turnover only** — Requires the unit to already exist. When import hasn’t run, the unit often doesn’t exist, so the user would need to create the unit first (e.g. via a separate flow or import). Two-step flow is more friction.
- **C) Single workflow** — One form: resolve or create the unit from (property_id + unit code), then create the turnover if the unit has no open turnover. Matches how import works (`_ensure_unit` then insert turnover) and keeps one open turnover per unit. No collision with import if `source_turnover_key` uses a dedicated manual namespace (see §4).

**Conclusion:** Implement **C** so that “add a turnover for a unit that may not exist yet” is a single, idempotent-friendly operation that aligns with existing import behavior and schema invariants.

---

## 2. Repo contracts summary (relevant)

| Contract | Location | Constraint |
|----------|----------|------------|
| `turnover.source_turnover_key` | schema.sql | NOT NULL UNIQUE |
| `turnover.move_out_date` | schema.sql | NOT NULL |
| One open turnover per unit | schema.sql | Partial UNIQUE on `(unit_id)` WHERE open |
| Unit uniqueness | schema.sql | UNIQUE(property_id, unit_code_norm), unit_code_norm <> '' |
| Import key format | import_service | `{property_id}:{unit_norm}:{move_out_iso}` (no prefix) |
| Unit ensure | import_service | `_ensure_unit(conn, property_id, unit_raw, unit_norm)` — get or create, update raw if exists |
| Task instantiation | import_service | `_instantiate_tasks_for_turnover(conn, turnover_id, unit_row, property_id)` |
| insert_turnover | repository | Requires property_id, unit_id, source_turnover_key, move_out_date, created_at, updated_at; optional move_in_date, report_ready_date, etc. |
| insert_unit | repository | property_id, unit_code_raw, unit_code_norm (required); optional has_carpet, has_wd_expected, is_active |

---

## 3. Minimal required inputs (validated against schema)

| Input | Required | Validation | Schema / invariant |
|-------|----------|------------|--------------------|
| **Phase / property_id** | Yes | One of allowed phases (e.g. 5, 7, 8); must exist in `property` table | turnover.property_id, unit.property_id FK |
| **Unit code (raw)** | Yes | Non-empty after trim; normalized to `unit_code_norm` (same rules as import) | unit_code_norm <> ''; UNIQUE(property_id, unit_code_norm) |
| **Move-out date** | Yes | Valid date | turnover.move_out_date NOT NULL |
| **Move-in date** | No | Valid date or empty | Optional |
| **Report ready date** | No | Valid date or empty | Optional |

- **Unit code normalization:** Reuse import’s rule so manual and import agree on the same unit: strip, optional “UNIT ” prefix removal, uppercase, collapse spaces → `unit_code_norm`. Same as `import_service._normalize_unit(raw)` → `(raw_clean, unit_norm)`.
- **Phase → property_id:** Today import uses `property_id` passed in (e.g. default 1); UI often uses “Phase” 5/7/8. Recommendation: UI sends `property_id` (e.g. 5, 7, 8); ensure those rows exist in `property` (bootstrap or config).

---

## 4. source_turnover_key for manual turnovers

### 4.1 Use a distinct manual namespace

- **Recommendation:** Use a **prefix** so manual keys never equal import keys.
- **Format:** `manual:{property_id}:{unit_norm}:{move_out_iso}`  
  Example: `manual:5:5-BLD-101:2025-02-01`
- **Why:** Import uses `{property_id}:{unit_norm}:{move_out_iso}` with no prefix. A manual key with the same format would (1) collide if import later runs for that same unit/date and (2) be indistinguishable. With prefix `manual:`:
  - Uniqueness: manual keys are distinct from import keys; no UNIQUE violation when import runs.
  - Idempotency: Import does **not** look up by `source_turnover_key`; it uses `get_open_turnover_by_unit(unit_id)`. So when import runs for the same unit and same move_out date, it finds the open (manual) turnover and only updates `last_seen_moveout_batch_id` (and related fields). It does not insert a second row.
  - Optional reporting: Can list or flag manual entries with `source_turnover_key LIKE 'manual:%'` without schema change.

### 4.2 Reconcile / merge when import arrives

- **No extra merge logic required.** Current import behavior already treats the manual turnover as the open turnover for that unit:
  - Same unit, same move_out → touch existing (manual) turnover.
  - Same unit, different move_out → CONFLICT (MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER); no duplicate turnover.
- Manual turnovers are “adopted” by import when the move-out date matches; no separate reconciliation step.

---

## 5. Service layer: functions to add

### 5.1 Option A — New module `services/manual_entry_service.py` (recommended)

Keep import_service focused on file-based import; put manual entry in a dedicated module that reuses repo + shared normalization and task instantiation.

- **`create_manual_turnover(conn, *, property_id: int, unit_code_raw: str, move_out_date: date, move_in_date: date | None = None, report_ready_date: date | None = None, actor: str = "manager") -> int`**
  - Returns: `turnover_id`.
  - Steps:
    1. Normalize unit: same rule as import (e.g. call a shared `normalize_unit_code(raw)` or duplicate `_normalize_unit` logic).
    2. If `unit_code_norm` is empty after normalize → raise ValueError.
    3. Ensure unit: get by (property_id, unit_code_norm); if missing, insert_unit (same defaults as import: has_carpet=0, has_wd_expected=0, is_active=1).
    4. `open_turnover = get_open_turnover_by_unit(conn, unit_id)`. If not None → raise ValueError("Unit already has an open turnover. Close or cancel it first.").
    5. `move_out_iso = move_out_date.isoformat()`; build `source_turnover_key = f"manual:{property_id}:{unit_code_norm}:{move_out_iso}"`.
    6. `now_iso = now_utc_iso()`. insert_turnover with: property_id, unit_id, source_turnover_key, move_out_date=move_out_iso, move_in_date, report_ready_date, created_at=now_iso, updated_at=now_iso, last_seen_moveout_batch_id=None, missing_moveout_count=0, and other nullable fields as None/default.
    7. Instantiate tasks: same logic as import (either call a function exposed from import_service, e.g. `instantiate_tasks_for_turnover(conn, turnover_id, unit_id, property_id)`, or move shared task-instantiation into a small shared helper used by both).
    8. Audit: insert_audit_log entity_type=turnover, entity_id=turnover_id, field_name="created", old_value=None, new_value="manual_entry", source="manual", actor=actor.
  - Caller owns transaction (commit/rollback/close).

- **Shared normalization:** Either:
  - Export from import_service: `normalize_unit_code(raw: str) -> tuple[str, str]` (raw_clean, unit_norm), used by both import and manual_entry_service, or
  - Define in a small shared module (e.g. `domain/unit_code.py` or inside `db/`) and use from both. Recommendation: add `normalize_unit_code` to import_service and call it from manual_entry_service to avoid duplication and keep one source of truth.

- **Task instantiation:** Prefer exposing from import_service something like:
  - `instantiate_tasks_for_turnover(conn, turnover_id: int, unit_id: int, property_id: int) -> None`
  which loads unit row, then calls existing `_instantiate_tasks_for_turnover(conn, turnover_id, unit_row, property_id)`. Manual entry then calls this after insert_turnover.

### 5.2 Option B — Extend `turnover_service.py`

- Add `create_manual_turnover(...)` in turnover_service. It would still need to call into something that can instantiate tasks (import_service or a shared helper). Keeps “turnover” ops in one place but couples turnover_service to unit creation and task templates. Slightly more coupling than a dedicated manual_entry_service.

**Recommendation:** Option A (dedicated `manual_entry_service`) with shared normalization and a single exposed task-instantiation entry point in import_service.

---

## 6. Schema changes

- **None required** for the recommended design. Existing schema supports:
  - insert_unit, get_unit_by_norm
  - insert_turnover (with manual source_turnover_key)
  - get_open_turnover_by_unit
  - task_template + task instantiation
- **Optional future:** If you want to query “manual” without string prefix, consider `turnover.source_type TEXT` or `turnover.is_manual INTEGER` and set it in this workflow. Not needed for correctness or import coexistence.

---

## 7. Edge cases and behavior

| Case | Behavior |
|------|----------|
| **Duplicate unit (same property_id + unit_norm)** | Do not insert a second unit; use existing unit (same as import `_ensure_unit`). Optionally update `unit_code_raw` to the latest input. |
| **Unit already has an open turnover** | Refuse to create a second turnover; raise clear error: "Unit X already has an open turnover. Close or cancel it first." |
| **Later import, same unit + same move_out** | Import finds open turnover by unit_id, sees same move_out_date, updates last_seen_moveout_batch_id (and similar). No duplicate; manual row is “adopted.” |
| **Later import, same unit + different move_out** | Import reports CONFLICT (MOVE_OUT_DATE_MISMATCH_FOR_OPEN_TURNOVER). User must resolve (e.g. close/cancel manual or correct dates via import or UI). |
| **Date corrections after creation** | Use existing `turnover_service.update_turnover_dates`; no change. |
| **Empty or invalid unit code** | After normalize, if unit_code_norm is empty → ValueError with message to supply a valid unit code. |
| **property_id not in property table** | FK will fail on insert_unit or insert_turnover; either ensure property rows exist (bootstrap) or validate property_id in service and raise a clear error before insert. |

---

## 8. UI form and validation

### 8.1 Form fields

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| Phase | Selectbox | Yes | Values 5, 7, 8 (or labels “Phase 5”, “Phase 7”, “Phase 8”) → property_id. |
| Unit code | Text input | Yes | Free text; normalized server-side same as import. |
| Move-out date | Date input | Yes | Required. |
| Move-in date | Date input | No | Optional. |
| Report ready date | Date input | No | Optional. |

Submit button: e.g. “Create turnover” or “Add manual turnover”.

### 8.2 Validation rules (client-side and service-side)

- **Phase:** Required; must be one of allowed property_ids (e.g. 5, 7, 8). If UI only has phases, map phase → property_id (e.g. phase 5 → property_id 5).
- **Unit code:** Required; after trim, must not be empty. Server normalizes and rejects if normalized form is empty.
- **Move-out date:** Required; valid date.
- **Move-in / report_ready:** Optional; if provided, valid date.
- **Server-side:** Before insert_turnover, check get_open_turnover_by_unit(unit_id); if open exists, return friendly error (e.g. “This unit already has an open turnover. Close or cancel it first.”).

### 8.3 Success behavior

- On success: show success message and either (a) redirect to the new turnover’s detail page, or (b) stay on the form and show the new turnover_id/unit for copy/link. Recommendation: redirect to turnover detail for the new turnover_id.

---

## 9. Summary

| Item | Recommendation |
|------|----------------|
| **Approach** | **C) Create Unit + Turnover together** in a single form/workflow. |
| **source_turnover_key** | `manual:{property_id}:{unit_norm}:{move_out_iso}` to avoid collision with import and allow optional reporting. |
| **Reconcile when import arrives** | No extra logic; import already “adopts” the manual turnover when unit and move_out match. |
| **New service** | `manual_entry_service.create_manual_turnover(conn, *, property_id, unit_code_raw, move_out_date, move_in_date=None, report_ready_date=None, actor="manager") -> int`. |
| **Shared pieces** | Reuse normalization (e.g. from import_service) and expose task instantiation (e.g. `instantiate_tasks_for_turnover(conn, turnover_id, unit_id, property_id)`) from import_service. |
| **Schema changes** | None. |
| **UI** | Single form: Phase (property_id), Unit code, Move-out (required), Move-in (optional), Report ready (optional); validate and show clear errors for “unit already has open turnover” and invalid/empty unit code. |

This design keeps manual entry consistent with import (same unit norm, one open turnover per unit, same task instantiation), avoids key collisions, and requires no schema or import logic changes.
