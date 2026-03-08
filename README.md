# Turnover Cockpit (v1)

Offline-first Streamlit operational cockpit for apartment turnover lifecycle management.

## Running the UI prototype (mock data only)

No database or env required. From the **project root**:

```bash
streamlit run the-dmrb/app_prototype.py
```

Or from the `the-dmrb` directory:

```bash
streamlit run app_prototype.py
```

The prototype includes: Dashboard (summary, Immediate Action, active turnover table with inline Status), Control Board 1 (unit/status table), Control Board 2 (task table), Turnover detail (unit status, WD, tasks, notes, risks), and Import (fake result + conflicts). All filters (Search, Filter, Assign, Move-ins, Phase, QC) and inline edits persist in session state for the run.

## Architecture (strict boundaries)
- UI layer contains no business logic.
- Domain layer contains pure deterministic functions.
- Services orchestrate transactions and write audit logs.
- DB layer handles persistence only.
# the-dmrb
