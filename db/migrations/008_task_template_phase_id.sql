-- Migration 008: Add phase_id to task_template for hierarchy. Backfill and table recreate in Python.

ALTER TABLE task_template ADD COLUMN phase_id INTEGER REFERENCES phase(phase_id);
