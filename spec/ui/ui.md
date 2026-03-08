UI Prototype (Mock Data, No Backend)

Goal

A minimal Streamlit app you can run locally to see and test the interface: dashboard (top bar, summary strip, sections, table), turnover detail (header, lifecycle strip, WD panel, task table with manual dropdowns for execution/confirmation status, QC button, notes, risks), and import console. No database or service layer — all data is hardcoded so you can iterate on layout, columns, and controls, then decide what to connect and what backend changes to make.



Approach





Single entrypoint: One Streamlit script (e.g. the-dmrb/app_prototype.py) that renders three "pages" via sidebar or session state.



Mock data module: One module (e.g. the-dmrb/ui/mock_data.py) that exposes in-memory lists/dicts shaped like the real domain (turnovers with unit_id, move_out_date, move_in_date, etc.; tasks with task_type, execution_status, confirmation_status; risks; conflicts). No db or services imports.



Same layout as spec: Top bar (search, filter, Import button, counts), summary strip (5 metrics), attention sections, active turnover table; detail view with task table whose Exec status and Confirm status are st.selectbox per row. Dropdown changes update in-memory state (or session state) so you can test flow; nothing is persisted.



Later connection: When you connect the backend, you replace the mock data layer with a thin data loader that calls repository/services; the Streamlit layout and widgets stay the same.



Sidebar, Pages, and Additions

Sidebar / pages





Pages: Dashboard | Control Board 1 | Control Board 2 | Turnover detail | Import. (Detail is shown when a turnover is selected or via unit search.)



Session state: page values include "dashboard", "control_board_1", "control_board_2", "detail", "import". Keep filter_phase, search_unit, selected_turnover_id, and from Excel parity: filter_assignee, filter_move_ins, filter_phase_id, filter_qc.

Excel workflow parity





Top bar (on Dashboard and both Control Boards): Search unit, Filter (Notice / Vacant / SMI / Stabilization), Assign (All / Michael / Brad / Miguel A / Miguel G), Move-ins (All / Today–this week / Next week / Next month), Phase (All / 5 / 7 / 8), QC (All / QC Done / QC Not done). Right side: Import button, Active count, CRITICAL count.



Mock data: assignee on turnovers; property_id or phase (5, 7, 8) for units/turnovers; move_in_date spread; helper get_turnovers_for_dashboard(..., all filter args).



Detail: Unit status dropdown (Vacant ready | Vacant not ready | On notice); task table with Exec/Confirm selectboxes (user-friendly labels optional).

Inline edits





Dashboard table: "Ready" column becomes an editable Status column: per-row st.selectbox (Vacant ready | Vacant not ready | On notice). On change, update session-state copy of that turnover (prototype: no DB).



Detail: Unit status dropdown in header; task table with per-row Exec/Confirm selectboxes. All changes update session-state (and mutable copies of mock data in session state so they persist for the run).

Two Control Board pages (additive)





Control Board 1 — Unit and status (before tasks)
One table: all units/turnovers (after filters). Columns: Unit, Phase, Move-out, Move-in, Status (editable dropdown), Ready date, WD summary, Assignee. Filters same as dashboard (search, Filter, Assign, Move-ins, Phase, QC). Inline edit: changing Status updates session-state turnover copy. "Open" column: button to go to Turnover detail.



Control Board 2 — Tasks
One table: one row per task. Columns: Unique # (turnover_id or unit code), Unit, Status (unit), Day (e.g. move_in_date or vendor_due_date), Task type, Exec status (editable), Confirm status (editable), Due. Same filters on top. Inline edit: changing Exec/Confirm updates session-state task copy. "Open" to go to Turnover detail for that turnover.

Data update surfaces (clarification)





Dashboard = read + navigate + inline status in table (Open, Quick Confirm QC).



Control Board 1 = bulk unit/status edits (inline Status dropdown).



Control Board 2 = bulk task edits (inline Exec/Confirm dropdowns).



Turnover detail = full single-unit control (unit status, WD, tasks, notes).



Import = bulk from file (fake in prototype).



All edits in prototype persist only in session state / in-memory copies.



Files to Add

1. Mock data — the-dmrb/ui/mock_data.py





Purpose: Provide lists/dicts that mimic what the app would get from the DB (turnovers, units, tasks, risks, conflict rows). Use dicts with the same keys as sqlite3.Row (e.g. turnover_id, unit_id, move_out_date, move_in_date, manual_ready_status, report_ready_date, etc.) so the UI code does not need to change when switching to real data.



Contents (conceptually):





MOCK_UNITS — list of dicts: unit_id, property_id, unit_code_raw, unit_code_norm, has_carpet, has_wd_expected, is_active.



MOCK_TURNOVERS — list of dicts: turnover_id, unit_id, property_id, move_out_date, move_in_date, manual_ready_status, manual_ready_confirmed_at, report_ready_date, wd_present, wd_supervisor_notified, wd_notified_at, wd_installed, closed_at, canceled_at, assignee (e.g. "Michael", "Brad", "Miguel A", "Miguel G"), etc. Include 5–8 open turnovers with varied phases (NOTICE, VACANT, SMI), assignees, and move_in_date spread (this week, next week, next month).



MOCK_TASKS — list of dicts: task_id, turnover_id, task_type, required, blocking, scheduled_date, vendor_due_date, vendor_completed_at, manager_confirmed_at, execution_status, confirmation_status. Spread across the mock turnovers; include at least one QC task, some VENDOR_COMPLETED/PENDING (confirmation backlog), some NOT_STARTED with past due date (overdue).



MOCK_RISKS — list of dicts: risk_id, turnover_id, risk_type, severity, triggered_at, resolved_at. Mix of CRITICAL/WARNING for a few turnovers.



MOCK_CONFLICTS — list of dicts: row_id, batch_id, unit_code_raw, unit_code_norm, conflict_reason, validation_status. 2–3 sample rows.



Helpers: get_turnovers_for_dashboard(search_unit=None, filter_phase=None, filter_assignee=None, filter_move_ins=None, filter_phase_id=None, filter_qc=None) (returns turnover dicts with unit_code; filter by lifecycle phase, assignee, move_in band, property/phase 5/7/8, QC done/not); get_tasks_for_turnover(turnover_id); get_risks_for_turnover(turnover_id); get_unit_for_turnover(turnover_id); get_tasks_flat(turnover_ids_or_filter_args) for Control Board 2 (all tasks with turnover/unit info, filtered by same turnover set).

2. Streamlit app — the-dmrb/app_prototype.py





