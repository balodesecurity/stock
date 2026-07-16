-- Migration 003: Drop unused data_source column from screener_companies
-- Written but never read by any script or the portal.
-- Applied: 2026-06-01
--
-- To apply:
--   sqlite3 /path/to/derived_metrics_analysis.db < migrations/003_drop_data_source_from_screener_companies.sql

ALTER TABLE screener_companies DROP COLUMN data_source;
