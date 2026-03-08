-- Migration 012: Add last_import_* columns for tracking most recent normalized import values.
-- Used by Authority & Import Comparison panel (read-layer only).
ALTER TABLE turnover ADD COLUMN last_import_move_out_date TEXT;
ALTER TABLE turnover ADD COLUMN last_import_ready_date TEXT;
ALTER TABLE turnover ADD COLUMN last_import_move_in_date TEXT;
ALTER TABLE turnover ADD COLUMN last_import_status TEXT;
