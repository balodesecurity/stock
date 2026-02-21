#!/usr/bin/env python3
"""
Update Stock Data from Yahoo Finance
- Quick mode: Prices only (hourly, ~30 seconds)
- Full mode: Prices + Fundamentals (daily, ~5-10 minutes)
"""

import sqlite3
import yfinance as yf
from datetime import datetime, time as dt_time
import pytz
import time as time_module
import math
import logging
import os

# Import database path from constants
from constants import DATABASE_PATH, YAHOO_FAILED_CACHE_DAYS, LOGS_DIR

# Setup logging
def setup_logger(mode='quick'):
    """Setup logger with daily rotation"""
    log_dir = LOGS_DIR
    os.makedirs(log_dir, exist_ok=True)

    today = datetime.now().strftime('%Y%m%d')
    log_file = os.path.join(log_dir, f"stock_prices_{mode}_{today}.log")

    logger = logging.getLogger(f'stock_prices_{mode}')
    logger.setLevel(logging.INFO)

    # Remove existing handlers
    logger.handlers.clear()

    # File handler
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.INFO)

    # Formatter (single line)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)

    logger.addHandler(fh)

    # Also log to console
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger

def is_market_hours():
    """Check if Indian stock market is open"""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)

    # Market hours: Monday-Friday, 9:15 AM - 3:30 PM IST
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    market_open = dt_time(9, 15)
    market_close = dt_time(15, 30)
    current_time = now.time()

    return market_open <= current_time <= market_close

def get_exchange_rate():
    """Get current USD/INR exchange rate"""
    try:
        usd_inr = yf.Ticker("INR=X")
        rate_data = usd_inr.history(period="5d")
        if not rate_data.empty:
            return rate_data['Close'].iloc[-1]
    except:
        pass
    return 85.0  # Fallback rate

def convert_to_crores(usd_value, exchange_rate):
    """Convert USD value to INR Crores"""
    inr_value = usd_value * exchange_rate
    crores = inr_value / 10000000
    return crores

def format_quarter(date_obj):
    """Convert datetime to quarter format: 'Dec 2025'"""
    return date_obj.strftime('%b %Y')

def search_ticker_by_name(company_name):
    """Search Yahoo Finance for a ticker symbol using company name.
    Tries: full name, Ltd<->Limited variant, then shortened name (before Ltd/Limited).
    Returns the first matching Indian exchange ticker (NSE/BSE) or None."""
    # Build search variants
    names_to_try = [company_name]
    if ' Ltd' in company_name:
        names_to_try.append(company_name.replace(' Ltd', ' Limited'))
        names_to_try.append(company_name.split(' Ltd')[0].strip())
    elif ' Limited' in company_name:
        names_to_try.append(company_name.replace(' Limited', ' Ltd'))
        names_to_try.append(company_name.split(' Limited')[0].strip())

    for name in names_to_try:
        try:
            results = yf.Search(name, max_results=5)
            for q in results.quotes:
                symbol = q.get('symbol', '')
                if symbol.endswith('.NS') or symbol.endswith('.BO'):
                    return symbol
        except Exception:
            continue
    return None


def check_quarter_exists(cursor, company_code, metric, quarter):
    """Check if a quarter already exists"""
    cursor.execute("""
        SELECT COUNT(*) FROM screener_quarterly
        WHERE company_code = ? AND metric = ? AND quarter = ?
    """, (company_code, metric, quarter))
    return cursor.fetchone()[0] > 0

