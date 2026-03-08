-- Migration 002: Add EXPOSURE_RISK to risk_flag.risk_type CHECK constraint.
-- SQLite cannot ALTER CHECK constraints, so we recreate the table.
-- Preserves all existing data and indexes.

PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

-- 1. Drop indexes that would conflict, then rename existing table
DROP INDEX IF EXISTS idx_one_active_risk_per_type;
DROP INDEX IF EXISTS idx_risk_flag_turnover_id;
ALTER TABLE risk_flag RENAME TO risk_flag_old;

-- 2. Create new table with EXPOSURE_RISK in CHECK
CREATE TABLE risk_flag (
  risk_id INTEGER PRIMARY KEY,
  turnover_id INTEGER NOT NULL REFERENCES turnover(turnover_id),
  risk_type TEXT NOT NULL CHECK(risk_type IN ('SLA_BREACH', 'QC_RISK', 'WD_RISK', 'CONFIRMATION_BACKLOG', 'EXECUTION_OVERDUE', 'DATA_INTEGRITY', 'DUPLICATE_OPEN_TURNOVER', 'EXPOSURE_RISK')),
  severity TEXT NOT NULL CHECK(severity IN ('INFO', 'WARNING', 'CRITICAL')),
  triggered_at TEXT NOT NULL,
  resolved_at TEXT,
  auto_resolve INTEGER NOT NULL DEFAULT 1 CHECK(auto_resolve IN (0, 1))
);

-- 3. Copy existing data
INSERT INTO risk_flag (risk_id, turnover_id, risk_type, severity, triggered_at, resolved_at, auto_resolve)
SELECT risk_id, turnover_id, risk_type, severity, triggered_at, resolved_at, auto_resolve
FROM risk_flag_old;

-- 4. Recreate indexes
CREATE UNIQUE INDEX idx_one_active_risk_per_type
  ON risk_flag(turnover_id, risk_type)
  WHERE resolved_at IS NULL;

CREATE INDEX idx_risk_flag_turnover_id ON risk_flag(turnover_id);

-- 5. Drop old table
DROP TABLE risk_flag_old;

COMMIT;

PRAGMA foreign_keys = ON;
