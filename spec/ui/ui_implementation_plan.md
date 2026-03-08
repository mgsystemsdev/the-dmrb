# Turnover Cockpit v1 — UI Analysis & Implementation Plan

Full analysis of the Streamlit UI per **Canonical Master Blueprint v1** (§16 UI Contract, §14 Performance, §15.2 Startup), the **functional cockpit specification** (attention control, field-mode, cognitive load), and the current backend. Plan is actionable for implementation in order.

---

## 1. UI Philosophy & Principles (Cockpit Spec)

This is **not a CRUD app**. It is a **deterministic attention-control cockpit** over a finite-state lifecycle.

The UI must:

1. **Show only what requires attention** — Prioritize by risk and proximity; hide noise.
2. **Prevent silent drift** — No auto-merge; conflicts visible; state changes explicit.
3. **Never hide risk** — If a risk exists, it is visible on dashboard and turnover page; it auto-resolves; it never disappears silently.
4. **Never silently mutate state** — Every change is user- or import-triggered; audit trail.
5. **Support &lt;10s confirmation flow in the field** — Unit search pinned; QC confirm in one click; execution status in ≤2 clicks; no heavy forms.
6. **Avoid nested navigation** — Three primary surfaces only; no deep hierarchies.

**Cognitive load strategy:** The system removes memory burden, spreadsheet scanning, manual SLA math, confirmation-backlog guessing, WD forgetfulness, and QC oversight. The UI enforces deterministic attention prioritization, explicit conflict surfacing, clear lifecycle positioning, and clean separation of manual vs system authority.

**What the UI does NOT do (v1):** No auto-scheduling, vendor calendar, drag-drop Gantt, predictive ETA, analytics charts, resident contact system. This is control, not reporting.

---

## 2. Information Architecture

**Three primary surfaces only:**

```
App
├── Dashboard (default landing) — “Where must I act right now?”
├── Turnover Detail (unit-specific operational control)
└── Import Console (upload, run, conflicts)
```

- **Search bar** (unit_code) is globally available (e.g. top bar or sidebar) so the user can jump to a unit from anywhere.
- No other major screens; Conflicts can be a subsection of Import or a dedicated list view.

---

## 3. Blueprint UI Requirements (Summary)

| Area | Blueprint reference | Requirements |
|------|--------------------|--------------|
| **Dashboard** | §16.1 | Sort: (1) risk severity, (2) move-in proximity, (3) SLA age. Sections: Immediate Action (CRITICAL), Needs Confirmation, Execution Overdue, Blocking Notes, Conflicts. |
| **Turnover detail** | §16.2 | Unit search; task actions (vendor complete, confirm, reject); WD toggles; QC confirm; manual ready; note create/resolve. |
| **Import panel** | §16.3 | Upload file; run import; summary (applied, conflicts, no-op/failed); link to conflict list. |
| **Startup** | §15.2 | Integrity check on load; if corrupt → block, show restore instructions + list backups. |
| **Performance** | §14 | Dashboard must avoid N+1; use pre-aggregated or batched queries. |

**Architecture rule (README):** UI layer contains no business logic; it only calls services/repository.

---

## 4. Current Backend vs UI Needs

### 4.1 What the UI can call today

- **Connection:** `db.connection.get_connection(db_path)`, `run_integrity_check(db_path)`, `backup_database(db_path, backup_dir, batch_id)`.
- **Repository:**  
  - Turnovers: `get_turnover_by_id`, `get_open_turnover_by_unit`, `list_open_turnovers_by_property`.  
  - Units: `get_unit_by_norm`, `insert_unit`, `update_unit_fields` — **no `get_unit_by_id`** (needed to show unit_code for a turnover).  
  - Tasks: `get_tasks_by_turnover`, `update_task_fields`.  
  - Risks: `get_active_risks_by_turnover`, `upsert_risk`, `resolve_risk`.  
  - SLA: `get_open_sla_event`.  
  - Import: `insert_import_batch`, `get_import_batch_by_checksum`, `insert_import_row` — **no list batches or list conflict rows**.  
  - Audit: `insert_audit_log`.  
  - **Notes:** table exists; **no note repository functions** (no get_notes_by_turnover, insert_note, resolve_note).