def _save_price_data(cursor, code, ticker_symbol, close, high, low, volume, today, logger):
    """Save price data and update market cap for a single company.

    Fetches previous_close, 52-week high/low, and marketCap from Yahoo Finance,
    inserts into screener_daily_prices, and updates derived_metrics_analysis.market_cap.

    Returns True on success, False on failure.
    """
    try:
        # Get previous close from latest record
        cursor.execute("""
            SELECT current_price
            FROM screener_daily_prices
            WHERE company_code = ?
            ORDER BY date DESC
            LIMIT 1
        """, (code,))
        prev_data = cursor.fetchone()
        previous_close = prev_data[0] if prev_data else close

        # Fetch 52-week high/low, market cap, PE, PEG, book value from Yahoo Finance
        week_52_high = close
        week_52_low = close
        market_cap_crores = None
        pe_ratio = None
        peg_ratio = None
        book_value = None
        try:
            info = yf.Ticker(ticker_symbol).info
            week_52_high = info.get('fiftyTwoWeekHigh', close)
            week_52_low = info.get('fiftyTwoWeekLow', close)
            raw_market_cap = info.get('marketCap')
            if raw_market_cap:
                # marketCap from Yahoo is in INR for .NS/.BO stocks; convert to Crores
                market_cap_crores = round(raw_market_cap / 10000000, 2)
            pe_ratio = info.get('trailingPE')
            peg_ratio = info.get('pegRatio')
            book_value = info.get('bookValue')
            # Calculate PEG if not available
            if not peg_ratio:
                pe = info.get('trailingPE') or info.get('forwardPE')
                earnings_growth = info.get('earningsGrowth')
                if pe and earnings_growth and earnings_growth != 0:
                    peg_ratio = pe / (earnings_growth * 100)
        except:
            pass

        cursor.execute("""
            INSERT OR REPLACE INTO screener_daily_prices
            (company_code, date, current_price, previous_close, day_high, day_low,
             volume, week_52_high, week_52_low, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (code, today, float(close), float(previous_close), float(high), float(low),
              int(volume), float(week_52_high), float(week_52_low)))

        # Update market cap, PE, PEG, book value, and sentiment in derived_metrics_analysis
        updates = []
        params = []
        if market_cap_crores is not None:
            updates.append("market_cap = ?")
            params.append(market_cap_crores)
        if pe_ratio is not None:
            updates.append("pe_ratio = ?")
            params.append(pe_ratio)
        if peg_ratio is not None:
            updates.append("peg_ratio = ?")
            params.append(peg_ratio)
        if book_value is not None:
            updates.append("book_value = ?")
            params.append(book_value)

        # Calculate sentiment rating from 52-week position
        if week_52_high > week_52_low:
            position = ((float(close) - float(week_52_low)) / (float(week_52_high) - float(week_52_low))) * 100
            position = max(0, min(100, position))
            if position >= 80:
                sentiment = 5
            elif position >= 60:
                sentiment = 4
            elif position >= 40:
                sentiment = 3
            elif position >= 20:
                sentiment = 2
            else:
                sentiment = 1
            updates.append("sentiment_rating = ?")
            params.append(sentiment)

        if updates:
            params.append(code)
            cursor.execute(f"""
                UPDATE derived_metrics_analysis
                SET {', '.join(updates)}
                WHERE company_code = ?
            """, params)

        return True
    except Exception as e:
        logger.info(f"   ✗ Error saving price data for {code}: {e}")
        return False

def _ensure_ticker_cache(conn):
    """Create yahoo_ticker_cache table if it doesn't exist"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS yahoo_ticker_cache (
            company_code TEXT PRIMARY KEY,
            resolved_ticker TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()


def _get_cached_ticker(cursor, company_code):
    """Get cached ticker for a company.

    Returns:
        (resolved_ticker, is_cached) where:
        - (ticker, True) = cached success, use this ticker
        - (None, True) = cached failure within YAHOO_FAILED_CACHE_DAYS, skip
        - (None, False) = no cache or expired, try fresh
    """
    cursor.execute("""
        SELECT resolved_ticker, updated_at FROM yahoo_ticker_cache
        WHERE company_code = ?
    """, (company_code,))
    row = cursor.fetchone()
    if not row:
        return None, False

    resolved_ticker, updated_at = row

    if resolved_ticker:
        # Cached success — always use it
        return resolved_ticker, True

    # Cached failure — check if expired
    try:
        cached_date = datetime.strptime(updated_at, '%Y-%m-%d %H:%M:%S')
        days_ago = (datetime.now() - cached_date).days
        if days_ago < YAHOO_FAILED_CACHE_DAYS:
            return None, True  # Still within cache window, skip
    except ValueError:
        pass

    return None, False  # Expired, retry


def _cache_ticker(cursor, company_code, resolved_ticker):
    """Cache a resolved ticker (or NULL for failure)"""
    cursor.execute("""
        INSERT OR REPLACE INTO yahoo_ticker_cache (company_code, resolved_ticker, updated_at)
        VALUES (?, ?, ?)
    """, (company_code, resolved_ticker, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))


def update_prices_quick(force=False, company_filter=None):
    """Quick price update (hourly) - Updates screener_daily_prices table

    Args:
        force: Skip market hours check
        company_filter: Optional list of company codes to update (default: all)
    """

    logger = setup_logger('quick')

    # Check if market is open (skip if not, unless forced)
    if not force and not is_market_hours():
        logger.info("Market is closed. Skipping quick update.")
        return

    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    cursor = conn.cursor()

    # Ensure enabled column exists
    try:
        conn.execute("ALTER TABLE screener_companies ADD COLUMN enabled INTEGER DEFAULT 1")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Ensure ticker cache table exists
    _ensure_ticker_cache(conn)

    # Get company codes (filtered or all, skip disabled)
    try:
        if company_filter:
            placeholders = ','.join('?' for _ in company_filter)
            cursor.execute(f"""SELECT d.company_code FROM derived_metrics_analysis d
                              JOIN screener_companies c ON d.company_code = c.company_code
                              WHERE d.company_code IN ({placeholders}) AND d.company_name IS NOT NULL AND c.enabled = 1""",
                           company_filter)
        else:
            cursor.execute("""SELECT d.company_code FROM derived_metrics_analysis d
                             JOIN screener_companies c ON d.company_code = c.company_code
                             WHERE d.company_name IS NOT NULL AND c.enabled = 1""")
    except sqlite3.OperationalError as e:
        logger.error("DB error: %s", e)
        logger.error("DATABASE_PATH = %s (exists=%s)", DATABASE_PATH, os.path.exists(DATABASE_PATH))
        conn.close()
        return
    all_companies = [row[0] for row in cursor.fetchall()]

    # Split companies by cache status
    companies = []          # Companies to fetch via batch (.NS)
    cached_tickers = {}     # company_code -> resolved_ticker (for direct fetch)
    skipped_cached = 0

    for code in all_companies:
        resolved_ticker, is_cached = _get_cached_ticker(cursor, code)
        if is_cached and resolved_ticker:
            # Known good ticker — fetch directly, skip batch
            cached_tickers[code] = resolved_ticker
        elif is_cached and resolved_ticker is None:
            # Known failure within cache window — skip entirely
            skipped_cached += 1
        else:
            # No cache or expired — try via batch
            companies.append(code)

    # Get today's date
    today = datetime.now().strftime('%Y-%m-%d')

    logger.info("=" * 100)
    logger.info("QUICK UPDATE: STOCK PRICES FROM YAHOO FINANCE")
    logger.info("=" * 100)
    logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Total companies: {len(all_companies)}")
    if skipped_cached:
        logger.info(f"Skipped (cached failures, {YAHOO_FAILED_CACHE_DAYS}d): {skipped_cached}")
    if cached_tickers:
        logger.info(f"Using cached tickers: {len(cached_tickers)}")

    updated = 0
    failed = 0

    # --- Phase 1: Fetch companies with known cached tickers directly ---
    if cached_tickers:
        total_cached = len(cached_tickers)
        for idx, (code, ticker) in enumerate(cached_tickers.items(), 1):
            if idx == 1 or idx % 50 == 0 or idx == total_cached:
                logger.info(f"⏳ Phase 1: fetching cached tickers {idx}/{total_cached} ✓{updated} ✗{failed}...")
            try:
                data_fb = yf.download(ticker, period='1d', progress=False)
                close_fb = float(data_fb['Close'].values.flat[-1])
                high_fb = float(data_fb['High'].values.flat[-1])
                low_fb = float(data_fb['Low'].values.flat[-1])
                volume_fb = int(data_fb['Volume'].values.flat[-1])

                if close_fb > 0:
                    if _save_price_data(cursor, code, ticker, close_fb, high_fb, low_fb, volume_fb, today, logger):
                        updated += 1
                    else:
                        failed += 1
                else:
                    failed += 1
            except (KeyError, IndexError, ValueError):
                # Yahoo responded but returned no valid data — ticker is likely delisted
                _cache_ticker(cursor, code, None)
                failed += 1
            except Exception:
                # Network/connection error — preserve the cached ticker for next run
                failed += 1
        conn.commit()

    # --- Phase 2: Batch fetch remaining companies via .NS ---
    batch_size = 50

    for i in range(0, len(companies), batch_size):
        batch = companies[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(companies) + batch_size - 1) // batch_size

        logger.info(f"📦 Batch {batch_num}/{total_batches} ({len(batch)} stocks)...")

        # Try .NS suffix first
        tickers_ns = [f"{code}.NS" for code in batch]

        try:
            # Bulk download with threading
            data = yf.download(
                tickers_ns,
                period='1d',
                progress=False,
                group_by='ticker',
                threads=True
            )

            # Update prices for each stock
            for code in batch:
                ticker = f"{code}.NS"

                try:
                    # Handle both single and multi-ticker responses
                    if len(batch) == 1:
                        close = data['Close'].iloc[-1]
                        high = data['High'].iloc[-1]
                        low = data['Low'].iloc[-1]
                        volume = data['Volume'].iloc[-1]
                    else:
                        close = data[ticker]['Close'].iloc[-1]
                        high = data[ticker]['High'].iloc[-1]
                        low = data[ticker]['Low'].iloc[-1]
                        volume = data[ticker]['Volume'].iloc[-1]

                    if math.isnan(close):
                        raise ValueError(f"NaN price for {ticker}")

                    if close > 0:
                        if _save_price_data(cursor, code, ticker, close, high, low, volume, today, logger):
                            updated += 1
                            _cache_ticker(cursor, code, ticker)
                        else:
                            failed += 1
                    else:
                        failed += 1

                except (KeyError, IndexError, ValueError):
                    # Try fallback suffixes: .BO, then -SM.NS (SME stocks)
                    fallback_ok = False
                    resolved = None
                    # Track whether Yahoo actually responded (vs network/connection error).
                    # We only cache NULL when Yahoo confirmed no data; transient errors
                    # should not permanently blacklist a ticker for YAHOO_FAILED_CACHE_DAYS.
                    got_api_response = False
                    for suffix in ['.BO', '-SM.NS']:
                        try:
                            ticker_fb = f"{code}{suffix}"
                            data_fb = yf.download(ticker_fb, period='1d', progress=False)
                            got_api_response = True  # Yahoo responded (even if data is empty/NaN)
                            close_fb = float(data_fb['Close'].values.flat[-1])
                            high_fb = float(data_fb['High'].values.flat[-1])
                            low_fb = float(data_fb['Low'].values.flat[-1])
                            volume_fb = int(data_fb['Volume'].values.flat[-1])

                            if close_fb > 0:
                                if _save_price_data(cursor, code, ticker_fb, close_fb, high_fb, low_fb, volume_fb, today, logger):
                                    updated += 1
                                    fallback_ok = True
                                    resolved = ticker_fb
                                    break
                        except Exception:
                            continue
                    # If download failed, try Ticker.info directly (works for SME/low-volume stocks)
                    if not fallback_ok:
                        for suffix in ['.NS', '.BO', '-SM.NS']:
                            try:
                                ticker_fb = f"{code}{suffix}"
                                info = yf.Ticker(ticker_fb).info
                                got_api_response = True  # Yahoo responded
                                close_fb = info.get('currentPrice') or info.get('regularMarketPrice')
                                if close_fb and close_fb > 0:
                                    high_fb = info.get('dayHigh', close_fb)
                                    low_fb = info.get('dayLow', close_fb)
                                    volume_fb = info.get('volume', 0) or 0
                                    if _save_price_data(cursor, code, ticker_fb, close_fb, high_fb, low_fb, volume_fb, today, logger):
                                        updated += 1
                                        fallback_ok = True
                                        resolved = ticker_fb
                                        break
                            except Exception:
                                continue
                    # If all suffixes failed and code is numeric, try searching by company name
                    if not fallback_ok and code.isdigit():
                        try:
                            cursor.execute("SELECT company_name FROM derived_metrics_analysis WHERE company_code = ?", (code,))
                            row = cursor.fetchone()
                            if row and row[0]:
                                found_ticker = search_ticker_by_name(row[0])
                                if found_ticker:
                                    data_fb = yf.download(found_ticker, period='1d', progress=False)
                                    got_api_response = True
                                    close_fb = float(data_fb['Close'].values.flat[-1])
                                    high_fb = float(data_fb['High'].values.flat[-1])
                                    low_fb = float(data_fb['Low'].values.flat[-1])
                                    volume_fb = int(data_fb['Volume'].values.flat[-1])

                                    if close_fb > 0:
                                        if _save_price_data(cursor, code, found_ticker, close_fb, high_fb, low_fb, volume_fb, today, logger):
                                            updated += 1
                                            logger.info(f"   ✓ {code} resolved via name search → {found_ticker}")
                                            fallback_ok = True
                                            resolved = found_ticker
                        except Exception:
                            pass
                    # Only cache the result if Yahoo actually responded.
                    # If all attempts threw network/connection errors, skip caching so the
                    # ticker is retried next run instead of being blacklisted as a failure.
                    if fallback_ok or got_api_response:
                        _cache_ticker(cursor, code, resolved)
                    if not fallback_ok:
                        failed += 1

            conn.commit()

        except Exception as e:
            logger.info(f"   ✗ Batch failed: {e}")
            failed += len(batch)
            continue

    conn.close()

    total_attempted = len(companies) + len(cached_tickers)
    logger.info("=" * 100)
    logger.info(f"✓ Updated: {updated}/{total_attempted}")
    logger.info(f"✗ Failed: {failed}/{total_attempted}")
    if skipped_cached:
        logger.info(f"○ Skipped (cached failures): {skipped_cached}")
    logger.info(f"Success rate: {(updated/total_attempted*100):.1f}%" if total_attempted > 0 else "No companies to update")
    logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 100)

