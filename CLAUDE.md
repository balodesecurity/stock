# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An Indian stock analysis system that scrapes financial data from screener.in, fetches live prices from Yahoo Finance, calculates derived metrics, and displays everything in a Streamlit portal. Tracks ~659 companies across multiple industries.

**Database:** `derived_metrics_analysis.db` (SQLite, ~35 MB)
**Portal:** `stock_portal.py` (Streamlit on port 8501)
**Virtual env:** `../venv/` (one level up from the stock/ directory)

## Development Setup

```bash
cd /Users/abalode/personnel/stock
source ../venv/bin/activate
pip install -r requirements.txt
```

## Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                                 │
├─────────────────┬──────────────────┬────────────────────────────┤
│  Screener.in    │  Yahoo Finance   │  Yahoo Finance             │
│  (web scrape)   │  (prices)        │  (fundamentals)            │
└────────┬────────┴────────┬─────────┴──────────┬─────────────────┘
         │                 │                    │
         ▼                 ▼                    ▼
  sync_new_companies  update_stock_        update_stock_
  .py (11 AM daily)   prices_v2.py        prices_v2.py
                       (hourly 9-3)        (--fundamentals 12 PM)
         │                 │                    │
         ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│              PRIMARY TABLES (Raw Data)                            │
│  screener_quarterly, screener_annual_pl, screener_balance_sheet  │
│  screener_cash_flow, screener_ratios, screener_shareholding      │
│  screener_daily_prices, screener_companies, portfolios           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                   update_derived_metrics.py (12 PM daily)
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              DERIVED TABLE (Calculated Metrics Only)              │
│  derived_metrics_analysis                                        │
│  - qoq_profit_growth, yoy_profit_growth, yoy_sales_growth       │
│  - roce, promoter_holding, promoter_trend, sentiment_rating      │
│  - ssgr, npm, nfat, dep_pct, dpr                                │
│  - total_fcf, fcf_category                                       │
│  - pe_ratio, peg_ratio, market_cap, debt_to_equity               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                     stock_portal.py (Streamlit UI)
```

## Active Scripts

### Core Scripts

| Script | Purpose | Schedule |
|--------|---------|----------|
| `sync_new_companies.py` | Sync new companies from Screener.in filter + static portfolio | Daily 11 AM |
| `update_stock_prices_v2.py` | Fetch prices from Yahoo Finance | Hourly 9 AM-3 PM (quick), Daily 12 PM (--fundamentals) |
| `update_derived_metrics.py` | Calculate all derived metrics from primary tables | Daily 12 PM |
| `backfill_sector_industry.py` | One-time/resume script to populate missing sector/industry; caches HTML in `cache/screener_html/` | Manual |

### Core Libraries

| File | Purpose |
|------|---------|
| `lib.py` | DB connection, logging, market hours, `ScriptLock` (fcntl-based cron deduplication), `batch_items()` |
| `constants.py` | All configuration: paths, table names, thresholds, `QUARTER_ORDER_DESC` SQL, `STATIC_PORTFOLIO` |
| `screener_downloader.py` | `ScreenerDownloader` class for scraping screener.in |

### Cron Schedule

```cron
0 11 * * *         /Users/abalode/personnel/stock/cron_sync_companies.sh
0 9-15 * * 1-5     /Users/abalode/personnel/stock/cron_update_prices_v2.sh
0 12 * * 1-5       /Users/abalode/personnel/stock/cron_update_fundamentals.sh
```

## Database Schema

### Primary Tables (Raw Data)

**screener_quarterly** - Sales, Profit, Cash Flow per quarter (~80K rows)
**screener_annual_pl** - Annual P&L statements (~77K rows)
**screener_balance_sheet** - Balance sheet items
**screener_cash_flow** - Cash flow statements
**screener_ratios** - ROCE %, ROE %, Debtor Days, etc.
**screener_shareholding** - Promoters+, FIIs+, DIIs+, Public+
**screener_daily_prices** - current_price, previous_close, day_high, day_low, volume, week_52_high, week_52_low, updated_at
**screener_companies** - company_code, company_name, enabled
**portfolios** - portfolio_name, company_code
**yahoo_ticker_cache** - Caches successful and failed Yahoo ticker resolutions (NULL ticker = failed; failures expire after `YAHOO_FAILED_CACHE_DAYS=30`)

### Derived Table

**derived_metrics_analysis** - All calculated metrics:

| Category | Columns |
|----------|---------|
| Company Info | company_code, company_name, sector, industry |
| FCF | total_fcf, fcf_cfo_ratio, avg_annual_fcf, fcf_category ('Positive'/'Negative'/'Zero') |
| Growth | year1/2/3_sales_growth, q1/2/3_sales_growth, qoq_profit_growth, yoy_profit_growth, yoy_sales_growth |
| SSGR | ssgr, ssgr_prev, npm, nfat, dep_pct, dpr |
| Valuation | net_profit, pe_ratio, peg_ratio, market_cap, book_value |
| Balance Sheet | debt_to_equity |
| Quality | star_rating (1-5), rating_score (0-100) — **LEGACY, not recalculated by update_derived_metrics.py** |
| Promoter | promoter_holding, promoter_trend, promoter_trend_display |
| Sentiment | sentiment_rating (1-5) — actively calculated from 52-week price position |
| Price (via JOIN) | current_price, previous_close, volume, week_52_high, week_52_low |

Portal queries JOIN `screener_daily_prices` for live prices:
```sql
LEFT JOIN (
    SELECT company_code, current_price, previous_close, ...
    FROM screener_daily_prices
    WHERE (company_code, date) IN (
        SELECT company_code, MAX(date) FROM screener_daily_prices GROUP BY company_code
    )
) p ON d.company_code = p.company_code
```

### Data in screener_* tables

Values stored as strings with commas. Convert numerically:
```sql
CAST(REPLACE(value, ',', '') AS REAL)
```

### Quarter String Sorting

Quarters stored as "Mon YYYY" (e.g., "Dec 2025", "Sep 2025"). Alphabetical sort is **wrong**. Always use `QUARTER_ORDER_DESC` from `constants.py`:
```sql
-- Defined in constants.QUARTER_ORDER_DESC
CAST(SUBSTR(quarter, -4) AS INTEGER) DESC,
CASE SUBSTR(quarter, 1, 3)
    WHEN 'Dec' THEN 12 ... WHEN 'Jan' THEN 1
