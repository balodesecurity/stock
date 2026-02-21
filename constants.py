"""
Constants and Configuration
Centralized configuration values used across all scripts
"""

import os
from pathlib import Path

# ==============================================================================
# PATHS
# ==============================================================================

# Base directory (stock/ is now the base for scripts)
BASE_DIR = Path(__file__).parent.absolute()

# Database (outside stock/ git repo, in parent directory)
DATABASE_NAME = 'derived_metrics_analysis.db'
DATABASE_PATH = BASE_DIR.parent / DATABASE_NAME

# Logs directory (inside stock/)
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Data directory (one level up from stock/)
DATA_DIR = BASE_DIR.parent / 'data'


# ==============================================================================
# DATABASE TABLES
# ==============================================================================

# Primary tables (raw data from sources)
TABLE_QUARTERLY = 'screener_quarterly'
TABLE_ANNUAL_PL = 'screener_annual_pl'
TABLE_CASH_FLOW = 'screener_cash_flow'
TABLE_BALANCE_SHEET = 'screener_balance_sheet'
TABLE_RATIOS = 'screener_ratios'
TABLE_SHAREHOLDING = 'screener_shareholding'
TABLE_DAILY_PRICES = 'screener_daily_prices'
TABLE_COMPANIES = 'screener_companies'
TABLE_PORTFOLIOS = 'portfolios'

# Derived table (calculated metrics)
TABLE_DERIVED = 'derived_metrics_analysis'


# ==============================================================================
# MARKET HOURS (Indian Stock Market)
# ==============================================================================

MARKET_TIMEZONE = 'Asia/Kolkata'
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# Trading days (Monday=0, Sunday=6)
MARKET_DAYS = [0, 1, 2, 3, 4]  # Monday to Friday


# ==============================================================================
# YAHOO FINANCE
# ==============================================================================

# Exchange suffixes
YAHOO_NSE_SUFFIX = '.NS'
YAHOO_BSE_SUFFIX = '.BO'

# Default USD/INR rate (fallback)
DEFAULT_EXCHANGE_RATE = 85.0

# Conversion factor (USD to INR Crores)
USD_TO_INR_CRORES_FACTOR = 10_000_000


# ==============================================================================
# BATCH PROCESSING
# ==============================================================================

# Batch sizes
PRICE_UPDATE_BATCH_SIZE = 50
FUNDAMENTALS_BATCH_SIZE = 10

# Rate limiting
RATE_LIMIT_SECONDS = 0.5


# ==============================================================================
# SQL HELPERS
# ==============================================================================

# Chronological ORDER BY for "Mon YYYY" quarter strings (e.g., "Dec 2025", "Sep 2025")
# Alphabetical sorting is WRONG: Dec < Jun < Mar < Sep
# This sorts by year DESC then month DESC for correct chronological order
QUARTER_ORDER_DESC = """
    CAST(SUBSTR(quarter, -4) AS INTEGER) DESC,
    CASE SUBSTR(quarter, 1, 3)
        WHEN 'Dec' THEN 12 WHEN 'Nov' THEN 11 WHEN 'Oct' THEN 10
        WHEN 'Sep' THEN 9 WHEN 'Aug' THEN 8 WHEN 'Jul' THEN 7
        WHEN 'Jun' THEN 6 WHEN 'May' THEN 5 WHEN 'Apr' THEN 4
        WHEN 'Mar' THEN 3 WHEN 'Feb' THEN 2 WHEN 'Jan' THEN 1
    END DESC
"""


# ==============================================================================
# QUARTERLY METRICS
# ==============================================================================

# Minimum quarters needed for calculations
MIN_QUARTERS_FOR_QOQ = 2
MIN_QUARTERS_FOR_YOY = 5
MIN_QUARTERS_FOR_PROMOTER_TREND = 2

# Promoter trend thresholds
PROMOTER_DECREASE_MAJOR_THRESHOLD = -10  # Percentage

# Yahoo Finance cache: skip companies that failed all ticker resolutions for N days.
# Kept short (3d) so a transient API outage doesn't lock companies out for weeks.
YAHOO_FAILED_CACHE_DAYS = 3


# ==============================================================================
# FIELD MAPPINGS (Yahoo Finance → Screener.in)
# ==============================================================================

# Quarterly financial mappings
QUARTERLY_INCOME_MAPPINGS = [
    ('Total Revenue', 'financials', 'Sales+'),
    ('Net Income', 'financials', 'Net Profit+'),
    ('Operating Income', 'financials', 'Operating Profit'),
    ('Diluted EPS', 'financials', 'EPS in Rs'),
    ('Interest Expense', 'financials', 'Interest'),
    ('Total Expenses', 'financials', 'Expenses+'),
    ('Other Income Expense', 'financials', 'Other Income+'),
    ('Pretax Income', 'financials', 'Profit before tax'),
    ('Reconciled Depreciation', 'financials', 'Depreciation'),
]

# Quarterly cash flow mappings
QUARTERLY_CASHFLOW_MAPPINGS = [
    ('Operating Cash Flow', 'cashflow', 'Operating Cash Flow+'),
    ('Free Cash Flow', 'cashflow', 'Free Cash Flow+'),
]

# Combined quarterly mappings
QUARTERLY_MAPPINGS = QUARTERLY_INCOME_MAPPINGS + QUARTERLY_CASHFLOW_MAPPINGS


# ==============================================================================
# LOGGING
# ==============================================================================

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_LEVEL_DEFAULT = 'INFO'


# ==============================================================================
# DISPLAY FORMATTING
# ==============================================================================

# Progress update frequency
PROGRESS_UPDATE_INTERVAL = 20

# Commit frequency (database)
COMMIT_INTERVAL = 50

# Display widths
COMPANY_CODE_WIDTH = 12
COMPANY_NAME_WIDTH = 30


# ==============================================================================
# URLS
# ==============================================================================

SCREENER_BASE_URL = 'https://www.screener.in'
SCREENER_FILTER_URL = 'https://www.screener.in/screens/3474068/vm/'