def update_fundamentals_for_company(cursor, company_code, exchange_rate):
    """Update quarterly and annual fundamentals for one company"""

    # Try both suffixes
    ticker_obj = None
    for suffix in ['.NS', '.BO', '-SM.NS']:
        try:
            ticker_symbol = company_code + suffix
            ticker_obj = yf.Ticker(ticker_symbol)

            # Quick check if data is available
            qf = ticker_obj.quarterly_financials
            if qf is not None and not qf.empty:
                break
        except:
            continue

    # If all suffixes failed and code is numeric, try searching by company name
    if ticker_obj is None and company_code.isdigit():
        try:
            cursor.execute("SELECT company_name FROM derived_metrics_analysis WHERE company_code = ?", (company_code,))
            row = cursor.fetchone()
            if row and row[0]:
                found_ticker = search_ticker_by_name(row[0])
                if found_ticker:
                    ticker_obj = yf.Ticker(found_ticker)
                    qf = ticker_obj.quarterly_financials
                    if qf is None or qf.empty:
                        ticker_obj = None
        except:
            pass

    if ticker_obj is None:
        return 0, 0

    # Get quarterly financials and cashflow
    qf = ticker_obj.quarterly_financials
    qc = ticker_obj.quarterly_cashflow

    inserted = 0
    skipped = 0

    # Field mappings: (Yahoo Field, Yahoo Source, Screener Field)
    quarterly_mappings = [
        ('Total Revenue', 'financials', 'Sales+'),
        ('Net Income', 'financials', 'Net Profit+'),
        ('Operating Income', 'financials', 'Operating Profit'),
        ('Diluted EPS', 'financials', 'EPS in Rs'),
        ('Interest Expense', 'financials', 'Interest'),
        ('Total Expenses', 'financials', 'Expenses+'),
        ('Other Income Expense', 'financials', 'Other Income+'),
        ('Pretax Income', 'financials', 'Profit before tax'),
        ('Reconciled Depreciation', 'financials', 'Depreciation'),
        ('Operating Cash Flow', 'cashflow', 'Operating Cash Flow+'),
        ('Free Cash Flow', 'cashflow', 'Free Cash Flow+'),
    ]

    # Process quarterly data
    if qf is not None and not qf.empty:
        # Only process latest 3 quarters (most recent data)
        for quarter_date in qf.columns[:3]:
            quarter_str = format_quarter(quarter_date)

            for yahoo_field, yahoo_source, screener_field in quarterly_mappings:
                # Get the appropriate data source
                if yahoo_source == 'financials':
                    data_source = qf
                elif yahoo_source == 'cashflow':
                    data_source = qc
                    if data_source is None or data_source.empty:
                        continue
                else:
                    continue

                # Check if field exists
                if yahoo_field not in data_source.index:
                    continue

                # Check if quarter exists in data source
                if quarter_date not in data_source.columns:
                    continue

                # Check if already exists in DB
                if check_quarter_exists(cursor, company_code, screener_field, quarter_str):
                    skipped += 1
                    continue

                try:
                    yahoo_value = data_source.loc[yahoo_field, quarter_date]

                    # Skip if NaN or None
                    if yahoo_value is None or math.isnan(float(yahoo_value)):
                        continue

                    yahoo_value = float(yahoo_value)

                    # Convert to Crores (except EPS which is per share)
                    if screener_field == 'EPS in Rs':
                        screener_value = yahoo_value * exchange_rate  # Already per share
                    else:
                        screener_value = convert_to_crores(yahoo_value, exchange_rate)

                    screener_value_str = f"{screener_value:,.0f}"

                    # Insert
                    cursor.execute("""
                        INSERT INTO screener_quarterly (company_code, metric, quarter, value)
                        VALUES (?, ?, ?, ?)
                    """, (company_code, screener_field, quarter_str, screener_value_str))
                    inserted += 1

                except Exception as e:
                    continue

    return inserted, skipped

