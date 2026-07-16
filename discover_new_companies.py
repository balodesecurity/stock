#!/usr/bin/env python3
"""
Sync new companies from Screener.in filter to database
Downloads and populates all required fields for the portal
"""

import sqlite3
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import time
from datetime import datetime
import sys
import os
import logging
from logging.handlers import TimedRotatingFileHandler

# Add current directory to path to import existing modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screener_downloader import ScreenerDownloader
from constants import SCREENER_FILTER_URL, DATABASE_PATH, QUARTER_ORDER_DESC, LOGS_DIR, DEFAULT_EXCHANGE_RATE
try:
    from us_stock_downloader import USStockDownloader
    _US_DOWNLOADER_AVAILABLE = USStockDownloader is not None
except (ImportError, Exception):
    USStockDownloader = None
    _US_DOWNLOADER_AVAILABLE = False

# Optional US-sync dependencies
try:
    import numpy as np
    from finvizfinance.screener.overview import Overview as FinvizOverview
    _FINVIZ_AVAILABLE = True
except ImportError:
    _FINVIZ_AVAILABLE = False

# Setup logging
def setup_logging():
    """Setup logging with daily rotation"""
    log_dir = LOGS_DIR
    os.makedirs(log_dir, exist_ok=True)

    # Log filename with date
    log_file = os.path.join(log_dir, f'discover_new_companies_{datetime.now().strftime("%Y%m%d")}.log')

    # Create logger
    logger = logging.getLogger('discover_new_companies')
    logger.setLevel(logging.INFO)

    # Remove existing handlers
    logger.handlers = []

    # File handler with daily rotation
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

logger = setup_logging()

def get_static_portfolio():
    """Fetch company codes from the Static portfolio in the DB."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT company_code FROM portfolios WHERE portfolio_name = 'Static'")
    codes = [row[0] for row in cursor.fetchall()]
    conn.close()
    return codes

def get_companies_from_filter():
    """Fetch company codes from all pages of Screener.in filter"""
    logger.info(f"Fetching companies from: {SCREENER_FILTER_URL}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    company_codes = []
    page = 1

    try:
        while True:
            url = f"{SCREENER_FILTER_URL}?page={page}"
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find all company links in the table
            found_on_page = 0
            for link in soup.select('table a[href*="/company/"]'):
                href = link.get('href', '')
                parts = href.split('/')
                if len(parts) >= 3 and parts[1] == 'company':
                    code = parts[2]
                    if code and code not in company_codes:
                        company_codes.append(code)
                        found_on_page += 1

            logger.info(f"  Page {page}: found {found_on_page} new companies")

            if found_on_page == 0:
                break

            # Check if there's a next page
            next_link = soup.select_one('a[href*="page="]:contains("Next")')
            if not next_link:
                # Also check for a page number greater than current
                page_links = soup.select(f'a[href*="page={page + 1}"]')
                if not page_links:
                    break

            page += 1
            time.sleep(2)  # Rate limiting

        logger.info(f"Found {len(company_codes)} companies in filter ({page} pages)")
        return company_codes

    except Exception as e:
        logger.info(f"Error fetching companies from filter (page {page}): {e}")
        return company_codes  # Return whatever we collected so far

def get_existing_companies():
    """Get list of companies already in database"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT company_code FROM derived_metrics_analysis")
    existing = [row[0] for row in cursor.fetchall()]
    conn.close()
    return existing

def parse_value(value_str):
    """Parse string value to float"""
    if not value_str or value_str == '-' or value_str == 'N/A':
        return None
    try:
        return float(value_str.replace(',', ''))
    except:
        return None

