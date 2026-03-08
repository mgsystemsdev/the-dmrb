-- Add report-authoritative planned ready date (exposure risk only; does not affect SLA or lifecycle).
ALTER TABLE turnover ADD COLUMN report_ready_date TEXT;