Imports: Only streamlit, datetime, and the mock_data module (and domain.lifecycle for derive_lifecycle_phase if you want real phase labels; optional to avoid touching domain — can hardcode phase strings in prototype).



Session state: page ("dashboard" | "control_board_1" | "control_board_2" | "detail" | "import"), selected_turnover_id, filter_phase, search_unit, filter_assignee, filter_move_ins, filter_phase_id, filter_qc. Mutable copies: st.session_state.turnovers and st.session_state.tasks (deep copies of mock data) updated on inline edits so dropdown changes persist for the run.



Layout:





Sidebar: Radio or selectbox for page: Dashboard, Control Board 1, Control Board 2, Turnover detail, Import.



Top bar (Dashboard and Control Boards): Left: st.text_input("Search unit"), st.selectbox("Filter", ["All", "Notice", "Vacant", "SMI", "Stabilization"]), Assign, Move-ins, Phase (5/7/8), QC. Right: st.button("Import") (go to Import page), st.metric("Active", N), st.metric("CRITICAL", M).



Summary strip: One row of 5 st.metric (Active Turnovers, SLA Breaches, Confirmation Backlog, QC Risk, WD Risk); values derived from filtered mock/session-state data.



Dashboard sections: At least one expander or container for "Immediate Action (CRITICAL)" — cards or rows with Unit, Phase, Move-In, SLA, risk summary, buttons "Open" / "Quick Confirm QC". Active turnover table with columns Unit, Phase, MO, MI, SLA, Status (editable per-row selectbox: Vacant ready | Vacant not ready | On notice), Risks, Actions (Open / Quick Confirm QC). Use session-state turnovers (filtered); "Open" sets selected_turnover_id and page = "detail".



Control Board 1: Same filters. Single table: Unit, Phase, MO, MI, Status (editable selectbox), Ready date, WD, Assignee, Open. Inline status edit updates session_state.turnovers.



Control Board 2: Same filters. One row per task: Unique #, Unit, Status, Day, Task type, Exec status (editable), Confirm status (editable), Open. Inline exec/confirm update session_state.tasks.



Turnover detail (when page == "detail"): If no selected_turnover_id, show unit search (text_input + "Go") that finds turnover by unit code and sets selected_turnover_id. Otherwise:





Header: Unit code (from mock unit), Phase (from lifecycle or hardcoded), Move-Out, Move-In, SLA Age, Manual Ready, System Ready; Unit status dropdown (Vacant ready | Vacant not ready | On notice) that updates session_state.turnovers; badges SLA/QC/WD if in mock risks; buttons Mark Ready, Cancel, Close (no-op in prototype).



Lifecycle strip: Text or simple horizontal layout: NOTICE → VACANT → SMI → … → STABILIZATION with current phase highlighted.



WD panel: Labels + values (WD Expected, WD Present, Supervisor Notified, Notified At, Installed); buttons Mark Supervisor Notified, Mark Installed (update session-state copy of turnover for prototype).



Task table with manual dropdowns: For each task in get_tasks_for_turnover(selected_turnover_id), one row with: Task (task_type), Required, Blocking, Due, Exec status = st.selectbox("", options=["NOT_STARTED","SCHEDULED","IN_PROGRESS","VENDOR_COMPLETED","NA","CANCELED"], index=..., key=task_id_exec), Confirm status = st.selectbox("", options=["PENDING","CONFIRMED","REJECTED","WAIVED"], index=..., key=task_id_conf). On change, update the in-memory/session-state task list so the next rerender shows the new value (no backend). Optional: "Apply" per row or global "Save" to mirror what you’d do with real backend.



QC section: If any task has task_type == "QC", show a large st.button("Confirm QC") (no-op or set that task’s confirmation_status to CONFIRMED in session state).



Notes: Simple form (type, blocking, severity, description) + list of mock notes with Resolve (session state only).



Risks: Read-only list of risks for this turnover from mock data.



Import console (when page == "import"): st.file_uploader("Select file"), st.selectbox("Report type", ["MOVE_OUTS","PENDING_MOVE_INS","AVAILABLE_UNITS","PENDING_FAS","DMRB"]), st.button("Run import"). On "Run import" (no real import): show a fixed summary, e.g. "Batch ID: 1 | Status: SUCCESS | Records: 42 | Conflicts: 2 | Applied: 38". Below, a small table of MOCK_CONFLICTS with columns Unit, Reason, Suggested Action, Open (link or button to go to detail if turnover exists in mock).



Run: From repo root, streamlit run the-dmrb/app_prototype.py (or from the-dmrb, streamlit run app_prototype.py). No DB file or env required.



What You Can Test With the Prototype





Layout and hierarchy: Top bar, summary strip, sections, table; detail header, timeline, WD panel, task table, notes, risks.



Columns and table type: Exact columns for dashboard table and task table; you can adjust order or add/remove columns without touching the backend.



Manual dropdowns: Change execution_status and confirmation_status in the task table; see how it feels (per-row selectbox vs one form per task). Same for manual_ready_status if you add a dropdown in the header.



Navigation: Search (filter mock list), filter by phase, Open to detail, back to dashboard, Import button to import console.



Copy and flow: Wording, button labels, and "Suggested Action" for conflicts can be tuned before wiring to real data.



What Stays Unconnected (Until You Decide)





No db.connection, no db.repository, no services.



No persistence: refresh loses in-session changes (or you persist only in session_state for the run).



No real import, no real task/turnover update. After you like the prototype, you introduce a small data layer (e.g. ui/data.py or services/dashboard_service.py) that loads from DB and replace mock_data calls with those; then add backend gaps (e.g. get_unit_by_id, note CRUD, conflict list) as in the existing UI implementation plan.



Implementation Order





Add the-dmrb/ui/mock_data.py with the mock lists (including assignee, phase variety, move_in spread) and helpers: get_turnovers_for_dashboard(..., all filter args), get_tasks_for_turnover, get_risks_for_turnover, get_unit_for_turnover, get_tasks_flat.



Add the-dmrb/app_prototype.py: session state (including filters and mutable turnovers/tasks copies), sidebar, shared top bar with all filters (Search, Filter, Assign, Move-ins, Phase, QC), summary strip, dashboard table with inline Status selectbox and one attention section, navigation to detail.



Add Control Board 1 page: same filters, single editable table (Unit to before task; inline Status).



Add Control Board 2 page: same filters, task table (one row per task; inline Exec/Confirm).



Implement detail page: unit search when no selection; header with unit status dropdown; lifecycle strip; WD panel; task table with st.selectbox for execution_status and confirmation_status; QC button; notes list; risks list; back to dashboard.