def calculate_fcf_metrics(company_code):
    """Calculate FCF metrics from quarterly data"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Get cash flow data for FCF calculation
    cursor.execute(f"""
        SELECT quarter, value
        FROM screener_quarterly
        WHERE company_code = ? AND metric = 'Operating Cash Flow+'
        ORDER BY {QUARTER_ORDER_DESC}
        LIMIT 10
    """, (company_code,))
    cfo_data = cursor.fetchall()

    cursor.execute(f"""
        SELECT quarter, value
        FROM screener_quarterly
        WHERE company_code = ? AND metric = 'Free Cash Flow+'
        ORDER BY {QUARTER_ORDER_DESC}
        LIMIT 10
    """, (company_code,))
    fcf_data = cursor.fetchall()

    conn.close()

    # Calculate total FCF and FCF/CFO ratio
    total_fcf = 0
    total_cfo = 0

    for quarter, value in fcf_data:
        fcf_val = parse_value(value)
        if fcf_val is not None:
            total_fcf += fcf_val

    for quarter, value in cfo_data:
        cfo_val = parse_value(value)
        if cfo_val is not None:
            total_cfo += cfo_val

    fcf_cfo_ratio = None
    if total_cfo and total_cfo != 0:
        fcf_cfo_ratio = (total_fcf / total_cfo) * 100
        # When both FCF and CFO are negative, ratio appears positive but is misleading - force negative
        if total_fcf < 0 and total_cfo < 0:
            fcf_cfo_ratio = -abs(fcf_cfo_ratio)

    return total_fcf if total_fcf else None, fcf_cfo_ratio

def calculate_qoq_yoy_profit(company_code):
    """Calculate Q-o-Q and Y-o-Y profit growth"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT quarter, value
        FROM screener_quarterly
        WHERE company_code = ? AND metric = 'Net Profit+'
        ORDER BY {QUARTER_ORDER_DESC}
        LIMIT 5
    """, (company_code,))

    results = cursor.fetchall()
    conn.close()

    if len(results) < 2:
        return None, None, None

    profits = []
    latest_quarter = None
    for quarter, value in results:
        profit = parse_value(value)
        if profit is not None:
            profits.append((quarter, profit))
            if latest_quarter is None:
                latest_quarter = quarter

    if len(profits) < 2:
        return None, None, latest_quarter

    # Q-o-Q
    qoq = None
    if profits[1][1] != 0:
        qoq = ((profits[0][1] - profits[1][1]) / profits[1][1]) * 100

    # Y-o-Y (4 quarters back)
    yoy = None
    if len(profits) >= 5 and profits[4][1] != 0:
        yoy = ((profits[0][1] - profits[4][1]) / profits[4][1]) * 100

    return qoq, yoy, latest_quarter

def calculate_yoy_sales(company_code):
    """Calculate Y-o-Y sales growth"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT quarter, value
        FROM screener_quarterly
        WHERE company_code = ? AND metric = 'Sales+'
        ORDER BY {QUARTER_ORDER_DESC}
        LIMIT 5
    """, (company_code,))

    results = cursor.fetchall()
    conn.close()

    if len(results) < 5:
        return None

    sales_data = []
    for quarter, value in results:
        sales = parse_value(value)
        if sales is not None:
            sales_data.append((quarter, sales))

    if len(sales_data) < 5:
        return None

    latest_sales = sales_data[0][1]
    year_ago_sales = sales_data[4][1]

    if latest_sales and year_ago_sales and year_ago_sales != 0:
        return ((latest_sales - year_ago_sales) / year_ago_sales) * 100

    return None

def calculate_promoter_trend(company_code):
    """Calculate promoter holding trend"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT quarter, value
        FROM screener_shareholding
        WHERE company_code = ? AND metric = 'Promoters+'
        ORDER BY {QUARTER_ORDER_DESC}
        LIMIT 4
    """, (company_code,))

    results = cursor.fetchall()
    conn.close()

    if len(results) < 4:
        return None, None

    holdings = []
    for quarter, value in results:
        holding = parse_value(value)
        if holding is not None:
            holdings.append(holding)

    if len(holdings) < 4:
        return None, None

    latest = holdings[0]
    oldest = holdings[-1]
    change = latest - oldest
    change_pct = (change / oldest * 100) if oldest > 0 else 0

    if change >= 0:
        trend = 'stable_or_increased'
        trend_display = f"🟢 {latest:.1f}%"
    elif change_pct <= -10:
        trend = 'decreased_10_plus'
        trend_display = f"🔴 {latest:.1f}% ({change:+.1f}%)"
    else:
        trend = 'decreased_minor'
        trend_display = f"🟡 {latest:.1f}% ({change:+.1f}%)"

    return trend, trend_display

def get_roce(company_code):
    """Get ROCE from ratios table"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT value, year
        FROM screener_ratios
        WHERE company_code = ? AND metric = 'ROCE %'
        ORDER BY year DESC
        LIMIT 1
    """, (company_code,))

    result = cursor.fetchone()
    conn.close()

    if result:
        roce_str, year = result
        try:
            return float(roce_str.replace('%', '').strip())
        except:
            return None
    return None

def fetch_yahoo_data(company_code):
    """Fetch data from Yahoo Finance"""
    logger.info(f"  Fetching Yahoo Finance data for {company_code}...")

    for suffix in ['.NS', '.BO']:
        try:
            ticker = yf.Ticker(company_code + suffix)
            info = ticker.info

            # Get current price
            current_price = info.get('currentPrice') or info.get('regularMarketPrice')
            previous_close = info.get('previousClose')

            # Get other data
            market_cap_raw = info.get('marketCap')
            market_cap = market_cap_raw / 10000000 if market_cap_raw else None  # Convert to Crores

            pe_ratio = info.get('trailingPE')
            peg_ratio = info.get('pegRatio')
            book_value = info.get('bookValue')
            week_52_high = info.get('fiftyTwoWeekHigh')
            week_52_low = info.get('fiftyTwoWeekLow')

            # Calculate PEG if not available
            if not peg_ratio:
                pe = info.get('trailingPE') or info.get('forwardPE')
                earnings_growth = info.get('earningsGrowth')
                if pe and earnings_growth and earnings_growth != 0:
                    growth_pct = earnings_growth * 100
                    peg_ratio = pe / growth_pct

            # Get company name
            company_name = info.get('longName') or info.get('shortName')
            industry = info.get('industry')

            return {
                'company_name': company_name,
                'industry': industry,
                'current_price': current_price,
                'previous_close': previous_close,
                'market_cap': market_cap,
                'pe_ratio': pe_ratio,
                'peg_ratio': peg_ratio,
                'book_value': book_value,
                'week_52_high': week_52_high,
                'week_52_low': week_52_low
            }

        except Exception as e:
            continue

    logger.info(f"  ⚠️  Could not fetch Yahoo Finance data for {company_code}")
    return None

def calculate_sentiment(current_price, week_52_high, week_52_low):
    """Calculate sentiment rating based on 52-week range"""
    if not current_price or not week_52_high or not week_52_low:
        return None

    if week_52_high == week_52_low:
        return 3

    position = (current_price - week_52_low) / (week_52_high - week_52_low)

    if position >= 0.8:
        return 5
    elif position >= 0.6:
        return 4
    elif position >= 0.4:
        return 3
    elif position >= 0.2:
        return 2
    else:
        return 1

def insert_data_section(conn, company_code, section_name, data_rows, table_name, period_type='year'):
    """Insert data from a section into appropriate table"""
    if not data_rows:
        return 0

    cursor = conn.cursor()
    inserted = 0

    for row in data_rows:
        metric = row.get('', '').strip()
        if not metric:
            continue

        # Get all period columns (quarters or years)
        periods = [k for k in row.keys() if k and k != '']

        for period in periods:
            value = row.get(period, '')

            if value:  # Only insert non-empty values
                try:
                    cursor.execute(f"""
                        INSERT OR REPLACE INTO {table_name}
                        (company_code, metric, {period_type}, value)
                        VALUES (?, ?, ?, ?)
                    """, (company_code, metric, period, value))
                    inserted += 1
                except Exception as e:
                    pass  # Silently ignore errors

    return inserted

def import_screener_data_to_db(company_code, data, source='sync'):
    """Import screener data into database tables"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # Insert company metadata — preserve created_at for existing companies
        cursor.execute("""
            INSERT INTO screener_companies
            (company_code, company_name, report_type, last_updated, created_at, source)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_code) DO UPDATE SET
                company_name = excluded.company_name,
                report_type  = excluded.report_type,
                last_updated = excluded.last_updated
        """, (
            company_code,
            data.get('company_name'),
            data.get('report_type'),
            datetime.now(),
            datetime.now(),
            source
        ))

        # Insert each data section
        sections = [
            ('quarterly_results', 'screener_quarterly', 'quarter'),
            ('annual_profit_loss', 'screener_annual_pl', 'year'),
            ('balance_sheet', 'screener_balance_sheet', 'year'),
            ('cash_flow', 'screener_cash_flow', 'year'),
            ('ratios', 'screener_ratios', 'year'),
            ('shareholding', 'screener_shareholding', 'quarter'),
        ]

        total_rows = 0
        for section_key, table_name, period_type in sections:
            section_data = data.get(section_key, [])
            count = insert_data_section(conn, company_code, section_key, section_data, table_name, period_type)
            total_rows += count

        conn.commit()
        conn.close()
        return total_rows > 0

    except Exception as e:
        conn.close()
        logger.info(f"  ✗ Error importing screener data: {e}")
        return False

