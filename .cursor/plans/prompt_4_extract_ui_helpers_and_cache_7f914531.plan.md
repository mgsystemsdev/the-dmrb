---
name: Prompt 4 Extract UI Helpers and Cache
overview: Extract all helper and cache logic from app.py into ui/helpers/ (formatting, dates, dropdowns) and ui/data/cache.py so that app.py contains only application startup, sidebar, and delegation to the router, and remains under 150 lines when combined with the Prompt 1 structure.
todos: []
isProject: false
---

# Prompt 4 — Extract UI Helpers and Cache

## Current state

- [app.py](app.py) still contains a large block of helper and cache functions (and, if Prompt 1 has not been run, the full screen implementations). For Prompt 4 we focus on **moving** the following into dedicated modules; call sites will be updated to import from the new locations.
- [ui/state/session.py](ui/state/session.py) already provides `dropdown_config_path()`, `load_dropdown_config()` (from file), and `save_dropdown_config(config)` (to file). app.py defines thin wrappers that read/write **session state** and then persist: `_load_dropdown_config()` returns `st.session_state.get("dropdown_config", {})`, and `_save_dropdown_config()` calls `save_dropdown_config(st.session_state.dropdown_config)`.

No **ui/helpers/** or **ui/data/** packages exist yet.

## Target structure


| Module                       | Responsibility                                                 | Functions to move from app.py                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ---------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ui/helpers/dates.py**      | Date parsing, coercion, formatting                             | `_parse_date`, `_to_date`, `_dates_equal`, `_fmt_date`, `_parse_date_for_input`, `_iso_to_date`. Use `datetime`/`date`; use `pandas` only where needed for NaT (e.g. in `_to_date`). Avoid importing Streamlit so helpers stay reusable.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **ui/helpers/formatting.py** | Label/option formatting and badges                             | `_normalize_label`, `_normalize_enum`, `_safe_index`, `_operational_state_to_badge`, `_get_attention_badge`. Pure functions; no Streamlit or DB. Use `unicodedata` where needed.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| **ui/helpers/dropdowns.py**  | Dropdown config (session + persist)                            | `_dropdown_config_path` (or delegate to ui.state.session.dropdown_config_path), `_load_dropdown_config`, `_save_dropdown_config`. These wrap session state and call ui.state.session.save_dropdown_config; Streamlit dependency here is acceptable. Can be thin wrappers that call session helpers and st.session_state.                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| **ui/data/cache.py**         | DB connection, cache identity, cached queries, active property | `_get_db_path`, `_get_conn`, `_db_available`, `_invalidate_ui_caches`, `_db_write`, `_db_cache_identity`, `_iso_to_date` (if used only by cache; otherwise keep in dates and import in cache), `_cached_list_properties`, `_cached_list_phases`, `_cached_list_buildings`, `_cached_list_units`, `_cached_list_unit_master_import_units`, `_cached_get_flag_bridge_rows`, `_cached_get_dmrb_board_rows`, `_cached_get_risk_radar_rows`, `_cached_get_turnover_detail`, `_sync_active_property`, `_get_active_property`, `_set_active_property`, `_render_active_property_banner`. These depend on Streamlit (st.cache_data, st.session_state), ui.actions.db, config.settings, and backend (db.repository, board_query_service). Keep those imports in cache.py. |


**Do not move** (stay in app.py or in screens/sidebar):

- `_init_session_state` — app startup; can stay in app.py or call ui.state.session.init_session_state.
- `EXEC_LABELS` / `CONFIRM_LABELS` — derived from ui.state constants; can stay in app or move to ui.state.
- `_sort_insp`, `_sort_dv_desc`, `_sort_mi_closest`, `_sort_ready_date`, `_FLAG_CATEGORIES`, `_sidebar_unit_btn` — sidebar Top Flags logic; belong in ui/components/sidebar_flags or stay in app if that component doesn’t exist yet.
- `_get_dmrb_rows`, `_get_flag_bridge_rows`, `_get_risk_radar_rows`, `_exec_label`, `_confirm_label` — screen-level data/display; belong in screen modules (Prompt 1). If Prompt 1 is not done, leave them in app.py for now; only their use of dates/formatting/cache should switch to the new modules.
- `_run_import_for_report`, `_chat_api_base_url`, `_chat_api_request` — feature-specific; stay in the screen/module that uses them (admin/import, ai_agent).

## Implementation plan

### 1. Create ui/helpers/

- **Create [ui/helpers/init.py](ui/helpers/__init__.py)** — Export public names from dates, formatting, dropdowns so callers can do `from ui.helpers import parse_date, fmt_date, ...` or `from ui.helpers.dates import parse_date`.
- **Create [ui/helpers/dates.py](ui/helpers/dates.py)**  
Move: `_parse_date`, `_to_date`, `_dates_equal`, `_fmt_date`, `_parse_date_for_input`, `_iso_to_date`.  
  - Use `from datetime import date`; for `_to_date` keep the same pandas NaT handling if present.  
  - Expose with clear names, e.g. `parse_date`, `to_date`, `dates_equal`, `fmt_date`, `parse_date_for_input`, `iso_to_date` (or keep underscore names if the rest of the codebase uses them).  
  - No `import streamlit`.
- **Create [ui/helpers/formatting.py](ui/helpers/formatting.py)**  
Move: `_normalize_label`, `_normalize_enum`, `_safe_index`, `_operational_state_to_badge`, `_get_attention_badge`.  
  - Use `import unicodedata` where needed.  
  - No Streamlit or DB.  
  - Expose with the same or public names.
- **Create [ui/helpers/dropdowns.py](ui/helpers/dropdowns.py)**  
Move: `_dropdown_config_path`, `_load_dropdown_config`, `_save_dropdown_config`.  
  - `_dropdown_config_path` can delegate to `ui.state.session.dropdown_config_path()` if the path logic matches, or stay as in app (path next to app.py).  
  - `_load_dropdown_config` / `_save_dropdown_config` read/write `st.session_state.dropdown_config` and call `save_dropdown_config` from ui.state.session.  
  - Streamlit is acceptable here; document that this module is UI-specific.

### 2. Create ui/data/

- **Create [ui/data/init.py](ui/data/__init__.py)** — Optionally re-export cache helpers used by app/screens.
- **Create [ui/data/cache.py](ui/data/cache.py)**  
Move all cache and active-property functions listed above.  
  - **Dependencies:** streamlit, config.settings (get_settings, APP_SETTINGS), ui.actions.db (get_conn, db_write, get_db_path), and backend (db.connection.get_connection, ensure_database_ready, db.repository, board_query_service). Pass or import backend availability and service refs (e.g. from a small bootstrap or from app) so cache.py does not import app.py.  
  - **Backend availability:** Cache functions already guard on `db_repository` / `board_query_service`; they can receive these as arguments or import from a module that sets them at startup (e.g. a `ui.data.backend` or the same place app.py sets _BACKEND_AVAILABLE). Prefer a single place (e.g. cache.py or a tiny backend.py) that imports db and services and exposes get_conn, db_repository, board_query_service, backend_available so app.py and cache.py both use it.  
  - Keep `@st.cache_data(ttl=..., show_spinner=False)` and all SQL/query logic unchanged; only relocate.  
  - `_iso_to_date` is used by cached helpers; either define it in cache.py or import from ui.helpers.dates to avoid duplication.  
  - Expose the same function names (with or without leading underscore) so callers can replace `_get_conn` with `cache.get_conn` or `from ui.data.cache import get_conn`.

### 3. Update app.py

- **Remove** the moved function definitions (all of the blocks for dates, formatting, dropdowns, and cache/active-property).
- **Add** imports from ui.helpers (dates, formatting, dropdowns) and ui.data.cache (e.g. get_conn, db_cache_identity, cached_list_properties, get_active_property, render_active_property_banner, etc.).
- **Replace** every in-file call to the moved functions with calls to the imported versions (e.g. `from ui.helpers.dates import parse_date as _parse_date` or use the new names directly).
- **Leave** in app.py only: docstring, minimal imports, backend-availability check, set_page_config, global CSS, init_session_state (or delegate to ui.state), bootstrap and optional backfill, render_navigation, sidebar Top Flags (if still in app; it should call cache and helpers from the new modules), and the router dispatch (if Prompt 1 was run) or the big if/elif screen dispatch (if not). Do not re-introduce helper or cache logic.
- **Result:** app.py is focused on startup and routing; helper and cache code live in ui/helpers and ui/data/cache. If Prompt 1 has already been run, app.py should remain under 150 lines; if not, it will still contain screen logic and may exceed 150 lines until Prompt 1 is executed.

### 4. Update other callers (if any)

- **Screens** (if Prompt 1 was run): Screens that currently import from app or use helpers/cache should import from ui.helpers.dates, ui.helpers.formatting, ui.helpers.dropdowns, and ui.data.cache instead. Grep for `_parse_date`, `_fmt_date`, `_get_active_property`, `_cached`_, etc., and update those files to use the new modules.
- **Sidebar component** (if ui/components/sidebar_flags.py exists): It should use ui.data.cache and ui.helpers.dates for Top Flags; ensure no remaining app.py imports for those helpers.

### 5. Avoid circular imports

- **app.py** imports ui.helpers and ui.data.cache; **cache.py** must not import app.py. Cache.py can import config, ui.actions.db, and (optionally) a small backend bootstrap module that sets db_repository and board_query_service; app.py and cache.py both use that bootstrap. Alternatively, app.py passes backend refs into cache (e.g. via a set_backend(...) or init_cache(...)) so cache.py does not import the heavy backend at module load if desired.

## Constraints (from prompt)

- Do not modify logic; only move functions and update imports.
- Avoid Streamlit in helpers when possible (dates and formatting can be pure; dropdowns and cache will use Streamlit where needed).
- After the refactor, app.py has no helper/cache definitions and stays focused on startup; app.py remains under 150 lines when combined with the Prompt 1 layout (router + screens).

## Order of operations

1. Create ui/helpers/**init**.py, ui/helpers/dates.py, ui/helpers/formatting.py, ui/helpers/dropdowns.py with the moved functions and correct imports.
2. Create ui/data/**init**.py and ui/data/cache.py with the moved cache and active-property functions; resolve backend availability and service refs (single place used by app and cache).
3. Update app.py: remove moved code, add imports from ui.helpers and ui.data.cache, replace all calls to the moved functions with the new imports.
4. Update any screen or sidebar code that references these helpers/cache (if Prompt 1 was run) to import from ui.helpers and ui.data.cache.
5. Run the app and a quick smoke test (navigation, one board and one admin action) to confirm nothing is broken.

## File list


| Action | Path                                                                                                             |
| ------ | ---------------------------------------------------------------------------------------------------------------- |
| Create | ui/helpers/**init**.py                                                                                           |
| Create | ui/helpers/dates.py                                                                                              |
| Create | ui/helpers/formatting.py                                                                                         |
| Create | ui/helpers/dropdowns.py                                                                                          |
| Create | ui/data/**init**.py                                                                                              |
| Create | ui/data/cache.py                                                                                                 |
| Modify | app.py (remove helpers/cache, add imports, use new modules)                                                      |
| Modify | ui/components/sidebar_flags.py or app.py sidebar block (if present) to use cache/helpers from new modules        |
| Modify | ui/screens/*.py (if Prompt 1 was run) to import from ui.helpers and ui.data.cache where they use these functions |


