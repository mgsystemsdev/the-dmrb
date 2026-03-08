-- Migration 007: Add phase_id and building_id to unit for hierarchy.
-- Backfill (phase/building creation and unit.phase_id, unit.building_id, unit.unit_number)
-- is performed in Python in ensure_database_ready after this script.

ALTER TABLE unit ADD COLUMN phase_id INTEGER REFERENCES phase(phase_id);
ALTER TABLE unit ADD COLUMN building_id INTEGER REFERENCES building(building_id);
