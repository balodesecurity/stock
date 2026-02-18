"""
Common Library Functions
Reusable utilities shared across all scripts
"""

import sqlite3
import logging
import os
import fcntl
import sys
from datetime import datetime, time as dt_time
import pytz
from pathlib import Path

# Import constants
from constants import (
    DATABASE_PATH,
    LOGS_DIR,
    LOG_FORMAT,
    MARKET_TIMEZONE,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
    MARKET_DAYS
)


# ==============================================================================
# SCRIPT LOCKING (prevent duplicate cron instances)
# ==============================================================================

LOCK_DIR = LOGS_DIR / 'locks'
LOCK_DIR.mkdir(parents=True, exist_ok=True)


class ScriptLock:
    """
    File-based lock to prevent multiple instances of the same script.

    Uses fcntl.flock for atomic OS-level locking. The lock is automatically
    released when the process exits (even on crash/kill).

    Usage:
        lock = ScriptLock('sync_companies')
        if not lock.acquire():
            print("Another instance is running")
            sys.exit(0)
        try:
            main()
        finally:
            lock.release()

    Or as a context manager:
        with ScriptLock('sync_companies') as lock:
            if not lock.acquired:
                sys.exit(0)
            main()
    """

    def __init__(self, script_name, logger=None):
        self.script_name = script_name
        self.lock_file = LOCK_DIR / f"{script_name}.lock"
        self.logger = logger
        self._fd = None
        self.acquired = False

    def acquire(self):
        """Try to acquire the lock. Returns True if successful."""
        self._fd = open(self.lock_file, 'w')
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fd.write(f"{os.getpid()}\n")
            self._fd.flush()
            self.acquired = True
            return True
        except OSError:
            msg = f"{self.script_name}: another instance is already running, exiting"
            if self.logger:
                self.logger.info(msg)
            else:
                print(msg)
            self._fd.close()
            self._fd = None
            self.acquired = False
            return False

    def release(self):
        """Release the lock."""
        if self._fd:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None
            self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


# ==============================================================================
# DATABASE
# ==============================================================================

def ensure_enabled_column(conn):
    """Add 'enabled' column to screener_companies if it doesn't exist"""
    try:
        conn.execute("ALTER TABLE screener_companies ADD COLUMN enabled INTEGER DEFAULT 1")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists


def get_database_connection():
    """
    Get SQLite database connection

    Returns:
        sqlite3.Connection: Database connection object
    """
    return sqlite3.connect(str(DATABASE_PATH))


# ==============================================================================
# LOGGING
# ==============================================================================

def setup_logger(script_name, log_to_console=True):
    """
    Setup logger with daily rotation

    Args:
        script_name (str): Name of the script (used in log filename)
        log_to_console (bool): Whether to also log to console

    Returns:
        logging.Logger: Configured logger instance

    Example:
        logger = setup_logger('stock_prices')
        logger.info("Starting update...")
    """
    # Create log filename with date
    today = datetime.now().strftime('%Y%m%d')
    log_file = LOGS_DIR / f"{script_name}_{today}.log"

    # Create logger
    logger = logging.getLogger(script_name)
    logger.setLevel(logging.INFO)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # File handler
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Console handler (optional)
    if log_to_console:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


# ==============================================================================
# DATE & TIME
# ==============================================================================

def is_market_hours():
    """
    Check if Indian stock market is currently open

    Returns:
        bool: True if market is open, False otherwise

    Market hours: Monday-Friday, 9:15 AM - 3:30 PM IST
    """
    ist = pytz.timezone(MARKET_TIMEZONE)
    now = datetime.now(ist)

    # Check if weekday
    if now.weekday() not in MARKET_DAYS:
        return False

    # Check if within trading hours
    market_open = dt_time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)
    market_close = dt_time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
    current_time = now.time()

    return market_open <= current_time <= market_close


def format_quarter(date_obj):
    """
    Convert datetime to quarter format

    Args:
        date_obj (datetime): Date object

    Returns:
        str: Quarter string in format 'Mon YYYY' (e.g., 'Dec 2025')
    """
    return date_obj.strftime('%b %Y')


def get_today_date():
    """
    Get today's date in YYYY-MM-DD format

    Returns:
        str: Today's date
    """
    return datetime.now().strftime('%Y-%m-%d')


def get_timestamp():
    """
    Get current timestamp string

    Returns:
        str: Current timestamp in format 'YYYY-MM-DD HH:MM:SS'
    """
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ==============================================================================
# DATA VALIDATION
# ==============================================================================

def is_valid_value(value):
    """
    Check if value is valid (not None, not 'N/A', not empty)

    Args:
        value: Value to check

    Returns:
        bool: True if valid, False otherwise
    """
    if value is None:
        return False
    if isinstance(value, str) and (value.strip() == '' or value.strip().upper() == 'N/A'):
        return False
    return True


def clean_numeric_string(value_str):
    """
    Clean numeric string by removing commas and whitespace

    Args:
        value_str (str): String with numeric value

    Returns:
        str: Cleaned string

    Example:
        clean_numeric_string("1,234.56") -> "1234.56"
    """
    if not isinstance(value_str, str):
        return str(value_str)
    return value_str.replace(',', '').strip()