Implement import page: uploader, report type, Run button, fake result, conflict table.



Run and test locally; verify all pages and inline edits work with fake data. Document that "Phase: Prototype" is done and "Phase: Connect backend" will swap mock_data for real data.

No schema, repository, or service changes in this prototype phase.
Prototype Plan Update + Implementation (Two Control Boards, Mock Data)

Scope





Plan doc: Update .cursor/plans/ui_prototype_mock_data_cf4e3c9d.plan.md to add the two Control Board pages, Excel-parity filters, and inline edits. Dashboard and all existing pages stay as specified; nothing removed.



Implementation: Add the-dmrb/ui/mock_data.py and the-dmrb/app_prototype.py so the app runs with streamlit run the-dmrb/app_prototype.py and shows all pages with fake data (no DB).



Part 1: Updates to the Prototype Plan Document

Add the following to the existing plan (no removals).

1. Sidebar / pages





Pages: Dashboard | Control Board 1 | Control Board 2 | Turnover detail | Import. (Detail is shown when a turnover is selected or via unit search.)



Session state: Add page value "control_board_1" and "control_board_2"; keep existing keys (filter_phase, search_unit, selected_turnover_id, and from Excel parity: filter_assignee, filter_move_ins, filter_phase_id, filter_qc).

2. Excel workflow parity (already agreed)





Top bar (on Dashboard and both Control Boards): Search unit, Filter (Notice / Vacant / SMI / Stabilization), Assign (All / Michael / Brad / Miguel A / Miguel G), Move-ins (All / Today–this week / Next week / Next month), Phase (All / 5 / 7 / 8), QC (All / QC Done / QC Not done). Right side: Import button, Active count, CRITICAL count.



Mock data: assignee on turnovers; property_id or phase (5,7,8) for units/turnovers; move_in_date spread; helper get_turnovers_for_dashboard(..., all filter args).



Detail: Unit status dropdown (Vacant ready | Vacant not ready | On notice); task table with Exec/Confirm selectboxes (user-friendly labels optional).

3. Inline edits





Dashboard table: "Ready" column becomes an editable Status column: per-row st.selectbox (Vacant ready | Vacant not ready | On notice). On change, update session-state copy of that turnover (prototype: no DB).



Detail: Unit status dropdown in header; task table with per-row Exec/Confirm selectboxes. All changes update session-state (and mutable copies of mock data in session state so they persist for the run).

4. Two Control Board pages (additive)





Control Board 1 — Unit and status (before tasks)  





One table: all units/turnovers (after filters). Columns: Unit, Phase, Move-out, Move-in, Status (editable dropdown), Ready date, WD summary, Assignee. Filters same as dashboard (search, Filter, Assign, Move-ins, Phase, QC). Inline edit: changing Status updates session-state turnover copy. "Open" column: button to go to Turnover detail.



Control Board 2 — Tasks  





One table: one row per task. Columns: Unique # (turnover_id or unit code), Unit, Status (unit), Day (e.g. move_in_date or vendor_due_date), Task type, Exec status (editable), Confirm status (editable), Due. Same filters on top. Inline edit: changing Exec/Confirm updates session-state task copy. "Open" to go to Turnover detail for that turnover.

5. Data update surfaces (clarification)





Add one short subsection: Dashboard = read + navigate + inline status in table; Control Board 1 = bulk unit/status edits; Control Board 2 = bulk task edits; Turnover detail = full single-unit control; Import = bulk from file. All edits in prototype persist only in session state / in-memory copies.



Part 2: Implementation

2.1 Create the-dmrb/ui/mock_data.py





No imports from db or services; only datetime/date if needed for filter logic.



Lists (dicts keyed like schema/Row):





MOCK_UNITS: 5–8 units with unit_id, property_id (1, 2, 3 or use 5, 7, 8 as property_id for phase), unit_code_raw, unit_code_norm, has_carpet, has_wd_expected, is_active. Unit codes like "5-101", "7-202" so phase can be derived from first segment.



MOCK_TURNOVERS: 5–8 open turnovers (no closed_at/canceled_at), each with turnover_id, unit_id, property_id, move_out_date, move_in_date, manual_ready_status (mix of "Vacant ready", "Vacant not ready", "On notice"), report_ready_date, wd_present, wd_supervisor_notified, wd_notified_at, wd_installed, manual_ready_confirmed_at, etc. Add assignee (e.g. "Michael", "Brad", "Miguel A", "Miguel G") on each for filtering. Spread move_in_date: some this week, next week, next month.



MOCK_TASKS: 2–4 tasks per turnover; include at least one QC task, some VENDOR_COMPLETED + PENDING, some NOT_STARTED. Keys: task_id, turnover_id, task_type, required, blocking, vendor_due_date, execution_status, confirmation_status, etc.



MOCK_RISKS: A few rows per turnover_id with risk_type, severity (CRITICAL/WARNING).



MOCK_CONFLICTS: 2–3 rows with unit_code_raw, conflict_reason, etc.



MOCK_NOTES: Optional; a few notes with turnover_id, blocking, description, resolved_at (some None).



Helpers:





get_turnovers_for_dashboard(search_unit=None, filter_phase=None, filter_assignee=None, filter_move_ins=None, filter_phase_id=None, filter_qc=None) — filter MOCK_TURNOVERS (join units/tasks for unit code and QC); return list of turnover dicts with unit_code attached (from MOCK_UNITS lookup). Use date.today() for move_ins bands and lifecycle.



get_tasks_for_turnover(turnover_id) — return tasks for that turnover.



get_risks_for_turnover(turnover_id) — return risks for that turnover.



get_unit_for_turnover(turnover_id) — return unit dict for that turnover’s unit_id.



get_tasks_flat() — return all tasks with turnover_id and unit_code (for Control Board 2 table); filter by same filter set applied to turnovers (so filter by turnover list).

Logic for filters: phase (lifecycle) can use a simple rule from move_out/move_in vs today (or hardcode phase string per turnover in mock). Move_ins: today ± 7 = this week; next 7–14 = next week; 14–31 = next month. QC: if turnover has any task with task_type == "QC" and confirmation_status != "CONFIRMED" then "QC Not done".

2.2 Create the-dmrb/app_prototype.py





Imports: streamlit as st, datetime/date, copy (for deepcopy of mock data into session state). Import mock_data (and optionally domain.lifecycle.derive_lifecycle_phase for phase labels; if so, pass date strings to lifecycle).



