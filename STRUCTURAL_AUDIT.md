# Structural Audit — The DMRB (Read-Only)

**Date:** 2025-03-11  
**Scope:** Full Python repository. No code was modified.

---

## STEP 1 — Repository Scan Summary

- **Total `.py` files:** 91 (excluding virtualenv)
- **Total lines:** ~15,299 (application code; tests/scripts included in count)
- **Layers identified:** UI, Application, Services, Repository/Database, Domain, Utilities/Infrastructure, API, Scripts, Tests

---

## STEP 2 — File Table (Layer, Responsibility, Risk)

| File Path | Line Count | Layer | Primary Responsibility | Risk Level | Reason |
|-----------|------------|-------|-------------------------|------------|--------|
| **app.py** | **2671** | **UI** | Routing, session init, CSS, sidebar, DMRB Board, Flag Bridge, Risk Radar, Turnover Detail, Admin (dropdown/property/add unit/unit master import/import/export), AI Agent, all cached data helpers, date/format helpers | **CRITICAL** | Monolithic entrypoint; executed on every Streamlit rerun; 50+ local functions; contains full screen implementations |
| db/repository.py | 1137 | Repository/Database | CRUD for units, properties, phases, buildings, turnovers, tasks, notes, risks, SLA events, import batches, chat sessions/messages, enrichment cache, audit log | **CRITICAL** | 800+ lines; single module for all persistence; used by every service and app.py |
| services/import_service.py | 920 | Services | Import orchestration (move-outs, pending move-ins, available units, Pending FAS, DMRB), validation, checksums, idempotent apply | **HIGH** | 500+ lines; complex branching and report-type logic; pulled in via application.workflows on app load |
| services/export_service.py | 821 | Services | Excel/zip export (Final Report, DMRB Report, Dashboard Chart, Weekly Summary), board_query_service + excel_writer | **HIGH** | 500+ lines; openpyxl/zip; imported at app.py top level (backend block) |
| ui/mock_data_v2.py | 701 | Utilities/Infrastructure | Mock units/turnovers/tasks/notes, build_flat_row, get_dmrb_board_rows, get_flag_bridge_rows (prototype v2) | **MEDIUM** | 700+ lines; only used by tests (test_enrichment_harness); duplication of logic with board_query_service |
| services/turnover_service.py | 455 | Services | Update dates, manual ready status, reconcile tasks, SLA/risk reconciliation | **HIGH** | 500- line band; central to workflows; imported early in app chain |
| services/board_query_service.py | 391 | Services | Build flat rows for board/flag_bridge/risk_radar/detail from repository + domain.enrichment | **MEDIUM** | 300+ lines; single place for all board data shapes |
| ui/mock_data.py | 340 | Utilities/Infrastructure | Legacy mock data (no db/services) | **LOW** | Not on app.py path; test/dev only if used |
| tests/test_sla_effective_anchor.py | 330 | Tests | SLA effective anchor tests | **LOW** | Test file |
| tests/test_manual_override_protection.py | 485 | Tests | Manual override protection tests | **LOW** | Test file |
| domain/enrichment.py | 272 | Domain | Enrich flat rows (lifecycle, SLA, facts, risk score); pure logic | **LOW** | Well-scoped; domain-only deps |
| services/unit_master_import_service.py | 265 | Services | Unit master CSV import, resolve units | **LOW** | Single responsibility |
| services/sla_service.py | 259 | Services | SLA state, reconcile_sla_for_turnover, open/close events | **LOW** | Single responsibility |
| imports/validation/schema_validator.py | 254 | Utilities/Infrastructure | Validate import schema | **LOW** | Focused |
| services/excel_writer.py | 219 | Services | Excel workbook building, styles, table formatting | **LOW** | Used by export_service |
| services/ai_context_service.py | 222 | Services | AI context building for chat (counts, summaries) | **LOW** | Single responsibility |
| db/adapters/base_adapter.py | 120 | Repository/Database | Connection wrapper, engine detection, execute/inserted_id | **LOW** | Adapter abstraction |
| application/workflows/write_workflows.py | 101 | Application | Workflows: update status/dates, task status, create turnover, apply import row, clear manual override | **MEDIUM** | Imports db + 5 services; on app.py import path → pulls heavy tree |
| domain/lifecycle.py | 104 | Domain | Lifecycle phases, effective_move_out_date, derive_lifecycle_phase | **LOW** | Pure domain |
| application/commands/write_commands.py | 59 | Application | Command dataclasses (ApplyImportRow, ClearManualOverride, CreateTurnover, UpdateTaskStatus, UpdateTurnoverDates, UpdateTurnoverStatus) | **LOW** | Data only |
| api/chat_routes.py | 106 | API | Chat API routes (sessions, messages, suggestions) | **LOW** | API layer |
| domain/risk_engine.py | 97 | Domain | evaluate_risks (SLA, QC, WD, confirmation backlog, etc.) | **LOW** | Pure domain |
| imports/validation/file_validator.py | 97 | Utilities/Infrastructure | Validate import file | **LOW** | Focused |
| domain/risk_radar.py | 77 | Domain | score_enriched_turnover, risk level bands | **LOW** | Pure domain |
| ui/state/session.py | 73 | UI | init_session_state, load/save_dropdown_config | **LOW** | State only |
| ui/state/constants.py | 69 | UI | ASSIGNEE_OPTIONS, STATUS_OPTIONS, BRIDGE_MAP, CONFIRM/EXEC labels, TASK_DISPLAY_NAMES, etc. | **LOW** | Constants only |
| config/settings.py | 78 | Utilities/Infrastructure | Settings dataclass, get_settings(), Streamlit secrets + env | **MEDIUM** | config used by app + services; get_setting() uses st.secrets → Streamlit in config layer |
| services/note_service.py | 83 | Services | Notes CRUD | **LOW** | Single responsibility |
| services/risk_service.py | 105 | Services | evaluate_risks, reconcile_risks_for_turnover | **LOW** | Single responsibility |
| services/task_service.py | 176 | Services | Task CRUD, reconcile_after_task_change, update_task_fields | **LOW** | Single responsibility |
| services/chat_service.py | 146 | Services | Chat sessions/messages, AI context | **LOW** | Single responsibility |
| services/manual_availability_service.py | 91 | Services | add_manual_availability (create turnover path) | **LOW** | Single responsibility |
| db/connection.py | 49 | Repository/Database | get_connection, ensure_database_ready, resolve_database_config, adapter | **LOW** | Entry to DB |
| db/postgres_bootstrap.py | 51 | Repository/Database | ensure_postgres_ready, schema migration | **LOW** | Bootstrap only |
| ui/actions/db.py | 40 | UI | get_conn, db_write, get_db_path (wraps db.connection + st) | **LOW** | Thin wrapper |
| ui/components/sidebar.py | 36 | UI | render_navigation (radio, page state) | **LOW** | Single responsibility |
| ui/state/__init__.py | 35 | UI | Re-export state constants and session | **LOW** | Barrel |
| ui/screens/*.py (admin, ai_agent, board, flag_bridge, risk_radar, turnover_detail) | 5–8 each | UI | Thin wrapper: render_*(render_impl) → render_impl() | **LOW** | Delegation only; real logic in app.py |
| db/config.py | 15 | Repository/Database | resolve_database_config | **LOW** | Config resolution |
| db/errors.py | 10 | Repository/Database | DatabaseIntegrityError | **LOW** | Error type |
| domain/unit_identity.py | 70 | Domain | unit_identity_key, normalization | **LOW** | Pure domain |
| domain/sla_engine.py | 30 | Domain | SLA thresholds, evaluate_sla_state | **LOW** | Pure domain |
| api/main.py | 21 | API | FastAPI app, health, startup, chat router | **LOW** | API entry |
| db/adapters/postgres_adapter.py | 21 | Repository/Database | Postgres adapter | **LOW** | Adapter impl |
| db/adapters/base.py | 18 | Repository/Database | Base adapter interface | **LOW** | Abstract |
| application/commands/__init__.py | 17 | Application | Re-export commands | **LOW** | Barrel |
| application/workflows/__init__.py | 17 | Application | Re-export workflows | **LOW** | Barrel |
| db/adapters/__init__.py | 11 | Repository/Database | get_adapter | **LOW** | Barrel |
| config/__init__.py | 3 | Utilities/Infrastructure | Package init | **LOW** | — |
| ui/actions/__init__.py | 3 | UI | Package init | **LOW** | — |
| ui/components/__init__.py | 3 | UI | Package init | **LOW** | — |
| imports/__init__.py | 1 | Utilities/Infrastructure | Package init | **LOW** | — |
| imports/validation/__init__.py | 1 | Utilities/Infrastructure | Package init | **LOW** | — |
| ui/__init__.py | 1 | UI | Package init | **LOW** | — |
| tests/__init__.py, tests/helpers/__init__.py | 1 each | Tests | Package init | **LOW** | — |
| scripts/*.py | 61–208 | Scripts | Migrations, export/import, verify, analyze | **LOW** | Off main app path |
| tests/test_*.py (remaining) | 26–283 | Tests | Unit/integration tests | **LOW** | Test only |

---

## STEP 3 — Structural Issues

### 1. File size thresholds

- **800+ lines (critical):**
  - **app.py** (2671)
  - **db/repository.py** (1137)
- **500+ lines (high risk):**
  - **services/import_service.py** (920)
  - **services/export_service.py** (821)
  - **services/turnover_service.py** (455)
- **300+ lines (warning):**
  - **services/board_query_service.py** (391)
  - **ui/mock_data_v2.py** (701) — test-only but large
  - **domain/enrichment.py** (272)

### 2. Multiple responsibilities (single file)

- **app.py:** Routing, session init, global CSS, dropdown config, DB bootstrap, cache helpers, sidebar “Top Flags”, DMRB Board UI, Flag Bridge UI, Risk Radar UI, Turnover Detail UI, Dropdown Manager, Property Structure, Add Availability, Unit Master Import, Import (with _run_import_for_report), Exports, Admin orchestrator, AI Agent UI, chat API helper. Effectively 15+ distinct responsibilities.
- **db/repository.py:** Units, properties, phases, buildings, task templates, turnovers, tasks, notes, risks, SLA events, import batches/rows, audit log, chat sessions/messages, enrichment cache. Many distinct aggregates in one module.

### 3. Runtime-heavy imports in UI entrypoint

- **app.py** top-level imports (before any `if page == ...`):
  - `application.workflows` → **write_workflows** → imports **db.repository**, **import_service**, **manual_availability_service**, **task_service**, **turnover_service**. So on every run we load repository (1137 lines) and these services (and their transitive deps: domain, imports.validation, sla_service, etc.).
  - **config.settings** → `get_settings()`; **config/settings.py** uses `streamlit as st` in `get_setting()` (secrets), so Streamlit is a dependency of config.
  - **ui.actions.db** → **db.connection** → **db.adapters**, **db.config**, **db.postgres_bootstrap**.
  - **ui.state** → constants + session (light).
- Backend try block (lines 62–77) then imports again: **db.connection**, **db.repository**, **board_query_service**, **export_service**, **import_service**, **manual_availability_service**, **note_service**, **task_service**, **turnover_service**, **unit_master_import_service**. So **export_service** (and thus **excel_writer** / openpyxl), **import_service** (pandas, schema_validator, file_validator, sla_service, domain), and the rest load on every rerun even when the user is only viewing one screen.

### 4. Cross-layer dependency violations

- **domain → services:** Not present. Domain only uses domain (e.g. enrichment → lifecycle, risk_radar). Good.
- **repository → workflows:** Not present. Repository has no application imports. Good.
- **UI → domain internals:** app.py does not import domain directly; it goes through services/board_query_service and workflows. Acceptable.
- **Config → UI:** **config/settings.py** imports **streamlit** for secrets. So Infrastructure depends on UI framework; ideally config would be UI-agnostic and secrets would be injected or read from env only.

### 5. app.py dependency tree (modules that load at parse/run time)

- **Direct:** application.commands, application.workflows, config.settings, ui.actions.db, ui.components.sidebar, ui.screens.*, ui.state, pandas, streamlit.
- **Via application.workflows:** db.repository, import_service, manual_availability_service, task_service, turnover_service.
- **Via backend try block:** db.connection, db.repository, board_query_service, export_service, import_service, manual_availability_service, note_service, task_service, turnover_service, unit_master_import_service.
- **Transitive from services:** domain.lifecycle, domain.unit_identity, domain.risk_engine, domain.enrichment, domain.risk_radar, domain.sla_engine, imports.validation.*, sla_service, excel_writer (openpyxl), db.connection, db.adapters, postgres_bootstrap.

So the entire backend and most of the domain/import stack load on every Streamlit rerun, regardless of the current page.

---

## STEP 4 — Performance Risks (Streamlit Reruns)

### app.py

- **Why it hurts:** The whole file runs on every rerun. That includes: all top-level imports (and thus the dependency tree above), `st.set_page_config`, large inline CSS block, `_init_session_state()`, `ensure_database_ready()` when bootstrap is not skipped, optional task backfill, `render_navigation()`, sidebar “Top Flags” (which calls `_cached_get_flag_bridge_rows` and sorts/filters rows), then the main dispatch that calls one of the big render functions (e.g. `render_dmrb_board`, `render_admin`). So even for a simple navigation click, we re-execute thousands of lines and re-load every imported module.

### Sidebar / router

- **ui/components/sidebar.py:** Light (render_navigation). But **app.py** implements the actual “Top Flags” sidebar block (lines ~418–611): it calls `_cached_get_flag_bridge_rows`, builds phase map, sorts rows, and renders expanders/buttons. That logic runs on every rerun and depends on `board_query_service` and `db_repository` already being imported.

### UI screen modules

- **ui/screens/*.py** are thin (call `render_impl()`). They do not add meaningful load. The real cost is that the **implementations** of those screens (e.g. `render_dmrb_board`, `render_admin`, `render_detail`) live in **app.py**, so any interaction that triggers a rerun re-executes the whole app and re-runs the selected screen’s full implementation.

### Modules imported at the top of app.py

- **application.workflows:** Pulls in **db.repository** and five services (import, manual_availability, task, turnover, and via them sla_service, domain, validation). So heavy persistence and business logic load on every run.
- **config.settings:** Uses Streamlit in `get_setting()`; small but ties config to Streamlit.
- **ui.actions.db:** Imports **db.connection** → adapters, config, postgres_bootstrap. So DB layer is loaded even when only rendering static content.
- **Backend block:** Explicitly loads **repository**, **board_query_service**, **export_service**, **import_service**, and the rest. **export_service** pulls in **openpyxl** and **excel_writer**; **import_service** pulls in **pandas** and validation. So heavy I/O and third-party libs are loaded on every rerun.

**Summary:** Rerun cost is dominated by (1) re-executing the whole of app.py, (2) loading the full import tree (repository, all listed services, domain, validation, openpyxl, pandas), and (3) running sidebar “Top Flags” and the chosen screen’s full implementation every time.

---

## STEP 5 — Refactor Recommendations

### app.py (2671 lines) — CRITICAL

**Suggested splits:**

| New path | Responsibility | Est. lines |
|----------|----------------|------------|
| **ui/router.py** | Page dispatch only: read `st.session_state.page`, call the appropriate screen renderer. No sidebar, no cache helpers. | ~30 |
| **ui/screens/dmrb_board.py** | `render_dmrb_board`: filters, metrics, tabbed tables (Unit Info, Unit Tasks), data_editor handlers, navigation to detail. Use shared helpers from ui/helpers. | ~400 |
| **ui/screens/flag_bridge.py** | `render_flag_bridge`: filters, table, breach columns, navigation to detail. | ~120 |
| **ui/screens/risk_radar.py** | `render_risk_radar`: filters, risk table. | ~80 |
| **ui/screens/turnover_detail.py** | `render_detail`: full turnover detail form, task/date/status edits, notes. | ~580 |
| **ui/screens/admin.py** | `render_admin`: tab routing to dropdown manager, property structure, add availability, unit master import, import, exports. Each sub-screen can be a function in the same file or further split. | ~400 |
| **ui/screens/unit_import.py** | `render_unit_master_import` (if extracted from admin). | ~80 |
| **ui/screens/import_export.py** | `render_import`, `render_exports`, `_run_import_for_report` (or split import vs export). | ~250 |
| **ui/screens/ai_agent.py** | `render_dmrb_ai_agent`: chat UI, sessions, suggestions. | ~90 |
| **ui/helpers/dates.py** | `_parse_date`, `_to_date`, `_dates_equal`, `_fmt_date`, `_parse_date_for_input`, `_iso_to_date`. | ~60 |
| **ui/helpers/formatting.py** | `_normalize_label`, `_normalize_enum`, `_safe_index`, `_operational_state_to_badge`, `_get_attention_badge`. | ~40 |
| **ui/helpers/dropdown_config.py** | `_dropdown_config_path`, `_load_dropdown_config`, `_save_dropdown_config` (or keep in state). | ~20 |
| **ui/data/cache.py** | All `_cached_*` and `_get_conn`, `_db_available`, `_db_write`, `_db_cache_identity`, `_get_active_property`, `_sync_active_property`, `_set_active_property`, `_render_active_property_banner`. | ~250 |
| **ui/components/sidebar_flags.py** | “Top Flags” sidebar: phase map, `_cached_get_flag_bridge_rows`, sort keys, expanders, unit buttons. | ~120 |
| **app.py** (slim) | Imports only: router, init_session_state, set_page_config, global CSS, bootstrap + backfill, then call `render_navigation` and `ui.router.render_current_page()`. | ~80–120 |

**Performance:** After split, only the router and the one active screen module need to run for a given page. Lazy-loading screen modules (e.g. `importlib.import_module` when `page == "dmrb_board"`) would avoid loading unused screens and their dependencies on each rerun, reducing parse and import cost.

---

### db/repository.py (1137 lines) — CRITICAL

**Suggested splits:**

| New path | Responsibility | Est. lines |
|----------|----------------|------------|
| **db/repository/units.py** | get_unit_by_id, list_unit_master_import_units, get_unit_by_norm, get_unit_by_identity_key, get_unit_by_building_and_number, resolve_unit, get_units_by_ids, insert_unit, update_unit_fields. | ~180 |
| **db/repository/properties.py** | list_properties, insert_property, list_phases, get_first_phase_for_property, get_phase, resolve_phase, list_buildings, get_building, resolve_building, list_units. | ~120 |
| **db/repository/task_templates.py** | get_active_task_templates, get_active_task_templates_by_phase, get_task_template_dependencies, insert_task_template, ensure_default_task_templates, insert_task_dependency. | ~180 |
| **db/repository/turnovers.py** | list_open_turnovers_by_property, list_open_turnovers, get_turnover_by_id, get_open_turnover_by_unit, insert_turnover, update_turnover_fields, invalidate_turnover_enrichment_cache, get_enrichment_cache_for_turnover_ids, upsert_turnover_enrichment_cache. | ~220 |
| **db/repository/tasks.py** | get_tasks_by_turnover, get_tasks_for_turnover_ids, insert_task, update_task_fields. | ~80 |
| **db/repository/notes.py** | get_note_by_id, get_notes_by_turnover, insert_note, update_note_resolved, get_notes_for_turnover_ids. | ~50 |
| **db/repository/risks.py** | get_active_risks_by_turnover, upsert_risk, _ensure_confirmation_invariant, resolve_risk. | ~90 |
| **db/repository/sla_events.py** | get_open_sla_event, insert_sla_event, close_sla_event, update_sla_event_current_anchor. | ~70 |
| **db/repository/import_batches.py** | insert_import_batch, get_import_batch_by_checksum, insert_import_row, get_import_rows_by_batch, insert_audit_log. | ~60 |
| **db/repository/chat.py** | get_chat_sessions, get_chat_session, insert_chat_session, update_chat_session_fields, get_chat_messages, insert_chat_message, delete_chat_session. | ~80 |
| **db/repository/helpers.py** | _row_to_dict, _rows_to_dicts, _inserted_id, TURNOVER_UPDATE_COLS, TASK_UPDATE_COLS, UNIT_UPDATE_COLS. | ~40 |
| **db/repository/__init__.py** | Re-export all public functions so `from db import repository` or `from db.repository import ...` still works. | ~50 |

**Performance:** Smaller, focused modules improve maintainability and can be lazy-loaded by services that only need a subset (e.g. chat routes only load repository.chat). App startup can stay the same until app.py is refactored to lazy-load services per screen.

---

### services/import_service.py (920 lines) — HIGH

**Suggested splits:**

| New path | Responsibility | Est. lines |
|----------|----------------|------------|
| **services/import_service/constants.py** | Report type constants, outcome constants, VALID_PHASES. | ~20 |
| **services/import_service/validation.py** | _validation_status_from_outcome, _sha256_file, _normalize_date_str, _normalize_status, validate_import_file/schema usage. | ~80 |
| **services/import_service/move_outs.py** | Move-outs report parsing and apply logic. | ~200 |
| **services/import_service/pending_move_ins.py** | Pending move-ins report logic. | ~150 |
| **services/import_service/available_units.py** | Available units report logic. | ~150 |
| **services/import_service/pending_fas.py** | Pending FAS report logic. | ~120 |
| **services/import_service/dmrb.py** | DMRB report-specific logic. | ~120 |
| **services/import_service/orchestrator.py** | Public API: run_import, apply flow, batch creation, delegation to report-specific modules. | ~80 |
| **services/import_service/__init__.py** | Re-export public API. | ~10 |

**Performance:** Import orchestrator can stay the only entry point; report-type modules can be loaded on demand when that report type is used (if wired that way), reducing initial load for users who only use one report type.

---

### services/export_service.py (821 lines) — HIGH

**Suggested splits:**

| New path | Responsibility | Est. lines |
|----------|----------------|------------|
| **services/export_service/final_report.py** | Final Report Excel build. | ~200 |
| **services/export_service/dmrb_report.py** | DMRB Report Excel build. | ~180 |
| **services/export_service/dashboard_chart.py** | Dashboard chart generation (if present). | ~80 |
| **services/export_service/weekly_summary.py** | Weekly summary text. | ~80 |
| **services/export_service/zip_bundle.py** | Zip assembly, public export entry point. | ~150 |
| **services/export_service/__init__.py** | Re-export; optionally lazy load submodules. | ~20 |

**Performance:** Only the export path actually used (e.g. “Export ZIP”) could load the corresponding submodule, reducing openpyxl and heavy processing impact when user never exports.

---

### services/turnover_service.py (455 lines) — HIGH

**Suggested splits:**

| New path | Responsibility | Est. lines |
|----------|----------------|------------|
| **services/turnover_service/dates.py** | update_turnover_dates, date validation. | ~80 |
| **services/turnover_service/ready_status.py** | set_manual_ready_status, confirmation invariant. | ~120 |
| **services/turnover_service/reconcile.py** | reconcile_missing_tasks, reconcile_after_task_change (or keep in task_service), call risk/SLA reconciliation. | ~100 |
| **services/turnover_service/__init__.py** | Re-export public API. | ~20 |

**Performance:** Slight improvement from smaller modules; larger gain comes from not loading turnover_service (and thus risk_service, sla_service) until a screen that needs it is loaded (lazy screen imports in app).

---

## STEP 6 — Final Architecture Summary

### 1. Current architecture map

```
                    ┌─────────────┐
                    │   app.py    │  (2671 lines; UI + routing + all screens + cache + sidebar flags)
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌──────────────┐  ┌─────────────┐
    │ ui.state   │  │ ui.actions   │  │ application │
    │ ui.screens │  │ ui.components│  │ .workflows  │
    └────────────┘  └──────┬───────┘  └──────┬──────┘
                           │                 │
                           ▼                 ▼
                    ┌────────────┐    ┌─────────────┐
                    │ db.        │    │ services   │
                    │ connection │    │ (all 10+)  │
                    └──────┬─────┘    └──────┬─────┘
                           │                 │
                           ▼                 ▼
                    ┌────────────┐    ┌─────────────┐
                    │ db.        │◄───┤ domain      │
                    │ repository │    │ imports.*   │
                    └────────────┘    └─────────────┘
```

- **Single entrypoint:** app.py.
- **Thick UI:** All screen logic and sidebar “Top Flags” in app.py; ui/screens are thin wrappers.
- **Single repository:** db/repository.py holds all persistence.
- **Workflows on import path:** application.workflows imports db + 5 services, so heavy tree loads with app.
- **Config:** config/settings uses Streamlit (secrets).

### 2. Recommended architecture map

```
  ┌──────────────────────────────────────────────────────────────────┐
  │  app.py (slim): set_page_config, CSS, init_session_state,         │
  │  ensure_database_ready, render_navigation, router.render_current   │
  └──────────────────────────────────────────────────────────────────┘
                                    │
  ┌─────────────────────────────────┼─────────────────────────────────┐
  │  ui/router.py                    │  ui/components/sidebar_flags.py  │
  │  (dispatch by page)              │  (Top Flags; uses data/cache)    │
  └─────────────────────────────────┼─────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
  ui/screens/                ui/data/cache.py            ui/helpers/
  dmrb_board.py              (cached_*, conn,             dates.py
  flag_bridge.py              active_property)            formatting.py
  risk_radar.py                                              dropdown_config.py
  turnover_detail.py
  admin.py (or admin/*.py)
  ai_agent.py
  import_export.py
         │
         │  (lazy import screen module when page selected)
         ▼
  application.workflows  (used only when screen needs write)
         │
         ▼
  services (lazy per feature: board_query for board/flag_bridge/detail; export only for export; etc.)
         │
         ▼
  db/repository/* (split into units, properties, turnovers, tasks, notes, risks, sla_events, import_batches, chat)
         │
         ▼
  domain (unchanged; no dependency on services or UI)
```

- **Slim app.py:** Only bootstrap, navigation, and router.
- **Screen modules:** One file (or small set) per screen; loaded on demand when that page is selected.
- **Shared UI:** ui/helpers (dates, formatting, dropdown_config), ui/data/cache (all cached data + conn/active property).
- **Repository:** Split into db/repository/* by aggregate; same public API via __init__.py.
- **Config:** Prefer making config/settings independent of Streamlit; pass secrets via env or inject where needed.

### 3. Top 10 files to refactor first

| Order | File | Lines | Priority reason |
|-------|------|-------|-----------------|
| 1 | **app.py** | 2671 | Single biggest cost on every rerun; contains all screens and sidebar logic. |
| 2 | **db/repository.py** | 1137 | Single persistence module; blocks smaller, testable units and optional lazy load. |
| 3 | **services/import_service.py** | 920 | Heavy and on app import path via workflows; split by report type. |
| 4 | **services/export_service.py** | 821 | Heavy (openpyxl); on app import path; split by report/artifact type. |
| 5 | **application/workflows/write_workflows.py** | 101 | Pulls db + 5 services at import; consider lazy use from screens or lighter command adapter. |
| 6 | **services/turnover_service.py** | 455 | Central to workflows; split by concern (dates, ready status, reconcile). |
| 7 | **services/board_query_service.py** | 391 | Single source for all board shapes; consider split by view (board vs flag_bridge vs risk_radar vs detail). |
| 8 | **ui/mock_data_v2.py** | 701 | Test-only; align with board_query_service and domain to avoid duplication. |
| 9 | **config/settings.py** | 78 | Remove Streamlit dependency from config for clearer layering. |
| 10 | **domain/enrichment.py** | 272 | Already focused; optional split (e.g. facts vs SLA vs risk) only if needed for clarity. |

### 4. Expected UI performance improvements after refactor

- **Lazy screen loading:** Load only the current page’s screen module and its dependencies (e.g. board_query_service only when on Board/Flag Bridge/Detail). Avoid loading import_service, export_service, unit_master_import_service, and their heavy deps (pandas, openpyxl, validation) until the user opens Admin/Import/Export. **Estimated:** 30–50% reduction in time to first paint after a rerun (depending on which page is shown).
- **Slim app.py:** Less code to execute on every rerun (no inline screen implementations, no large blocks of helpers). **Estimated:** 10–20% reduction in rerun execution time.
- **Sidebar “Top Flags”:** If moved to a dedicated module and fed by a single cached call, sidebar logic is clearer; further gains if “Top Flags” is behind an expander or only computed when sidebar is expanded. **Estimated:** Small but clearer separation.
- **Repository split:** No direct rerun speedup; improves maintainability and allows future per-feature lazy load of repository submodules if needed.
- **Config without Streamlit:** Removes one UI dependency from config; enables reuse and testing of config outside Streamlit.

**Overall:** The largest gain is from **lazy-loading screen modules and their service dependencies**. That, plus a **slim app.py** and **split repository/services**, should give a noticeable improvement in Streamlit rerun responsiveness and a cleaner structure for future changes.

---

## Additional notes

- **db/repository.py** uses `sqlite3.Connection` in type hints in many places but does not import `sqlite3` at the top of the file. This may be a bug or rely on a stub; worth fixing in a separate change.
- **ui/screens** are currently thin wrappers; the real screen logic lives in app.py. Moving that logic into the corresponding ui/screens/*.py (or ui/screens/admin/*.py) completes the “screen split” and keeps app.py as a thin entrypoint.

---

*End of structural audit. No code was modified.*
