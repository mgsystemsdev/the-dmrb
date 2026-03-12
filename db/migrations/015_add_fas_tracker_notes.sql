-- Migration 015: add FAS tracker notes table for Report Operations.
CREATE TABLE IF NOT EXISTS fas_tracker_notes (
  unit_id INTEGER NOT NULL REFERENCES unit(unit_id),
  fas_date TEXT NOT NULL,
  note_text TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (unit_id, fas_date)
);

CREATE INDEX IF NOT EXISTS idx_fas_tracker_notes_unit_id ON fas_tracker_notes(unit_id);