END DESC
```

## Key Formulas

### Free Cash Flow (FCF)
```
FCF = Operating Cash Flow (CFO) + Investing Cash Flow (usually negative)
Total_FCF_10yr = SUM(CFO 10 years) + SUM(Investing 9 years)
fcf_category: 'Positive' / 'Negative' / 'Zero'
```
Edge case: if both CFO and FCF are negative, ratio is forced negative.

### Self-Sustainable Growth Rate (SSGR) - Dr. Vijay Malik
```
SSGR = [(1 - Dep%) + NFAT x NPM x (1 - DPR)] - 1

Components (3-year averages):
- Dep%  = avg_depreciation / avg_net_fixed_assets
- NFAT  = avg_sales / avg_net_fixed_assets
- NPM   = avg_net_profit / avg_sales
- DPR   = avg_dividend_payout_pct / 100

Data sources:
- Sales, Net Profit, Depreciation, Dividend Payout % from Annual P&L
- Fixed Assets+ / Net Block+ from Balance Sheet
```

`ssgr_prev` stores historical SSGR (3–6 year lookback via `year_offset=3`).

Interpretation:
- SSGR > 40%: Exceptional organic growth capability
- SSGR 20-40%: Excellent
- SSGR 10-20%: Good
- SSGR 0-10%: Moderate
- SSGR < 0%: Needs external financing to grow

### Sentiment Rating (1-5)
```
position = (current_price - week_52_low) / (week_52_high - week_52_low) * 100
>=80%: 5 (Very Bullish), >=60%: 4, >=40%: 3, >=20%: 2, <20%: 1 (Very Bearish)
```
Calculated in `update_stock_prices_v2.py`, not `update_derived_metrics.py`.

### Star Rating — LEGACY (not actively updated)
The `star_rating` and `rating_score` columns exist in `derived_metrics_analysis` but are **not recalculated** by `update_derived_metrics.py`. They are reference/historical data only.

### Derived Metrics Calculations

```
Q-o-Q Profit Growth = (Q_latest - Q_previous) / |Q_previous| x 100
Y-o-Y Profit Growth = (Q_latest - Q_4_quarters_ago) / |Q_4_quarters_ago| x 100
Y-o-Y Sales Growth  = (Q_latest - Q_4_quarters_ago) / Q_4_quarters_ago x 100
P/E = Market Cap / Net Profit  (Yahoo primary; fallback: current_price / EPS from screener_annual_pl)
PEG = P/E / Year1 Sales Growth
```

PE/PEG/market_cap: Yahoo Finance values take priority. Computed from screener data only as fallback when Yahoo doesn't provide them.

Promoter Trend (4-quarter analysis):
- stable_or_increased: change >= 0
- decreased_minor: decreased < 10%
- decreased_10_plus: decreased >= 10%

### Dual Data Source for Financials

Financial sector companies report "Revenue+" instead of "Sales+". Throughout the codebase, Sales+ is tried first, with Revenue+ as fallback. This applies to: annual sales growth, NPM, YoY sales calculations.

### 5-Year Sales CAGR (Portal)

Calculated inline in the portal SQL (not pre-stored):
```sql
ROUND((POWER(latest_sales / oldest_sales, 1.0/5) - 1) * 100, 2)
```

## Adding Companies

### Via Static Portfolio

Edit `constants.py` and add to `STATIC_PORTFOLIO`:
```python
STATIC_PORTFOLIO = [
    'GGAUTO',      # GG Auto Components Ltd
    'NEWCOMPANY',  # Company Name
]
```
Then run `python sync_new_companies.py` or wait for daily 11 AM sync.

Company codes must match screener.in URLs: `https://www.screener.in/company/CODE/`