Session state init: page (default "dashboard"), selected_turnover_id (None), search_unit, filter_phase, filter_assignee, filter_move_ins, filter_phase_id, filter_qc. Mutable data: st.session_state.turnovers and st.session_state.tasks as copies of mock lists that get updated on inline edits (so dropdown changes persist for the run). Initialize from mock_data on first run if not set.



Sidebar: Radio or selectbox for page: Dashboard, Control Board 1, Control Board 2, Turnover detail, Import. Setting page switches view.



Shared top bar (when on Dashboard or Control Board 1 or 2): Left: Search unit (text_input), Filter (Notice/Vacant/SMI/Stabilization), Assign, Move-ins, Phase (5/7/8), QC. Right: Button "Import" (switch to Import page), st.metric("Active", N), st.metric("CRITICAL", M). N/M computed from filtered turnover list and risks.



Dashboard page: Summary strip (5 metrics from filtered list). One section "Immediate Action" (e.g. turnovers with CRITICAL risk). Active turnover table: build with columns Unit, Phase, MO, MI, SLA (simple), Status (st.selectbox per row, key=status_{turnover_id}), Risks, Actions (Open, Quick Confirm QC). On selectbox change: detect new value, update st.session_state.turnovers for that turnover_id, then st.rerun(). "Open" sets selected_turnover_id, page = "detail", rerun.



Control Board 1 page: Same filters. Single table: Unit, Phase, MO, MI, Status (editable selectbox), Ready date, WD, Assignee, Open. Data = same get_turnovers_for_dashboard(...) (or from session_state.turnovers filtered). Inline status edit updates session_state.turnovers and rerun.



Control Board 2 page: Same filters. Data = flat task list (get_tasks_flat filtered by current turnover set). Table: Turnover ID or Unit, Unit status, Day (move_in or due), Task type, Exec status (selectbox), Confirm status (selectbox), Open. Inline exec/confirm update session_state.tasks and rerun.



Turnover detail page: If no selected_turnover_id, show unit search (text_input + button "Go") that finds turnover by unit code and sets selected_turnover_id. Else: header (unit code, phase, MO, MI, SLA, manual ready); unit status dropdown (updates session_state.turnovers); lifecycle strip (text); WD panel (values + buttons that update session_state.turnovers); task table with Exec/Confirm selectboxes per task (update session_state.tasks); Confirm QC button; notes list; risks list. Back button to Dashboard.



Import page: File uploader, Report type selectbox, Run import button. On Run: show fixed summary (Batch 1, SUCCESS, Records 42, etc.) and MOCK_CONFLICTS table. No real file read.



Run: From repo root, streamlit run the-dmrb/app_prototype.py. No DB or env required.

2.3 Session-state mutable copies





On first load (e.g. if "turnovers" not in st.session_state): st.session_state.turnovers = copy.deepcopy(mock_data.MOCK_TURNOVERS), st.session_state.tasks = copy.deepcopy(mock_data.MOCK_TASKS). All reads for dashboard and control boards use these. All inline edits write to these so changes persist until browser refresh. Optionally re-sync from MOCK_* on a "Reset" button for testing.



Part 3: Implementation Order





Update the prototype plan document — Add "Sidebar and pages", "Excel workflow parity", "Inline edits", "Two Control Board pages", and "Data update surfaces" as above (append or insert sections in .cursor/plans/ui_prototype_mock_data_cf4e3c9d.plan.md).



Implement mock_data.py — Create the-dmrb/ui/ if missing. Add mock lists and helper functions; ensure filter logic and assignee/phase/move_ins/QC work.



Implement app_prototype.py — Session state init, sidebar, shared top bar, Dashboard (summary, one section, table with inline status), Control Board 1 (single editable table), Control Board 2 (task rows, editable exec/confirm), Turnover detail (full layout, unit status + task dropdowns), Import (fake result + conflicts table).



Run and verify — streamlit run the-dmrb/app_prototype.py from repo root; click through all pages, change filters, edit status and task dropdowns, confirm changes persist in-session.



Files Touched







File



Action





.cursor/plans/ui_prototype_mock_data_cf4e3c9d.plan.md



Edit: add Control Boards, Excel parity, inline edits, data-update subsection





the-dmrb/ui/mock_data.py



Create: mock lists + get_turnovers_for_dashboard, get_tasks_for_turnover, get_risks_for_turnover, get_unit_for_turnover, get_tasks_flat





the-dmrb/app_prototype.py



Create: Streamlit app with all pages and session-state edits



Diagram (pages and data flow)

flowchart TB
  subgraph sidebar [Sidebar]
    D[Dashboard]
    CB1[Control Board 1]
    CB2[Control Board 2]
    TD[Turnover detail]
    IMP[Import]
  end
  subgraph data [Mock and session state]
    Mock[mock_data.py lists]
    SS[session_state.turnovers and .tasks]
  end
  subgraph views [Views]
    D --> DTable[Dashboard table with inline Status]
    CB1 --> T1[Unit table: Unit to before task, editable Status]
    CB2 --> T2[Task table: one row per task, editable Exec/Confirm]
    TD --> Detail[Header, WD, task table, unit status]
    IMP --> Fake[Fake import result and conflicts]
  end
  Mock --> SS
  SS --> DTable
  SS --> T1
  SS --> T2
  SS --> Detail
  DTable --> TD
  T1 --> TD
  T2 --> TD

Dashboard keeps full control (sections, table, Open, Quick Confirm QC). Control Board 1 and 2 are additive; all three plus Detail use the same filters and same session-state-backed data for a consistent prototype you can run with fake data before connecting.





Add Excel-Parity to UI Prototype Plan

Context

The current plan is ui_prototype_mock_data_cf4e3c9d.plan.md. Prototype files do not exist yet (the-dmrb/ui/mock_data.py, the-dmrb/app_prototype.py). This plan adds the Excel workflow parity (filters and dropdowns) into that plan so the prototype, when built, works with fake data and restores "full control via dropdowns."



1. What Gets Added to the Plan Document

Add a new section "Excel workflow parity (filters and dropdowns)" to the existing plan that specifies:





Top bar filters (in addition to existing Search + Filter phase): Assign, Move-ins, Phase (PH), QC.



Mock data fields and helpers to support those filters.



Detail page: explicit unit status dropdown; optional task dropdown labels (Excel wording).

No change to "What stays unconnected" or to schema/repo in this phase; assignee and filter logic live only in mock data and session state.



2. Mock Data Additions (the-dmrb/ui/mock_data.py)

New/expanded fields:





