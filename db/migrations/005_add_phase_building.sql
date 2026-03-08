-- Migration 005: Add phase and building tables for hierarchy (property → phase → building → unit).
-- No data yet; backfill in 007.

CREATE TABLE IF NOT EXISTS phase (
  phase_id INTEGER PRIMARY KEY,
  property_id INTEGER NOT NULL REFERENCES property(property_id),
  phase_code TEXT NOT NULL,
  name TEXT,
  UNIQUE(property_id, phase_code)
);

CREATE TABLE IF NOT EXISTS building (
  building_id INTEGER PRIMARY KEY,
  phase_id INTEGER NOT NULL REFERENCES phase(phase_id),
  building_code TEXT NOT NULL,
  UNIQUE(phase_id, building_code)
);

CREATE INDEX IF NOT EXISTS idx_phase_property_id ON phase(property_id);
CREATE INDEX IF NOT EXISTS idx_building_phase_id ON building(phase_id);