def add_company_to_db(company_code, source='sync'):
    """Add new company with all required fields"""
    logger.info("")
    logger.info("="*80)
    logger.info(f"Adding new company: {company_code}")
    logger.info("="*80)

    # Step 1: Download Screener.in data
    logger.info("Step 1: Downloading Screener.in data...")
    downloader = ScreenerDownloader()

    try:
        data = downloader.download_company_data(company_code, 'consolidated')
        if not data:
            logger.info("  ✗ Failed to download data from Screener.in")
            return False

        # If consolidated has no usable column data, fall back to base URL (standalone)
        if not downloader._has_valid_financial_data(data):
            logger.info("  ⚠️  No financial data in consolidated, trying base URL...")
            time.sleep(2)
            base_data = downloader.download_company_data(company_code, '')
            if base_data and downloader._has_valid_financial_data(base_data):
                data = base_data
                logger.info("  ✓ Using base URL data")

        # Import to database
        if not import_screener_data_to_db(company_code, data, source=source):
            logger.info("  ✗ Failed to import data to database")
            return False

        logger.info("  ✓ Screener.in data downloaded and saved")

    except Exception as e:
        logger.info(f"  ✗ Error downloading Screener data: {e}")
        return False

    time.sleep(2)  # Rate limiting

    # Step 2: Fetch Yahoo Finance data
    logger.info("Step 2: Fetching Yahoo Finance data...")
    yahoo_data = fetch_yahoo_data(company_code)

    if not yahoo_data:
        yahoo_data = {
            'company_name': None,
            'industry': None,
            'current_price': None,
            'previous_close': None,
            'market_cap': None,
            'pe_ratio': None,
            'peg_ratio': None,
            'book_value': None,
            'week_52_high': None,
            'week_52_low': None
        }
    else:
        logger.info("  ✓ Yahoo Finance data fetched")

    # Step 3: Calculate all metrics
    logger.info("Step 3: Calculating metrics...")

    total_fcf, fcf_cfo_ratio = calculate_fcf_metrics(company_code)
    qoq_profit, yoy_profit, latest_quarter = calculate_qoq_yoy_profit(company_code)
    yoy_sales = calculate_yoy_sales(company_code)
    promoter_trend, promoter_trend_display = calculate_promoter_trend(company_code)
    roce = get_roce(company_code)
    sentiment = calculate_sentiment(
        yahoo_data.get('current_price'),
        yahoo_data.get('week_52_high'),
        yahoo_data.get('week_52_low')
    )

    logger.info("  ✓ Metrics calculated")

    # Step 4: Insert into derived_metrics_analysis table
    logger.info("Step 4: Inserting into derived_metrics_analysis table...")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO derived_metrics_analysis (
                company_code, company_name, industry, sector,
                current_price, previous_close,
                market_cap, pe_ratio, peg_ratio, book_value,
                week_52_high, week_52_low,
                sentiment_rating,
                total_fcf, fcf_cfo_ratio,
                qoq_profit_growth, yoy_profit_growth, yoy_sales_growth,
                latest_quarter,
                promoter_trend, promoter_trend_display,
                roce,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            company_code,
            yahoo_data.get('company_name'),
            data.get('industry'),
            data.get('sector'),
            yahoo_data.get('current_price'),
            yahoo_data.get('previous_close'),
            yahoo_data.get('market_cap'),
            yahoo_data.get('pe_ratio'),
            yahoo_data.get('peg_ratio'),
            yahoo_data.get('book_value'),
            yahoo_data.get('week_52_high'),
            yahoo_data.get('week_52_low'),
            sentiment,
            total_fcf,
            fcf_cfo_ratio,
            qoq_profit,
            yoy_profit,
            yoy_sales,
            latest_quarter,
            promoter_trend,
            promoter_trend_display,
            roce
        ))

        conn.commit()
        conn.close()

        logger.info(f"  ✓ Successfully added {company_code} to database")
        company_name = yahoo_data.get('company_name') or 'N/A'
        current_price = yahoo_data.get('current_price')
        logger.info(f"    Company: {company_name}")
        if current_price:
            logger.info(f"    Price: ₹{current_price:.2f}")
        else:
            logger.info("    Price: N/A")
        if fcf_cfo_ratio:
            logger.info(f"    FCF/CFO: {fcf_cfo_ratio:.1f}%")
        else:
            logger.info("    FCF/CFO: N/A")
        if qoq_profit:
            logger.info(f"    Q-o-Q Profit: {qoq_profit:.1f}%")
        else:
            logger.info("    Q-o-Q Profit: N/A")
        if yoy_profit:
            logger.info(f"    Y-o-Y Profit: {yoy_profit:.1f}%")
        else:
            logger.info("    Y-o-Y Profit: N/A")
        if yoy_sales:
            logger.info(f"    Y-o-Y Sales: {yoy_sales:.1f}%")
        else:
            logger.info("    Y-o-Y Sales: N/A")

        return True

    except Exception as e:
        conn.close()
        logger.info(f"  ✗ Error inserting into database: {e}")
        return False

