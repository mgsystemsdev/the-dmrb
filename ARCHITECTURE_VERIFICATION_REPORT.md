# Architecture Verification Report

**Repository:** the-dmrb  
**Scope:** Full architectural audit (analysis only, no code changes)  
**Standards:** Clean Architecture (dependency rule), Layered Architecture, Modular Monolith, Streamlit runtime best practices, separation of concerns, module responsibility discipline.

---

## 1. Architecture Overview (Text Diagram)

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                      app.py (entrypoint)                 │
                    │  imports: ui.components.sidebar, sidebar_flags,           │
                    │           ui.data.backend, ui.router, ui.state            │
                    └───────────────────────────┬─────────────────────────────┘
                                                │
        ┌───────────────────────────────────────┼───────────────────────────────────────┐
        │                                       ▼                                         │
        │  ┌─────────────────────────────────────────────────────────────────────────┐   │
        │  │  UI LAYER                                                                │   │
        │  │  ui/router.py (lazy screen via importlib)                                │   │
        │  │  ui/components/sidebar.py, sidebar_flags.py                              │   │
        │  │  ui/screens/* (board, admin, turnover_detail, flag_bridge, risk_radar,   │   │
        │  │               ai_agent, unit_import, exports, report_operations)          │   │
        │  │  ui/data/backend.py (facade: loads db + services; sets globals)           │   │
        │  │  ui/data/cache.py (st.cache_data + service-based list/board/flag/detail)  │   │
        │  │  ui/state/*, ui/actions/db.py, ui/helpers/*                              │   │
        │  └───────────────────────────────────┬─────────────────────────────────────┘   │
        │                                      │                                           │
        │  UI → Services (via backend/cache): property_service, unit_service,             │
        │       board_query_service, import_service, etc.                                 │
        │  UI holds db_repository only as backend-availability check (no repo calls).    │
        │  Violation: config/settings → streamlit (st.secrets).                           │
        └──────────────────────────────────────┼─────────────────────────────────────────┘
                                               ▼
        ┌────────────────────────────────────────────────────────────────────────────────┐
        │  APPLICATION LAYER (commands + workflows)                                       │
        │  application/commands/write_commands.py (dataclasses only)                      │
        │  application/workflows/write_workflows.py (orchestrates services only;          │
        │      clear_manual_override_workflow → turnover_service)                         │
        └───────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
        ┌────────────────────────────────────────────────────────────────────────────────┐
        │  SERVICE LAYER                                                                  │
        │  services/turnover_service, task_service, board_query_service, export_service, │
        │  import_service, sla_service, note_service, risk_service, chat_service,        │
        │  ai_context_service, manual_availability_service, unit_master_import_service,  │
        │  property_service, unit_service, report_operations_service                      │
        │  services/imports/* (orchestrator, move_ins, move_outs, dmrb, etc.)            │
        │  services/excel_writer                                                          │
        └───────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
        ┌────────────────────────────────────────────────────────────────────────────────┐
        │  DOMAIN LAYER                                                                  │
        │  domain/lifecycle, domain/risk_radar, domain/enrichment, domain/unit_identity,│
        │  domain/sla_engine, domain/risk_engine                                         │
        │  Pure logic; no DB/UI imports. Used by services and board_query_service.       │
        └────────────────────────────────────────────────────────────────────────────────┘
                                            ▲
        ┌───────────────────────────────────┴────────────────────────────────────────────┐
        │  REPOSITORY LAYER                                                               │
        │  db/repository/* (turnovers, units, tasks, properties, risks, sla, notes,       │
        │  chat, imports, fas_tracker_notes, _helpers)                                    │
        │  turnovers.py → risks._ensure_confirmation_invariant (repo-repo + rule in repo) │
        │  risks.py → imports.insert_audit_log; tasks→turnovers; units→properties        │
        └───────────────────────────────────┬────────────────────────────────────────────┘
                                              │
                                              ▼
        ┌────────────────────────────────────────────────────────────────────────────────┐
        │  INFRASTRUCTURE LAYER                                                           │
        │  db/connection.py, db/config.py, db/adapters/*, db/postgres_bootstrap.py        │
        │  db/errors.py                                                                  │
        │  config/settings.py (imports streamlit for st.secrets — violation)              │
        │  imports/validation/* (file_validator, schema_validator)                        │
        └────────────────────────────────────────────────────────────────────────────────┘
```

**Intended dependency direction:** UI → Application → Services → Repository → Infrastructure; Domain has no outward dependencies.  
**Reality:** UI and Application go through services for data and writes. UI keeps a reference to `db_repository` only for backend-availability checks (no repository method calls). Config depends on Streamlit. Repository has cross-module calls and one business rule (`_ensure_confirmation_invariant`) inside the repository layer.

---

## 2. Module Classification Table

*Production Python modules only (excluding `tests/`, `scripts/`, and one-off `test_supabase_connection.py`). Line counts from current workspace.*

| Module path | Line count | Layer | Primary responsibility |
|-------------|------------|--------|------------------------|
| app.py | 94 | UI | Entrypoint; page config, bootstrap, sidebar, router |
| ui/__init__.py | 1 | UI | Package marker |
| ui/router.py | 23 | UI | Resolve page, lazy-import screen module, call render() |
| ui/components/__init__.py | 3 | UI | Package marker |
| ui/components/sidebar.py | 37 | UI | Navigation radio and page state |
| ui/components/sidebar_flags.py | 110 | UI | Top flags widget; uses backend (availability) and cache |
| ui/screens/__init__.py | 12 | UI | Package marker |
| ui/screens/board.py | 555 | UI | DMRB board: filters, metrics, tabbed unit/task views |
| ui/screens/flag_bridge.py | 229 | UI | Flag bridge view; uses cache |
| ui/screens/risk_radar.py | 136 | UI | Risk radar view; uses cache |
| ui/screens/ai_agent.py | 176 | UI | AI agent chat UI |
| ui/screens/admin.py | 783 | UI | Admin tabs: Property structure, Add Unit, Import, Unit Master, Exports, Dropdowns; uses services |
| ui/screens/turnover_detail.py | 622 | UI | Turnover detail view |
| ui/screens/unit_import.py | 114 | UI | Unit master import screen |
| ui/screens/exports.py | 87 | UI | Exports screen |
| ui/screens/report_operations.py | 205 | UI | Report Operations: Missing Move-Out queue, FAS Tracker; uses report_operations_service |
| ui/helpers/__init__.py | 33 | UI | Re-exports dates, formatting, dropdowns |
| ui/helpers/formatting.py | 48 | UI | Badges and display formatting |
| ui/helpers/dates.py | 70 | UI | Date parsing/formatting for UI |
| ui/helpers/dropdowns.py | 23 | UI | Dropdown config load/save |
| ui/state/__init__.py | 35 | UI | Session and constants re-exports |
| ui/state/constants.py | 69 | UI | Options, labels, task types (no Streamlit) |
| ui/state/session.py | 73 | UI | init_session_state, dropdown config (uses Streamlit) |
| ui/actions/__init__.py | 3 | UI | Package marker |
| ui/actions/db.py | 40 | UI | get_conn, db_write, get_db_path; calls db.connection, config |
| ui/data/__init__.py | 71 | UI | Re-exports backend/cache identity |
| ui/data/backend.py | 68 | UI | Backend availability; try/except import of db + services |
| ui/data/cache.py | 252 | UI | st.cache_data wrappers; list/board/flag/detail via services |
| ui/mock_data.py | 340 | UI | Mock data for UI (dev/demos) |
| ui/mock_data_v2.py | 701 | UI | Mock data v2 (harness/tests also use) |
| application/commands/__init__.py | 17 | Application | Re-export write commands |
| application/commands/write_commands.py | 59 | Application | Command dataclasses (CreateTurnover, ApplyImportRow, etc.) |
| application/workflows/__init__.py | 17 | Application | Re-export workflows |
| application/workflows/write_workflows.py | 83 | Application | Workflows calling services only |
| services/import_service.py | 30 | Service | Facade to imports.orchestrator + get_import_rows_by_batch |
| services/property_service.py | 28 | Service | Property/phase/building CRUD wrapper around repository |
| services/unit_service.py | 12 | Service | Unit list wrappers around repository |
| services/report_operations_service.py | 112 | Service | Missing move-out queue, FAS tracker rows |
| services/turnover_service.py | 464 | Service | Turnover CRUD, reconciliation, lifecycle |
| services/task_service.py | 176 | Service | Task updates, reconcile_after_task_change |
| services/board_query_service.py | 391 | Service | Build board/flag/detail rows; repository + domain.enrichment |
| services/export_service.py | 821 | Service | Export reports (Excel, zip); repository + board_query_service |
| services/excel_writer.py | 219 | Service | Excel writing helpers |
| services/sla_service.py | 259 | Service | SLA reconciliation; repository + domain.sla_engine |
| services/note_service.py | 83 | Service | Notes CRUD |
| services/risk_service.py | 105 | Service | Risk reconciliation |
| services/chat_service.py | 146 | Service | Chat sessions/messages |
| services/ai_context_service.py | 222 | Service | AI context building |
| services/manual_availability_service.py | 91 | Service | Manual add unit / turnover creation |
| services/unit_master_import_service.py | 265 | Service | Unit master CSV import; repository + domain.unit_identity |
| services/imports/__init__.py | 21 | Service | Package marker |
| services/imports/orchestrator.py | 144 | Service | Import file orchestration; db + repository + validation |
| services/imports/common.py | 167 | Service | Shared import helpers; repository + domain.unit_identity |
| services/imports/constants.py | 17 | Service | Constants |
| services/imports/dmrb.py | 150 | Service | DMRB report parsing/apply |
| services/imports/move_ins.py | 131 | Service | Pending move-ins apply |
| services/imports/move_outs.py | 211 | Service | Move-outs apply |
| services/imports/pending_fas.py | 148 | Service | Pending FAS apply |
| services/imports/available_units.py | 179 | Service | Available units apply |
| services/imports/tasks.py | 71 | Service | Task instantiation for turnover |
| services/imports/validation.py | 43 | Service | Validation helpers |
| db/repository/__init__.py | 160 | Repository | Re-export all repository functions |
| db/repository/_helpers.py | 54 | Repository | _row_to_dict, _inserted_id, UPDATE_COLS |
| db/repository/chat.py | 79 | Repository | Chat sessions/messages CRUD |
| db/repository/imports.py | 110 | Repository | Import batch/row, audit log |
| db/repository/notes.py | 60 | Repository | Notes CRUD |
| db/repository/properties.py | 139 | Repository | Property/phase/building CRUD |
| db/repository/risks.py | 96 | Repository | Risk flags; _ensure_confirmation_invariant |
| db/repository/sla.py | 62 | Repository | SLA events CRUD |
| db/repository/tasks.py | 238 | Repository | Tasks and templates CRUD |
| db/repository/turnovers.py | 204 | Repository | Turnovers and enrichment cache; uses risks._ensure_confirmation_invariant |
| db/repository/units.py | 194 | Repository | Units CRUD; uses properties |
| db/repository/fas_tracker_notes.py | 27 | Repository | FAS tracker notes CRUD |
| domain/lifecycle.py | 104 | Domain | effective_move_out_date, derive_lifecycle_phase, constants |
| domain/risk_radar.py | 77 | Domain | score_enriched_turnover (pure) |
| domain/enrichment.py | 272 | Domain | Enrichment computation; lifecycle + risk_radar |
| domain/unit_identity.py | 70 | Domain | normalize_unit_code, parse_unit_parts, compose_identity_key |
| domain/sla_engine.py | 30 | Domain | evaluate_sla_state, SLA_THRESHOLD_DAYS |
| domain/risk_engine.py | 97 | Domain | Risk logic (pure) |
| db/connection.py | 49 | Infrastructure | get_connection, ensure_database_ready; uses adapters |
| db/config.py | 15 | Infrastructure | resolve_database_config; uses config.settings |
| db/errors.py | 10 | Infrastructure | DB exception types |
| db/postgres_bootstrap.py | 51 | Infrastructure | ensure_postgres_ready |
| db/adapters/__init__.py | 11 | Infrastructure | Adapter exports |
| db/adapters/base_adapter.py | 120 | Infrastructure | BaseAdapter, ConnectionWrapper, DatabaseConfig |
| db/adapters/base.py | 18 | Infrastructure | Legacy base (if used) |
| db/adapters/postgres_adapter.py | 21 | Infrastructure | Postgres adapter |
| config/settings.py | 78 | Infrastructure | get_settings(); uses streamlit for secrets |
| config/__init__.py | 3 | Infrastructure | Package marker |
| imports/validation/file_validator.py | 97 | Infrastructure | File validation |
| imports/validation/schema_validator.py | 254 | Infrastructure | Schema validation |
| imports/validation/__init__.py | 1 | Infrastructure | Package marker |
| imports/__init__.py | 1 | Infrastructure | Package marker |
| api/main.py | 21 | API | FastAPI app; chat router |
| api/__init__.py | 3 | API | Package marker |
| api/chat_routes.py | 106 | API | Chat HTTP routes; db + services |

---

## 3. Dependency Rule Analysis

### 3.1 Violations

| Violation | Location | Why it is problematic |
|-----------|----------|------------------------|
| **Config → UI (Streamlit)** | config/settings.py | `get_setting()` uses `st.secrets`. Infrastructure/config should not depend on the UI framework; makes settings unusable in non-Streamlit contexts (e.g. API, scripts, tests) without st. |
| **Repository → Repository (cross-module)** | db/repository/turnovers.py | Imports `_ensure_confirmation_invariant` from db/repository/risks. Cross-repository dependency; the invariant is a business rule (legal_confirmation vs confirmed_move_out_date) that could live in domain or a small service. |
| **Repository → Repository** | db/repository/risks.py | Imports `insert_audit_log` from db/repository/imports. Couples risk persistence to audit logging in another repo module. |
| **Repository → Repository** | db/repository/tasks.py | Imports `invalidate_turnover_enrichment_cache` from db/repository/turnovers. |
| **Repository → Repository** | db/repository/units.py | Imports from db/repository/properties (resolve_phase, resolve_building, etc.). Entity-level coupling. |
| **UI reference to repository symbol** | ui/screens/board.py, flag_bridge.py, risk_radar.py, unit_import.py, sidebar_flags.py | Use `db_repository` from backend only as a **boolean availability check** (`if db_repository and ...`). No repository methods are called. This is a mild coupling (UI knows the name of the repository layer); could be replaced by `BACKEND_AVAILABLE` or a dedicated flag. |

### 3.2 Correct Directions Observed

- **UI → Services for data and writes:** cache.py uses property_service_mod, unit_service_mod, board_query_service for list/board/flag/detail. admin.py uses property_service_mod (insert_property, resolve_phase, resolve_building), import_service_mod.get_import_rows_by_batch. report_operations.py uses report_operations_service. No UI module calls repository methods directly.
- **Application → Services:** write_workflows.py calls turnover_service, task_service, manual_availability_service, import_service only. clear_manual_override_workflow uses turnover_service.clear_manual_override (no direct repository).
- **Services → Repository:** All service modules correctly use `db.repository` for data access.
- **Services → Domain:** turnover_service, sla_service, board_query_service, enrichment, imports/common, unit_master_import_service use domain (lifecycle, sla_engine, risk_radar, enrichment, unit_identity) without domain depending back.
- **Domain:** lifecycle, risk_radar, enrichment, unit_identity, sla_engine, risk_engine have no imports from db, services, or ui.
- **Router lazy loading:** ui/router.py uses `importlib.import_module(f"ui.screens.{module_name}")` so only the active screen module is loaded on each run.

---

## 4. File Size and Responsibility Analysis

### 4.1 Modules Exceeding 800 Lines (Architectural Risk)

| File | Lines | Responsibilities | Assessment |
|------|-------|------------------|------------|
| services/export_service.py | 821 | Export orchestration: Final Report, DMRB Report, Dashboard Chart, Weekly Summary, zip; task/status/SLA/phase helpers; repository + board_query_service + excel_writer | Single “export” capability but many report types and helpers in one module. Splitting by report type (e.g. final_report, dmrb_report, dashboard, weekly_summary) would improve cohesion and testability. |

### 4.2 Modules Exceeding 500 Lines (High Complexity)

| File | Lines | Responsibilities | Assessment |
|------|-------|------------------|------------|
| ui/screens/admin.py | 783 | Tabs: Property structure (CRUD property/phase/building), Add Unit (manual availability), Import console, Unit Master Import (delegate), Exports (delegate), Dropdown Manager; uses property_service, import_service, cache | Clear candidate to split: one module per tab (e.g. admin_property_structure, admin_add_unit, admin_import, admin_dropdowns) with shared layout in admin.py. |
| ui/mock_data_v2.py | 701 | Mock data builders and flat row building for tests/UI | Isolated test/data harness; splitting optional. |
| ui/screens/turnover_detail.py | 622 | Single turnover detail view: load data, task/status updates, date overrides, manual overrides | One screen with many actions; could extract “detail actions” into small handlers or keep as-is. |
| ui/screens/board.py | 555 | Board filters, metrics, unit info tab, task tab, status/date updates via workflows | Uses application workflows; size is mostly UI layout and wiring. |
| services/turnover_service.py | 464 | Create/update turnovers, set manual status, update dates, reconcile tasks/SLA/risks, missing-task backfill | Core business logic; single responsibility (turnover lifecycle). Size acceptable. |

### 4.3 Modules Exceeding 300 Lines (Warning)

| File | Lines | Note |
|------|-------|------|
| ui/data/cache.py | 252 | Cached list + board/flag row loaders via services; active property sync. Cohesive “UI cache + list helpers”. |
| domain/enrichment.py | 272 | Pure enrichment and fact computation. Cohesive. |
| services/unit_master_import_service.py | 265 | Unit master CSV parse and upsert. Single responsibility. |
| services/sla_service.py | 259 | SLA reconciliation. Single responsibility. |
| imports/validation/schema_validator.py | 254 | Schema validation. Single responsibility. |
| services/excel_writer.py | 219 | Excel styling and table writing. Single responsibility. |
| services/imports/move_outs.py | 211 | Move-outs apply logic. Single responsibility. |
| db/repository/tasks.py | 238 | Task and template CRUD. Single responsibility. |
| services/board_query_service.py | 391 | Build flat rows, enrich, filter. Single responsibility. |
| ui/screens/flag_bridge.py | 229 | Flag bridge UI. Single screen. |
| services/ai_context_service.py | 222 | AI context building. Single responsibility. |
| db/repository/turnovers.py | 204 | Turnovers + enrichment cache; calls risks._ensure_confirmation_invariant. |
| ui/screens/report_operations.py | 205 | Report Operations screen; uses report_operations_service. |
| db/repository/units.py | 194 | Units CRUD. |
| services/imports/available_units.py | 179 | Available units apply. |
| ui/screens/ai_agent.py | 176 | AI agent UI. |
| services/task_service.py | 176 | Task updates and reconciliation. |
| ui/mock_data.py | 340 | Mock data; dev/demo. |

**Summary:** The only file in “architectural risk” by size is `services/export_service.py`. The main structural improvement from size is splitting `ui/screens/admin.py` by tab and, if desired, splitting `export_service` by report type.

---

## 5. Streamlit Runtime Performance Analysis

### 5.1 What Runs at App Startup (every run, including reruns)

1. **app.py** executes top to bottom:
   - Imports: `ui.components.sidebar`, `ui.components.sidebar_flags`, `ui.data.backend`, `ui.router`, `ui.state`.
2. **ui/data/backend.py** (imported by app.py):
   - In a single `try`, imports: `db.connection`, `db.repository` (full package), `services.board_query_service`, `services.export_service`, `services.import_service`, `services.manual_availability_service`, `services.note_service`, `services.property_service`, `services.task_service`, `services.turnover_service`, `services.unit_master_import_service`, `services.unit_service`.
   - So on every Streamlit rerun, **all of db + repository + the listed services** are loaded. That pulls in domain, config, and (via config) streamlit.
3. **Bootstrap and backfill:**
   - `ensure_database_ready(get_db_path())` runs (DB connection + schema check).
   - If backend available, `turnover_service_mod.reconcile_missing_tasks(conn)` runs (DB write path).
4. **UI:** `init_session_state()`, `render_navigation()`, `render_top_flags()`, `render_current_page()`.

### 5.2 What Runs on “Rerun” (UI interaction)

- The same as above: **full script re-execution**. So every widget interaction re-imports backend (and thus db + all listed services) and re-runs bootstrap/backfill (backfill is no-op if nothing to do). The router only runs `importlib.import_module(f"ui.screens.{module_name}")` for the current page, so **screen modules are lazy** (only the one screen is loaded in addition to the already-loaded backend).

### 5.3 Findings

| Topic | Finding |
|-------|---------|
| **Heavy top-level imports** | Yes. `app.py` → `ui.data.backend` → db + entire repository package + multiple services. All run on every rerun. |
| **Router lazy loading** | Screen bodies are lazy: only `ui.screens.<current>` is imported. Heavy loading is from the central backend facade, not from the router. |
| **DB at import** | No DB queries run during `import` of repository or services; queries run when code paths are invoked (e.g. `get_conn()`, `cached_list_*`, workflows). |
| **Expensive work at module load** | `config.settings.get_settings()` is `lru_cache(maxsize=1)`; first call reads env and st.secrets. No other heavy computation observed at import. |

**Conclusion:** The router-based lazy loading correctly prevents loading **other screens** until they are selected. However, **all backend and service code is loaded once at app startup** (and on every rerun) because `app.py` imports `ui.data.backend`, which eagerly imports db and services. To improve startup/rerun cost, backend could be loaded lazily (e.g. only when first needed) or services could be loaded per-screen. That would be a design change, not a small tweak.

---

## 6. Repository Architecture Evaluation

| Criterion | Status | Notes |
|-----------|--------|------|
| **Organized by domain entity** | Yes | Separate modules: units, turnovers, tasks, properties, risks, sla, notes, chat, imports, fas_tracker_notes; shared _helpers. |
| **SQL vs business rules** | Mostly | SQL and connection handling live in repository. Exception: `_ensure_confirmation_invariant` in db/repository/risks.py encodes a business rule (legal_confirmation_source ⇒ confirmed_move_out_date) and writes risk + audit; this is rule logic inside the repository layer. |
| **Purely data-access** | Mostly | Repository functions are CRUD + queries. The invariant in risks and its use from turnovers blur “data access” with “invariant enforcement.” Cross-repo calls (risks→imports, tasks→turnovers, units→properties) are data-access coordination, not domain logic. |

**Recommendation:** Move “legal_confirmation requires confirmed_move_out_date” into domain or a small service; repository should only persist and expose data; invariant checks could run in a service that calls repository and then writes risk/audit.

---

## 7. Service Layer Design Evaluation

| Criterion | Status | Notes |
|-----------|--------|------|
| **Contain business logic** | Yes | turnover_service, sla_service, risk_service, manual_availability_service, import orchestrator, etc. contain coordination and rules. |
| **Coordinate repository** | Yes | Services call repository; no services call UI. |
| **No UI dependencies** | Yes | No service module imports streamlit or ui. |
| **Thin pass-through** | Few | import_service, property_service, unit_service are thin facades around repository (or orchestrator). Acceptable for a single clear API boundary. report_operations_service encapsulates report-specific queries. |

No problematic “service only forwards to repository with no logic” patterns beyond intentional facades.

---

## 8. Domain Logic Evaluation

| Criterion | Status | Notes |
|-----------|--------|------|
| **Pure computations and rules** | Yes | lifecycle (effective_move_out_date, derive_lifecycle_phase), risk_radar (score_enriched_turnover), unit_identity (normalize, parse, compose), sla_engine (evaluate_sla_state), risk_engine, enrichment (domain-only imports). |
| **No infrastructure** | Yes | No domain module imports db, config, or adapters. |
| **Independent of UI and DB** | Yes | Domain is only imported by services and board_query_service; domain does not import UI or DB. |

Domain layer is clean and dependency-compliant.

---

## 9. Modular Monolith Assessment

| Capability | Modules involved | Coherence |
|------------|------------------|-----------|
| **Units** | db/repository/units, properties; services/unit_service, unit_master_import_service; domain/unit_identity; ui/screens/unit_import, admin | Coherent. |
| **Turnovers** | db/repository/turnovers; services/turnover_service; domain/lifecycle; application/workflows; ui/screens/board, turnover_detail, admin | Coherent; UI and application use services/workflows. |
| **Tasks** | db/repository/tasks; services/task_service; application/workflows; ui/screens/board, turnover_detail | Coherent. |
| **Imports** | db/repository/imports; services/import_service, imports/*; imports/validation/*; application/workflows; ui/screens/admin | Coherent; admin and cache use import_service and cache (service-based). |
| **Risk / SLA** | db/repository/risks, sla; services/risk_service, sla_service; domain/risk_radar, risk_engine, sla_engine | Coherent; _ensure_confirmation_invariant lives in repository. |
| **Exports** | services/export_service, excel_writer; services/board_query_service; ui/screens/exports, admin | Coherent; export_service is large (single module for all report types). |
| **Report Operations** | services/report_operations_service; ui/screens/report_operations | Coherent; screen uses service. |
| **Chat / AI** | db/repository/chat; services/chat_service, ai_context_service; api/chat_routes; ui/screens/ai_agent | Coherent. |

**Conclusion:** The codebase behaves as a **modular monolith** with recognizable capability boundaries (units, turnovers, tasks, imports, risk, SLA, exports, report operations, chat). Boundaries are coherent; UI and application call services or workflows, not repository directly. The router maps `report_operations` to `ui.screens.report_operations`, which exists and uses report_operations_service.

---

## 10. Architecture Cleanliness Scorecard

| Dimension | Score (1–5) | Explanation |
|-----------|-------------|-------------|
| **Layer separation** | 4 | Clear layers (UI, application, service, repository, domain, infrastructure) and mostly respected. Deduction for config depending on Streamlit and repository-repository + rule-in-repo. |
| **Dependency discipline** | 4 | UI and application go through services; no UI/application calls to repository methods. Remaining: config→Streamlit; repository→repository and one business rule in repository; UI uses `db_repository` only as availability flag. |
| **Module cohesion** | 4 | Most modules have a single responsibility. admin.py and export_service.py are large and combine multiple sub-responsibilities. |
| **Runtime performance design** | 3 | Router correctly lazy-loads screen modules. Backend (and thus db + all listed services) is loaded eagerly on every run; bootstrap and backfill run every rerun. Acceptable for many deployments but not optimized for minimal load. |
| **Maintainability** | 4 | Structure is understandable; commands/workflows and domain are clear. Large admin and export_service increase cognitive load; repository-repository and rule-in-repo are localized. |
| **Testability** | 4 | Domain and services are testable without UI. Repository is testable with a DB. UI and cache are testable with backend mocked; config’s Streamlit dependency complicates non-Streamlit tests. |

**Overall:** The architecture is **largely clean and maintainable**, with a clear layered and modular-monolith shape. The main gaps are config→Streamlit, repository cross-deps and one rule in repository, and one oversized service (export_service) and one oversized screen (admin). Domain and service boundaries are in good shape; UI no longer calls repository methods.

---

## 11. Unavoidable vs Improvable Compromises

### Likely Unavoidable (or acceptable trade-offs)

- **Streamlit rerun model:** Full script re-execution on each interaction is a Streamlit constraint. The code does not add extra heavy work per widget beyond what’s already triggered by importing backend.
- **Backend facade in UI:** Having a single place (ui/data/backend.py) that tries to load db and services and exposes them to the UI is a practical way to handle “backend optional” and avoid scattering try/except. The downside (eager load of all services) could be traded for lazy loading if startup becomes an issue.
- **Config and Streamlit secrets:** Using `st.secrets` for config is convenient in Streamlit; moving to env-only or a separate config loader would allow config to be framework-agnostic but requires a small refactor.
- **Repository-repository for invariant:** Keeping “legal_confirmation ⇒ confirmed_move_out_date” in the repository layer is a pragmatic placement so that any write path that touches turnover can enforce it; moving it to a service would require every such path to go through that service.
- **Thin property/unit services:** Thin wrappers (property_service, unit_service) give UI a single place to call for list/CRUD and keep repository behind the service boundary; acceptable.

### Improvable

- **Config → Streamlit:** `get_setting()` could read from env only when not in Streamlit, or from an adapter that is injected so that config has no direct streamlit import.
- **UI availability check:** Replace `if db_repository and ...` with `if BACKEND_AVAILABLE and ...` (or a dedicated flag) so UI does not reference the repository symbol.
- **Heavy startup:** If needed, defer loading of backend (or individual services) until first use, or load only the services required by the current screen.
- **Move _ensure_confirmation_invariant out of repository:** Implement the rule in domain or a small service; repository remains pure persistence; service or repository caller invokes the check and then writes risk/audit as needed.
- **Split admin and export_service:** Split ui/screens/admin.py by tab into smaller modules; split services/export_service.py by report type to reduce size and improve cohesion.

---

## 12. Remaining Architectural Improvements (Summary)

1. **Remove Config → Streamlit:** Make settings readable from environment (or a non-UI abstraction) so config/settings.py does not import streamlit; optional: keep a thin Streamlit-specific shim that pushes st.secrets into env or a settings provider.
2. **Optional: UI availability check:** Use `BACKEND_AVAILABLE` (or similar) instead of `db_repository` in board, flag_bridge, risk_radar, sidebar_flags, unit_import so UI does not reference the repository layer.
3. **Optional: Move _ensure_confirmation_invariant out of repository:** Implement the “legal_confirmation ⇒ confirmed_move_out_date” rule in domain or a small service; repository remains pure persistence; service or repository caller invokes the check and then writes risk/audit as needed.
4. **Optional: Split admin and export_service:** Split ui/screens/admin.py by tab into smaller modules; split services/export_service.py by report type to reduce size and improve cohesion.
5. **Optional: Lazy backend load:** If startup/rerun cost becomes an issue, defer loading of backend (or individual services) until first use.

---

**End of report.** No code was modified; this document is analysis only.