- **Services:**  
  - `turnover_service`: `set_manual_ready_status`, `confirm_manual_ready`, `update_wd_panel`.  
  - `task_service`: `mark_vendor_completed`, `confirm_task`, `reject_task`.  
  - `risk_service`: `reconcile_risks_for_turnover` (called by turnover_service after changes; UI triggers via turnover_service).  
  - `sla_service`: `reconcile_sla_for_turnover` (same).  
  - `import_service`: `import_report_file(conn, report_type, file_path, property_id=1, actor=..., db_path=..., backup_dir=..., today=...)` — caller must commit after.

### 4.2 Gaps to close for UI

| Gap | Purpose | Suggested fix |
|-----|--------|----------------|
| **get_unit_by_id(conn, unit_id)** | Show unit_code_raw on dashboard/detail | Add to repository. |
| **Note CRUD** | Blocking Notes section; note create/resolve on detail | Add `get_notes_by_turnover(conn, turnover_id)`, `insert_note(conn, data)`, `update_note_resolved(conn, note_id, resolved_at)` (or a single resolve function). Optionally thin `note_service` for create/resolve. |
| **List conflict rows** | Conflicts section; Import “link to conflict list” | Add `get_import_rows_with_conflicts(conn, limit=500)` or `get_import_rows_by_batch(conn, batch_id)`. Dashboard “Conflicts” can show recent conflict rows (with batch_id / unit / reason); link to turnover if unit/turnover is known. |
| **List recent batches** | Import panel “last run” / conflict list by batch | Add `get_import_batches_recent(conn, limit=20)` (optional). |
| **EXPOSURE_RISK in schema** | risk_engine emits EXPOSURE_RISK; DB CHECK may reject | Schema has `risk_type CHECK(...)` without EXPOSURE_RISK. Add migration `002_add_exposure_risk_type.sql`: alter CHECK to include `'EXPOSURE_RISK'` (SQLite: recreate table or add CHECK only if supported). Verify schema/repository allow persisting EXPOSURE_RISK. |
| **Dashboard data without N+1** | §14: avoid N+1 | Either (A) one dashboard query (e.g. SQL that joins turnover + unit + aggregated counts for risks/tasks/notes), or (B) batched repo calls: list_open_turnovers → batch get units by unit_ids, batch get risks/tasks/notes by turnover_ids. Prefer (B) with new repo helpers if needed (e.g. get_units_by_ids, get_risks_for_turnover_ids, get_tasks already per-turnover so loop is acceptable if we pre-load all turnovers). |

---

## 5. Screen-by-Screen Functional Spec (Cockpit Blueprint)

Use this for layout, copy, and behavior when building the UI.

### 5.1 Dashboard — Command Center

**When it’s used:** Morning ritual, before leaving office, during crisis, after imports. It answers: *“Where must I act right now?”*

**Top bar**

- **Left:** Search field (unit_code); Filter dropdown (All | Notice | Vacant | SMI | Stabilization).
- **Right:** Import button (navigate to Import Console); Active turnover count; Active CRITICAL risk count badge.

**Summary strip (horizontal KPIs)**

Each metric clickable → filters or focuses the list below.

| Metric | Meaning |
|--------|--------|
| Active Turnovers | Open (not closed/canceled) |
| SLA Breaches | Active breach count |
| Confirmation Backlog | Tasks &gt;2 days vendor-completed but unconfirmed |
| QC Risk | Upcoming move-ins lacking QC confirm |
| WD Risk | Move-ins lacking WD communication |

**Primary attention sections (stacked)**

