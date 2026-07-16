-- Migration 002: Drop unused url column from screener_companies
-- The url column was written but never read by any script or the portal.
-- Applied: 2026-06-01
--
-- To apply:
--   sqlite3 /path/to/derived_metrics_analysis.db < migrations/002_drop_url_from_screener_companies.sql
--
-- To verify:
--   sqlite3 /path/to/derived_metrics_analysis.db ".schema screener_companies"

ALTER TABLE screener_companies DROP COLUMN url;
