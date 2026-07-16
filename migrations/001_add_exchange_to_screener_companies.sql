-- Migration 001: Add exchange column to screener_companies
-- Purpose: Track which exchange a company is listed on, enabling non-Indian stocks (US, etc.)
-- Backward compatible: DEFAULT 'NSE' preserves existing Indian stock behaviour
-- Applied: 2026-06-01
--
-- To apply:
--   sqlite3 /path/to/derived_metrics_analysis.db < migrations/001_add_exchange_to_screener_companies.sql
--
-- To verify:
--   sqlite3 /path/to/derived_metrics_analysis.db "SELECT DISTINCT exchange FROM screener_companies LIMIT 10;"

ALTER TABLE screener_companies ADD COLUMN exchange TEXT DEFAULT 'NSE';