def backfill_sector_industry():
    """Backfill sector/industry for existing companies that are missing it.

    Checks for cached HTML on disk first; only hits screener.in if no cache exists.
    """
    from pathlib import Path
    from constants import BASE_DIR

    cache_dir = BASE_DIR / 'cache' / 'screener_html'
    cache_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT company_code FROM derived_metrics_analysis
        WHERE sector IS NULL OR sector = '' OR industry IS NULL OR industry = ''
        ORDER BY company_code
    """)
    companies = [row[0] for row in cursor.fetchall()]

    if not companies:
        logger.info("✓ All companies already have sector/industry.")
        conn.close()
        return

    logger.info(f"Backfilling sector/industry for {len(companies)} companies...")

    downloader = ScreenerDownloader()
    updated = 0
    failed = 0

    for i, code in enumerate(companies, 1):
        cache_file = cache_dir / f"{code}.html"

        try:
            if cache_file.exists():
                html_content = cache_file.read_bytes()
                source = "cache"
            else:
                url = f"{downloader.BASE_URL}/company/{code}/consolidated/"
                response = downloader.session.get(url, timeout=15)
                response.raise_for_status()
                html_content = response.content
                cache_file.write_bytes(html_content)
                source = "web"
                time.sleep(2)

            soup = BeautifulSoup(html_content, 'lxml')
            result = downloader._extract_sector_industry(soup)
            sector = result.get('sector')
            industry = result.get('industry')

            if sector or industry:
                cursor.execute("""
                    UPDATE derived_metrics_analysis
                    SET sector = ?, industry = ?
                    WHERE company_code = ?
                """, (sector, industry, code))
                conn.commit()
                updated += 1
                logger.info(f"  [{i}/{len(companies)}] {code} [{source}] sector={sector}, industry={industry}")
            else:
                logger.info(f"  [{i}/{len(companies)}] {code} [{source}] no sector/industry found")

        except Exception as e:
            failed += 1
            logger.info(f"  [{i}/{len(companies)}] {code} ERROR: {e}")

    conn.close()
    logger.info(f"Backfill done. Updated: {updated}, Failed: {failed}, Total: {len(companies)}")


def backfill_standalone_financials():
    """Re-download standalone data for enabled companies that have no quarterly financial data.

    This handles companies where consolidated page exists but has no financials
    (e.g., companies that only file standalone results).
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Find enabled companies missing any key financial table (quarterly, annual P&L, or balance sheet)
    cursor.execute("""
        SELECT c.company_code FROM screener_companies c
        LEFT JOIN screener_quarterly q ON c.company_code = q.company_code
        LEFT JOIN screener_annual_pl a ON c.company_code = a.company_code
        LEFT JOIN screener_balance_sheet b ON c.company_code = b.company_code
        WHERE c.enabled = 1 AND (q.company_code IS NULL OR a.company_code IS NULL OR b.company_code IS NULL)
        GROUP BY c.company_code
        ORDER BY c.company_code
    """)
    companies = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not companies:
        logger.info("✓ All enabled companies have quarterly data.")
        return

    logger.info(f"Found {len(companies)} enabled companies with no quarterly data: {', '.join(companies)}")

    downloader = ScreenerDownloader()
    fixed = 0

    for i, code in enumerate(companies, 1):
        try:
            # Try base URL (no consolidated/standalone suffix) — works for companies
            # that only have one set of financials
            data = downloader.download_company_data(code, '')
            if not data:
                logger.info(f"  [{i}/{len(companies)}] {code}: download failed")
                time.sleep(3)
                continue

            has_financials = any(data.get(key) for key in ['quarterly_results', 'annual_profit_loss', 'balance_sheet'])
            if has_financials:
                import_screener_data_to_db(code, data)
                fixed += 1
                logger.info(f"  [{i}/{len(companies)}] {code}: ✓ imported data")
            else:
                logger.info(f"  [{i}/{len(companies)}] {code}: no financial data available")

            time.sleep(3)

        except Exception as e:
            logger.info(f"  [{i}/{len(companies)}] {code}: ERROR {e}")

    logger.info(f"Backfill done. Fixed: {fixed}/{len(companies)}")


