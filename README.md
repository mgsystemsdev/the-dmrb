# DMRB — Digital Make Ready Board

DMRB is an offline-first operational application for managing apartment turn and make-ready workflows. It gives property operations teams a single working board for tracking units from notice through vacancy, make ready, move-in readiness, and stabilization, with explicit support for imports, manual overrides, task orchestration, SLA monitoring, and risk visibility.

The application is implemented as a Streamlit frontend backed by SQLite and a layered Python architecture. It is designed to keep business rules out of the UI, preserve an audit trail for important mutations, and support deterministic lifecycle evaluation through domain services and tests.

## Project Overview

DMRB models the apartment turnover lifecycle around a few core concepts:

- `unit`: the physical apartment and its identity within a property hierarchy
- `turnover`: an open make-ready lifecycle for a unit
- `task`: operational work required to complete the turnover
- `note`: human-entered operational context
- `risk_flag` and `sla_event`: system-generated signals that highlight issues and breaches
- `import_batch` and `import_row`: append-only records for report imports and validation outcomes

The primary UI is a board-oriented operational cockpit with supporting detail and admin workflows. The current application supports:

- Viewing active turnovers in a DMRB board
- Filtering by phase, status, lifecycle state, assignee, and QC state
- Surfacing flag categories and breach conditions through a Flag Bridge
- Reviewing and updating turnover details, tasks, notes, and washer/dryer state
- Importing operational reports from external files
- Bootstrapping and maintaining unit hierarchy via a unit master import
- Preserving manual overrides against conflicting import updates

## Key Features

- Offline-first local deployment using SQLite with WAL mode enabled
- Automatic schema bootstrap and ordered database migrations on startup
- Streamlit UI with operational views for board, flag bridge, turnover detail, and admin tools
- FastAPI chat endpoints for the DMRB AI Agent (`/api/chat/*`)
- Deterministic domain logic for lifecycle phase, board enrichment, SLA evaluation, and risk evaluation
- Import pipelines for `MOVE_OUTS`, `PENDING_MOVE_INS`, `AVAILABLE_UNITS`, `PENDING_FAS`, and `DMRB`
- Unit Master import for phase/building/unit hierarchy creation and unit metadata updates
- Task instantiation from templates, including dependencies and conditional applicability
- Audit logging for manual, import-driven, and system-generated changes
- Manual override protections so validated operator decisions are not silently overwritten by imports
- SLA breach tracking and reconciliation
- Risk reconciliation for QC, overdue execution, confirmation backlog, washer/dryer risk, exposure risk, and integrity issues
- Test coverage around imports, lifecycle rules, task creation, manual availability, unit identity, and truth-safety behaviors

## Technology Stack

- Python 3
- Streamlit
- SQLite
- pandas
- openpyxl
- pytest

## How It Works

At runtime, `app.py` starts the Streamlit UI, resolves the database path, ensures the database schema and migrations are current, and backfills missing tasks for existing open turnovers.

Operational data is persisted in SQLite. The UI delegates reads to service functions and performs writes only when the `Enable DB Writes` toggle is turned on. Business rules live in the `domain/` layer and orchestration logic lives in `services/`, which keeps the frontend thin and reduces coupling between display logic and lifecycle behavior.

Imports are treated as first-class operational events. Each import is checksum-tracked for idempotency, row outcomes are recorded, and important field changes are audited. When imported values conflict with manual overrides, DMRB preserves the override and records the skipped update for traceability.

## Project Structure

```text
.
├── app.py                     # Streamlit application entrypoint
├── db/
│   ├── connection.py          # SQLite connection management, bootstrap, migrations
│   ├── repository.py          # Persistence layer and query/update helpers
│   ├── schema.sql             # Canonical schema
│   └── migrations/            # Ordered schema evolution scripts
├── domain/
│   ├── enrichment.py          # Board facts, intelligence, and breach calculations
│   ├── lifecycle.py           # Lifecycle and effective move-out rules
│   ├── risk_engine.py         # Pure risk evaluation rules
│   ├── sla_engine.py          # Pure SLA breach evaluation rules
│   └── unit_identity.py       # Canonical unit normalization and identity parsing
├── services/
│   ├── board_query_service.py         # Board/detail query assembly and filtering
│   ├── import_service.py              # Report import orchestration
│   ├── manual_availability_service.py # Manual turnover creation for existing units
│   ├── note_service.py                # Note creation and resolution
│   ├── risk_service.py                # Risk reconciliation
│   ├── sla_service.py                 # SLA reconciliation
│   ├── task_service.py                # Task mutations and transition handling
│   ├── turnover_service.py            # Turnover lifecycle updates
│   └── unit_master_import_service.py  # Unit master bootstrap and repair import
├── tests/                     # Automated test suite
├── data/                      # Local database, config, and sample import files
├── docs/                      # Design and migration notes
├── spec/                      # Architecture and audit reference material
├── scripts/                   # Utility and verification scripts
└── ui/                        # Mock/legacy UI data helpers
```

