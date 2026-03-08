# PART I — Manual Add Single Unit Availability

**Status:** Implemented.  
**Context:** Add one open turnover (availability) for an **existing** unit via UI. Unit is resolved by property → phase → building → unit_number. No unit creation; one open turnover per unit preserved; same SLA and task semantics as operational imports.

---

## 1. Requirements (summary)

- Resolve unit via **property / phase / building / unit_number** (hierarchy lookup only; **do not create** units).
- Enforce **one open turnover per unit** (DB-level invariant; fail if unit already has an open turnover).
- Use **turnover_service** for turnover creation and post-create reconciliation (no direct SQL in UI).
- Generate tasks via the **same path as operational imports** (templates by phase, repository.insert_task, task dependencies).
- Trigger **SLA logic** (same as operational imports: `reconcile_sla_for_turnover` after creation).
- Trigger **risk reconciliation** (same as manual/import: `reconcile_risks_for_turnover` after creation).

---

## 2. UI field contract

| Field | Type | Required | Validation | Notes |
|-------|------|----------|------------|--------|
| **Property** | Selectbox or hidden | Yes | Must exist in `property`; single-property may default to 1 | Value: `property_id` (int). |
| **Phase** | Selectbox | Yes | Must be a phase_code for the selected property (from `phase` table) | Value: `phase_id` (int) preferred for service call, or (property_id, phase_code). |
| **Building** | Selectbox or text | Yes | Must be a building_code under the selected phase | Value: `building_code` (str). Optional: resolve to building_id in service. |
| **Unit number** | Text input | Yes | Non-empty after strip | Value: `unit_number` (str). |
| **Move-out date** | Date input | Yes | Valid date | Required. |
| **Move-in date** | Date input | No | Valid date or empty | Optional. |
| **Report ready date** | Date input | No | Valid date or empty | Optional. |

- **Unit identity:** (property_id, phase_id, building_code, unit_number) or (property_id, phase_code, building_code, unit_number). Service accepts either phase_id or (property_id + phase_code) to resolve phase.
- **Submit:** e.g. "Add availability" or "Create turnover". On success: redirect to turnover detail or show success and new turnover_id.

---

## 3. Service-level function signature

**Option A — New function in `turnover_service` (recommended)**

```text
def add_manual_availability(
    *,
    conn,
    unit_id: int,
    move_out_date: date,
    move_in_date: date | None = None,
    report_ready_date: date | None = None,
    today: date | None = None,
    actor: str = "manager",
) -> int:
    """
    Create one open turnover for the given unit (must already exist).
    Enforces one open turnover per unit; instantiates tasks from templates;
    runs SLA and risk reconciliation. Returns turnover_id.
    Raises ValueError if unit has an open turnover or unit_id invalid.
    """
```

- **Caller** is responsible for resolving (property_id, phase_code, building_code, unit_number) → unit_id **before** calling this (e.g. in a thin orchestration layer or in the same service with a second entry point that does lookup then calls this).

**Option B — Single entry point that does lookup + create**

```text
def add_manual_availability_for_unit(
    *,
    conn,
    property_id: int,
    phase_code: str,
    building_code: str,
    unit_number: str,
    move_out_date: date,
    move_in_date: date | None = None,
    report_ready_date: date | None = None,
    today: date | None = None,
    actor: str = "manager",
) -> int:
    """
    Look up unit by (property_id, phase_code, building_code, unit_number).
    If unit not found → ValueError (does not create unit).
    If unit has open turnover → ValueError.
    Else create turnover, instantiate tasks, reconcile SLA/risks; return turnover_id.
    """
```

- **Recommendation:** Option B in a dedicated module (e.g. `services/manual_availability_service.py`) that uses repository for lookup and calls into turnover_service for the create + reconcile flow, so that turnover_service only needs a small addition (create turnover + trigger task instantiation + SLA/risk reconcile) and no unit-resolution logic.

**Concrete recommendation**