def update_fundamentals_full(force=False, company_filter=None):
    """Full fundamentals update (daily) - Updates screener_quarterly, etc.

    Args:
        force: Skip market hours check
        company_filter: Optional list of company codes to update (default: all)
    """

    logger = setup_logger('full')

    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    cursor = conn.cursor()

    # Ensure enabled column exists
    try:
        conn.execute("ALTER TABLE screener_companies ADD COLUMN enabled INTEGER DEFAULT 1")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Get company codes (filtered or all, skip disabled)
    try:
        if company_filter:
            placeholders = ','.join('?' for _ in company_filter)
            cursor.execute(f"""SELECT d.company_code FROM derived_metrics_analysis d
                              JOIN screener_companies c ON d.company_code = c.company_code
                              WHERE d.company_code IN ({placeholders}) AND d.company_name IS NOT NULL AND c.enabled = 1""",
                           company_filter)
        else:
            cursor.execute("""SELECT d.company_code FROM derived_metrics_analysis d
                             JOIN screener_companies c ON d.company_code = c.company_code
                             WHERE d.company_name IS NOT NULL AND c.enabled = 1""")
    except sqlite3.OperationalError as e:
        logger.error("DB error: %s", e)
        logger.error("DATABASE_PATH = %s (exists=%s)", DATABASE_PATH, os.path.exists(DATABASE_PATH))
        conn.close()
        return
    companies = [row[0] for row in cursor.fetchall()]

    logger.info("=" * 100)
    logger.info("FULL UPDATE: PRICES + FUNDAMENTALS FROM YAHOO FINANCE")
    logger.info("=" * 100)
    logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Total companies: {len(companies)}")
    logger.info(f"Mode: Updating prices + quarterly fundamentals")
