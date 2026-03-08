-- Migration 006: Add unit attribute columns (floor_plan, gross_sq_ft, placeholders).
-- Phase/building FKs (phase_id, building_id) added in 007.

ALTER TABLE unit ADD COLUMN floor_plan TEXT;
ALTER TABLE unit ADD COLUMN gross_sq_ft INTEGER;
ALTER TABLE unit ADD COLUMN bed_count INTEGER;
ALTER TABLE unit ADD COLUMN bath_count REAL;
ALTER TABLE unit ADD COLUMN layout_code TEXT;