- **🔴 Immediate Action (CRITICAL)**  
  Sorted by: (1) risk severity, (2) days to move-in, (3) SLA age.  
  Card per turnover, e.g.:
  ```
  Unit 5-18-0206
  Phase: SMI  |  Move-In: 2 days  |  SLA Age: 12 days (BREACH)
  CRITICAL: QC not confirmed (2 days to move-in); WD not notified
  ```
  Buttons: **Open** (→ Turnover detail), **Quick Confirm QC** (if QC task exists and eligible).

- **🟠 Needs Confirmation**  
  Vendor completed but not manager-confirmed &gt;2 days.  
  **Grouped by task type**, e.g. “Paint – 4 units”, “Make Ready – 3 units”, “Carpet Clean – 2 units”. Expandable list.

- **🟡 Execution Overdue**  
  Vendor due date passed, not completed.

- **⚫ Blocking Notes**  
  Human-created blockers only (unresolved, blocking=1).

- **⚠ Data Integrity Conflicts**  
  Weak matches, duplicate turnovers, move-in without turnover, etc. (from import_row conflicts or DATA_INTEGRITY risk).

**Active turnover table (below sections)**

Compact grid:

| Unit | Phase | MO | MI | SLA | Ready | Risks | Actions |
|------|--------|----|----|-----|-------|-------|---------|

- **Color coding:** SLA breach → red; QC risk → orange; WD risk → yellow.
- **Actions column:** Open; Quick Confirm QC (if eligible).
- Pagination not required (max ~200 rows).

---

### 5.2 Turnover Detail — Operational Control Room

Single unit; vertically structured for cognitive flow.

**Header panel (top)**

- Unit code, Phase, Move-Out, Move-In, SLA Age, Manual Ready, System Ready.
- Badges: SLA BREACH, QC RISK, WD RISK (when active).
- Buttons: **Mark Ready** (sets manual_ready_confirmed_at), **Cancel Turnover**, **Close Turnover** (if eligible).

**Lifecycle timeline strip**

- Visual: `NOTICE → VACANT → … → READY → MOVE-IN → STABILIZATION`.
- Current state highlighted. Derived only; not editable.

**Washer/Dryer panel**

- WD Expected | WD Present | Supervisor Notified | Notified At | Installed.
- Buttons: **Mark Supervisor Notified**, **Mark Installed**.
- If move-in ≤7 days and not notified: **warning banner**.

**Task list (core engine)**

- Columns: Task | Required | Blocking | Due | Exec Status | Confirm Status | Actions.
- Execution status: Not Started | Scheduled | In Progress | Vendor Completed | NA. When set to Vendor Completed, auto-stamp vendor_completed_at.
- Confirmation: **Confirm** | **Reject** (Reject → REJECTED + IN_PROGRESS, clear manager_confirmed_at).
- Order: blocking first, then required, then sort_order.

**QC section (quick access)**

- If QC task exists: one large **[ Confirm QC ]** button — must be 1-click in field.

**Notes section**

- Create: Type, Blocking checkbox, Severity, Description.
- List below with **Resolve** per note. Blocking notes shown as banner above tasks.

**Risk section (read-only)**

- List active risk_flags: type, severity, triggered_at, short explanation (derived). No manual edit.

---

### 5.3 Import Console

**Upload section**

- Select file → Choose report type → **Run Import**.
- After run, show:
  - Batch ID, Status (SUCCESS | NO_OP | FAILED), Records, Conflicts, New Turnovers, Updated, Canceled (when available from result/backend).

**Conflict viewer**

- Table: Unit | Reason | Suggested Action | Open (link to turnover if exists).
- Example reasons: WEAK_MATCH_MOVE_OUT_DATE, MOVE_IN_WITHOUT_TURNOVER, PENDING_FAS_MOVE_OUT_MISMATCH, etc.
- Resolution always manual (link to unit/turnover; no auto-merge).

---

### 5.4 Field mode optimization

