-- Migration 004: Add unit identity columns (nullable for backfill; Python backfill then enforces NOT NULL + UNIQUE).
-- Backfill and table recreation run in ensure_database_ready() after this script.

ALTER TABLE unit ADD COLUMN phase_code TEXT;
ALTER TABLE unit ADD COLUMN building_code TEXT;
ALTER TABLE unit ADD COLUMN unit_number TEXT;
ALTER TABLE unit ADD COLUMN unit_identity_key TEXT;