### Via Screener.in Filter

Companies from the filter at `https://www.screener.in/screens/3474068/vm/` are automatically synced daily.

## Adding New Metrics

1. Add calculation function to `update_derived_metrics.py`
2. Call it from `update_all_metrics()` function
3. Add any new constants to `constants.py`
4. Test: `python update_derived_metrics.py`

## Adding New Data Extraction

When adding new screener.in data sections:
1. Identify the HTML section ID on screener.in pages
2. Add a new `_extract_*()` method in `ScreenerDownloader` class
3. Call the method in `download_company_data()` and add to data dictionary

## Logging

Log files in `stock/logs/` with daily rotation:
```
stock_prices_quick_YYYYMMDD.log    (hourly price updates)
stock_prices_full_YYYYMMDD.log     (daily fundamentals)
derived_metrics_YYYYMMDD.log       (daily metrics recalculation)
sync_companies_YYYYMMDD.log        (daily company sync)
```

Format: `YYYY-MM-DD HH:MM:SS - LEVEL - MESSAGE`

View logs:
```bash
tail -f stock/logs/derived_metrics_$(date +%Y%m%d).log
grep "ERROR" stock/logs/*.log
grep "RELIANCE" stock/logs/derived_metrics_*.log
```

## Useful SQL Queries

```sql
-- Best value stocks (high star rating, low P/E, strong FCF)
SELECT company_code, company_name, star_rating, pe_ratio, ssgr, total_fcf, debt_to_equity
FROM derived_metrics_analysis
WHERE star_rating >= 4 AND pe_ratio < 25 AND fcf_category = 'Positive'
ORDER BY pe_ratio ASC;

-- Consistent growers (3-year positive growth)
SELECT company_code, company_name,
       year3_sales_growth as Y3, year2_sales_growth as Y2, year1_sales_growth as Y1,
       pe_ratio, total_fcf
FROM derived_metrics_analysis
WHERE year1_sales_growth > 10 AND year2_sales_growth > 10 AND year3_sales_growth > 10
ORDER BY (year1_sales_growth + year2_sales_growth + year3_sales_growth)/3 DESC;

-- Quality compounders (high SSGR, low debt)
SELECT company_code, company_name, ssgr, debt_to_equity, pe_ratio, total_fcf
FROM derived_metrics_analysis
WHERE ssgr > 30 AND debt_to_equity < 0.5 AND star_rating >= 4
ORDER BY ssgr DESC;

-- Industry leaders
SELECT industry, company_code, company_name, star_rating, pe_ratio, total_fcf, ssgr
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY industry ORDER BY star_rating DESC, total_fcf DESC) as rn
    FROM derived_metrics_analysis WHERE star_rating >= 4
) WHERE rn = 1
ORDER BY star_rating DESC, total_fcf DESC;

-- 10-year profit history from screener data
SELECT year, value as profit_cr
FROM screener_annual_pl
WHERE company_code = 'NH' AND metric = 'Net Profit+' AND year LIKE 'Mar%'
ORDER BY year DESC;

-- Promoter holding for portfolio
SELECT s.company_code, c.company_name, s.value as promoter_pct, s.quarter
FROM screener_shareholding s
JOIN screener_companies c ON s.company_code = c.company_code
WHERE s.metric = 'Promoters+'
  AND s.quarter = (SELECT MAX(quarter) FROM screener_shareholding WHERE company_code = s.company_code)
ORDER BY CAST(REPLACE(REPLACE(s.value, '%', ''), ',', '') AS REAL) DESC;
```

## Running Commands

```bash
# Manual price update (force outside market hours)
python update_stock_prices_v2.py --force

# Manual fundamentals + metrics update
python update_stock_prices_v2.py --fundamentals --force
python update_derived_metrics.py

# Sync new companies
python sync_new_companies.py

# Start portal
cd /Users/abalode/personnel/stock
streamlit run stock_portal.py --server.port 8501

# Database queries
sqlite3 derived_metrics_analysis.db -header -box "YOUR_QUERY_HERE"
```

## Rate Limiting

- screener.in: 2-3 second delay between requests
- Yahoo Finance: Bulk fetching in batches of 50 stocks (price), 10 (fundamentals), 0.5s delay
- Price updates only during market hours (9:15 AM - 3:30 PM IST, Mon-Fri); use `--force` to override