- **Unit search** always pinned (top bar or sidebar).
- **Confirm QC** in ≤10 seconds (one big button).
- **Execution status change** in ≤2 clicks; no heavy forms.
- **Mobile-friendly:** Responsive layout; task list can collapse to vertical cards; big confirm buttons; no complex hover-only interactions.

---

## 6. Data Flow (What Each Screen Needs)

### 6.1 Startup / integrity

- **Input:** `db_path` (config or env), optional `backup_dir`.
- **Flow:** On app load → `run_integrity_check(db_path)`. If exception → show “Database corrupt” page (restore instructions + list files in `backup_dir`). If OK → set “integrity_ok” and render main app (sidebar + page routing).
- **Restore:** Button or script that copies selected backup file over `db_path`, then rerun/reload.

### 6.2 Dashboard

- **Input:** `property_id` (default 1), `today` (date.today()).
- **Data per open turnover:**  
  - Turnover row (move_out_date, move_in_date, unit_id, …).  
  - Unit (unit_code_raw for display).  
  - Active risks (for “highest severity” and “Immediate Action”).  
  - Tasks (for “Needs Confirmation”: vendor_completed but not confirmed; “Execution Overdue”: past vendor_due_date, not VENDOR_COMPLETED).  
  - Unresolved blocking notes (for “Blocking Notes”).  
  - “Conflicts”: either (a) recent import_row with conflict_flag=1, joined to unit/turnover if possible, or (b) turnover-level “has open DATA_INTEGRITY risk” from risk_flag.
- **Sort:** Load all open turnovers; compute per-row: max risk severity (CRITICAL > WARNING > INFO), move_in_date (proximity), days since move_out_date (SLA age). Sort by (severity desc, move_in_date asc nulls last, move_out_date asc).
- **Sections:** Filter the same list into: Immediate Action (has CRITICAL risk), Needs Confirmation (has confirmation backlog), Execution Overdue (has overdue task), Blocking Notes (has blocking unresolved note), Conflicts (has conflict row or DATA_INTEGRITY risk). Display as sections; each row clickable → Turnover detail (turnover_id).

### 6.3 Turnover detail

- **Entry:** (a) turnover_id from Dashboard, or (b) “Unit search”: user types unit code → normalize → get_unit_by_norm → get_open_turnover_by_unit(unit_id) → turnover_id.
- **Load:** get_turnover_by_id, get_unit (need get_unit_by_id), get_tasks_by_turnover, get_active_risks_by_turnover, get_open_sla_event, get_notes_by_turnover (once added).
- **Display:** Unit code, dates (move_out, move_in, report_ready, manual_ready), lifecycle phase (derive_lifecycle_phase in UI or via a tiny read-only helper), SLA status, risks list, tasks list (with status), notes list.
- **Actions (all via services/repository):**  
  - **Vendor complete:** `task_service.mark_vendor_completed(conn, task_id=...)` then refresh; optionally call risk_service.reconcile_risks_for_turnover (or turnover_service already does it when manual_ready is set — need to ensure task confirm/reject also trigger risk reconcile; currently only turnover_service calls it. So after task_service.confirm_task or reject_task, UI must call risk reconciliation for this turnover. So either turnover_service exposes a “reconcile_risks_for_turnover_after_task_change” or UI calls risk_service.reconcile_risks_for_turnover with turnover data. Easiest: after any task action, reload turnover + tasks, then call reconcile_risks_for_turnover with the same args turnover_service uses.)  
  - **Confirm task:** `task_service.confirm_task(conn, task_id=...)` then reconcile_risks + refresh.  
  - **Reject task:** `task_service.reject_task(conn, task_id=...)` then reconcile_risks + refresh.  
  - **WD toggles:** `turnover_service.update_wd_panel(conn, turnover_id=..., wd_present=..., wd_supervisor_notified=..., today=..., actor=...)`.  
  - **QC quick confirm:** Same as confirm task for the QC task.  
  - **Manual ready:** `turnover_service.set_manual_ready_status(..., manual_ready_status=...)` and/or `turnover_service.confirm_manual_ready(...)`.  
  - **Notes:** Create: insert_note (repo or note_service). Resolve: set resolved_at (repo or note_service).