- **`services/manual_availability_service.py`**  
  - **`add_manual_availability(conn, *, property_id, phase_code, building_code, unit_number, move_out_date, move_in_date=None, report_ready_date=None, today=None, actor="manager") -> int`**  
  - Resolves unit by **lookup only** (see §4). Raises if unit not found or unit has open turnover. Builds `source_turnover_key = f"manual:{property_id}:{phase_code}:{building_code}:{unit_number}:{move_out_iso}"` (or reuse `manual:{property_id}:{unit_norm}:{move_out_iso}` with unit_norm from unit row). Calls repository.insert_turnover; then task instantiation (same as import); then turnover_service reconciliation (SLA + risks).

- **`turnover_service`**  
  - Add **`create_turnover_and_reconcile(conn, *, unit_id, property_id, source_turnover_key, move_out_date, move_in_date=None, report_ready_date=None, today, actor) -> int`** (or equivalent) that:  
    - Inserts turnover via repository.insert_turnover.  
    - Calls shared task-instantiation (from import_service or a shared helper) for the new turnover_id and unit row.  
    - Calls sla_service.reconcile_sla_for_turnover.  
    - Calls risk_service.reconcile_risks_for_turnover.  
  - So turnover_service owns “create one turnover + reconcile”; manual_availability_service owns “resolve unit (lookup only) + build key + call turnover_service”.

---

## 4. Required repository calls

**Lookup-only resolution (unit must exist)**

1. **Phase:** Either `repository.get_phase(property_id, phase_code)` returning one row or None (if not implemented, use `SELECT * FROM phase WHERE property_id = ? AND phase_code = ?` in repository and return None if no row).
2. **Building:** `repository.get_building(phase_id, building_code)` returning one row or None (or `SELECT * FROM building WHERE phase_id = ? AND building_code = ?`).
3. **Unit:** `repository.get_unit_by_building_and_number(conn, building_id=..., unit_number=...)` → unit row or None.

If any step returns None → raise ValueError("Unit not found") with a clear message (e.g. "No unit found for Phase X, Building Y, Unit Z").

**After unit is found**

4. **Open turnover check:** `repository.get_open_turnover_by_unit(conn, unit_id)`. If not None → raise ValueError("Unit already has an open turnover. Close or cancel it first.").
5. **Insert turnover:** `repository.insert_turnover(conn, data)` with property_id, unit_id, source_turnover_key, move_out_date, move_in_date, report_ready_date, created_at, updated_at, and other required/defaulted fields (no wd_*, closed_at, canceled_at; last_seen_moveout_batch_id=None, missing_moveout_count=0).
6. **Task instantiation:** Use same logic as import: load templates by `repository.get_active_task_templates_by_phase(conn, phase_id=unit_row["phase_id"])` (or by property_id if phase_id missing), filter by _apply_template_filter(unit_row), then `repository.insert_task` for each, then `repository.get_task_template_dependencies` and `repository.insert_task_dependency`. Prefer exposing **`import_service.instantiate_tasks_for_turnover(conn, turnover_id, unit_row, property_id)`** (or same signature) so manual flow calls one function.
7. **SLA:** `sla_service.reconcile_sla_for_turnover(conn, turnover_id=turnover_id, move_out_date=move_out_date, manual_ready_confirmed_at=None, today=today, actor=actor)`.
8. **Risks:** `risk_service.reconcile_risks_for_turnover(conn, turnover_id=..., move_in_date=..., move_out_date=..., today=..., tasks=..., wd_present=None, wd_supervisor_notified=None, has_data_integrity_conflict=False, has_duplicate_open_turnover=False, actor=actor)`.
9. **Audit:** `repository.insert_audit_log(conn, { entity_type="turnover", entity_id=turnover_id, field_name="created", old_value=None, new_value="manual_availability", source="manual", actor=actor })`.

**Repository additions (if not present)**

- **get_phase(conn, property_id, phase_code) -> row | None** (read-only; no create).
- **get_building(conn, phase_id, building_code) -> row | None** (read-only; no create).

These can be implemented as simple SELECTs. **Do not use** `resolve_phase` / `resolve_building` here — they are get-or-create and would create phase/building; for PART I we require the unit (and thus phase/building) to already exist.

---

## 5. Edge case handling

