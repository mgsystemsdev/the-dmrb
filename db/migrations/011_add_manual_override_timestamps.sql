-- Migration 011: Add nullable override timestamps for manual-edit protection (auto-clear-on-match).
-- Protects: scheduled_move_out_date, report_ready_date, move_in_date, manual_ready_status.
ALTER TABLE turnover ADD COLUMN move_out_manual_override_at TEXT;
ALTER TABLE turnover ADD COLUMN ready_manual_override_at TEXT;
ALTER TABLE turnover ADD COLUMN move_in_manual_override_at TEXT;
ALTER TABLE turnover ADD COLUMN status_manual_override_at TEXT;