- **Transaction:** Each action: conn = get_connection(); try: action; conn.commit(); finally: conn.close(). Then refresh data.

### 6.4 Import panel

- **Upload:** Streamlit `st.file_uploader`; save to temp or `data/imports/`; get file path.
- **Report type:** Select one of MOVE_OUTS, PENDING_MOVE_INS, AVAILABLE_UNITS, PENDING_FAS, DMRB (use constants from import_service).
- **Run:** conn = get_connection(db_path); try: result = import_service.import_report_file(conn=conn, report_type=..., file_path=..., property_id=1, db_path=db_path, backup_dir=backup_dir); conn.commit(); except: conn.rollback(); raise; finally: conn.close(). Display result dict: status, applied_count, conflict_count, invalid_count, record_count, batch_id.
- **Conflict list link:** Navigate to “Conflicts” view: list import_row where conflict_flag=1 (e.g. get_import_rows_with_conflicts), show batch_id, unit_code_raw, unit_code_norm, conflict_reason; optionally link to turnover if we can resolve unit → open turnover.

---

## 7. Implementation Plan (Ordered)

### Phase A — Prerequisites (backend gaps)

1. **Schema: EXPOSURE_RISK**  
   - Add migration so `risk_flag.risk_type` CHECK includes `'EXPOSURE_RISK'` (SQLite may require table recreation or a new CHECK; keep repository insert as-is).

2. **Repository**  
   - Add `get_unit_by_id(conn, unit_id)`.  
   - Add note support: `get_notes_by_turnover(conn, turnover_id)` (unresolved only or all), `insert_note(conn, data)`, and resolve (e.g. `update_note_fields` with resolved_at or dedicated `resolve_note(conn, note_id, resolved_at)`).  
   - Add `get_import_rows_with_conflicts(conn, limit=500)` (and optionally `get_import_rows_by_batch(conn, batch_id)`).  
   - Optional: `get_import_batches_recent(conn, limit=20)`.

3. **Risk reconcile after task actions**  
   - Ensure after task_service.confirm_task / reject_task / mark_vendor_completed the UI (or a wrapper) calls risk_service.reconcile_risks_for_turnover for that turnover so confirmation backlog and other risks update. (Turnover_service already calls it for manual_ready and WD; task_service does not. So either add a call in task_service to reconcile_risks after task change, or have the UI call reconcile_risks after every task action. Prefer UI calling it to avoid task_service depending on risk_service if that’s not already the case — but task_service currently doesn’t call risk_service. So: UI will call turnover_service or risk_service after task actions. Easiest: UI calls risk_service.reconcile_risks_for_turnover after any task action, passing the same args that turnover_service builds (turnover row, tasks, etc.). So UI needs to load turnover + tasks and call reconcile_risks_for_turnover. Document in plan.)

### Phase B — App shell and startup

4. **Entrypoint and config**  
   - Add `app.py` (or `streamlit_app.py`) at project root or under `the-dmrb/`.  
   - Read `db_path` and `backup_dir` from env (e.g. `DB_PATH`, `BACKUP_DIR`) or a small config module; default e.g. `data/cockpit.db` and `data/backups`.

5. **Startup integrity**  
   - At top of app: run `run_integrity_check(db_path)`. On failure: `st.stop()` and render a single page: “Database integrity check failed. Restore from backup.” + list files in backup_dir (e.g. `os.listdir(backup_dir)`), plus instructions (“Copy one of these over your DB_PATH and refresh”). Optional: “Restore” button that copies selected file to db_path and then `st.rerun()`.