def safe_float_convert(value):
    """
    Safely convert value to float, handling errors

    Args:
        value: Value to convert

    Returns:
        float or None: Converted value or None if conversion fails
    """
    try:
        if isinstance(value, str):
            value = clean_numeric_string(value)
        return float(value)
    except (ValueError, TypeError):
        return None


# ==============================================================================
# FINANCIAL CALCULATIONS
# ==============================================================================

def calculate_percentage_change(current, previous):
    """
    Calculate percentage change between two values

    Args:
        current (float): Current value
        previous (float): Previous value

    Returns:
        float or None: Percentage change, or None if calculation not possible

    Formula:
        ((current - previous) / |previous|) * 100
    """
    if previous is None or current is None:
        return None

    if previous == 0:
        return None

    return ((current - previous) / abs(previous)) * 100


def calculate_growth_rate(latest, oldest):
    """
    Calculate growth rate between two values

    Args:
        latest (float): Latest value
        oldest (float): Oldest value

    Returns:
        float or None: Growth rate percentage, or None if calculation not possible

    Formula:
        ((latest - oldest) / oldest) * 100
    """
    if latest is None or oldest is None or oldest == 0:
        return None

    return ((latest - oldest) / oldest) * 100


# ==============================================================================
# DATABASE QUERIES
# ==============================================================================

def get_all_companies(conn):
    """
    Get list of all enabled companies from derived_metrics_analysis table

    Args:
        conn: Database connection

    Returns:
        list: List of tuples (company_code, company_name)
    """
    ensure_enabled_column(conn)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.company_code, d.company_name
        FROM derived_metrics_analysis d
        JOIN screener_companies c ON d.company_code = c.company_code
        WHERE d.company_name IS NOT NULL AND c.enabled = 1
        ORDER BY d.company_code
    """)
    return cursor.fetchall()


def check_quarter_exists(cursor, company_code, metric, quarter):
    """
    Check if a quarter entry already exists in screener_quarterly

    Args:
        cursor: Database cursor
        company_code (str): Company code
        metric (str): Metric name
        quarter (str): Quarter string (e.g., 'Dec 2025')

    Returns:
        bool: True if exists, False otherwise
    """
    cursor.execute("""
        SELECT COUNT(*) FROM screener_quarterly
        WHERE company_code = ? AND metric = ? AND quarter = ?
    """, (company_code, metric, quarter))
    return cursor.fetchone()[0] > 0


# ==============================================================================
# FORMATTING
# ==============================================================================

def format_progress(current, total, company_code, company_name, max_name_length=30):
    """
    Format progress message for logging

    Args:
        current (int): Current index
        total (int): Total count
        company_code (str): Company code
        company_name (str): Company name
        max_name_length (int): Maximum length for company name

    Returns:
        str: Formatted progress string

    Example:
        "[123/277] RELIANCE     Reliance Industries Ltd"
    """
    truncated_name = company_name[:max_name_length]
    return f"[{current:3d}/{total}] {company_code:<12} {truncated_name:<{max_name_length}}"


def format_percentage(value, decimal_places=1, show_sign=True):
    """
    Format percentage value

    Args:
        value (float): Percentage value
        decimal_places (int): Number of decimal places
        show_sign (bool): Whether to show +/- sign

    Returns:
        str: Formatted percentage string

    Example:
        format_percentage(15.5) -> "+15.5%"
        format_percentage(-5.2) -> "-5.2%"
    """
    if value is None:
        return "N/A"

    if show_sign:
        return f"{value:+.{decimal_places}f}%"
    else:
        return f"{value:.{decimal_places}f}%"


# ==============================================================================
# ERROR HANDLING
# ==============================================================================

def log_error(logger, message, exception=None):
    """
    Log error with optional exception details

    Args:
        logger: Logger instance
        message (str): Error message
        exception (Exception, optional): Exception object
    """
    if exception:
        logger.error(f"{message}: {str(exception)}")
    else:
        logger.error(message)


# ==============================================================================
# BATCH PROCESSING
# ==============================================================================

def batch_items(items, batch_size):
    """
    Split items into batches

    Args:
        items (list): List of items
        batch_size (int): Size of each batch

    Yields:
        list: Batch of items

    Example:
        for batch in batch_items(companies, 50):
            process_batch(batch)
    """
    for i in range(0, len(items), batch_size):
        yield items[i:i+batch_size]


# ==============================================================================
# SUMMARY STATISTICS
# ==============================================================================

def calculate_success_rate(successful, total):
    """
    Calculate success rate percentage

    Args:
        successful (int): Number of successful operations
        total (int): Total number of operations

    Returns:
        float: Success rate percentage
    """
    if total == 0:
        return 0.0
    return (successful / total) * 100


def format_summary_stats(stats_dict):
    """
    Format summary statistics for logging

    Args:
        stats_dict (dict): Dictionary with stat names and values

    Returns:
        list: List of formatted stat strings

    Example:
        stats = {'updated': 240, 'failed': 37, 'total': 277}
        format_summary_stats(stats)
        -> ["✓ Updated: 240/277", "✗ Failed: 37/277"]
    """
    lines = []
    total = stats_dict.get('total', 0)

    for key, value in stats_dict.items():
        if key == 'total':
            continue

        symbol = "✓" if "success" in key.lower() or "updated" in key.lower() else "✗"
        label = key.replace('_', ' ').title()
        lines.append(f"{symbol} {label}: {value}/{total}")

    return lines