def ensure_enabled_column():
    """Add 'enabled' column to screener_companies if it doesn't exist"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE screener_companies ADD COLUMN enabled INTEGER DEFAULT 1")
        conn.commit()
        logger.info("Added 'enabled' column to screener_companies")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.close()


def update_enabled_status(active_companies):
    """Update enabled status for all companies based on active set"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    if not active_companies:
        conn.close()
        return

    placeholders = ','.join('?' for _ in active_companies)
    active_list = list(active_companies)

    # Enable active companies
    cursor.execute(f"""
        UPDATE screener_companies SET enabled = 1
        WHERE company_code IN ({placeholders})
    """, active_list)

    # Disable inactive companies
    cursor.execute(f"""
        UPDATE screener_companies SET enabled = 0
        WHERE company_code NOT IN ({placeholders})
    """, active_list)

    conn.commit()

    # Log counts
    cursor.execute("SELECT enabled, COUNT(*) FROM screener_companies GROUP BY enabled")
    counts = dict(cursor.fetchall())
    enabled = counts.get(1, 0)
    disabled = counts.get(0, 0)
    logger.info(f"Enabled: {enabled}, Disabled: {disabled}")

    conn.close()


def main():
    """Main sync function"""
    logger.info("="*80)
    logger.info("SYNCING NEW COMPANIES FROM SCREENER.IN FILTER + STATIC PORTFOLIO")
    logger.info("="*80)
    logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    # Ensure enabled column exists
    ensure_enabled_column()

    # Get companies from filter
    filter_companies = get_companies_from_filter()
    logger.info(f"Found {len(filter_companies)} companies in Screener.in filter")

    # Get companies from static portfolio
    static_portfolio = get_static_portfolio()
    logger.info(f"Found {len(static_portfolio)} companies in static portfolio: {', '.join(static_portfolio) if static_portfolio else 'None'}")

    # Combine both sources (remove duplicates)
    all_companies = list(set(filter_companies + static_portfolio))
    logger.info(f"Total unique companies from both sources: {len(all_companies)}")

    if not all_companies:
        logger.info("No companies found in any source. Exiting.")
        return

    # Get existing companies
    existing_companies = get_existing_companies()
    logger.info(f"Existing companies in DB: {len(existing_companies)}")

    # Find new companies
    new_companies = [code for code in all_companies if code not in existing_companies]

    logger.info("")
    logger.info(f"New companies to add: {len(new_companies)}")

    if new_companies:
        logger.info(f"Companies: {', '.join(new_companies)}")
        logger.info("")

        # Add each new company
        added = 0
        failed = 0

        for company_code in new_companies:
            try:
                if add_company_to_db(company_code):
                    added += 1
                else:
                    failed += 1

                # Rate limiting between companies
                time.sleep(3)

            except Exception as e:
                logger.info(f"✗ Unexpected error processing {company_code}: {e}")
                failed += 1

        logger.info("")
        logger.info(f"✓ Added: {added}/{len(new_companies)}")
        logger.info(f"✗ Failed: {failed}/{len(new_companies)}")
    else:
        logger.info("✓ No new companies to add.")

    # Backfill company_name from screener_companies where derived table has NULL
    logger.info("")
    logger.info("-"*80)
    logger.info("BACKFILL: COMPANY NAMES")
    logger.info("-"*80)
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE derived_metrics_analysis
        SET company_name = (
            SELECT company_name FROM screener_companies
            WHERE screener_companies.company_code = derived_metrics_analysis.company_code
        )
        WHERE company_name IS NULL OR company_name = ''
    """)
    backfilled_names = cursor.rowcount
    conn.commit()
    conn.close()
    if backfilled_names > 0:
        logger.info(f"✓ Backfilled company_name for {backfilled_names} companies")
    else:
        logger.info("✓ All companies already have names.")

    # Backfill: re-download standalone data for enabled companies with no quarterly data
    logger.info("")
    logger.info("-"*80)
    logger.info("BACKFILL: STANDALONE FINANCIALS")
    logger.info("-"*80)
    backfill_standalone_financials()

    # Backfill sector/industry for any companies missing it
    logger.info("")
    logger.info("-"*80)
    logger.info("BACKFILL: SECTOR & INDUSTRY")
    logger.info("-"*80)
    backfill_sector_industry()

    # Update enabled status based on active company set
    logger.info("")
    logger.info("-"*80)
    logger.info("UPDATE ENABLED STATUS")
    logger.info("-"*80)

    # Build active set from all 3 sources
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT company_code FROM portfolios")
    portfolio_companies = [row[0] for row in cursor.fetchall()]
    conn.close()

    active_set = set(filter_companies + static_portfolio + portfolio_companies)
    logger.info(f"Active companies: {len(active_set)} (filter={len(filter_companies)}, portfolios={len(portfolio_companies)}, static={len(static_portfolio)})")
    update_enabled_status(active_set)

    # Update source: sync = in filter/static, manual = everything else
    # Only run if filter fetch succeeded — skip entirely if filter returned nothing
    # to avoid accidentally marking everything manual on a failed run.
    logger.info("")
    logger.info("-"*80)
    logger.info("UPDATE SOURCE (SYNC vs MANUAL)")
    logger.info("-"*80)
    if not filter_companies:
        logger.warning("⚠ Skipping source update — filter returned 0 companies (possible fetch failure).")
    else:
        sync_set = list(set(filter_companies + static_portfolio))
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        placeholders = ','.join('?' for _ in sync_set)
        cursor.execute(f"UPDATE screener_companies SET source = 'sync' WHERE company_code IN ({placeholders})", sync_set)
        cursor.execute(f"UPDATE screener_companies SET source = 'manual' WHERE company_code NOT IN ({placeholders})", sync_set)
        conn.commit()
        cursor.execute("SELECT source, COUNT(*) FROM screener_companies GROUP BY source")
        counts = dict(cursor.fetchall())
        conn.close()
        logger.info(f"sync={counts.get('sync', 0)}, manual={counts.get('manual', 0)}")

    # Sync US companies (Finviz + yfinance)
    sync_us_companies()

    logger.info("")
    logger.info("="*80)
    logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)

def _refresh_screener_data(company_code):
    """Re-download Screener.in financials for an existing company and upsert into DB."""
    downloader = ScreenerDownloader()
    try:
        data = downloader.download_company_data(company_code, 'consolidated')
        if not data:
            logger.info("  ✗ No data returned from Screener.in (consolidated)")
            return False
        if not downloader._has_valid_financial_data(data):
            logger.info("  ⚠️  No financials in consolidated, trying base URL...")
            time.sleep(2)
            base_data = downloader.download_company_data(company_code, '')
            if base_data and downloader._has_valid_financial_data(base_data):
                data = base_data
                logger.info("  ✓ Using base URL data")
        if not import_screener_data_to_db(company_code, data, source='manual'):
            logger.info("  ✗ Failed to import Screener data to DB")
            return False
        logger.info("  ✓ Screener.in data refreshed")
        return True
    except Exception as e:
        logger.info(f"  ✗ Error refreshing Screener data: {e}")
        return False


def sync_single_company(company_code):
    """Targeted sync for a single company — skips filter fetch, just downloads and enables."""
    logger.info("="*80)
    logger.info(f"TARGETED SYNC: {company_code}")
    logger.info("="*80)
    logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    ensure_enabled_column()

    existing = get_existing_companies()
    if company_code in existing:
        # Company row exists — but re-download financials in case they're missing or stale
        logger.info(f"✓ {company_code} already in DB — refreshing financial data from Screener.in...")
        ok = _refresh_screener_data(company_code)
        if not ok:
            logger.info(f"✗ Failed to refresh {company_code} from Screener.in.")
            return
    else:
        ok = add_company_to_db(company_code, source='manual')
        if not ok:
            logger.info(f"✗ Failed to add {company_code}.")
            return

    # Mark the company as enabled
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute(
        "UPDATE screener_companies SET enabled = 1 WHERE company_code = ?",
        (company_code,)
    )
    conn.commit()
    conn.close()
    logger.info(f"✓ {company_code} enabled.")

    # Fetch live price now that company is confirmed in DB
    logger.info(f"Fetching live price for {company_code}...")
    from fetch_market_data import update_prices_quick
    update_prices_quick(company_filter=[company_code])

    # Recalculate all derived metrics so the new company is fully populated
    logger.info(f"Recalculating derived metrics for all companies...")
    from compute_growth_metrics import update_all_metrics
    update_all_metrics()

    logger.info("="*80)
    logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)


# ── US Stock Sync ─────────────────────────────────────────────────────────────

# Maps yfinance exchange codes to canonical names stored in screener_companies.exchange
_YF_EXCHANGE_MAP = {
    'NYQ': 'NYSE', 'NYE': 'NYSE',
    'NMS': 'NASDAQ', 'NGM': 'NASDAQ', 'NCM': 'NASDAQ', 'NAS': 'NASDAQ',
    'ASE': 'AMEX',
}
_US_EXCHANGES = {'NYSE', 'NASDAQ', 'AMEX'}


def _get_us_candidates_from_finviz():
    """Phase 1: Finviz pre-screen. Returns list of ticker symbols (~300-600)."""
    logger.info("Fetching US candidates from Finviz pre-screen...")
    try:
        fov = FinvizOverview()
        fov.set_filter(filters_dict={
            "Market Cap.":       "+Micro (over $50mln)",
            "InsiderOwnership":  "Over 10%",
            "Net Profit Margin": "Positive (>0%)",
            "Country":           "USA",
        })
        df = fov.screener_view()
        symbols = df["Ticker"].tolist()
        logger.info(f"  Finviz returned {len(symbols)} candidates")
        return symbols
    except Exception as e:
        logger.error(f"  Finviz pre-screen failed: {e}")
        return []


def _fetch_us_company_metrics(symbol):
    """Phase 2: yfinance deep metrics for one US stock. Returns dict or None if filtered out."""
    try:
        t    = yf.Ticker(symbol)
        info = t.info

        market_cap    = info.get("marketCap") or 0
        current_ratio = info.get("currentRatio")
        insider_pct   = (info.get("heldPercentInsiders") or 0) * 100

        # Cheap pre-filter before hitting financials endpoints
        if current_ratio is not None and current_ratio <= 1.25:
            return None
        if insider_pct <= 10:
            return None

        fin = t.financials
        if fin is None or fin.empty:
            return None

        def _row(df, *names):
            for n in names:
                if n in df.index:
                    return df.loc[n]
            return None

        rev_row  = _row(fin, "Total Revenue", "Revenue")
        ebit_row = _row(fin, "EBIT", "Operating Income", "Ebit")
        int_row  = _row(fin, "Interest Expense", "Interest Expense Non Operating")
        ni_row   = _row(fin, "Net Income", "Net Income Common Stockholders")

        revenues     = [v for v in (rev_row.values if rev_row is not None else [])
                        if v is not None and not np.isnan(v)]
        ebit         = ebit_row.iloc[0] if ebit_row is not None else None
        interest_exp = abs(int_row.iloc[0] or 0) if int_row is not None else None
        net_income   = ni_row.iloc[0] if ni_row is not None else None

        if not net_income or net_income <= 0:
            return None

        def _cagr(years):
            if len(revenues) <= years:
                return None
            r, p = revenues[0], revenues[years]
            if not r or not p or p <= 0 or r <= 0:
                return None
            return (r / p) ** (1.0 / years) - 1

        ttm_growth = _cagr(1)
        growth_3y  = _cagr(3)

        interest_coverage = None
        if ebit is not None and interest_exp and interest_exp > 0:
            interest_coverage = ebit / interest_exp

        bs   = t.balance_sheet
        roce = None
        if bs is not None and not bs.empty and ebit is not None:
            ta_row = _row(bs, "Total Assets")
            cl_row = _row(bs, "Current Liabilities", "Total Current Liabilities")
            if ta_row is not None and cl_row is not None:
                ta = ta_row.iloc[0]
                cl = cl_row.iloc[0]
                if ta and cl and (ta - cl) > 0:
                    roce = (ebit / (ta - cl)) * 100

        # Quality filters (mirrors us_stock_screener.py apply_filters)
        if current_ratio is not None and current_ratio <= 1.25:
            return None
        if interest_coverage is not None and interest_coverage <= 1:
            return None
        if insider_pct <= 10:
            return None
        if ttm_growth is not None and growth_3y is not None and ttm_growth <= growth_3y:
            return None  # Require accelerating growth
        if roce is not None and roce <= 2:
            return None

        exchange = _YF_EXCHANGE_MAP.get(info.get('exchange', ''), 'NYSE')

        # Convert market cap: USD → INR Crores (1M USD * rate / 10 = Cr)
        market_cap_cr = round(market_cap / 1e6 * DEFAULT_EXCHANGE_RATE / 10, 2) if market_cap else None

        return {
            'symbol':             symbol,
            'company_name':       info.get('longName') or info.get('shortName') or symbol,
            'exchange':           exchange,
            'sector':             info.get('sector'),
            'industry':           info.get('industry'),
            'market_cap_cr':      market_cap_cr,
            'pe_ratio':           info.get('trailingPE'),
            'peg_ratio':          info.get('pegRatio'),
            'book_value':         info.get('bookValue'),
            'debt_to_equity':     info.get('debtToEquity'),
            'current_price':      info.get('currentPrice') or info.get('regularMarketPrice'),
            'previous_close':     info.get('previousClose'),
            'week_52_high':       info.get('fiftyTwoWeekHigh'),
            'week_52_low':        info.get('fiftyTwoWeekLow'),
            'insider_pct':        round(insider_pct, 2),
            'roce':               round(roce, 2) if roce is not None else None,
            'year1_sales_growth': round(ttm_growth * 100, 1) if ttm_growth is not None else None,
            'year3_sales_growth': round(growth_3y  * 100, 1) if growth_3y  is not None else None,
        }
    except Exception:
        return None


def _upsert_us_company(metrics):
    """Insert or update one US company across screener_companies, derived_metrics_analysis, and screener_daily_prices."""
    symbol = metrics['symbol']
    sentiment = calculate_sentiment(
        metrics.get('current_price'),
        metrics.get('week_52_high'),
        metrics.get('week_52_low'),
    )
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO screener_companies
                (company_code, company_name, last_updated, created_at, source, exchange, enabled)
            VALUES (?, ?, ?, ?, 'sync', ?, 1)
            ON CONFLICT(company_code) DO UPDATE SET
                company_name = excluded.company_name,
                last_updated = excluded.last_updated,
                exchange     = excluded.exchange,
                enabled      = 1
        """, (
            symbol,
            metrics.get('company_name'),
            datetime.now(), datetime.now(),
            metrics.get('exchange', 'NYSE'),
        ))

        cp = metrics.get('current_price')
        if cp:
            cursor.execute("""
                INSERT OR REPLACE INTO screener_daily_prices
                    (company_code, date, current_price, previous_close, week_52_high, week_52_low, updated_at)
                VALUES (?, DATE('now'), ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (symbol, cp, metrics.get('previous_close'),
                  metrics.get('week_52_high'), metrics.get('week_52_low')))

        cursor.execute("""
            INSERT INTO derived_metrics_analysis
                (company_code, company_name, sector, industry,
                 market_cap, pe_ratio, peg_ratio, book_value,
                 roce, debt_to_equity,
                 year1_sales_growth, year3_sales_growth,
                 promoter_holding, sentiment_rating,
                 exchange, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(company_code) DO UPDATE SET
                company_name       = excluded.company_name,
                sector             = excluded.sector,
                industry           = excluded.industry,
                market_cap         = excluded.market_cap,
                pe_ratio           = excluded.pe_ratio,
                peg_ratio          = excluded.peg_ratio,
                book_value         = excluded.book_value,
                roce               = excluded.roce,
                debt_to_equity     = excluded.debt_to_equity,
                year1_sales_growth = excluded.year1_sales_growth,
                year3_sales_growth = excluded.year3_sales_growth,
                promoter_holding   = excluded.promoter_holding,
                sentiment_rating   = excluded.sentiment_rating,
                exchange           = excluded.exchange,
                updated_at         = CURRENT_TIMESTAMP
        """, (
            symbol,
            metrics.get('company_name'),
            metrics.get('sector'),
            metrics.get('industry'),
            metrics.get('market_cap_cr'),
            metrics.get('pe_ratio'),
            metrics.get('peg_ratio'),
            metrics.get('book_value'),
            metrics.get('roce'),
            metrics.get('debt_to_equity'),
            metrics.get('year1_sales_growth'),
            metrics.get('year3_sales_growth'),
            metrics.get('insider_pct'),  # stored in promoter_holding as proxy for insider %
            sentiment,
            metrics.get('exchange', 'NYSE'),
        ))

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"  ✗ DB error for US company {symbol}: {e}")
        return False
    finally:
        conn.close()


def sync_us_companies():
    """Daily US sync: Finviz pre-screen → yfinance deep metrics → DB upsert.

    New companies passing filters are added; existing US companies that fall off
    the filter are disabled (enabled=0).
    """
    logger.info("")
    logger.info("="*80)
    logger.info("SYNCING US COMPANIES (FINVIZ + YFINANCE)")
    logger.info("="*80)

    if not _FINVIZ_AVAILABLE:
        logger.warning("finvizfinance / numpy not installed — skipping US sync.")
        logger.warning("Install with: pip install finvizfinance numpy")
        return

    # Phase 1: Finviz pre-screen
    symbols = _get_us_candidates_from_finviz()
    if not symbols:
        logger.info("No candidates returned from Finviz. Skipping US sync.")
        return

    # Phase 2: yfinance deep metrics + quality filters
    logger.info(f"Phase 2: Fetching deep metrics for {len(symbols)} candidates...")
    passing = []
    for i, sym in enumerate(symbols, 1):
        if i % 50 == 0:
            logger.info(f"  Progress: {i}/{len(symbols)} checked, {len(passing)} passing")
        m = _fetch_us_company_metrics(sym)
        if m:
            passing.append(m)
        time.sleep(0.5)

    logger.info(f"  {len(passing)} companies passed all filters")
    if not passing:
        logger.info("No US companies passed filters. Skipping DB update.")
        return

    passing_codes = {m['symbol'] for m in passing}

    # Disable existing US companies no longer passing the filter
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT company_code FROM screener_companies
        WHERE exchange IN ('NYSE', 'NASDAQ', 'AMEX') AND enabled = 1
    """)
    existing_us = {row[0] for row in cursor.fetchall()}
    conn.close()

    to_disable = existing_us - passing_codes
    if to_disable:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute(
            f"UPDATE screener_companies SET enabled = 0 WHERE company_code IN ({','.join('?'*len(to_disable))})",
            list(to_disable)
        )
        conn.commit()
        conn.close()
        logger.info(f"  Disabled {len(to_disable)} US companies that fell off filter")

    # Upsert all passing companies; for new ones also pull EDGAR history
    added = updated = failed = 0
    if not _US_DOWNLOADER_AVAILABLE:
        logger.warning("edgartools not installed — skipping US stock EDGAR sync")
        return
    edgar_downloader = USStockDownloader()
    for m in passing:
        was_existing = m['symbol'] in existing_us
        if _upsert_us_company(m):
            if was_existing:
                updated += 1
            else:
                added += 1
                logger.info(f"  + New US company: {m['symbol']} ({m.get('company_name')}) [{m.get('exchange')}]")
                # Pull full financial history from EDGAR for new companies
                try:
                    edgar_data = edgar_downloader.download_company_data(m['symbol'])
                    if edgar_data:
                        import_screener_data_to_db(m['symbol'], edgar_data, source='sync')
                        logger.info(f"    ✓ EDGAR history imported for {m['symbol']}")
                except Exception as e:
                    logger.warning(f"    ⚠ EDGAR import failed for {m['symbol']}: {e}")
        else:
            failed += 1

    logger.info(f"✓ New: {added}  Updated: {updated}  Failed: {failed}  Disabled: {len(to_disable)}")
    logger.info("="*80)


def refresh_all_screener_data():
    """Re-download Screener.in annual + quarterly financials for all enabled Indian companies."""
    logger.info("="*80)
    logger.info("REFRESH ALL: Re-scraping Screener.in annual data for all enabled Indian companies")
    logger.info("="*80)
    logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    conn = sqlite3.connect(DATABASE_PATH)
    rows = conn.execute("""
        SELECT company_code, company_name FROM screener_companies
        WHERE enabled = 1 AND (exchange IS NULL OR exchange IN ('NSE', 'BSE'))
        ORDER BY company_code
    """).fetchall()
    conn.close()

    total = len(rows)
    logger.info(f"Found {total} enabled Indian companies to refresh\n")

    ok = failed = 0
    for i, (code, name) in enumerate(rows, 1):
        logger.info(f"[{i}/{total}] {code} — {name}")
        try:
            if _refresh_screener_data(code):
                ok += 1
            else:
                failed += 1
        except Exception as e:
            logger.info(f"  ✗ Unexpected error: {e}")
            failed += 1
        time.sleep(3)

    logger.info("")
    logger.info(f"✓ Refreshed: {ok}/{total}")
    logger.info(f"✗ Failed:    {failed}/{total}")
    logger.info("="*80)
    logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)


if __name__ == "__main__":
    from lib import ScriptLock

    # Parse flags
    companies_arg = None
    refresh_all = "--rescrape-annual-all" in sys.argv
    if "--companies" in sys.argv:
        idx = sys.argv.index("--companies") + 1
        if idx < len(sys.argv):
            companies_arg = sys.argv[idx].upper()

    lock = ScriptLock('discover_new_companies', logger=logger)
    if not lock.acquire():
        sys.exit(0)
    try:
        if companies_arg:
            sync_single_company(companies_arg)
        elif refresh_all:
            refresh_all_screener_data()
        else:
            main()
    finally:
        lock.release()
