# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An Indian stock analysis system that scrapes financial data from screener.in, fetches live prices from Yahoo Finance, calculates derived metrics, and displays everything in a Streamlit portal. Tracks ~670 companies across multiple industries.

**Database:** `/home/amitbalode/personnel/derived_metrics_analysis.db` (SQLite, ~35 MB)
**Portal:** `stock_portal.py` (Streamlit on port 8501)
**Virtual env:** `/home/amitbalode/personnel/venv/`

## Development Setup

```bash
cd /home/amitbalode/personnel/stock
source /home/amitbalode/personnel/venv/bin/activate
pip install -r requirements.txt
# Note: requirements.txt is incomplete. Also install: streamlit yfinance pytz
# For US stock sync also install: finvizfinance numpy
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
  discover_new_companies      fetch_market_        fetch_market_
  .py (11 AM daily)   data.py             data.py
                       (--yahoo-daily-     (-i yahoo-price-and-recent-quarter
                        change, hourly)     12 PM)
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
                   compute_growth_metrics.py (12 PM daily)
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
| `discover_new_companies.py` | Sync new companies from Screener.in filter + static portfolio + US Finviz screen | Daily 11 AM |
| `discover_new_companies.py --rescrape-annual-all` | Re-scrape annual P&L, balance sheet, cash flow for ALL enabled Indian companies via ScreenerDownloader | Monthly (1st of month, 2 AM) |
| `fetch_market_data.py` | Fetch prices + quarterly fundamentals from Yahoo Finance | Hourly 9 AM-3 PM (quick), Daily 12 PM (-i yahoo-price-and-recent-quarter) |
| `compute_growth_metrics.py` | Calculate all derived metrics from primary tables | Daily 12 PM |
| `cron_full_sync.sh` | Run all 3 crons in sequence (adhoc full sync) | Manual |
| `backfill_sector_industry.py` | One-time/resume script to populate missing sector/industry; caches HTML in `cache/screener_html/` | Manual |

**Important distinction:** `fetch_market_data.py -i yahoo-price-and-recent-quarter` fetches quarterly data from **Yahoo Finance** (fast, ~5 min). It does NOT update `screener_annual_pl`, `screener_balance_sheet`, or `screener_cash_flow`. Annual data (FY results) only comes from ScreenerDownloader via `discover_new_companies.py`. Run `--rescrape-annual-all` after FY results season (April–July) or whenever screener.in publishes consolidated annual data.

### Core Libraries

| File | Purpose |
|------|---------|
| `lib.py` | DB connection, logging, market hours, `ScriptLock` (fcntl-based cron deduplication), `batch_items()` |
| `constants.py` | All configuration: paths, table names, thresholds, `QUARTER_ORDER_DESC` SQL, `STATIC_PORTFOLIO` |
| `screener_downloader.py` | `ScreenerDownloader` class for scraping screener.in |

### Cron Schedule

```cron
0 11 * * *         /home/amitbalode/personnel/stock/cron_discover_new_companies.sh
0 9-15 * * 1-5     /home/amitbalode/personnel/stock/cron_update_prices.sh
0 12 * * 1-5       /home/amitbalode/personnel/stock/cron_update_fundamentals.sh
0 2 1 * *          /home/amitbalode/personnel/stock/cron_refresh_annual.sh
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
**screener_companies** - company_code, company_name, enabled, created_at, source ('sync'/'manual'), exchange ('NSE'/'BSE'/'NYSE'/'NASDAQ'/...)
**portfolios** - portfolio_name, company_code (portfolios: 'Paytmmoney' = Amit's holdings, 'Static' = custom watchlist)
**yahoo_ticker_cache** - Caches successful and failed Yahoo ticker resolutions (NULL ticker = failed; failures expire after `YAHOO_FAILED_CACHE_DAYS=30`)

### screener_companies: source column

`source` distinguishes how a company entered the DB:
- `'sync'` — discovered via the Screener.in filter (`https://www.screener.in/screens/3474068/vm/`) or `STATIC_PORTFOLIO` in `constants.py`
- `'manual'` — explicitly added via the portal "Add Stock" form (calls `discover_new_companies.py --companies CODE`)

`source` is recalculated on every successful `discover_new_companies.py` run. The update is **skipped entirely** if the filter returns 0 companies (guards against accidentally marking everything manual on a failed fetch).

`created_at` is set once at first insert and never overwritten on re-sync.

**Important:** Both `created_at` timestamps (Python `datetime.now()`) and SQLite `CURRENT_TIMESTAMP` may coexist in the DB with different formats (with/without microseconds). Always use `pd.to_datetime(..., format='mixed')` when parsing `created_at` in pandas.

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
| Quality | star_rating (1-5), rating_score (0-100) — **LEGACY, not recalculated by compute_growth_metrics.py** |
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

## Portal Features

`stock_portal.py` is the Streamlit UI. Key sections:

- **Sidebar filters**: portfolio filter (All / Amit's Portfolio / Static Portfolio), search, sentiment, P/E, industry, debt, market cap, 5Y CAGR, promoter holding, FCF/CFO
- **Add Stock** (sidebar): paste a screener.in URL → adds to Static portfolio + triggers `sync_single_company` in background → company appears after ~60s refresh
- **Delete Stock** (sidebar): select a company → confirmation modal → removes from all DB tables
- **KPI cards**: summary stats across filtered companies
- **Main table** (`st.data_editor`): all metrics with delete checkbox; includes Source (SYNC/MANUAL) and First Added date columns
- **Company detail panel**: click a company for detailed metrics breakdown
- **`load_data()`**: cached with `@st.cache_data(ttl=60)`; also runs DB migrations for new columns (`enabled`, `created_at`, `source`) on first call

`stock_portal_old.py` — legacy file, do not modify.

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
Calculated in `fetch_market_data.py`, not `compute_growth_metrics.py`.

### Star Rating — LEGACY (not actively updated)
The `star_rating` and `rating_score` columns exist in `derived_metrics_analysis` but are **not recalculated** by `compute_growth_metrics.py`. They are reference/historical data only.

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

### Via Portal (Manual)
Use the **Add Stock** form in the sidebar — paste a screener.in URL. Sets `source='manual'`.

### Via Static Portfolio (Sync)
Edit `constants.py` and add to `STATIC_PORTFOLIO`:
```python
STATIC_PORTFOLIO = [
    'GGAUTO',      # GG Auto Components Ltd
    'NEWCOMPANY',  # Company Name
]
```
Then run `python discover_new_companies.py` or wait for daily 11 AM sync. Sets `source='sync'`.

### Via Screener.in Filter
Companies from `https://www.screener.in/screens/3474068/vm/` are automatically synced daily. Sets `source='sync'`.

## Schema Migrations

All schema changes are tracked as numbered SQL files in `migrations/`. Always write migrations to be backward compatible (use `ADD COLUMN ... DEFAULT ...` rather than destructive changes).

### Applying to production

```bash
sqlite3 /home/amitbalode/personnel/derived_metrics_analysis.db < migrations/001_add_exchange_to_screener_companies.sql
```

### Migration history

| # | File | Change |
|---|------|--------|
| 001 | `001_add_exchange_to_screener_companies.sql` | Added `exchange TEXT DEFAULT 'NSE'` to `screener_companies` — enables tracking non-Indian stocks (US, etc.) |
| 002 | `002_drop_url_from_screener_companies.sql` | Dropped unused `url` column from `screener_companies` — was written but never read |
| 003 | `003_drop_data_source_from_screener_companies.sql` | Dropped unused `data_source` column from `screener_companies` — was written but never read |

### Exchange values

| Exchange | Notes |
|----------|-------|
| `NSE` | Indian — default for all pre-existing companies |
| `BSE` | Indian — BSE-only listings |
| `NYSE` | US |
| `NASDAQ` | US |

Yahoo Finance ticker suffixes (in `constants.py`): `.NS` = NSE, `.BO` = BSE, no suffix = US.

## Adding New Metrics

1. Add calculation function to `compute_growth_metrics.py`
2. Call it from `update_all_metrics()` function
3. Add any new constants to `constants.py`
4. Test: `python compute_growth_metrics.py`

## Adding New Data Extraction

When adding new screener.in data sections:
1. Identify the HTML section ID on screener.in pages
2. Add a new `_extract_*()` method in `ScreenerDownloader` class
3. Call the method in `download_company_data()` and add to data dictionary

## Logging

Log files in `logs/` with daily rotation:
```
stock_prices_quick_YYYYMMDD.log    (hourly price updates)
stock_prices_full_YYYYMMDD.log     (daily fundamentals)
derived_metrics_YYYYMMDD.log       (daily metrics recalculation)
discover_new_companies_YYYYMMDD.log        (daily company sync)
```

Format: `YYYY-MM-DD HH:MM:SS - LEVEL - MESSAGE`

View logs:
```bash
tail -f logs/derived_metrics_$(date +%Y%m%d).log
grep "ERROR" logs/*.log
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

-- SYNC vs MANUAL companies
SELECT source, COUNT(*) FROM screener_companies GROUP BY source;
```

## Running Commands

```bash
# Activate virtual environment (required before running any script)
source /home/amitbalode/personnel/venv/bin/activate

# Manual price update (force outside market hours)
python fetch_market_data.py -i yahoo-daily-change
# Manual fundamentals + metrics update
python fetch_market_data.py -i yahoo-price-and-recent-quarterpython compute_growth_metrics.py

# Sync new companies
python discover_new_companies.py

# Re-scrape annual P&L, balance sheet, cash flow for ALL Indian companies (run during results season)
python discover_new_companies.py --rescrape-annual-all

# Full adhoc sync (all 3 crons in sequence)
bash cron_full_sync.sh

# Add a single company by code
python discover_new_companies.py --companies TICKER

# Start portal locally
streamlit run stock_portal.py --server.port 8501 --server.headless true
```

## Claude Slash Commands

- `/amit-stock-sync` — runs the full sync (`cron_full_sync.sh`) from within Claude Code

## Rate Limiting

- screener.in: 2-3 second delay between requests
- Yahoo Finance: Bulk fetching in batches of 50 stocks (price), 10 (fundamentals), 0.5s delay
- Price updates only during market hours (9:15 AM - 3:30 PM IST, Mon-Fri); use `--force` to override

## Docker & Cloud Deployment

### Overview
The portal runs as a Docker container on AWS EC2, accessible at **https://alphavest.in**

### Infrastructure
| Resource | Value |
|----------|-------|
| **Domain** | `alphavest.in` (BigRock registrar, Cloudflare DNS + SSL) |
| **EC2 Instance** | `i-0e84f65e1c1b066ef`, `t3.micro`, `ap-south-1` (Mumbai) |
| **Elastic IP** | `13.204.149.14` (permanent, won't change on stop/start) |
| **ECR Repository** | `782818417773.dkr.ecr.ap-south-1.amazonaws.com/stock-portal` |
| **AWS Account** | `782818417773`, IAM user `amitbalode.work` |
| **SSH Key** | `~/.ssh/stock-portal-key.pem` |
| **DB on EC2** | `/home/ec2-user/derived_metrics_analysis.db` |

### SSH into EC2
```bash
ssh -i ~/.ssh/stock-portal-key.pem ec2-user@13.204.149.14
```

### Copy DB from Mac to EC2
```bash
scp -i ~/.ssh/stock-portal-key.pem \
  /Users/abalode/personnel/derived_metrics_analysis.db \
  ec2-user@13.204.149.14:/home/ec2-user/derived_metrics_analysis.db
```

### Redeploy after code changes
```bash
# 1. Build for linux/amd64 (EC2 is x86_64, Mac is ARM — must specify platform)
cd /Users/abalode/personnel/stock
docker buildx build --platform linux/amd64 -t stock-portal:amd64 --load .

# 2. Push to ECR
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 782818417773.dkr.ecr.ap-south-1.amazonaws.com
docker tag stock-portal:amd64 782818417773.dkr.ecr.ap-south-1.amazonaws.com/stock-portal:latest
docker push 782818417773.dkr.ecr.ap-south-1.amazonaws.com/stock-portal:latest

# 3. Pull and restart on EC2
ssh -i ~/.ssh/stock-portal-key.pem ec2-user@13.204.149.14 \
  "aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 782818417773.dkr.ecr.ap-south-1.amazonaws.com && \
   docker pull 782818417773.dkr.ecr.ap-south-1.amazonaws.com/stock-portal:latest && \
   docker stop stock-portal && docker rm stock-portal && \
   docker run -d --name stock-portal --restart unless-stopped -p 8501:8501 \
   -v /home/ec2-user/derived_metrics_analysis.db:/app/derived_metrics_analysis.db \
   782818417773.dkr.ecr.ap-south-1.amazonaws.com/stock-portal:latest"
```

### Local dev with Docker
```bash
cd /Users/abalode/personnel/stock
docker-compose up --build   # first time
docker-compose up           # subsequent runs
docker-compose down         # stop
```
Portal available at http://localhost:8501

### Architecture
- **Cloudflare** sits in front — handles SSL (Flexible mode), DNS, DDoS protection
- **Nginx** on EC2 — reverse proxy from port 80 → Streamlit on port 8501
- **Docker container** — runs Streamlit portal, mounts DB as volume
- **WebSockets** — enabled in Cloudflare (required for Streamlit real-time UI)