MOCK_TURNOVERS: Add assignee (str) to each turnover, e.g. "Michael", "Brad", "Miguel A", "Miguel G". Ensure variety so filtering has effect. Schema does not have assignee yet; mock key is assignee for UI only.



MOCK_UNITS / MOCK_TURNOVERS: Ensure property_id (or a derived phase) varies: e.g. 5, 7, 8 so "Phase" filter (PH) has meaning. Use property_id if it already exists in mock; otherwise add a phase key for display/filter (e.g. from unit_code: "5-18-0206" -> 5).



Move-in dates: Ensure at least one turnover with move_in in "today/this week", one "next week", one "next month" so the Move-ins filter shows different result sets.

Helper signature (or in-app filter):





get_turnovers_for_dashboard(search_unit=None, filter_phase=None, filter_assignee=None, filter_move_ins=None, filter_phase_id=None, filter_qc=None) that:





Filters by unit search (unit_code contains/norm match).



Filter phase: All | Notice | Vacant | SMI | Stabilization (derive from lifecycle or manual_ready_status + dates).



Filter assignee: All | Michael | Brad | Miguel A | Miguel G (and optionally "Total" as no filter if desired).



Filter move-ins: All | Today / This week | Next week | Next month (band move_in_date by today).



Filter phase (PH): All | 5 | 7 | 8 (by property_id or unit_code leading segment).



Filter QC: All | QC Done | QC Not done (subquery or join tasks: has QC task with confirmation_status == CONFIRMED vs not).

Return the same list-of-dict shape so the dashboard table and sections consume it.



3. Streamlit App Additions (the-dmrb/app_prototype.py)

Session state (add):





filter_assignee (default "All")



filter_move_ins (default "All")



filter_phase_id (default "All") for PH 5/7/8



filter_qc (default "All")

Top bar (add after existing Filter):





Assign: st.selectbox("Assign", ["All", "Michael", "Brad", "Miguel A", "Miguel G"]) (or add "Total" if you want it to mean "show all" same as All).



Move-ins: st.selectbox("Move-ins", ["All", "Today / This week", "Next week", "Next month"]).



Phase (PH): st.selectbox("Phase", ["All", "5", "7", "8"]).



QC: st.selectbox("QC", ["All", "QC Done", "QC Not done"]).

Wire these to the dashboard data call: pass session state into get_turnovers_for_dashboard(...) so the table and sections show only rows matching all selected filters.

Detail page:





Unit status dropdown: In the header (or just below), add st.selectbox("Unit status", ["Vacant ready", "Vacant not ready", "On notice"], index=...) bound to the selected turnover’s manual_ready_status. On change, update the session-state copy of that turnover so the next rerender shows the new value (no backend). Use same values as schema: ('Vacant ready', 'Vacant not ready', 'On notice') per the-dmrb/db/schema.sql.

Task table (optional for prototype):





Label mapping: Show user-friendly labels in the Exec/Confirm dropdowns and map to DB values when updating session state. Example: Exec status display options "Not Started", "Scheduled", "In Progress", "Done", "Blocked", "N/A" mapping to NOT_STARTED, SCHEDULED, IN_PROGRESS, VENDOR_COMPLETED, CANCELED, NA; Confirm: "Pending", "Confirmed", "Rejected", "Waived" mapping to PENDING, CONFIRMED, REJECTED, WAIVED. This keeps the prototype feeling like the Excel TS column while storing schema-compatible values.



4. How the Prototype Will Behave With Fake Data

flowchart LR
  subgraph topbar [Top bar]
    Search[Search unit]
    PhaseFilter[Filter phase]
    Assign[Assign]
    MoveIns[Move-ins]
    PH[Phase 5/7/8]
    QC[QC]
  end
  subgraph data [Mock data]
    Helpers[get_turnovers_for_dashboard with all filters]
    MOCK_TURNOVERS[MOCK_TURNOVERS with assignee and dates]
    MOCK_TASKS[MOCK_TASKS for QC filter]
  end
  subgraph views [Views]
    Summary[Summary strip]
    Sections[Dashboard sections]
    Table[Active turnover table]
    Detail[Turnover detail with unit status and task dropdowns]
  end
  topbar --> Helpers
  Helpers --> MOCK_TURNOVERS
  Helpers --> MOCK_TASKS
  Helpers --> Summary
  Helpers --> Sections
  Helpers --> Table
  Table --> Detail





Changing any top-bar dropdown (Assign, Move-ins, Phase, QC, or existing Filter) recalculates the list from mock data and re-renders summary strip, sections, and table. No persistence; filters are session state only.



"Open" on a row still sets selected_turnover_id and navigates to detail. Detail shows unit status dropdown and task Exec/Confirm dropdowns; changes update session-state (and optional in-memory copy of mock tasks/turnovers) so the UI reflects them until refresh.



5. Where to Document This in the Plan





In "Files to Add" / Mock data: Add bullet for assignee and phase variety; add get_turnovers_for_dashboard(..., filter_assignee, filter_move_ins, filter_phase_id, filter_qc) and describe the filter semantics.



In "Files to Add" / Streamlit app / Layout: Extend "Top bar" with Assign, Move-ins, Phase, QC; extend "Turnover detail" with unit status dropdown and optional task label mapping.



New subsection: "Excel workflow parity" summarizing the eight controls (TS -> task dropdowns, Status -> unit status + phase filter, Move ins -> filter, W/D -> WD panel, Assign -> filter, Status apt -> phase/status, PH -> filter, QC -> filter) and that the prototype replicates them with fake data.



6. Implementation Order (Unchanged, With One Addition)

Keep the existing 5 steps; insert after step 2 (dashboard table):





2b. Add top-bar filters (Assign, Move-ins, Phase, QC) and wire dashboard data to get_turnovers_for_dashboard(..., session_state filters). Add unit status dropdown on detail.

So: 1) mock_data with assignee, phase variety, move-in spread, and filter helper; 2) app shell + top bar + summary + table + new filters; 2b) detail unit status dropdown; 3) detail page (task table, QC, notes, risks); 4) import page; 5) run and iterate.



7. Outcome

After implementation, you can run the prototype with fake data and:





Use Assign, Move-ins, Phase, and QC to narrow the list like in Excel.



Open a unit and set unit status and task status via dropdowns; see changes in-session.



Validate layout and wording before connecting the backend; when connecting, add real assignee (e.g. schema + repo) and replace mock_data with real data loader while keeping the same UI controls.