6. **Navigation**  
   - Sidebar: “Dashboard” | “Turnover detail” | “Import” | (optional) “Conflicts”.  
   - Use `st.session_state` for current page and selected turnover_id.  
   - Default page: Dashboard.

### Phase C — Dashboard

7. **Dashboard data loading** (see §5.1 for layout: top bar, summary strip, sections, table)  
   - Get open turnovers: `list_open_turnovers_by_property(conn, property_id=1)`.  
   - Batch get units: for each turnover.unit_id, call `get_unit_by_id(conn, unit_id)` (or add get_units_by_ids and call once).  
   - For each turnover_id: `get_active_risks_by_turnover`, `get_tasks_by_turnover`, `get_notes_by_turnover` (once added). Avoid N+1: e.g. two bulk queries for all risks and all tasks for the set of turnover_ids if repo supports (e.g. get_risks_for_turnover_ids), or accept one query per turnover for v1 if list is small (<200).  
   - Conflicts: `get_import_rows_with_conflicts(conn)`; optionally map unit_code_norm → turnover for “link to turnover”.

8. **Dashboard sort and sections**  
   - Compute severity order (CRITICAL=3, WARNING=2, INFO=1); move_in_date; days since move_out.  
   - Sort rows by (max_severity desc, move_in_date asc, move_out_date asc).  
   - Split into sections: Immediate Action (CRITICAL), Needs Confirmation (confirmation backlog), Execution Overdue, Blocking Notes, Conflicts.  
   - Render each section with a table or cards; click row → set session_state turnover_id and switch to “Turnover detail”.

### Phase D — Turnover detail

9. **Detail load and unit search** (see §5.2 for layout: header, timeline, WD panel, task list, QC button, notes, risks)  
   - If turnover_id in session: load turnover, unit (get_unit_by_id), tasks, risks, sla_event, notes.  
   - If “Unit search” used: input → normalize unit → get_unit_by_norm → get_open_turnover_by_unit → then load as above.

10. **Detail display**  
    - Show unit code, dates, lifecycle (derive_lifecycle_phase from turnover row + today), SLA (open breach or not), risks table, tasks table (task_type, execution_status, confirmation_status, vendor_completed_at, manager_confirmed_at), notes table (blocking, description, resolved_at).

11. **Detail actions**  
    - Buttons/forms that call: task_service.mark_vendor_completed, confirm_task, reject_task; turnover_service.update_wd_panel, set_manual_ready_status, confirm_manual_ready; note create/resolve (repo or note_service). After each: commit, then call risk_service.reconcile_risks_for_turnover (and sla_service.reconcile_sla_for_turnover where applicable), then refresh page data.

### Phase E — Import panel

12. **Upload and run**  
    - File uploader; save to temp/file path.  
    - Select report_type (dropdown).  
    - Button “Run import”: get_connection; import_service.import_report_file(...); commit; show result (status, applied_count, conflict_count, invalid_count, batch_id).

13. **Summary and conflict link**  
    - Display result dict.  
    - “View conflicts” → navigate to Conflicts view or expand inline list from get_import_rows_with_conflicts (optionally filter by last batch_id).

### Phase F — Conflicts view (optional but recommended)

14. **Conflicts page**  
    - List rows from get_import_rows_with_conflicts; columns: batch_id, unit_code_raw, unit_code_norm, conflict_reason, move_out_date, move_in_date.  
    - Link to Turnover detail when open turnover exists for that unit (get_unit_by_norm → get_open_turnover_by_unit).

### Phase G — Restore path

15. **Restore**  
    - On corrupt page: list backups; on “Restore” copy selected file to db_path and st.rerun(). Or provide scripts/restore_backup.py that does the copy (user runs it manually then restarts app).

---

## 8. File Layout (Proposed)

