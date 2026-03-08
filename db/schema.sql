-- ---------------------------------------------------------------------------
-- Turnover Operational Control System — Canonical Schema v1
-- ---------------------------------------------------------------------------
-- Runtime must enable:
--   PRAGMA journal_mode=WAL;
--   PRAGMA foreign_keys=ON;
-- All timestamps stored in UTC.
-- No destructive deletes in v1.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 1. property
-- ---------------------------------------------------------------------------
CREATE TABLE property (
  property_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- 2. unit
-- ---------------------------------------------------------------------------
CREATE TABLE unit (
  unit_id INTEGER PRIMARY KEY,
  property_id INTEGER NOT NULL REFERENCES property(property_id),
  unit_code_raw TEXT NOT NULL,
  unit_code_norm TEXT NOT NULL,
  has_carpet INTEGER NOT NULL DEFAULT 0 CHECK(has_carpet IN (0, 1)),
  has_wd_expected INTEGER NOT NULL DEFAULT 0 CHECK(has_wd_expected IN (0, 1)),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
  UNIQUE(property_id, unit_code_norm),
  CHECK(unit_code_norm <> '')
);

-- ---------------------------------------------------------------------------
-- 3. turnover
-- ---------------------------------------------------------------------------
CREATE TABLE turnover (
  turnover_id INTEGER PRIMARY KEY,
  property_id INTEGER NOT NULL REFERENCES property(property_id),
  unit_id INTEGER NOT NULL REFERENCES unit(unit_id),
  source_turnover_key TEXT NOT NULL UNIQUE,
  move_out_date TEXT NOT NULL,
  move_in_date TEXT,
  report_ready_date TEXT,
  manual_ready_status TEXT CHECK(manual_ready_status IN ('Vacant ready', 'Vacant not ready', 'On notice') OR manual_ready_status IS NULL),
  manual_ready_confirmed_at TEXT,
  expedited_flag INTEGER NOT NULL DEFAULT 0 CHECK(expedited_flag IN (0, 1)),
  wd_present INTEGER CHECK(wd_present IN (0, 1)),
  wd_supervisor_notified INTEGER CHECK(wd_supervisor_notified IN (0, 1)),
  wd_notified_at TEXT,
  wd_installed INTEGER CHECK(wd_installed IN (0, 1)),
  wd_installed_at TEXT,
  closed_at TEXT,
  canceled_at TEXT,
  cancel_reason TEXT,
  last_seen_moveout_batch_id INTEGER REFERENCES import_batch(batch_id),
  missing_moveout_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(move_out_date IS NOT NULL),
  CHECK(NOT (closed_at IS NOT NULL AND canceled_at IS NOT NULL))
);

CREATE UNIQUE INDEX idx_one_open_turnover_per_unit
  ON turnover(unit_id)
  WHERE closed_at IS NULL AND canceled_at IS NULL;

-- ---------------------------------------------------------------------------
-- 4. task_template
-- ---------------------------------------------------------------------------
CREATE TABLE task_template (
  template_id INTEGER PRIMARY KEY,
  property_id INTEGER NOT NULL REFERENCES property(property_id),
  task_type TEXT NOT NULL,
  required INTEGER NOT NULL CHECK(required IN (0, 1)),
  blocking INTEGER NOT NULL CHECK(blocking IN (0, 1)),
  sort_order INTEGER NOT NULL,
  applies_if_has_carpet INTEGER CHECK(applies_if_has_carpet IN (0, 1)),
  applies_if_has_wd_expected INTEGER CHECK(applies_if_has_wd_expected IN (0, 1)),
  is_active INTEGER NOT NULL CHECK(is_active IN (0, 1)),
  UNIQUE(property_id, task_type, is_active),
  CHECK(task_type <> '')
);

-- ---------------------------------------------------------------------------
-- 5. task_template_dependency
-- ---------------------------------------------------------------------------
CREATE TABLE task_template_dependency (
  template_id INTEGER NOT NULL REFERENCES task_template(template_id),
  depends_on_template_id INTEGER NOT NULL REFERENCES task_template(template_id),
  PRIMARY KEY(template_id, depends_on_template_id),
  CHECK(template_id <> depends_on_template_id)
);

-- ---------------------------------------------------------------------------
-- 6. task
-- ---------------------------------------------------------------------------
CREATE TABLE task (
  task_id INTEGER PRIMARY KEY,
  turnover_id INTEGER NOT NULL REFERENCES turnover(turnover_id),
  task_type TEXT NOT NULL,
  required INTEGER NOT NULL CHECK(required IN (0, 1)),
  blocking INTEGER NOT NULL CHECK(blocking IN (0, 1)),
  scheduled_date TEXT,
  vendor_due_date TEXT,
  vendor_completed_at TEXT,
  manager_confirmed_at TEXT,
  execution_status TEXT NOT NULL CHECK(execution_status IN ('NOT_STARTED', 'SCHEDULED', 'IN_PROGRESS', 'VENDOR_COMPLETED', 'NA', 'CANCELED')),
  confirmation_status TEXT NOT NULL CHECK(confirmation_status IN ('PENDING', 'CONFIRMED', 'REJECTED', 'WAIVED')),
  UNIQUE(turnover_id, task_type),
  CHECK(execution_status != 'VENDOR_COMPLETED' OR vendor_completed_at IS NOT NULL),
  CHECK(confirmation_status != 'CONFIRMED' OR vendor_completed_at IS NOT NULL),
  CHECK(confirmation_status != 'CONFIRMED' OR manager_confirmed_at IS NOT NULL)
);

-- ---------------------------------------------------------------------------
-- 7. task_dependency
-- ---------------------------------------------------------------------------
CREATE TABLE task_dependency (
  task_id INTEGER NOT NULL REFERENCES task(task_id),
  depends_on_task_id INTEGER NOT NULL REFERENCES task(task_id),
  PRIMARY KEY(task_id, depends_on_task_id),
  CHECK(task_id <> depends_on_task_id)
);

-- ---------------------------------------------------------------------------
-- 8. turnover_task_override
-- ---------------------------------------------------------------------------
CREATE TABLE turnover_task_override (
  turnover_id INTEGER NOT NULL REFERENCES turnover(turnover_id),
  task_type TEXT NOT NULL,
  required_override INTEGER CHECK(required_override IN (0, 1)),
  blocking_override INTEGER CHECK(blocking_override IN (0, 1)),
  PRIMARY KEY(turnover_id, task_type)
);

-- ---------------------------------------------------------------------------
-- 9. note (human-only)
-- ---------------------------------------------------------------------------
CREATE TABLE note (
  note_id INTEGER PRIMARY KEY,
  turnover_id INTEGER NOT NULL REFERENCES turnover(turnover_id),
  note_type TEXT NOT NULL,
  blocking INTEGER NOT NULL CHECK(blocking IN (0, 1)),
  severity TEXT NOT NULL CHECK(severity IN ('INFO', 'WARNING', 'CRITICAL')),
  description TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved_at TEXT
);

-- ---------------------------------------------------------------------------
-- 10. risk_flag (system-only)
-- ---------------------------------------------------------------------------
CREATE TABLE risk_flag (
  risk_id INTEGER PRIMARY KEY,
  turnover_id INTEGER NOT NULL REFERENCES turnover(turnover_id),
  risk_type TEXT NOT NULL CHECK(risk_type IN ('SLA_BREACH', 'QC_RISK', 'WD_RISK', 'CONFIRMATION_BACKLOG', 'EXECUTION_OVERDUE', 'DATA_INTEGRITY', 'DUPLICATE_OPEN_TURNOVER', 'EXPOSURE_RISK')),
  severity TEXT NOT NULL CHECK(severity IN ('INFO', 'WARNING', 'CRITICAL')),
  triggered_at TEXT NOT NULL,
  resolved_at TEXT,
  auto_resolve INTEGER NOT NULL DEFAULT 1 CHECK(auto_resolve IN (0, 1))
);

CREATE UNIQUE INDEX idx_one_active_risk_per_type
  ON risk_flag(turnover_id, risk_type)
  WHERE resolved_at IS NULL;

-- ---------------------------------------------------------------------------
-- 11. sla_event (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE sla_event (
  sla_event_id INTEGER PRIMARY KEY,
  turnover_id INTEGER NOT NULL REFERENCES turnover(turnover_id),
  breach_started_at TEXT NOT NULL,
  breach_resolved_at TEXT
);

CREATE UNIQUE INDEX idx_one_open_sla_breach
  ON sla_event(turnover_id)
  WHERE breach_resolved_at IS NULL;

-- ---------------------------------------------------------------------------
-- 12. audit_log (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE audit_log (
  audit_id INTEGER PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id INTEGER NOT NULL,
  field_name TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  changed_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  source TEXT NOT NULL CHECK(source IN ('manual', 'import', 'system')),
  correlation_id TEXT
);

-- ---------------------------------------------------------------------------
-- 13. import_batch (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE import_batch (
  batch_id INTEGER PRIMARY KEY,
  report_type TEXT NOT NULL,
  checksum TEXT NOT NULL UNIQUE,
  source_file_name TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('SUCCESS', 'NO_OP', 'FAILED')),
  imported_at TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- 14. import_row (append-only)
-- ---------------------------------------------------------------------------
CREATE TABLE import_row (
  row_id INTEGER PRIMARY KEY,
  batch_id INTEGER NOT NULL REFERENCES import_batch(batch_id),
  raw_json TEXT NOT NULL,
  unit_code_raw TEXT NOT NULL,
  unit_code_norm TEXT NOT NULL,
  move_out_date TEXT,
  move_in_date TEXT,
  validation_status TEXT NOT NULL,
  conflict_flag INTEGER NOT NULL DEFAULT 0 CHECK(conflict_flag IN (0, 1)),
  conflict_reason TEXT
);

-- ---------------------------------------------------------------------------
-- Performance indexes
-- ---------------------------------------------------------------------------
CREATE INDEX idx_turnover_unit_id ON turnover(unit_id);
CREATE INDEX idx_turnover_move_out_date ON turnover(move_out_date);
CREATE INDEX idx_turnover_move_in_date ON turnover(move_in_date);
CREATE INDEX idx_task_turnover_id ON task(turnover_id);
CREATE INDEX idx_import_row_batch_id ON import_row(batch_id);
CREATE INDEX idx_risk_flag_turnover_id ON risk_flag(turnover_id);
CREATE INDEX idx_note_turnover_id ON note(turnover_id);

-- ---------------------------------------------------------------------------
-- Bootstrap: migration version (managed by ensure_database_ready)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_version (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  version INTEGER NOT NULL
);
INSERT OR REPLACE INTO schema_version (singleton, version) VALUES (1, 0);