Add these two because I don't see plan_bridge, and plan_bridge is really important because plan_bridge lets me know when the company is ready. They need to be updated. This code that I'm sending you is all I just want you to use as a reference. :
import pandas as pd
import numpy as np
from datetime import date

# =========================
# CONSTANTS / HELPERS
# =========================

EXCEL_COLUMNS = [
    "Unit","Status","Move_out","Ready_Date","DV","Move_in","DTBR","N/V/M",
    "Insp","Insp_status","Paint","Paint_status","MR","MR_Status",
    "HK","HK_Status","CC","CC_status","Assign","W_D","QC","P","B","U","Notes"
]

TASK_SEQUENCE = ["Inspection", "Paint", "MR", "HK", "CC"]

TASK_COLS = {
    "Inspection": ("Insp", "Insp_status", 1),
    "Paint": ("Paint", "Paint_status", 2),
    "MR": ("MR", "MR_Status", 3),
    "HK": ("HK", "HK_Status", 6),
    "CC": ("CC", "CC_status", 7),
}

ALLOWED_PHASES = ["5", "7", "8"]

def business_days(start, end):
    if pd.isna(start) or pd.isna(end):
        return np.nan
    s = pd.to_datetime(start, errors="coerce")
    e = pd.to_datetime(end, errors="coerce")
    if pd.isna(s) or pd.isna(e):
        return np.nan
    return np.busday_count(s.date(), e.date())


# =========================
# STAGE 1 — FACT ENGINE (VECTORIZED)
# =========================