## Installation

### Prerequisites

- Python 3.10+ recommended
- `pip`

### Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Setup and Configuration

DMRB supports SQLite by default and can be prepared for Postgres.

### Default database location

If no environment variable is set, the app uses:

```bash
data/cockpit.db
```

### SQLite environment variables

Set `COCKPIT_DB_PATH` to point to another SQLite file:

```bash
export COCKPIT_DB_PATH=/absolute/path/to/cockpit.db
```

On startup, the application will:

1. Create the database if it does not exist.
2. Apply the canonical schema if required.
3. Run ordered migrations.
4. Reconcile open turnovers that are missing task rows.

No separate migration command is required for normal local startup.

### Postgres preparation variables

To route runtime connections to Postgres (after running migration):

```bash
export DB_ENGINE=postgres
export DATABASE_URL=postgresql://user:password@localhost:5432/dmrb
```

If `DB_ENGINE` is omitted, DMRB uses SQLite.

## Running the Application

From the repository root, run the API and UI in separate terminals:

```bash
uvicorn api.main:app --reload
```

```bash
streamlit run app.py
```

Then open the local Streamlit URL shown in the terminal.

## Usage

### Main navigation

The current Streamlit application exposes four primary areas:

- `DMRB Board`: operational board of active turnovers
- `Flag Bridge`: filtered breach and flag analysis view
- `Turnover Detail`: detailed lifecycle, tasks, notes, and washer/dryer management
- `DMRB AI Agent`: conversational assistant powered by `/api/chat/*` and full turnover context injection
- `Admin`: imports, dropdown management, property structure, and unit tools

### Export workflows

The Admin area includes an `Exports` tab that generates operational report artifacts from
all open turnovers (closed/canceled turnovers are excluded, and current UI filters are ignored):

- `Final_Report.xlsx` (7 sheets)
- `DMRB_Report.xlsx` (12 sheets)
- `Dashboard_Chart.png`
- `Weekly_Summary.txt`
- `DMRB_Reports.zip` (bundle of all artifacts above)

Use `Prepare Export Files` and then download each file (or all files via ZIP).

### Write safety

The UI includes an `Enable DB Writes` toggle in the sidebar. Reads are always available, but mutations are intentionally gated so the app can be used safely in a read-only mode during inspection or demos.

### Import workflows

The Admin area supports report ingestion for:

- `MOVE_OUTS`
- `PENDING_MOVE_INS`
- `AVAILABLE_UNITS`
- `PENDING_FAS`
- `DMRB`

These imports update turnover lifecycle data, create turnovers when appropriate, instantiate tasks, and record row-level validation outcomes.

### Unit Master import

The Unit Master import is intended to bootstrap or repair the unit hierarchy and metadata. It updates structure-oriented data such as:

- phase/building/unit identity
- floor plan
- square footage

It does not create turnover, task, SLA, or risk records directly.

## Development Guidelines

This repository already reflects a fairly strict layering model. When making changes, preserve these boundaries:

- `ui/app`: presentation only; avoid business rules in Streamlit handlers
- `domain/`: pure deterministic logic with no UI or database imports
- `services/`: orchestration, reconciliation, and audit-aware workflows
- `db/`: persistence concerns only

Recommended development practices for this codebase:

- Add or update tests for lifecycle, risk, SLA, import, and override behavior when changing rules.
- Keep mutations auditable through `audit_log`.
- Prefer repository helpers over ad hoc SQL in service or UI code.
- Add schema changes through migrations in `db/migrations/`.
- Keep import behavior idempotent and explicit about conflicts.

## Testing

Run the automated test suite from the repository root:

```bash
pytest -q
```

## SQLite to Postgres Migration (Phase 3 prep)

The repository now includes a one-command migration workflow:

```bash
python -m scripts.migrate_to_postgres \
  --sqlite-path data/cockpit.db \
  --postgres-url postgresql://user:password@localhost:5432/dmrb
```

This command:

1. Applies Postgres schema bootstrap.
2. Exports SQLite data to structured JSON.
3. Imports the data into Postgres.
4. Verifies record counts, key entities, and required-field parity.

See [Postgres Migration Guide](docs/POSTGRES_MIGRATION.md) for the full checklist.

At the time of review, the suite does not fully pass in the current repository state. The README instructions above reflect the intended test command, but the codebase currently has failing tests around enrichment parity and some turnover/manual-override schema paths.

## Contributing

If this repository will be developed collaboratively, a practical contribution workflow is:

1. Create a feature branch.
2. Make focused changes within the existing architecture boundaries.
3. Add or update tests for behavior changes.
4. Run `pytest -q`.
5. Open a pull request with a concise description of the operational impact.

For larger changes, document any schema, import-contract, or lifecycle-rule implications in `docs/` or `spec/` so the operational model stays explicit.

## License

License information has not been defined yet.

Add the appropriate license here, for example:

```text
MIT
Apache-2.0
Proprietary
```
