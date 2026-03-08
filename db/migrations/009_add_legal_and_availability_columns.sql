-- Migration 009: Add turnover columns for legal/availability modeling.
-- All columns nullable; no NOT NULL, FKs, or indexes.

-- Move-out modeling
ALTER TABLE turnover ADD COLUMN scheduled_move_out_date TEXT;
ALTER TABLE turnover ADD COLUMN confirmed_move_out_date TEXT;

-- Legal confirmation
ALTER TABLE turnover ADD COLUMN legal_confirmation_source TEXT CHECK(legal_confirmation_source IN ('fas','manual'));
ALTER TABLE turnover ADD COLUMN legal_confirmed_at TEXT;
ALTER TABLE turnover ADD COLUMN legal_confirmation_note TEXT;

-- Availability modeling
ALTER TABLE turnover ADD COLUMN available_date TEXT;
ALTER TABLE turnover ADD COLUMN availability_status TEXT;

-- Backfill: set scheduled_move_out_date from move_out_date where null
UPDATE turnover
SET scheduled_move_out_date = move_out_date
WHERE scheduled_move_out_date IS NULL;