# blank line

    # First, do quick price update
    logger.info("Step 1: Updating prices...")
    conn.close()
    update_prices_quick(force=True, company_filter=company_filter)

    # Reconnect for fundamentals
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    cursor = conn.cursor()

    # Get exchange rate
    logger.info("Step 2: Fetching exchange rate...")
    exchange_rate = get_exchange_rate()
    logger.info(f"USD/INR Exchange Rate: {exchange_rate:.2f}")

    logger.info("Step 3: Updating quarterly fundamentals...")
    logger.info("(This will take ~5-10 minutes for all companies)")
# blank line

    total_inserted = 0
    total_skipped = 0
    processed = 0

    for idx, company_code in enumerate(companies, 1):
        try:
            if idx % 10 == 0:
                logger.info(f"  Progress: {idx}/{len(companies)} companies processed...")

            inserted, skipped = update_fundamentals_for_company(cursor, company_code, exchange_rate)
            total_inserted += inserted
            total_skipped += skipped
            processed += 1

            # Commit every 10 companies
            if idx % 10 == 0:
                conn.commit()

            # Rate limiting
            time_module.sleep(0.5)

        except Exception as e:
            logger.info(f"  ✗ Error processing {company_code}: {e}")
            continue

    conn.commit()
    conn.close()

# blank line
    logger.info("=" * 100)
    logger.info("FUNDAMENTALS UPDATE SUMMARY")
    logger.info("=" * 100)
    logger.info(f"✓ Processed: {processed}/{len(companies)} companies")
    logger.info(f"✓ Inserted: {total_inserted} new quarterly records")
    logger.info(f"○ Skipped: {total_skipped} existing records")
    logger.info(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 100)

if __name__ == "__main__":
    import sys
    from lib import ScriptLock

    force = "--force" in sys.argv
    fundamentals = "--fundamentals" in sys.argv

    # Parse --companies CODE1 CODE2 ... (all args after --companies until next flag)
    company_filter = None
    if "--companies" in sys.argv:
        idx = sys.argv.index("--companies") + 1
        codes = []
        while idx < len(sys.argv) and not sys.argv[idx].startswith("--"):
            codes.append(sys.argv[idx].upper())
            idx += 1
        if codes:
            company_filter = codes

    lock_name = 'stock_prices_full' if fundamentals else 'stock_prices_quick'
    lock = ScriptLock(lock_name)
    if not lock.acquire():
        sys.exit(0)
    try:
        if fundamentals:
            # Full update: Prices + Fundamentals (daily at 12 PM)
            update_fundamentals_full(force=force, company_filter=company_filter)
        else:
            # Quick update: Prices only (hourly)
            update_prices_quick(force=force, company_filter=company_filter)
    finally:
        lock.release()