| Case | Handling |
|------|----------|
| **Unit not found** (phase/building/unit_number does not exist) | Raise ValueError("Unit not found for the given property, phase, building, and unit number."). Do not create unit. |
| **Unit already has an open turnover** | Raise ValueError("This unit already has an open turnover. Close or cancel it first."). Do not insert a second turnover. |
| **Invalid move-out date** | Validate before insert; raise ValueError if missing or invalid. |
| **property_id or phase not in DB** | Lookup phase returns None → "Unit not found" (or "Phase not found" if desired). |
| **Duplicate source_turnover_key** | Key format `manual:{property_id}:{unit_identity_key}:{move_out_iso}` is unique per (unit, move_out). If same unit + same move_out is submitted twice, second attempt would try to create another turnover and fail on one-open-per-unit. So no separate key collision case. |
| **Task template missing for phase** | Same as import: instantiate_tasks_for_turnover may create zero tasks if no templates; turnover is still created and SLA/risk run. |
| **Transaction rollback** | Caller owns conn and transaction; on any raised exception, caller should rollback and not commit. |

---

## 6. source_turnover_key format

- Use a distinct manual prefix to avoid collision with import keys.  
- **Format:** `manual:{property_id}:{unit_identity_key}:{move_out_iso}`  
  Example: `manual:1:5-25-0206:2025-03-01`  
- `unit_identity_key` from unit row (unit.unit_identity_key) or composed from phase_code, building_code, unit_number via `domain.unit_identity.compose_identity_key`.

---

## 7. Test plan

| Test | Description |
|------|-------------|
| **Unit not found** | Call add_manual_availability with (property_id, phase_code, building_code, unit_number) that does not exist in DB. Expect ValueError("Unit not found" or similar); no turnover inserted; no tasks. |
| **Open turnover exists** | Seed one unit and one open turnover. Call add_manual_availability for that unit_id (or for that unit's hierarchy). Expect ValueError("already has an open turnover"); no second turnover. |
| **Success creates turnover and tasks** | Seed property, phase, building, unit; no open turnover. Call add_manual_availability with valid dates. Assert one new turnover for that unit_id; assert tasks created from task_template for that phase; assert get_open_turnover_by_unit(unit_id) returns the new turnover. |
| **SLA reconciliation** | After add_manual_availability, call repository.get_open_sla_event(conn, turnover_id). Assert SLA state consistent with move_out_date and manual_ready_confirmed_at (e.g. breach opened if applicable per sla_engine rules). |
| **Risk reconciliation** | After add_manual_availability, fetch active risks for turnover; assert no spurious risks and any expected risks (e.g. SLA_BREACH) are present per risk_engine. |
| **Idempotency / no duplicate** | Run add_manual_availability twice for same unit without closing the first turnover; second call must raise (open turnover exists). |
| **Audit log** | After success, assert one audit_log row for entity_type=turnover, entity_id=turnover_id, field_name="created", source="manual". |
| **No unit creation** | Use a DB with no unit for (property, phase, building, unit_number). Call add_manual_availability. Expect ValueError; assert no new row in unit table. |

---

## 8. Summary

| Item | Choice |
|------|--------|
| **Unit resolution** | Lookup only: get_phase → get_building → get_unit_by_building_and_number. No resolve_unit (no create). |
| **Where it lives** | New `services/manual_availability_service.py` with `add_manual_availability(conn, *, property_id, phase_code, building_code, unit_number, move_out_date, move_in_date=None, report_ready_date=None, today=None, actor) -> int`. Optional: turnover_service gains `create_turnover_and_reconcile` used by this and possibly import. |
| **Tasks** | Same as import: instantiate from task_template by phase (or property_id fallback), via import_service or shared helper; no direct SQL. |
| **SLA / risks** | Same as operational imports: after insert_turnover and task instantiation, call reconcile_sla_for_turnover and reconcile_risks_for_turnover. |
| **UI** | Fields: Property, Phase, Building, Unit number, Move-out (required), Move-in (optional), Report ready (optional). Submit → call service; on success redirect or show success; on ValueError show message. |
| **Invariant** | One open turnover per unit: enforced by check get_open_turnover_by_unit before insert; DB unique index already enforces. |