```
the-dmrb/
  app.py                    # Streamlit entry; integrity check; sidebar; page dispatch
  config.py                 # Optional: DB_PATH, BACKUP_DIR from env
  ui/
    components/             # Optional: shared widgets (e.g. turnover table row)
    pages/
      dashboard.py          # Dashboard tab content
      turnover_detail.py    # Turnover detail tab content
      import_panel.py       # Import tab content
      conflicts.py          # Conflicts list content
  db/
    repository.py           # + get_unit_by_id, note CRUD, get_import_rows_with_conflicts
  services/
    (existing)
  ...
```

Alternatively, a single `app.py` with `if page == "dashboard": ... elif page == "detail": ...` and no separate page files for v1 is acceptable.

**Streamlit layout hints**

- **Session state:** `page` (dashboard | detail | import | conflicts), `turnover_id`, `filter_phase`, `search_unit`; persist so refresh doesn’t lose context.
- **Top bar:** `st.columns([3,1])` or sidebar for search + filter; right side for Import button and badges (active count, CRITICAL count).
- **Dashboard:** Summary strip = one row of `st.metric`; sections = `st.expander` or `st.container` per section; table = `st.dataframe` with `on_click` or use row selection + “Open” button; cards = loop with `st.container` + key by turnover_id.
- **Detail:** One column or narrow sidebar for actions; main column for header → timeline → WD panel → task table → QC button → notes → risks.
- **Import:** `st.file_uploader`, `st.selectbox` (report type), `st.button("Run import")`; result in `st.success`/`st.warning`; conflict table below or via link.

---

## 9. Dependencies

- **Streamlit** is already in requirements.txt.  
- No new packages required unless you add a date picker (streamlit or use `datetime.date` inputs).

---

## 10. Definition of Done (UI)

**Core**

- [ ] App starts; integrity check runs; on failure, corrupt page with backup list and restore instructions.  
- [ ] Dashboard loads open turnovers, sorted by severity / move-in / SLA; sections Immediate Action, Needs Confirmation (grouped by task type), Execution Overdue, Blocking Notes, Conflicts; click → detail.  
- [ ] Turnover detail: global unit search; header (unit, phase, dates, SLA age, ready); lifecycle strip; WD panel with buttons; task list with exec/confirm actions; one-click **Confirm QC**; notes create/resolve; risk list (read-only); risk/SLA reconcile after actions.  
- [ ] Import: upload, select type, run; summary (batch ID, status, records, conflicts, applied); link to conflict list.  
- [ ] Conflicts view: table with Unit, Reason, Suggested Action, Open (link to turnover when available).  
- [ ] Restore from backup possible (in-app or script).

**Cockpit spec**

- [ ] Top bar: search (unit) always available; filter (All / Notice / Vacant / SMI / Stabilization); Import button; active turnover count; CRITICAL risk badge.  
- [ ] Summary strip: Active Turnovers, SLA Breaches, Confirmation Backlog, QC Risk, WD Risk; each clickable to focus list.  
- [ ] Dashboard table: Unit, Phase, MO, MI, SLA, Ready, Risks, Actions; color coding (SLA=red, QC=orange, WD=yellow); Quick Confirm QC where eligible.  
- [ ] Field mode: QC confirm in ≤10s (one big button); execution status in ≤2 clicks; responsive layout; big confirm buttons; no heavy forms.

---

## 11. Risk / Note

- **EXPOSURE_RISK in DB:** If the schema CHECK for risk_type still omits EXPOSURE_RISK, inserts from risk_service will fail. Add migration in Phase A.  
- **Note table:** note_type and severity are required; define allowed values (e.g. note_type: “blocking” vs “info”; severity per blueprint INFO/WARNING/CRITICAL) and enforce in repo or a thin note_service.

**What this UI enables operationally:** User opens dashboard → sees CRITICAL risks, confirmation backlog, execution overdue, blocking notes, conflicts. That’s the day’s attention list — not a spreadsheet, not memory, not scattered reports. The plan above is the single reference for implementing the Streamlit UI in the-dmrb.
