-- Migration 003: Add task.assignee, task.blocking_reason, turnover.wd_present_type for frontend alignment.
-- New columns are nullable; no data backfill required.

ALTER TABLE task ADD COLUMN assignee TEXT;
ALTER TABLE task ADD COLUMN blocking_reason TEXT;

ALTER TABLE turnover ADD COLUMN wd_present_type TEXT;