def run_facts(df, today=None):
    if today is None:
        today = date.today()

    df = df.copy()

    # Normalize dates upfront
    for col in ["Move_in", "Ready_Date", "Move_out"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    # Notes
    df["Note_Text"] = df["Notes"].fillna("").astype(str).str.strip()
    df["Has_Note_Context"] = df["Note_Text"].ne("")

    df["Note_Category"] = (
        df["Note_Text"].str.upper()
        .str.extract("(HOLD|ISSUE|REOPEN|DECISION)", expand=False)
        .fillna("")
    )

    # Assignment
    df["Has_Assignment"] = df["Assign"].fillna("").astype(str).str.strip().str.lower().ne("total") & \
                           df["Assign"].astype(str).str.strip().ne("")

    # Move-in / Ready flags
    df["Is_MoveIn_Present"] = df["Move_in"].notna()
    df["Is_Ready_Declared"] = df["Ready_Date"].notna()

    # N/V/M flags
    upper_nvm = df["N/V/M"].fillna("").astype(str).str.strip().str.upper()
    df["Is_Vacant"] = upper_nvm.eq("VACANT")
    df["Is_SMI"] = upper_nvm.str.contains("SMI|MOVE IN")
    df["Is_On_Notice"] = upper_nvm.str.contains("NOTICE")

    # Phase
    df["Is_Allowed_Phase"] = (
        df["P"].fillna("").astype(str).str.strip().isin(ALLOWED_PHASES)
    )

    # QC
    df["Is_QC_Done"] = df["QC"].fillna("").astype(str).str.strip().str.upper().eq("DONE")

    # Business days
    df["Aging_Business_Days"] = df["Move_out"].apply(lambda d: business_days(d, today))

    return df


# =========================
# STAGE 2 — TASK MECHANICS (FULLY VECTORIZED)
# =========================

def apply_task_mechanics(df):
    df = df.copy()

    # Pre-normalize all 5 status columns
    status_cols = [TASK_COLS[t][1] for t in TASK_SEQUENCE]

    for col in status_cols:
        df[col] = df[col].fillna("").astype(str).str.strip().replace("", "Not Started").str.title()

    # ---- Task State ----
    all_done = df[status_cols].eq("Done").all(axis=1)
    none_started = df[status_cols].eq("Not Started").all(axis=1)

    df["Task_State"] = np.select(
        [all_done, none_started],
        ["All Tasks Complete", "Not Started"],
        default="In Progress"
    )

    # ---- Completion Ratio ----
    df["Task_Completion_Ratio"] = (
        df[status_cols].eq("Done").sum(axis=1) / len(status_cols) * 100
    )

    # ---- Current / Next Task ----
    done_matrix = df[status_cols].eq("Done")
    first_not_done_col = (~done_matrix).idxmax(axis=1)         # the status col name
    cur_index = first_not_done_col.map(lambda name: status_cols.index(name) if name in status_cols else np.nan)

    df["Table_Current_Task"] = cur_index.map(
        lambda i: TASK_SEQUENCE[int(i)] if pd.notna(i) else ""
    )

    df["Table_Next_Task"] = cur_index.add(1).map(
        lambda i: TASK_SEQUENCE[int(i)] if pd.notna(i) and i < len(TASK_SEQUENCE) else ""
    )

    # ---- Stalled Logic ----
    stall_matrix = pd.DataFrame({
        task: (
            df["Is_Vacant"] &
            ~df[TASK_COLS[task][1]].eq("Done") &
            (df["Aging_Business_Days"] > (TASK_COLS[task][2] + 1))
        )
        for task in TASK_SEQUENCE
    })

    df["Is_Task_Stalled"] = stall_matrix.any(axis=1)

    return df


# =========================
# EXCEL HOOK
# =========================

raw_df = xl("DMRB5")
raw_df.columns = EXCEL_COLUMNS

df = run_facts(raw_df)
df = apply_task_mechanics(df)

df
import pandas as pd
import numpy as np
from datetime import date

# ============================================================
# ENGINE CONFIG
# ============================================================

BASE_COLUMN_COUNT = 25

EXPECTED_HEADERS = [
    "Unit", "Status", "Move_out", "Ready_Date", "DV", "Move_in", "DTBR", "N/V/M",
    "Insp", "Insp_status", "Paint", "Paint_status", "MR", "MR_Status",
    "HK", "HK_Status", "CC", "CC_status", "Assign", "W_D",
    "QC", "P", "B", "U", "Notes"
]

# Derived columns from Stage 1 (Core_Facts)
STAGE1_DERIVED = [
    "Note_Text",
    "Has_Note_Context",
    "Note_Category",
    "Has_Assignment",
    "Is_MoveIn_Present",
    "Is_Ready_Declared",
    "Is_Vacant",
    "Is_SMI",
    "Is_On_Notice",
    "Is_Allowed_Phase",
    "Is_QC_Done",
    "Aging_Business_Days",
    "Task_State",
    "Task_Completion_Ratio",
    "Table_Current_Task",
    "Table_Next_Task",
    "Is_Task_Stalled",
]

ALL_INPUT_COLUMNS = EXPECTED_HEADERS + STAGE1_DERIVED

# Task configuration
TASK_SEQUENCE = ["Inspection", "Paint", "MR", "HK", "CC"]

TASK_COLS = {
    "Inspection": ("Insp_status", 1),
    "Paint": ("Paint_status", 2),
    "MR": ("MR_Status", 3),
    "HK": ("HK_Status", 6),
    "CC": ("CC_status", 7),
}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def norm_status(v):
    if pd.isna(v) or str(v).strip() == "":
        return "Not Started"
    return str(v).strip().title()

def is_done(v):
    return str(v).strip().upper() == "DONE"

# ============================================================
# STAGE 2 ENGINE
# ============================================================

def run_intelligence_engine():
    """
    Reads Core_Facts output from Stage 1 and produces Intelligence Layer
    """
    
    df = xl("Core_Facts", header=None)
    today = date.today()
    
    # Handle empty table
    if df.empty or df.shape[0] == 0:
        empty_df = pd.DataFrame(columns=ALL_INPUT_COLUMNS + [
            "Status_Norm",
            "Is_Unit_Ready",
            "Is_Unit_Ready_For_Moving",
            "In_Turn_Execution",
            "Operational_State",
            "Prevention_Risk_Flag",
            "Attention_Badge",
        ])
        
        manifest = {
            "base_column_count": BASE_COLUMN_COUNT,
            "stage1_derived_count": len(STAGE1_DERIVED),
            "stage2_derived_count": 7,
            "all_headers": list(empty_df.columns),
        }
        return empty_df, manifest
    
    # Validate column count
    if df.shape[1] != len(ALL_INPUT_COLUMNS):
        raise ValueError(
            f"Column count mismatch: Core_Facts has {df.shape[1]} columns, "
            f"but Stage 2 expects {len(ALL_INPUT_COLUMNS)} columns"
        )
    
    # Assign headers
    df.columns = ALL_INPUT_COLUMNS
    
    # Clean column names
    df.columns = (
        df.columns
        .astype(str)
        .str.replace("\u00a0", "", regex=False)
        .str.strip()
    )
    
    # ============================================================
    # STAGE 2 DERIVED COLUMNS (7 total)
    # ============================================================
    
    # 1. Status normalization for consumer filtering
    df["Status_Norm"] = (
        df["Status"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    
    # 2. Readiness flags
    df["Is_Unit_Ready"] = (
        df["Status"].astype(str).str.upper().eq("VACANT READY") &
        (df["Task_State"] == "All Tasks Complete")
    )
    
    # 3. Move-in readiness
    df["Is_Unit_Ready_For_Moving"] = (
        df["Is_Unit_Ready"] &
        df["Is_MoveIn_Present"] &
        df["Is_QC_Done"]
    )
    
    # 4. Turn execution flag
    df["In_Turn_Execution"] = df["Is_Vacant"] & (~df["Is_Unit_Ready"])
    
    # 5. Operational State
    def operational_state(r):
        # NOTICE units (tenant gave notice, not yet vacant)
        if r["Is_On_Notice"]:
            if r["Is_SMI"]:  # NOTICE + SMI
                return "On Notice - Scheduled"
            else:  # Just NOTICE
                return "On Notice"
        
        # Out of scope (not vacant, not SMI, not notice)
        if not (r["Is_Vacant"] or r["Is_SMI"]):
            return "Out of Scope"
        
        # Vacant/SMI logic
        if r["Is_MoveIn_Present"] and not r["Is_Unit_Ready_For_Moving"] and r["In_Turn_Execution"]:
            return "Move-In Risk"
        if r["Is_Unit_Ready"] and r["Is_MoveIn_Present"] and not r["Is_QC_Done"]:
            return "QC Hold"
        if r["Is_Task_Stalled"]:
            return "Work Stalled"
        if r["Task_State"] == "In Progress":
            return "In Progress"
        if r["Is_Unit_Ready"]:
            return "Apartment Ready"
        return "Pending Start"
    
    df["Operational_State"] = df.apply(operational_state, axis=1)
    
    # 6. Prevention Risk Flag
    df["Prevention_Risk_Flag"] = (
        df["In_Turn_Execution"] & (
            df["Note_Category"].isin(["HOLD", "ISSUE", "REOPEN"]) |
            (~df["Has_Assignment"]) |
            ((df["Task_State"] == "In Progress") & (~df["Is_Task_Stalled"]))
        )
    )
    
    # 7. Attention Badge
    def attention_badge(r):
        # NOTICE units
        if r["Is_On_Notice"]:
            if r["Is_SMI"]:
                return "📋 On Notice - Scheduled"
            else:
                return "📋 On Notice"
        
        # SMI/MOVE IN with move-in date
        if r["Is_SMI"] and r["Is_MoveIn_Present"]:
            return "📅 Scheduled to Move In"
        
        # Standard operational state mapping
        base = {
            "Out of Scope": "Out of Scope",
            "Move-In Risk": "🔴 Move-In Risk",
            "QC Hold": "🚫 QC Hold",
            "Work Stalled": "⏸️ Work Stalled",
            "In Progress": "🔧 In Progress",
            "Pending Start": "⏳ Pending Start",
            "Apartment Ready": "🟢 Apartment Ready",
        }[r["Operational_State"]]
        
        if r["Operational_State"] in {"Pending Start", "In Progress"} and r["Prevention_Risk_Flag"]:
            return "🟡 Needs Attention"
        
        return base
    
    df["Attention_Badge"] = df.apply(attention_badge, axis=1)
    
    # ============================================================
    # SORTING
    # ============================================================
    df = df.sort_values(
        by="Aging_Business_Days",
        ascending=False,
        na_position="last"
    )
    
    # ============================================================
    # MANIFEST
    # ============================================================
    manifest = {
        "base_column_count": BASE_COLUMN_COUNT,
        "stage1_derived_count": len(STAGE1_DERIVED),
        "stage2_derived_columns": [
            "Status_Norm",
            "Is_Unit_Ready",
            "Is_Unit_Ready_For_Moving",
            "In_Turn_Execution",
            "Operational_State",
            "Prevention_Risk_Flag",
            "Attention_Badge",
        ],
        "all_headers": list(df.columns),
    }
    
    return df, manifest

# ============================================================
# EXECUTE
# ============================================================

df_out, manifest = run_intelligence_engine()
df
import pandas as pd
import numpy as np
from datetime import date

# ============================================================
# SLA CONFIGURATION
# ============================================================

INSPECTION_SLA_DAYS = 1       # Inspection must happen within 1 business day
TURN_SLA_DAYS = 10            # Unit must be ready within 10 business days
MOVE_IN_BUFFER_DAYS = 2       # Must be ready 2 days before move-in

# ============================================================
# ENGINE CONFIG
# ============================================================

BASE_COLUMN_COUNT = 25

EXPECTED_HEADERS = [
    "Unit", "Status", "Move_out", "Ready_Date", "DV", "Move_in", "DTBR", "N/V/M",
    "Insp", "Insp_status", "Paint", "Paint_status", "MR", "MR_Status",
    "HK", "HK_Status", "CC", "CC_status", "Assign", "W_D",
    "QC", "P", "B", "U", "Notes"
]

STAGE1_DERIVED = [
    "Note_Text",
    "Has_Note_Context",
    "Note_Category",
    "Has_Assignment",
    "Is_MoveIn_Present",
    "Is_Ready_Declared",
    "Is_Vacant",
    "Is_SMI",
    "Is_On_Notice",
    "Is_Allowed_Phase",
    "Is_QC_Done",
    "Aging_Business_Days",
    "Task_State",
    "Task_Completion_Ratio",
    "Table_Current_Task",
    "Table_Next_Task",
    "Is_Task_Stalled",
]

STAGE2_DERIVED = [
    "Status_Norm",
    "Is_Unit_Ready",
    "Is_Unit_Ready_For_Moving",
    "In_Turn_Execution",
    "Operational_State",
    "Prevention_Risk_Flag",
    "Attention_Badge",
]

ALL_INPUT_COLUMNS = EXPECTED_HEADERS + STAGE1_DERIVED + STAGE2_DERIVED

# ============================================================
# STAGE 3 ENGINE
# ============================================================

def run_sla_engine():
    """
    Reads Intelligence_Layer output from Stage 2 and adds SLA compliance flags
    """
    
    df = xl("Intelligence_Layer", header=None)
    today = date.today()
    
    # Handle empty table
    if df.empty or df.shape[0] == 0:
        empty_df = pd.DataFrame(columns=ALL_INPUT_COLUMNS + [
            "Days_To_MoveIn",
            "Inspection_SLA_Breach",
            "SLA_Breach",
            "SLA_MoveIn_Breach",
            "Plan_Breach",
        ])
        
        manifest = {
            "base_column_count": BASE_COLUMN_COUNT,
            "stage1_derived_count": len(STAGE1_DERIVED),
            "stage2_derived_count": len(STAGE2_DERIVED),
            "stage3_derived_count": 5,
            "all_headers": list(empty_df.columns),
        }
        return empty_df, manifest
    
    # Validate column count
    if df.shape[1] != len(ALL_INPUT_COLUMNS):
        raise ValueError(
            f"Column count mismatch: Intelligence_Layer has {df.shape[1]} columns, "
            f"but Stage 3 expects {len(ALL_INPUT_COLUMNS)} columns"
        )
    
    # Assign headers
    df.columns = ALL_INPUT_COLUMNS
    
    # Clean column names
    df.columns = (
        df.columns
        .astype(str)
        .str.replace("\u00a0", "", regex=False)
        .str.strip()
    )
    
    # ============================================================
    # STAGE 3 DERIVED COLUMNS (5 total)
    # ============================================================
    
    # 1. Days to Move-In (helper metric)
    def calc_days_to_move_in(move_in_date):
        if pd.isna(move_in_date):
            return np.nan
        try:
            move_in = pd.to_datetime(move_in_date)
            if pd.isna(move_in):
                return np.nan
            delta = (move_in.date() - today)
            return delta.days
        except:
            return np.nan
    
    df["Days_To_MoveIn"] = df["Move_in"].apply(calc_days_to_move_in)
    
    # 2. Inspection SLA Breach
    # "Inspection did not occur within 1 business day after move-out"
    df["Inspection_SLA_Breach"] = (
        df["Is_Vacant"] &
        (df["Insp_status"].astype(str).str.upper() != "DONE") &
        (df["Aging_Business_Days"] > INSPECTION_SLA_DAYS)
    )
    
    # 3. Global Turn SLA Breach
    # "Unit is still vacant and not ready after 10 business days"
    df["SLA_Breach"] = (
        df["Is_Vacant"] &
        (~df["Is_Unit_Ready"]) &
        (df["Aging_Business_Days"] > TURN_SLA_DAYS)
    )
    
    # 4. Move-In SLA Breach
    # "Move-in is scheduled and unit cannot meet it (< 2 days away, not ready)"
    df["SLA_MoveIn_Breach"] = (
        df["Is_MoveIn_Present"] &
        (~df["Is_Unit_Ready_For_Moving"]) &
        (df["Days_To_MoveIn"] <= MOVE_IN_BUFFER_DAYS) &
        (df["Days_To_MoveIn"] >= 0)  # Only if move-in is in the future or today
    )
    
    # 5. Plan Breach
    # "Declared Ready_Date has passed, but unit is not actually ready"
    def calc_plan_breach(row):
        if not row["Is_Ready_Declared"]:
            return False
        
        try:
            ready_date = pd.to_datetime(row["Ready_Date"])
            if pd.isna(ready_date):
                return False
            
            # Today is on or after the declared ready date
            if today >= ready_date.date():
                # But unit is NOT actually ready
                return not row["Is_Unit_Ready"]
            else:
                return False
        except:
            return False
    
    df["Plan_Breach"] = df.apply(calc_plan_breach, axis=1)
    
    # ============================================================
    # SORTING (maintain Stage 2 sort)
    # ============================================================
    df = df.sort_values(
        by="Aging_Business_Days",
        ascending=False,
        na_position="last"
    )
    
    # ============================================================
    # MANIFEST
    # ============================================================
    manifest = {
        "base_column_count": BASE_COLUMN_COUNT,
        "stage1_derived_count": len(STAGE1_DERIVED),
        "stage2_derived_count": len(STAGE2_DERIVED),
        "stage3_derived_columns": [
            "Days_To_MoveIn",
            "Inspection_SLA_Breach",
            "SLA_Breach",
            "SLA_MoveIn_Breach",
            "Plan_Breach",
        ],
        "sla_configuration": {
            "inspection_sla_days": INSPECTION_SLA_DAYS,
            "turn_sla_days": TURN_SLA_DAYS,
            "move_in_buffer_days": MOVE_IN_BUFFER_DAYS,
        },
        "all_headers": list(df.columns),
    }
    
    return df, manifest

# ============================================================
# EXECUTE
# ============================================================

df_out, manifest = run_sla_engine()
df_out