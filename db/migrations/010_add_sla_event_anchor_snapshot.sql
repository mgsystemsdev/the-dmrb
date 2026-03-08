-- Migration 010: Add SLA event snapshot fields for anchor + threshold.
-- Additive; preserves existing rows.

ALTER TABLE sla_event ADD COLUMN opened_anchor_date TEXT;
ALTER TABLE sla_event ADD COLUMN current_anchor_date TEXT;
ALTER TABLE sla_event ADD COLUMN evaluated_threshold_days INTEGER;

-- Backfill anchor snapshots from current effective anchor on turnover.
-- (confirmed when legal_confirmation_source is set, else scheduled, else legacy move_out_date)
UPDATE sla_event
SET opened_anchor_date = (
  SELECT CASE
    WHEN t.legal_confirmation_source IS NOT NULL THEN t.confirmed_move_out_date
    ELSE COALESCE(t.scheduled_move_out_date, t.move_out_date)
  END
  FROM turnover t
  WHERE t.turnover_id = sla_event.turnover_id
)
WHERE opened_anchor_date IS NULL;

UPDATE sla_event
SET current_anchor_date = COALESCE(current_anchor_date, opened_anchor_date)
WHERE current_anchor_date IS NULL;

UPDATE sla_event
SET evaluated_threshold_days = 10
WHERE evaluated_threshold_days IS NULL;

