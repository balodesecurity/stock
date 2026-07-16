#!/usr/bin/env python3
"""
Stock Analysis Portal v2 - Premium Finance Theme
Built with Streamlit
"""

import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import sqlite3

from constants import DATABASE_PATH, QUARTER_ORDER_DESC

# Page configuration
st.set_page_config(
    page_title="Stock Analysis Portal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium Finance Theme CSS
st.markdown("""
<style>
    /* ===== Google Fonts ===== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ===== Global Font ===== */
    html, body, [class*="css"], .stMarkdown, .stTextInput, .stSelectbox,
    .stSlider, .stButton, .stSidebar, .stTabs, .stDataFrame {
        font-family: 'Inter', sans-serif !important;
    }

    /* ===== Base Layout ===== */
    .main > div { padding-top: 0.25rem; }
    .block-container { padding-top: 0.75rem !important; }

    /* ===== Hide sidebar ===== */
    section[data-testid="stSidebar"],
    [data-testid="collapsedControl"] { display: none !important; }

    /* ===== KPI Cards ===== */
    .kpi-card {
        background: linear-gradient(145deg, #131c2e 0%, #0e1726 100%);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 14px;
        padding: 20px 22px;
        margin-bottom: 8px;
        min-height: 104px;
        box-shadow: 0 4px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.04);
        position: relative;
        overflow: hidden;
    }
    .kpi-card-accent {
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        border-radius: 14px 14px 0 0;
    }
    .kpi-value {
        font-size: 26px;
        font-weight: 700;
        color: #f1f5f9;
        font-family: 'Inter', sans-serif;
        line-height: 1.2;
        letter-spacing: -0.5px;
    }
    .kpi-label {
        font-size: 10px;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        color: #5a6a7e;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-top: 6px;
    }
    .kpi-sub {
        font-size: 12px;
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        margin-top: 4px;
    }

    /* ===== Company Detail Cards ===== */
    .detail-card {
        background: linear-gradient(145deg, #131c2e 0%, #0e1726 100%);
        border: 1px solid rgba(255,255,255,0.07);
        border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .detail-card-title {
        color: #5a6a7e;
        font-size: 10px;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 10px;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .detail-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 5px 0;
        border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    .detail-row:last-child { border-bottom: none; }
    .detail-label {
        color: #8898aa;
        font-size: 12px;
        font-family: 'Inter', sans-serif;
        font-weight: 400;
    }
    .detail-value {
        color: #f1f5f9;
        font-size: 13px;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
    }
    .detail-value.positive { color: #10d98f; }
    .detail-value.negative { color: #f06067; }
    .detail-value.neutral  { color: #f5a623; }

    /* ===== Navigation — underline tab style ===== */
    div[data-testid="stRadio"],
    div[data-testid="stRadio"] > div,
    div[data-testid="stRadio"] > div > div {
        width: 100% !important;
        display: block !important;
        background: transparent !important;
        border-radius: 0 !important;
        padding: 0 !important;
        gap: 0 !important;
    }
    /* The actual flex container Streamlit uses for horizontal radio */
    div[data-testid="stRadio"] [data-baseweb="radio-group"],
    div[data-testid="stRadio"] [role="radiogroup"] {
        display: flex !important;
        flex-direction: row !important;
        justify-content: space-between !important;
        align-items: flex-end !important;
        width: 100% !important;
        gap: 0 !important;
        border-bottom: 1px solid rgba(255,255,255,0.08) !important;
        margin-bottom: 24px !important;
        margin-top: 0 !important;
        background: transparent !important;
        padding: 0 !important;
    }
    div[data-testid="stRadio"] label[data-baseweb="radio"] {
        flex: 1 !important;
        justify-content: center !important;
        text-align: center !important;
        padding: 10px 24px !important;
        border-radius: 0 !important;
        color: #475569 !important;
        font-size: 13px !important;
        font-weight: 500 !important;
        font-family: 'Inter', sans-serif !important;
        transition: color 0.15s !important;
        gap: 0 !important;
        margin: 0 0 -1px 0 !important;
        cursor: pointer !important;
        border-bottom: 2px solid transparent !important;
        background: transparent !important;
        white-space: nowrap !important;
    }
    div[data-testid="stRadio"] label[data-baseweb="radio"]:hover {
        color: #94a3b8 !important;
        background: transparent !important;
    }
    /* Hide the radio circle indicator */
    div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
        display: none !important;
    }
    /* Active state injected dynamically per-tab (see _nav_css below) */

    /* ===== Form input hint override ===== */
    div[data-testid="InputInstructions"] {
        visibility: hidden !important;
        position: relative !important;
    }
    div[data-testid="InputInstructions"]::before {
        content: "Enter company's screener URL";
        visibility: visible !important;
        position: absolute !important;
        left: 0 !important;
        color: #475569 !important;
        font-size: 12px !important;
        font-family: 'Inter', sans-serif !important;
    }

    /* ===== Tables ===== */
    .stDataFrame {
        border: 1px solid rgba(255,255,255,0.07) !important;
        border-radius: 8px !important;
    }

    /* ===== Hide Streamlit chrome ===== */
    #MainMenu { visibility: hidden; }
    header[data-testid="stHeader"] { display: none; }
    .stDeployButton { display: none; }

    /* ===== Star Rating ===== */
    .star-rating { font-size: 18px; color: #f5a623; }

    /* ===== Selectbox pill style ===== */
    .stSelectbox label, .stMultiSelect label {
        font-size: 10px !important;
        font-weight: 600 !important;
        color: #5a6a7e !important;
        text-transform: uppercase !important;
        letter-spacing: 1.5px !important;
        margin-bottom: 4px !important;
    }
    .stSelectbox div[data-baseweb="select"] > div,
    .stMultiSelect div[data-baseweb="select"] > div {
        background: rgba(129,140,248,0.06) !important;
        border: 1px solid rgba(129,140,248,0.22) !important;
        border-radius: 20px !important;
        padding-left: 4px !important;
        transition: border-color 0.15s ease;
    }
    .stSelectbox div[data-baseweb="select"] > div:hover,
    .stMultiSelect div[data-baseweb="select"] > div:hover {
        border-color: rgba(129,140,248,0.5) !important;
    }
    .stSelectbox div[data-baseweb="select"] span,
    .stMultiSelect div[data-baseweb="select"] span {
        font-size: 12px !important;
        color: #94a3b8 !important;
        font-family: 'Inter', sans-serif !important;
    }

    /* ===== Scrollbar ===== */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }

    /* ===== Auth chip (top-right user button) ===== */
    section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type
      div[data-testid="stColumn"]:last-child button {
        background: rgba(255,255,255,0.04) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #64748b !important;
        font-size: 11px !important;
        border-radius: 20px !important;
        min-height: 28px !important;
        padding: 0 12px !important;
        font-weight: 500 !important;
        letter-spacing: 0.2px !important;
    }
    section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type
      div[data-testid="stColumn"]:last-child button:hover {
        border-color: rgba(129,140,248,0.35) !important;
        color: #94a3b8 !important;
        background: rgba(129,140,248,0.06) !important;
    }
    /* Sign-in keeps primary colour */
    section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type
      div[data-testid="stColumn"]:last-child button[kind="primary"] {
        background: #818cf8 !important;
        border-color: #818cf8 !important;
        color: #fff !important;
    }
    section[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:first-of-type
      div[data-testid="stColumn"]:last-child button[kind="primary"]:hover {
        background: #6366f1 !important;
        border-color: #6366f1 !important;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────
# Database & Data Loading (unchanged from v1)
# ─────────────────────────────────────────────────────────

@st.cache_resource
def get_connection():
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
    try:
        conn.execute("ALTER TABLE screener_companies ADD COLUMN enabled INTEGER DEFAULT 1")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE screener_companies ADD COLUMN created_at TIMESTAMP")
        conn.execute("UPDATE screener_companies SET created_at = last_updated WHERE created_at IS NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE screener_companies ADD COLUMN source TEXT DEFAULT 'sync'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT    UNIQUE NOT NULL,
            name       TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_portfolio_stocks (
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_code TEXT    NOT NULL,
            added_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, company_code)
        );
    """)
    return conn

@st.cache_data(ttl=60)
def load_data(show_disabled=False):
    """Load all stock data"""
    conn = get_connection()
    query = """
        SELECT
            d.company_code,
            d.company_name,
            d.sector,
            d.industry,
            d.star_rating,
            d.sentiment_rating,
            d.pe_ratio,
            d.peg_ratio,
            d.market_cap,
            d.book_value,
            d.ssgr,
            d.ssgr_prev,
            d.total_fcf,
            d.fcf_category,
            d.fcf_cfo_ratio,
            d.debt_to_equity,
            d.year1_sales_growth,
            d.year2_sales_growth,
            d.year3_sales_growth,
            d.q1_sales_growth,
            d.q2_sales_growth,
            d.npm,
            d.nfat,
            d.dpr,
            d.qoq_profit_growth,
            d.qoq_profit_growth_prev,
            d.yoy_profit_growth,
            d.latest_quarter,
            d.prev_quarter,
            d.promoter_holding,
            d.promoter_trend_display,
            d.roce,
            d.yoy_sales_growth,
            p.current_price,
            p.previous_close,
            p.day_high,
            p.day_low,
            p.volume,
            p.week_52_high,
            p.week_52_low,
            p.updated_at,
            (SELECT ROUND((POWER(latest_sales / oldest_sales, 1.0/5) - 1) * 100, 2)
             FROM (
               SELECT
                 (SELECT CAST(REPLACE(value, ',', '') AS REAL)
                  FROM screener_annual_pl
                  WHERE company_code = d.company_code AND metric IN ('Sales+', 'Revenue+')
                    AND year <> 'TTM' AND value IS NOT NULL AND value <> ''
                  ORDER BY CAST(SUBSTR(year, -4) AS INTEGER) DESC LIMIT 1
                 ) as latest_sales,
                 (SELECT CAST(REPLACE(value, ',', '') AS REAL)
                  FROM screener_annual_pl
                  WHERE company_code = d.company_code AND metric IN ('Sales+', 'Revenue+')
                    AND year <> 'TTM' AND value IS NOT NULL AND value <> ''
                  ORDER BY CAST(SUBSTR(year, -4) AS INTEGER) DESC LIMIT 1 OFFSET 5
                 ) as oldest_sales
             )
             WHERE oldest_sales > 0
            ) as sales_growth_5y,
            c.created_at,
            c.source,
            c.exchange
        FROM derived_metrics_analysis d
        JOIN screener_companies c ON d.company_code = c.company_code
        LEFT JOIN (
            SELECT company_code, current_price, previous_close, day_high, day_low,
                   volume, week_52_high, week_52_low, updated_at
            FROM screener_daily_prices
            WHERE (company_code, date) IN (
                SELECT company_code, MAX(date)
                FROM screener_daily_prices
                GROUP BY company_code
            )
        ) p ON d.company_code = p.company_code
        WHERE d.company_name IS NOT NULL
    """
    if not show_disabled:
        query += " AND c.enabled = 1"
    df = pd.read_sql_query(query, conn)

    # For US companies promoter_trend_display is always NULL; fill with formatted insider %
    us_mask = df['exchange'].isin({'NYSE', 'NASDAQ', 'AMEX'})
    df.loc[us_mask, 'promoter_trend_display'] = df.loc[us_mask, 'promoter_holding'].apply(
        lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
    )
    df['promoter_trend_display'] = df['promoter_trend_display'].fillna("N/A")
    df['avg_3yr_growth'] = (df['year1_sales_growth'] + df['year2_sales_growth'] + df['year3_sales_growth']) / 3
    df['price_change_pct'] = df.apply(
        lambda x: ((x['current_price'] - x['previous_close']) / x['previous_close'] * 100)
        if pd.notna(x['current_price']) and pd.notna(x['previous_close']) and x['previous_close'] > 0
        else None, axis=1
    )
    return df

# ─────────────────────────────────────────────────────────
# Formatting helpers (unchanged from v1)
# ─────────────────────────────────────────────────────────

def render_stars(rating):
    """Render star rating as emoji"""
    if pd.isna(rating):
        return ""
    stars = int(rating)
    return "★" * stars + "☆" * (5 - stars)

def render_valuation(rating):
    """Render sentiment as a 52-week position label."""
    if pd.isna(rating):
        return "N/A"
    r = int(rating)
    return {1: "🟢 Near 52W Low", 2: "🟢 Lower Range", 3: "🟡 Mid Range",
            4: "🔴 Upper Range", 5: "🔴 Near 52W High"}.get(r, "N/A")

def format_number(num, currency='₹', unit='Cr'):
    """Format large numbers"""
    if pd.isna(num):
        return "N/A"
    if unit == 'M':  # USD millions
        if abs(num) >= 1000:
            return f"${num/1000:.1f}B"
        else:
            return f"${num:.0f}M"
    if abs(num) >= 10000:
        return f"{currency}{num/1000:.1f}k Cr"
    elif abs(num) >= 1000:
        return f"{currency}{num:.0f} Cr"
    else:
        return f"{currency}{num:.1f} Cr"

def format_price(price, change_pct, updated_at=None, currency='₹'):
    """Format price with change percentage and update time"""
    if pd.isna(price):
        return "N/A"

    time_str = ""
    if pd.notna(updated_at):
        try:
            from datetime import datetime
            import pytz

            if isinstance(updated_at, str):
                dt = datetime.fromisoformat(updated_at)
            else:
                dt = updated_at

            ist = pytz.timezone('Asia/Kolkata')
            if dt.tzinfo is None:
                dt = ist.localize(dt)
            else:
                dt = dt.astimezone(ist)

            time_str = f" [{dt.strftime('%d-%b %I:%M %p')}]"
        except:
            pass

    if pd.isna(change_pct):
        return f"{currency}{price:.2f}{time_str}"
    emoji = "🟢" if change_pct >= 0 else "🔴"
    return f"{emoji} {currency}{price:.2f} ({change_pct:+.2f}%){time_str}"

SCREENER_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?screener\.in/company/([A-Za-z0-9]+)(?:/(consolidated|standalone))?/?'
)

def parse_screener_url(url):
    """Extract company code from a screener.in URL. Returns (code, error)."""
    url = url.strip()
    if not url:
        return None, "URL cannot be empty."
    match = SCREENER_URL_PATTERN.fullmatch(url)
    if not match:
        return None, "Invalid URL. Expected format: https://www.screener.in/company/CODE/consolidated/"
    return match.group(1).upper(), None

# ── Rate limiting for Track Stock ────────────────────────────────────────────
_RATE_LIMIT_TABLE = "rate_limit_add_company"
_RATE_HOURLY_IP   = 60   # max adds per IP per hour
_RATE_DAILY_IP    = 30   # max adds per IP per 24 h
_RATE_HOURLY_GLOB = 24   # max adds globally per hour (each add ~60 s of CPU)
_COOLDOWN_SECS    = 15   # minimum seconds between two submits in the same session

def _get_client_ip() -> str:
    try:
        h = st.context.headers
        return (h.get("X-Forwarded-For") or h.get("X-Real-Ip") or "unknown").split(",")[0].strip()
    except Exception:
        return "unknown"

def _ensure_rate_limit_table(conn):
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {_RATE_LIMIT_TABLE} (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ip           TEXT    NOT NULL,
            attempted_at TEXT    NOT NULL
        )
    """)
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_rl_ip_time ON {_RATE_LIMIT_TABLE}(ip, attempted_at)")
    conn.commit()

def check_rate_limit(client_ip: str) -> tuple:
    """Return (allowed: bool, reason: str). Fails open on any DB error."""
    try:
        conn = get_connection()
        _ensure_rate_limit_table(conn)
    except Exception:
        return True, ""  # DB unavailable — allow rather than block everyone
    try:
        now = datetime.now()
        conn.execute(f"DELETE FROM {_RATE_LIMIT_TABLE} WHERE attempted_at < ?",
                     ((now - timedelta(hours=24)).isoformat(),))
        conn.commit()

        hour_ago = (now - timedelta(hours=1)).isoformat()
        day_ago  = (now - timedelta(hours=24)).isoformat()

        hourly_ip = conn.execute(
            f"SELECT COUNT(*) FROM {_RATE_LIMIT_TABLE} WHERE ip = ? AND attempted_at > ?",
            (client_ip, hour_ago)
        ).fetchone()[0]
        if hourly_ip >= _RATE_HOURLY_IP:
            return False, f"Too many requests — you can add up to {_RATE_HOURLY_IP} companies per hour."

        daily_ip = conn.execute(
            f"SELECT COUNT(*) FROM {_RATE_LIMIT_TABLE} WHERE ip = ? AND attempted_at > ?",
            (client_ip, day_ago)
        ).fetchone()[0]
        if daily_ip >= _RATE_DAILY_IP:
            return False, f"Daily limit reached — maximum {_RATE_DAILY_IP} additions per day per user."

        global_hourly = conn.execute(
            f"SELECT COUNT(*) FROM {_RATE_LIMIT_TABLE} WHERE attempted_at > ?",
            (hour_ago,)
        ).fetchone()[0]
        if global_hourly >= _RATE_HOURLY_GLOB:
            return False, "Server is busy — too many additions in the last hour. Please try again later."

        return True, ""
    except Exception:
        return True, ""  # Fail open on any query error

def record_rate_limit(client_ip: str):
    conn = get_connection()
    _ensure_rate_limit_table(conn)
    conn.execute(f"INSERT INTO {_RATE_LIMIT_TABLE} (ip, attempted_at) VALUES (?, ?)",
                 (client_ip, datetime.now().isoformat()))
    conn.commit()

# ─────────────────────────────────────────────────────────────────────────────

@st.dialog("Confirm Delete")
def confirm_delete_dialog(company_code: str):
    st.markdown(f"Delete **{company_code}** from all tables?")
    st.caption("This action cannot be undone.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Confirm", use_container_width=True):
            ok, msg = delete_company(company_code)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
            st.rerun()
    with col2:
        if st.button("❌ Cancel", use_container_width=True):
            st.rerun()

def delete_company(company_code):
    """Delete a company from all tables in the database. Returns (success, message)."""
    conn = get_connection()
    tables = [
        'derived_metrics_analysis',
        'screener_companies',
        'user_portfolio_stocks',
        'screener_quarterly',
        'screener_annual_pl',
        'screener_balance_sheet',
        'screener_cash_flow',
        'screener_ratios',
        'screener_shareholding',
        'screener_daily_prices',
        'yahoo_ticker_cache',
    ]
    try:
        total_deleted = 0
        for table in tables:
            cur = conn.execute(f"DELETE FROM {table} WHERE company_code = ?", (company_code,))
            total_deleted += cur.rowcount
        conn.commit()
        return True, f"Deleted {company_code} from {len(tables)} tables ({total_deleted} rows removed)."
    except Exception as e:
        return False, f"Failed to delete {company_code}: {e}"

def _upsert_user(conn, email, name=None):
    """Ensure a users row exists and return its id."""
    conn.execute("INSERT OR IGNORE INTO users (email, name) VALUES (?, ?)", (email, name))
    if name:
        conn.execute("UPDATE users SET name = ? WHERE email = ? AND name IS NULL", (name, email))
    conn.commit()
    return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]


def get_user_portfolio_codes(user_email, user_name=None):
    conn = get_connection()
    uid = _upsert_user(conn, user_email, user_name)
    rows = conn.execute(
        "SELECT company_code FROM user_portfolio_stocks WHERE user_id = ?", (uid,)
    ).fetchall()
    return [r[0] for r in rows]


def add_to_user_portfolio(company_code, user_email, user_name=None):
    conn = get_connection()
    try:
        uid = _upsert_user(conn, user_email, user_name)
        conn.execute(
            "INSERT OR IGNORE INTO user_portfolio_stocks (user_id, company_code) VALUES (?, ?)",
            (uid, company_code)
        )
        conn.commit()
        return True
    except Exception:
        return False


def remove_from_user_portfolio(company_code, user_email):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (user_email,)).fetchone()
        if not row:
            return False
        conn.execute(
            "DELETE FROM user_portfolio_stocks WHERE user_id = ? AND company_code = ?",
            (row[0], company_code)
        )
        conn.commit()
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────
# UI helpers

def section_header(title: str, badge: str = ""):
    badge_html = (
        f'<span style="margin-left:10px;padding:2px 8px;background:rgba(129,140,248,0.12);'
        f'border:1px solid rgba(129,140,248,0.25);border-radius:20px;'
        f'font-size:11px;color:#818cf8;font-weight:500">{badge}</span>'
        if badge else ""
    )
    st.markdown(
        f'<div style="margin:28px 0 14px 0;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.07)">'
        f'<span style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:2px">{title}</span>'
        f'{badge_html}'
        f'</div>',
        unsafe_allow_html=True
    )
# ─────────────────────────────────────────────────────────


def render_kpi_cards(df: pd.DataFrame, filtered_df: pd.DataFrame):
    """Render 5 Bloomberg-style KPI cards above the table."""
    total    = len(df)
    filtered = len(filtered_df)

    positive_fcf   = int((filtered_df['fcf_category'] == 'Positive').sum())
    avg_ssgr_val   = filtered_df['ssgr'].dropna().mean()
    high_sentiment = int(((filtered_df['sentiment_rating'] >= 4) & filtered_df['sentiment_rating'].notna()).sum())
    roce_20        = int(((filtered_df['roce'] >= 20) & filtered_df['roce'].notna()).sum())

    pct_fcf        = f"{positive_fcf / filtered * 100:.0f}% of view" if filtered > 0 else "—"
    avg_ssgr_str   = f"{avg_ssgr_val:.1f}%" if pd.notna(avg_ssgr_val) else "N/A"

    accent = ["#818cf8", "#10d98f", "#f5a623", "#a78bfa", "#10d98f"]
    cards = [
        ("COMPANIES",      f"{filtered}",       f"of {total} total",         accent[0]),
        ("POSITIVE FCF",   str(positive_fcf),    pct_fcf,                     accent[1]),
        ("AVG SSGR",       avg_ssgr_str,         "Self-Sustainable Growth",   accent[2]),
        ("HIGH SENTIMENT", str(high_sentiment),  "Rating ≥ 4 stars",          accent[3]),
        ("ROCE ≥ 20%",     str(roce_20),         "Quality companies",         accent[4]),
    ]

    cols = st.columns(5)
    for col, (label, value, sub, color) in zip(cols, cards):
        with col:
            st.markdown(
                f'<div class="kpi-card">'
                f'<div class="kpi-card-accent" style="background:{color}"></div>'
                f'<div class="kpi-value">{value}</div>'
                f'<div class="kpi-label">{label}</div>'
                f'<div class="kpi-sub" style="color:{color}">{sub}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def _vrow(label: str, formatted: str, css_class: str = "") -> str:
    """Generate a single detail-card row."""
    cls = f"detail-value {css_class}".strip()
    return (
        f'<div class="detail-row">'
        f'<span class="detail-label">{label}</span>'
        f'<span class="{cls}">{formatted}</span>'
        f'</div>'
    )


def render_company_detail(filtered_df: pd.DataFrame, preselect_code: str = None):
    """Render company detail panel. Pass preselect_code to skip the dropdown."""
    if preselect_code:
        code = preselect_code
        matches = filtered_df[filtered_df['company_code'] == code]
        if matches.empty:
            st.warning(f"{code} not found — data may still be syncing. Refresh in a moment.")
            return
        row = matches.iloc[0]
    else:
        options = ["— select company —"] + [
            f"{r['company_code']} – {r['company_name']}"
            for _, r in filtered_df[['company_code', 'company_name']].drop_duplicates('company_code').iterrows()
        ]
        selected = st.selectbox("Filtered Companies", options, key="cmp_detail_select", label_visibility="collapsed")
        if selected == "— select company —":
            return
        code = selected.split(" – ")[0]
        matches = filtered_df[filtered_df['company_code'] == code]
        if matches.empty:
            st.warning("Company not found in filtered data.")
            return
        row = matches.iloc[0]

    st.markdown(f"#### {row['company_name']}  `{code}`")
    c1, c2, c3, c4 = st.columns(4)

    # ── Col 1: Price ──
    _det_cur = '$' if row.get('exchange') in {'NYSE', 'NASDAQ', 'AMEX'} else '₹'
    cmp_str = f"{_det_cur}{row['current_price']:.2f}" if pd.notna(row['current_price']) else "N/A"
    chg_pct = row.get('price_change_pct')
    chg_str = f"{chg_pct:+.2f}%" if pd.notna(chg_pct) else "N/A"
    chg_cls = ("positive" if chg_pct >= 0 else "negative") if pd.notna(chg_pct) else ""
    w52h    = f"{_det_cur}{row['week_52_high']:.0f}" if pd.notna(row['week_52_high']) else "N/A"
    w52l    = f"{_det_cur}{row['week_52_low']:.0f}"  if pd.notna(row['week_52_low'])  else "N/A"
    vol_str = f"{int(row['volume']):,}" if pd.notna(row.get('volume')) else "N/A"

    with c1:
        st.markdown(
            f'<div class="detail-card">'
            f'<div class="detail-card-title">Price</div>'
            f'{_vrow("CMP", cmp_str)}'
            f'{_vrow("Change", chg_str, chg_cls)}'
            f'{_vrow("52W High", w52h)}'
            f'{_vrow("52W Low", w52l)}'
            f'{_vrow("Volume", vol_str)}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Col 2: Growth ──
    def fmt_growth(val):
        if pd.isna(val):
            return "N/A", ""
        return f"{val:+.1f}%", "positive" if val >= 0 else "negative"

    qoq_s,  qoq_c  = fmt_growth(row.get('qoq_profit_growth'))
    yoyp_s, yoyp_c = fmt_growth(row.get('yoy_profit_growth'))
    yoys_s, yoys_c = fmt_growth(row.get('yoy_sales_growth'))
    cagr_s, cagr_c = fmt_growth(row.get('sales_growth_5y'))
    lq = row.get('latest_quarter', 'N/A') or 'N/A'

    with c2:
        st.markdown(
            f'<div class="detail-card">'
            f'<div class="detail-card-title">Growth</div>'
            f'{_vrow("QoQ Profit", qoq_s, qoq_c)}'
            f'{_vrow("YoY Profit", yoyp_s, yoyp_c)}'
            f'{_vrow("YoY Sales", yoys_s, yoys_c)}'
            f'{_vrow("5Y CAGR", cagr_s, cagr_c)}'
            f'{_vrow("Latest Q", lq)}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Col 3: Quality ──
    def fmt_ssgr(val):
        if pd.isna(val):
            return "N/A", ""
        return f"{val:.1f}%", "positive" if val > 0 else "negative"

    ssgr_s,      ssgr_c      = fmt_ssgr(row.get('ssgr'))
    ssgr_prev_s, ssgr_prev_c = fmt_ssgr(row.get('ssgr_prev'))

    roce_val = row.get('roce')
    roce_s = f"{roce_val:.1f}%" if pd.notna(roce_val) else "N/A"
    roce_c = (
        "positive" if pd.notna(roce_val) and roce_val >= 20 else
        "neutral"  if pd.notna(roce_val) and roce_val >= 15 else
        "negative" if pd.notna(roce_val) else ""
    )

    fcf_cfo_val = row.get('fcf_cfo_ratio')
    fcf_s = f"{fcf_cfo_val:.1f}%" if pd.notna(fcf_cfo_val) else "N/A"
    fcf_c = (
        "positive" if pd.notna(fcf_cfo_val) and fcf_cfo_val >= 25 else
        "negative" if pd.notna(fcf_cfo_val) else ""
    )
    fcf_cat = row.get('fcf_category', 'N/A') or 'N/A'

    with c3:
        st.markdown(
            f'<div class="detail-card">'
            f'<div class="detail-card-title">Quality</div>'
            f'{_vrow("SSGR", ssgr_s, ssgr_c)}'
            f'{_vrow("SSGR Prev", ssgr_prev_s, ssgr_prev_c)}'
            f'{_vrow("ROCE", roce_s, roce_c)}'
            f'{_vrow("FCF/CFO", fcf_s, fcf_c)}'
            f'{_vrow("FCF Category", fcf_cat)}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Col 4: Valuation & Promoter ──
    pe_val  = row.get('pe_ratio')
    bv      = row.get('book_value')
    cmp_raw = row.get('current_price')
    pb_val  = (cmp_raw / bv) if pd.notna(cmp_raw) and pd.notna(bv) and bv > 0 else None
    peg_val = row.get('peg_ratio')
    promo   = row.get('promoter_holding')
    de_val  = row.get('debt_to_equity')

    pe_s    = f"{pe_val:.1f}x"  if pd.notna(pe_val)  else "N/A"
    pb_s    = f"{pb_val:.1f}x"  if pd.notna(pb_val)  else "N/A"
    peg_s   = f"{peg_val:.2f}"  if pd.notna(peg_val) else "N/A"
    promo_s = f"{promo:.1f}%"   if pd.notna(promo)   else "N/A"
    de_s    = f"{de_val:.2f}x"  if pd.notna(de_val)  else "N/A"
    pe_cls  = "neutral" if pd.notna(pe_val)  and pe_val  > 50  else ""
    peg_cls = "neutral" if pd.notna(peg_val) and peg_val > 3   else ""
    de_cls  = ("positive" if de_val <= 0.5 else ("negative" if de_val > 1.0 else "")) if pd.notna(de_val) else ""

    with c4:
        st.markdown(
            f'<div class="detail-card">'
            f'<div class="detail-card-title">Valuation &amp; Promoter</div>'
            f'{_vrow("P/E", pe_s, pe_cls)}'
            f'{_vrow("P/B", pb_s)}'
            f'{_vrow("PEG", peg_s, peg_cls)}'
            f'{_vrow("Promoter Holding", promo_s)}'
            f'{_vrow("D/E Ratio", de_s, de_cls)}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Multi-year Financial Summary Table ────────────────────────────────────
    st.markdown(
        '<div style="margin:28px 0 14px 0;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.07)">'
        '<span style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:2px">Financial Summary</span>'
        '</div>',
        unsafe_allow_html=True
    )

    _is_us_detail = row.get('exchange') in {'NYSE', 'NASDAQ', 'AMEX'}
    _unit_label   = '$ Millions' if _is_us_detail else '₹ Crores'

    conn = get_connection()
    cur  = conn.cursor()

    def _v(d, year, metric):
        return d.get(metric, {}).get(year)

    # ── Fetch annual P&L ──
    cur.execute("""
        SELECT metric, year, CAST(REPLACE(value,',','') AS REAL)
        FROM screener_annual_pl
        WHERE company_code = ?
          AND metric IN ('Sales+','Revenue+','Operating Profit','OPM %',
                         'Other Income+','Interest','Depreciation',
                         'Profit before tax','Net Profit+','Tax %',
                         'Dividend Payout %')
        ORDER BY CAST(SUBSTR(year,-4) AS INTEGER) DESC
    """, (code,))
    pl: dict = {}
    for metric, year, val in cur.fetchall():
        pl.setdefault(metric, {})[year] = val

    # Sales: prefer Sales+, fallback Revenue+
    sales_d = pl.get('Sales+') or pl.get('Revenue+', {})

    # ── Fetch cash flow ──
    cur.execute("""
        SELECT metric, year, CAST(REPLACE(value,',','') AS REAL)
        FROM screener_cash_flow
        WHERE company_code = ?
          AND metric IN ('Cash from Operating Activity+','Cash from Investing Activity+')
        ORDER BY CAST(SUBSTR(year,-4) AS INTEGER) DESC
    """, (code,))
    cf: dict = {}
    for metric, year, val in cur.fetchall():
        cf.setdefault(metric, {})[year] = val

    # ── Fetch balance sheet ──
    cur.execute("""
        SELECT metric, year, CAST(REPLACE(value,',','') AS REAL)
        FROM screener_balance_sheet
        WHERE company_code = ?
          AND (metric LIKE 'Borrowings%' OR metric IN ('Fixed Assets+','Net Block+','CWIP') OR metric = 'Equity Capital')
        ORDER BY CAST(SUBSTR(year,-4) AS INTEGER) DESC
    """, (code,))
    bs: dict = {}
    for metric, year, val in cur.fetchall():
        if year != 'TTM' and year[-4:].isdigit():
            bs.setdefault(metric, {})[year] = val
    debt_d    = {k: v for d in [bs.get(m, {}) for m in bs if 'Borrowings' in m] for k, v in d.items()}
    # Fixed assets: screener.in uses 'Fixed Assets+', EDGAR downloader uses 'Net Block+'
    nfa_d     = bs.get('Fixed Assets+') or bs.get('Net Block+', {})
    cwip_d    = bs.get('CWIP', {})
    eq_cap_d  = bs.get('Equity Capital', {})

    # ── Last 4 quarters (TTM) ──
    cur.execute(f"""
        SELECT metric, CAST(REPLACE(value,',','') AS REAL)
        FROM screener_quarterly
        WHERE company_code = ?
          AND metric IN ('Sales+','Revenue+','Net Profit+','Operating Profit',
                         'Other Income+','Interest','Depreciation','Profit before tax',
                         'Operating Cash Flow+','Free Cash Flow+')
        ORDER BY {QUARTER_ORDER_DESC}
    """, (code,))
    q_raw: dict = {}
    for metric, val in cur.fetchall():
        if val is not None:
            q_raw.setdefault(metric, []).append(val)
    def _ttm(metric, alt=None):
        vals = (q_raw.get(metric) or q_raw.get(alt or '', []))[:4]
        return sum(vals) if len(vals) == 4 else None

    ttm_sales  = _ttm('Sales+', 'Revenue+')
    ttm_pat    = _ttm('Net Profit+')
    ttm_op     = _ttm('Operating Profit')
    ttm_oi     = _ttm('Other Income+')
    ttm_int    = _ttm('Interest')
    ttm_dep    = _ttm('Depreciation')
    ttm_pbt    = _ttm('Profit before tax')
    ttm_cfo    = _ttm('Operating Cash Flow+')
    ttm_fcf_q  = _ttm('Free Cash Flow+')

    # ── Determine year columns (last 10, oldest→newest) ──
    # Use union of all available annual metrics to maximise year range
    _valid_years = {
        y for y in (
            set(sales_d)
            | set(pl.get('Net Profit+', {}))
            | set(pl.get('Depreciation', {}))
            | set(pl.get('Operating Profit', {}))
            | set(cf.get('Cash from Operating Activity+', {}))
        )
        if y != 'TTM' and y[-4:].isdigit()
    }
    # Detect fiscal year end month (most common) to filter out stub/transition periods
    # e.g. a Dec FY company may have one-off Jun-2020 entries from acquisition stubs
    from collections import Counter
    _month_counts = Counter(y[:3] for y in _valid_years)
    if _month_counts:
        _fy_month = _month_counts.most_common(1)[0][0]
        _valid_years = {y for y in _valid_years if y[:3] == _fy_month}

    all_years = sorted(_valid_years, key=lambda y: (int(y[-4:]), y[:3]))
    years = all_years[-10:]  # last 10

    # ── Dividend = Dividend Payout % × Net Profit / 100 ──
    div_pct_d = pl.get('Dividend Payout %', {})
    pat_annual = pl.get('Net Profit+', {})
    div_d: dict = {}
    for yr in set(div_pct_d) & set(pat_annual):
        dp = div_pct_d[yr]
        np_val = pat_annual[yr]
        if dp is not None and np_val is not None and np_val > 0:
            div_d[yr] = round(dp / 100 * np_val, 1)

    # ── Capex = Depreciation + Δ(NFA + CWIP) ──
    # Requires NFA and CWIP for current year AND previous year
    all_bs_years = sorted(
        {y for y in set(nfa_d) | set(cwip_d) if y[-4:].isdigit()},
        key=lambda y: (int(y[-4:]), y[:3])
    )
    capex_d: dict = {}
    for i, yr in enumerate(all_bs_years):
        if i == 0:
            continue  # need prior year to compute change
        prev_yr = all_bs_years[i - 1]
        dep     = pl.get('Depreciation', {}).get(yr)
        nfa_cur  = nfa_d.get(yr)
        nfa_prev = nfa_d.get(prev_yr)
        cwip_cur  = cwip_d.get(yr, 0) or 0
        cwip_prev = cwip_d.get(prev_yr, 0) or 0
        if dep is not None and nfa_cur is not None and nfa_prev is not None:
            capex_d[yr] = round(dep + (nfa_cur + cwip_cur) - (nfa_prev + cwip_prev), 1)

    # ── Pre-compute FCF = CFO − Capex, FCFE.1, FCFE.2 per year ──
    cfo_d  = cf.get('Cash from Operating Activity+', {})
    icf_d  = cf.get('Cash from Investing Activity+', {})
    int_d  = pl.get('Interest', {})
    oi_d   = pl.get('Other Income+', {})

    fcf_d: dict = {}
    for y in years:
        c   = cfo_d.get(y)
        cap = capex_d.get(y)
        if c is not None and cap is not None:
            fcf_d[y] = round(c - cap, 1)
        # Years without Capex data (first year of NFA series) are excluded

    fcfe1_d: dict = {}
    for y in years:
        f = fcf_d.get(y)
        if f is not None:
            fcfe1_d[y] = round(f - (int_d.get(y) or 0), 1)

    fcfe2_d: dict = {}
    for y in years:
        f = fcfe1_d.get(y)
        if f is not None:
            fcfe2_d[y] = round(f + (oi_d.get(y) or 0), 1)

    # ── 10-year summary totals ──
    # All three must cover the same years so that FCF = CFO − Capex holds in the summary.
    # FCF is only computable where both CFO and Capex exist; restrict CFO and Capex to match.
    def _sum(d): return round(sum(v for v in d.values() if v is not None), 1)
    fcf_years   = set(fcf_d.keys())
    total_cfo   = _sum({y: cfo_d.get(y)   for y in fcf_years})
    total_capex = _sum({y: capex_d.get(y) for y in fcf_years})
    total_fcf    = _sum(fcf_d)
    total_fcfe1  = _sum(fcfe1_d)
    total_fcfe2  = _sum(fcfe2_d)
    total_div10  = _sum({y: div_d.get(y) for y in years if div_d.get(y) is not None})
    total_int_sum = round(sum(int_d.get(y) or 0 for y in years), 1)
    total_oi_sum  = round(sum(oi_d.get(y) or 0 for y in years), 1)

    yrs_with_debt = [y for y in years if debt_d.get(y) is not None]
    inc_debt10    = round(debt_d[yrs_with_debt[-1]] - debt_d[yrs_with_debt[0]], 1) if len(yrs_with_debt) >= 2 else None
    # Cash Surplus = FCFE.2 + Inc_in_Debt − Dividends
    # Inc_in_Debt is added: incremental debt is a cash inflow (even if a quality concern)
    # Debt repayment is a cash outflow (reduces surplus)
    surplus10     = round(total_fcfe2 + (inc_debt10 or 0) - total_div10, 1) if inc_debt10 is not None else None

    # ── SSGR per year using rolling offsets ──
    from compute_growth_metrics import calculate_ssgr as _calc_ssgr
    # Map most-recent year → offset 0, next → offset 1, etc.
    ssgr_by_year: dict = {}
    rev_years = list(reversed(years))
    for i, yr in enumerate(rev_years):
        val = _calc_ssgr(cur, code, year_offset=i)
        if val is not None:
            ssgr_by_year[yr] = val

    # ── Build rows ──
    def _pct(num, den):
        if num is not None and den and den != 0:
            return round(num / den * 100, 1)
        return None

    _signed_rows = {'Free Cash Flow from core business', 'Free cash flow from core business − Interest + Other Income'}

    def _fmt(val, is_pct=False, row_name=''):
        """Format cell value. FCF rows use -12 sign; others use (12) parentheses."""
        if val is None:
            return ''
        if is_pct:
            s = f"{val:.0f}%"
        else:
            s = f"{val:,.0f}"
        if val < 0:
            s = f"-{s.lstrip('-')}" if row_name in _signed_rows else f"({s.lstrip('-')})"
        return s

    rows_def = [
        # (display_name, data_dict_or_fn, is_pct, is_bold, is_separator)
        ('Sales',               sales_d,                                        False, False, False),
        ('Operating Profit',    pl.get('Operating Profit', {}),                 False, False, False),
        ('OPM %',               {y: _pct(pl.get('Operating Profit',{}).get(y), sales_d.get(y)) for y in years}, True, False, False),
        ('Other Income',        pl.get('Other Income+', {}),                    False, False, False),
        ('Interest',            pl.get('Interest', {}),                         False, False, False),
        ('Depreciation',        pl.get('Depreciation', {}),                     False, False, False),
        ('Profit before Tax',   pl.get('Profit before tax', {}),                False, False, False),
        ('Tax %',               {y: _pct((pl.get('Profit before tax',{}).get(y) or 0) - (pl.get('Net Profit+',{}).get(y) or 0), pl.get('Profit before tax',{}).get(y)) for y in years}, True, False, False),
        ('Net Profit (PAT)',    pl.get('Net Profit+', {}),                      False, True,  False),
        ('NPM %',               {y: _pct(pl.get('Net Profit+',{}).get(y), sales_d.get(y)) for y in years}, True, False, False),
        ('─' * 20,              {},                                             False, False, True),
        ('CFO',                 cf.get('Cash from Operating Activity+', {}),    False, False, False),
        ('Capex',               capex_d,                                        False, True,  False),
        ('Free Cash Flow from core business',         fcf_d,                                          False, True,  False),
        ('FCF/CFO %',           {y: _pct(fcf_d.get(y), cfo_d.get(y)) for y in years if cfo_d.get(y)}, True, False, False),
        ('Free cash flow from core business − Interest + Other Income',           fcfe2_d,                                        False, True,  False),
        ('─' * 20,              {},                                             False, False, True),
        ('Total Debt',          debt_d,                                         False, True,  False),
        ('Share Capital',       eq_cap_d,                                       False, False, False),
        ('Dividend Paid',       div_d,                                          False, False, False),
        ('─' * 20,              {},                                             False, False, True),
        ('SSGR (3yr avg)',      ssgr_by_year,                                   True,  True,  False),
    ]

    # ── TTM values for last-column ──
    def _ttm_for(name):
        m = {
            'Sales': ttm_sales, 'Operating Profit': ttm_op,
            'Other Income': ttm_oi, 'Interest': ttm_int,
            'Depreciation': ttm_dep, 'Profit before Tax': ttm_pbt,
            'Net Profit (PAT)': ttm_pat, 'CFO': ttm_cfo, 'Free Cash Flow from core business': ttm_fcf_q,
            'FCF/CFO %': _pct(ttm_fcf_q, ttm_cfo),
            'Free cash flow from core business − Interest + Other Income': (ttm_fcf_q - (ttm_int or 0) + (ttm_oi or 0)) if ttm_fcf_q is not None else None,
            'OPM %': _pct(ttm_op, ttm_sales),
            'NPM %': _pct(ttm_pat, ttm_sales),
            'Tax %': _pct((ttm_pbt or 0) - (ttm_pat or 0), ttm_pbt),
        }
        return m.get(name)

    # PAT by year for CFO conditional formatting
    pat_d = pl.get('Net Profit+', {})

    # ── Render table as HTML ──
    yr_headers = [y.replace(' ', '-').replace('Mar', 'Mar').replace('Dec','Dec') for y in years]
    col_style  = 'padding:5px 10px;text-align:right;font-size:12px;white-space:nowrap;color:#cbd5e1'
    hdr_style  = f'{col_style};color:#818cf8;font-weight:600;border-bottom:1px solid rgba(255,255,255,0.08)'
    lbl_style  = 'padding:5px 10px;font-size:12px;white-space:nowrap;min-width:180px;color:#f1f5f9'

    header = (
        f'<tr>'
        f'<th style="{hdr_style};text-align:left">Narration ({_unit_label})</th>'
        + ''.join(f'<th style="{hdr_style}">{h}</th>' for h in yr_headers)
        + f'<th style="{hdr_style};color:#f5a623">TTM / L4Q</th>'
        + f'<th style="{hdr_style};color:#f5a623">Total</th>'
        + '</tr>'
    )

    body = ''
    for name, data, is_pct, is_bold, is_sep in rows_def:
        if is_sep:
            body += f'<tr><td colspan="{len(years)+3}" style="padding:2px;border-top:1px solid rgba(255,255,255,0.08)"></td></tr>'
            continue

        row_cells = ''
        total_val = 0.0
        # has_total: True for flow metrics that meaningfully sum across years
        _no_total = {'Total Debt', 'Share Capital', 'SSGR (3yr avg)', 'OPM %', 'NPM %', 'Tax %', 'Dividend Paid', 'FCF/CFO %'}
        has_total = not is_pct and name not in _no_total

        for yr in years:
            val = data.get(yr) if isinstance(data, dict) else None
            if val is None:
                row_cells += f'<td style="{col_style}">—</td>'
            else:
                fw    = 'font-weight:600;' if is_bold else ''
                # CFO row: green bg if CFO > PAT, red bg if CFO < PAT
                if name == 'CFO':
                    pat_val = pat_d.get(yr)
                    if pat_val is not None:
                        bg = 'background:rgba(16,217,143,0.07);' if val >= pat_val else 'background:rgba(240,96,103,0.07);'
                    else:
                        bg = ''
                    cell_clr = '#f06067' if val < 0 else ''
                    extra = f'color:{cell_clr};' if cell_clr else ''
                    row_cells += f'<td style="{col_style};{fw}{bg}{extra}">{_fmt(val, is_pct, name)}</td>'
                # Total Debt: green if fell vs prior year, red if rose
                elif name == 'Total Debt':
                    yr_idx   = years.index(yr)
                    prev_val = debt_d.get(years[yr_idx - 1]) if yr_idx > 0 else None
                    if prev_val is not None:
                        bg = 'background:rgba(16,217,143,0.07);' if val <= prev_val else 'background:rgba(240,96,103,0.07);'
                    else:
                        bg = ''
                    row_cells += f'<td style="{col_style};{fw}{bg}">{_fmt(val, is_pct, name)}</td>'
                # Share Capital: green if decreased (buyback), red if increased (dilution)
                elif name == 'Share Capital':
                    yr_idx   = years.index(yr)
                    prev_val = eq_cap_d.get(years[yr_idx - 1]) if yr_idx > 0 else None
                    if prev_val is not None:
                        bg = 'background:rgba(16,217,143,0.07);' if val <= prev_val else 'background:rgba(240,96,103,0.07);'
                    else:
                        bg = ''
                    row_cells += f'<td style="{col_style};{fw}{bg}">{_fmt(val, is_pct, name)}</td>'
                # Dividend: green if increased vs prior year, red if decreased
                elif name == 'Dividend Paid':
                    yr_idx   = years.index(yr)
                    prev_val = div_d.get(years[yr_idx - 1]) if yr_idx > 0 else None
                    if prev_val is not None:
                        bg = 'background:rgba(16,217,143,0.07);' if val >= prev_val else 'background:rgba(240,96,103,0.07);'
                    else:
                        bg = ''
                    row_cells += f'<td style="{col_style};{fw}{bg}">{_fmt(val, is_pct, name)}</td>'
                # Capex row: green bg if Capex < CFO, red bg if Capex > CFO
                elif name == 'Capex':
                    cfo_val = cf.get('Cash from Operating Activity+', {}).get(yr)
                    if cfo_val is not None:
                        bg = 'background:rgba(16,217,143,0.07);' if val <= cfo_val else 'background:rgba(240,96,103,0.07);'
                    else:
                        bg = ''
                    row_cells += f'<td style="{col_style};{fw}{bg}">{_fmt(val, is_pct, name)}</td>'
                else:
                    cell_clr = '#f06067' if val < 0 else ''
                    extra = f'color:{cell_clr};' if cell_clr else ''
                    row_cells += f'<td style="{col_style};{fw}{extra}">{_fmt(val, is_pct, name)}</td>'
                if not is_pct:
                    total_val += val

        # TTM column
        ttm = _ttm_for(name)
        if ttm is not None:
            tc = '#f06067' if ttm < 0 else '#f5a623'
            ttm_cell = f'<td style="{col_style};color:{tc};font-weight:600">{_fmt(ttm, is_pct, name)}</td>'
        else:
            ttm_cell = f'<td style="{col_style};color:#94a3b8">—</td>'

        # Total column
        if has_total and total_val != 0:
            tc2 = '#f06067' if total_val < 0 else '#818cf8'
            total_cell = f'<td style="{col_style};color:{tc2};font-weight:700">{_fmt(total_val, False, name)}</td>'
        else:
            total_cell = f'<td style="{col_style};color:#94a3b8">—</td>'

        fw_row = 'font-weight:600;' if is_bold else ''
        body += (
            f'<tr style="border-bottom:1px solid rgba(255,255,255,0.04)">'
            f'<td style="{lbl_style};{fw_row}">{name}</td>'
            + row_cells + ttm_cell + total_cell +
            '</tr>'
        )

    st.markdown(
        f'<div style="overflow-x:auto;margin-top:8px">'
        f'<table style="border-collapse:collapse;width:100%;background:#0b0e1a">'
        f'<thead>{header}</thead>'
        f'<tbody>{body}</tbody>'
        f'</table></div>',
        unsafe_allow_html=True
    )

    # ── 10-Year Summary Box ───────────────────────────────────────────────────
    # Market cap and surplus as % of market cap
    mkt_cap = row.get('market_cap')  # always in Crores (INR equiv for US)
    if surplus10 is not None and pd.notna(mkt_cap) and mkt_cap and mkt_cap > 0:
        # Convert surplus to same unit as market cap (Crores)
        if _is_us_detail:
            from constants import DEFAULT_EXCHANGE_RATE
            surplus_cr = surplus10 * DEFAULT_EXCHANGE_RATE / 10  # USD millions → INR Crores
        else:
            surplus_cr = surplus10
        surplus_pct_mktcap = round(surplus_cr / mkt_cap * 100, 1)
    else:
        surplus_pct_mktcap = None

    def _sfmt(v, label=''):
        if v is None: return '—'
        s = f"{abs(v):,.0f}"
        if v < 0:
            return f'-{s}'
        return s

    _desc = {
        'CFO':                    'Cash generated from core business operations',
        'Capex':                  'Dep + Δ(Fixed Assets + CWIP) — money spent on plant/equipment',
        'Free Cash Flow from core business':            'CFO − Capex — discretionary surplus after capital expenditure. If negative, company cannot fund capex from operations.',
        'Other Income':           'Non-operating income (interest earned, dividends received, asset sales). Added back to arrive at Free cash flow from core business − Interest + Other Income.',
        'Free cash flow from core business − Interest + Other Income':              'FCF minus interest paid, plus other income — total surplus available to shareholders after all capital needs. More stringent than Free Cash Flow from core business.',
        'Total Div 10 Yrs':       '🔴 if dividends exceed Free cash flow from core business − Interest + Other Income — company paid more than it generated',
        'Inc. in Debt 10Y':       '🟢 if debt fell (self-funded), 🔴 if debt rose (reliant on borrowing)',
        f'Available Cash Surplus in last {len(years)} years including debt (in bank)': 'Free cash flow from core business − Interest + Other Income + Inc.Debt − Dividends. Tracks <b>cash liquidity</b>: debt inflows add cash, repayments reduce it. Compare with increase in Cash+Investments over the same period to validate.',
        'Interest Paid':          'Total interest paid over the period — direct deduction from FCF to arrive at Free cash flow from core business − Interest + Other Income. High interest = high debt burden eating into shareholder surplus.',
    }

    def _srow(label, val, color=None, bg=None, bold_label=False):
        clr = color or ('#f06067' if (val is not None and val < 0) else '#f1f5f9')
        bg_style = f'background:{bg};' if bg else ''
        desc = _desc.get(label, '')
        lbl_fw = 'font-weight:700;color:#f1f5f9;' if bold_label else ''
        return (
            f'<tr style="border-bottom:1px solid rgba(255,255,255,0.04)">'
            f'<td style="padding:4px 10px;font-size:12px;color:#94a3b8;white-space:nowrap;{lbl_fw}">{label}</td>'
            f'<td style="padding:4px 10px;font-size:12px;font-weight:700;text-align:right;'
            f'white-space:nowrap;color:{clr};{bg_style}">{_sfmt(val, label)}</td>'
            f'<td style="padding:4px 10px;font-size:11px;color:#5a6a7e;max-width:280px">{desc}</td>'
            f'</tr>'
        )

    div_bg = 'background:rgba(240,96,103,0.07);' if (total_div10 and total_fcfe2 is not None and total_div10 > total_fcfe2) else ''
    debt_bg = ('background:rgba(16,217,143,0.07);' if inc_debt10 is not None and inc_debt10 < 0
               else 'background:rgba(240,96,103,0.07);' if inc_debt10 is not None and inc_debt10 > 0 else '')

    _mktcap_str = (f"₹{mkt_cap:,.0f} Cr" if not _is_us_detail else f"{mkt_cap:,.0f} Cr (INR equiv)") if pd.notna(mkt_cap) and mkt_cap else "N/A"

    summary_html = (
        f'<table style="border-collapse:collapse;background:#131c2e;border:1px solid rgba(255,255,255,0.08);border-radius:12px;min-width:220px">'
        f'<thead>'
        f'<tr><th colspan="3" style="padding:6px 10px;font-size:11px;color:#818cf8;text-align:left;'
        f'border-bottom:1px solid rgba(255,255,255,0.08);letter-spacing:1px">{len(years)}-YEAR SUMMARY ({_unit_label})</th></tr>'
        f'<tr><td colspan="3" style="padding:4px 10px;font-size:12px;color:#94a3b8">'
        f'Market Cap: <b style="color:#f1f5f9">{_mktcap_str}</b></td></tr>'
        f'</thead>'
        f'<tbody>'
        + _srow('CFO',                    total_cfo)
        + _srow('Capex',                  total_capex)
        + _srow('Free Cash Flow from core business',            total_fcf,
                color='#10d98f' if total_fcf is not None and total_fcf > 0 else '#f06067')
        + _srow('Other Income',           total_oi_sum,
                color='#10d98f' if total_oi_sum > 0 else '#94a3b8')
        + _srow('Free cash flow from core business − Interest + Other Income',              total_fcfe2,
                color='#10d98f' if total_fcfe2 is not None and total_fcfe2 > 0 else '#f06067')
        + f'<tr><td colspan="3" style="padding:2px;border-top:1px solid rgba(255,255,255,0.08)"></td></tr>'
        + _srow(f'Available Cash Surplus in last {len(years)} years including debt (in bank)',   surplus10, bold_label=True,
                color='#10d98f' if (surplus10 is not None and surplus10 > 0) else '#f06067')
        + (f'<tr style="border-bottom:1px solid rgba(255,255,255,0.04)">'
           f'<td style="padding:4px 10px;font-size:12px;color:#94a3b8">  └ % of Market Cap</td>'
           f'<td style="padding:4px 10px;font-size:12px;font-weight:700;text-align:right;'
           f'color:{"#10d98f" if surplus_pct_mktcap and surplus_pct_mktcap > 0 else "#f06067"}">'
           f'{f"{surplus_pct_mktcap:+.1f}%" if surplus_pct_mktcap is not None else "—"}</td>'
           f'<td style="padding:4px 10px;font-size:11px;color:#5a6a7e">Higher = more cash generated vs company size</td>'
           f'</tr>'
           if surplus_pct_mktcap is not None else '')
        + f'</tbody></table>'
    )

    _n = len(years)
    _lbl_div  = f'Total Div Paid in {_n} Yrs'
    _lbl_debt = f'Inc. in Debt {_n}Y'
    _desc[_lbl_div]  = 'Total dividends distributed to shareholders. Reduces cash available in the business.'
    _desc[_lbl_debt] = '🟢 negative = net debt repaid (self-funded). 🔴 positive = net new debt raised — company needed external capital to sustain operations or growth.'

    deductions_html = (
        f'<table style="border-collapse:collapse;background:#131c2e;border:1px solid rgba(255,255,255,0.08);border-radius:12px;min-width:220px">'
        f'<thead>'
        f'<tr><th colspan="3" style="padding:6px 10px;font-size:11px;color:#f5a623;text-align:left;'
        f'border-bottom:1px solid rgba(255,255,255,0.08);letter-spacing:1px">DEDUCTIONS ({_unit_label})</th></tr>'
        f'<tr><td colspan="3" style="padding:4px 10px;font-size:12px;color:#94a3b8">'
        f'Over {_n} years</td></tr>'
        f'</thead>'
        f'<tbody>'
        + _srow('Interest Paid', total_int_sum, color='#f06067')
        + _srow(_lbl_div,        total_div10,
                color='#f5a623' if total_div10 and total_div10 > 0 else '#94a3b8')
        + _srow(_lbl_debt,       inc_debt10,
                color='#10d98f' if (inc_debt10 is not None and inc_debt10 < 0)
                      else '#f06067' if (inc_debt10 is not None and inc_debt10 > 0) else None,
                bg='rgba(16,217,143,0.07)' if (inc_debt10 is not None and inc_debt10 < 0)
                   else 'rgba(240,96,103,0.07)' if (inc_debt10 is not None and inc_debt10 > 0) else None)
        + f'</tbody></table>'
    )

    st.markdown(
        f'<div style="margin-top:16px;display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">'
        f'{summary_html}{deductions_html}'
        f'</div>',
        unsafe_allow_html=True
    )




# ─────────────────────────────────────────────────────────
# Main app
# ─────────────────────────────────────────────────────────

def main():
    _us_markets    = {'NYSE', 'NASDAQ', 'AMEX'}
    _india_markets = {'NSE', 'BSE'}
    market_filter  = "🇮🇳 India"
    _is_india = True
    _is_us    = False
    _currency = '₹'

    if _is_india:
        _source_badge = (
            '<span style="font-size:10px;font-weight:600;color:#818cf8;text-transform:uppercase;letter-spacing:1px">Source</span>'
            '<span style="color:rgba(255,255,255,0.15);font-size:14px;margin:0 2px">|</span>'
            '<span style="font-size:12px;color:#94a3b8">Pre-filtered Quality companies from NSE/BSE via</span>'
            '<a href="https://www.screener.in/screens/3474068/vm/" target="_blank" '
            'style="font-size:12px;color:#818cf8;text-decoration:none;font-weight:500">screener.in filter</a>'
        )
    else:
        _source_badge = (
            '<span style="font-size:10px;font-weight:600;color:#818cf8;text-transform:uppercase;letter-spacing:1px">Source</span>'
            '<span style="color:rgba(255,255,255,0.15);font-size:14px;margin:0 2px">|</span>'
            '<span style="font-size:12px;color:#94a3b8">Finviz pre-screen + yfinance quality filters</span>'
        )

    _title_col, _nav_col, _user_col = st.columns([2, 7, 1], gap='small')

    # Login / logout button — top right
    with _user_col:
        if st.user.is_logged_in:
            if st.button("Sign out", use_container_width=True):
                st.logout()
        else:
            if st.button("Sign in", use_container_width=True, type="primary"):
                st.login("google")
    st.sidebar.divider()

    # Sidebar filters
    st.sidebar.header("🔍 Filters")

    show_disabled = st.sidebar.checkbox(
        "Show disabled companies", value=False,
        help="Show companies no longer in the screener filter or watchlists"
    )

    df = load_data(show_disabled=show_disabled)

    # Apply market filter — always one of the two markets
    if _is_us:
        df = df[df['exchange'].isin(_us_markets)]
    else:
        df = df[df['exchange'].isin(_india_markets) | df['exchange'].isna()]

    search_query = st.sidebar.text_input(
        "🔎 Search Company",
        placeholder="Type company name or ticker...",
        help="Search by company name or code. Partial matches supported."
    )

    st.sidebar.markdown("---")

    _qf_help = (
        "Preset: Sentiment ≥ 1 • P/E ≤ 105 • D/E ≤ 1.0 • 5Y CAGR ≥ 20% • Promoter ≥ 40% • FCF/CFO ≥ 10%"
        if _is_india else
        "Preset: Sentiment ≥ 1 • P/E ≤ 105 • D/E ≤ 1.0 • 5Y CAGR ≥ 20% • FCF/CFO ≥ 10%"
    )
    quick_filter = st.sidebar.checkbox("⚡ Filter for Growth & Quality", value=False, help=_qf_help)
    _qk = "qf" if quick_filter else "nqf"

    min_sentiment = st.sidebar.slider("Minimum Sentiment", 0, 5,
        1 if quick_filter else 0, key=f"sentiment_{_qk}_{market_filter}")
    max_pe = st.sidebar.slider("Maximum P/E Ratio", 0, 5000,
        105 if quick_filter else 100, key=f"max_pe_{_qk}_{market_filter}")

    industries        = ['All'] + sorted(df['industry'].dropna().unique().tolist())
    selected_industry = st.sidebar.selectbox("Industry", industries, key=f"industry_{market_filter}")

    max_debt = st.sidebar.slider("Maximum Debt/Equity", 0.0, 5.0,
        1.0 if quick_filter else 5.0, key=f"max_debt_{_qk}_{market_filter}")

    _cap_label  = "Market Cap Range (₹ Cr)" if _is_india else "Market Cap Range (Cr, INR equiv.)"
    market_cap_range = st.sidebar.slider(
        _cap_label, min_value=0, max_value=500000, value=(0, 500000),
        step=1000, format="₹%d Cr", key=f"mktcap_{market_filter}"
    )

    min_sales_growth_5y = st.sidebar.number_input(
        "Min Sales Growth 5Y CAGR (%)", min_value=0, max_value=100,
        value=20 if quick_filter else 0, step=1,
        help="Minimum 5-year sales CAGR. Companies with less than 6 years of data are excluded.",
        key=f"cagr_{_qk}_{market_filter}"
    )

    if _is_india:
        min_promoter = st.sidebar.slider(
            "Min Promoter Holding (%)", 0.0, 100.0,
            40.0 if quick_filter else 0.0, step=5.0,
            help="Minimum promoter holding %. Companies without promoter data are included.",
            key=f"promoter_{_qk}"
        )
    else:
        min_promoter = st.sidebar.slider(
            "Min Promoter Holding (%)", 0.0, 100.0, 0.0, step=5.0,
            help="Minimum insider holding %. Companies without insider data are included.",
            key=f"insider_{_qk}"
        )

    min_fcf_cfo = st.sidebar.slider(
        "Min FCF/CFO Ratio (%)", -100, 100,
        10 if quick_filter else 0, step=5,
        help="Minimum Free Cash Flow / Cash from Operations ratio. Green threshold is 25%.",
        key=f"fcf_cfo_{_qk}_{market_filter}"
    )

    # ── Apply filters ──
    filtered_df = df.copy()

    if search_query:
        sq = search_query.lower()
        filtered_df = filtered_df[
            filtered_df['company_name'].str.lower().str.contains(sq, na=False) |
            filtered_df['company_code'].str.lower().str.contains(sq, na=False)
        ]

    if min_sentiment > 0:
        filtered_df = filtered_df[
            (filtered_df['sentiment_rating'] >= min_sentiment) | (filtered_df['sentiment_rating'].isna())
        ]

    if max_pe > 0:
        filtered_df = filtered_df[
            (filtered_df['pe_ratio'] <= max_pe) | (filtered_df['pe_ratio'].isna())
        ]

    if max_debt < 5.0:
        filtered_df = filtered_df[
            (filtered_df['debt_to_equity'] <= max_debt) | (filtered_df['debt_to_equity'].isna())
        ]

    if selected_industry != 'All':
        filtered_df = filtered_df[filtered_df['industry'] == selected_industry]

    min_cap, max_cap = market_cap_range
    if min_cap > 0 or max_cap < 500000:
        filtered_df = filtered_df[
            ((filtered_df['market_cap'] >= min_cap) & (filtered_df['market_cap'] <= max_cap)) |
            (filtered_df['market_cap'].isna())
        ]

    if min_sales_growth_5y > 0:
        filtered_df = filtered_df[
            filtered_df['sales_growth_5y'].notna() & (filtered_df['sales_growth_5y'] >= min_sales_growth_5y)
        ]

    if min_promoter > 0:
        filtered_df = filtered_df[
            (filtered_df['promoter_holding'] >= min_promoter) | (filtered_df['promoter_holding'].isna())
        ]

    if min_fcf_cfo != 0:
        filtered_df = filtered_df[
            (filtered_df['fcf_cfo_ratio'] >= min_fcf_cfo) | (filtered_df['fcf_cfo_ratio'].isna())
        ]

    # Green score sorting
    filtered_df = filtered_df.copy()
    filtered_df['fcf_green']       = (filtered_df['fcf_cfo_ratio'] >= 25).astype(int)
    filtered_df['ssgr_green']      = (filtered_df['ssgr'] > 0).astype(int)
    filtered_df['qoq_green']       = (filtered_df['qoq_profit_growth'] > 0).astype(int)
    filtered_df['yoy_green']       = (filtered_df['yoy_profit_growth'] > 0).astype(int)
    filtered_df['yoy_sales_green'] = (filtered_df['yoy_sales_growth'] > 0).astype(int)
    filtered_df['green_score']     = (
        filtered_df['fcf_green'] + filtered_df['ssgr_green'] + filtered_df['qoq_green'] +
        filtered_df['yoy_green'] + filtered_df['yoy_sales_green']
    )
    filtered_df = filtered_df.sort_values(
        by=['green_score', 'fcf_cfo_ratio', 'ssgr', 'qoq_profit_growth', 'yoy_profit_growth', 'yoy_sales_growth'],
        ascending=[False, False, False, False, False, False],
        na_position='last'
    )

    with _title_col:
        st.markdown(
            '<div style="padding:10px 0 10px 0;border-bottom:1px solid rgba(255,255,255,0.08);'
            'margin-bottom:0;white-space:nowrap;overflow:hidden">'
            '<span style="font-size:20px;font-weight:700;color:#f1f5f9;letter-spacing:-0.5px">Stock Analysis</span>'
            '&nbsp;&nbsp;<span style="font-size:10px;font-weight:500;color:#334155;letter-spacing:2px;'
            'text-transform:uppercase;vertical-align:middle">Portfolio Intelligence</span>'
            '</div>',
            unsafe_allow_html=True
        )

    # ── Navigation (radio persists across reruns via session_state) ──
    _portfolio_tab_name = None
    _is_admin = st.user.is_logged_in and st.user.email == 'amit.balode@gmail.com'
    if st.user.is_logged_in:
        _pf_first = (st.user.name or st.user.email or "User").split()[0]
        _portfolio_tab_name = f"{_pf_first}'s Portfolio"
    _nav_options = ['Home', 'Company Analysis', 'Filtered Companies', 'Track Stock']
    if _portfolio_tab_name:
        _nav_options.append(_portfolio_tab_name)
    _nav_options.append('FAQ')
    if _is_admin:
        _nav_options.append('Admin')

    if 'nav_tab' not in st.session_state:
        st.session_state.nav_tab = 'Home'
    elif st.session_state.nav_tab not in _nav_options:
        st.session_state.nav_tab = 'Home'

    with _nav_col:
        _nav = st.radio(
            'nav', _nav_options,
            horizontal=True, label_visibility='collapsed', key='nav_tab'
        )

    # Inject active-tab underline based on current tab
    _nav_styles = {
        'Home':              (1, '#94a3b8'),
        'Company Analysis':  (2, '#34d399'),
        'Filtered Companies':(3, '#818cf8'),
        'Track Stock':       (4, '#f5a623'),
    }
    if _portfolio_tab_name:
        _nav_styles[_portfolio_tab_name] = (5, '#38bdf8')
        _nav_styles['FAQ'] = (6, '#f472b6')
        _nav_styles['Admin'] = (7, '#fb923c')
    else:
        _nav_styles['FAQ'] = (5, '#f472b6')
        _nav_styles['Admin'] = (6, '#fb923c')

    _ni, _nc = _nav_styles[_nav]
    st.markdown(
        f'<style>div[data-testid="stRadio"] label[data-baseweb="radio"]:nth-of-type({_ni})'
        f'{{border-bottom:2px solid {_nc}!important;color:#f1f5f9!important;font-weight:600!important;}}</style>',
        unsafe_allow_html=True
    )

    # ─────────────────────────────────────────────────────
    # Home
    # ─────────────────────────────────────────────────────
    if _nav == 'Home':
        total_cos  = len(df)
        with_price = int(df['current_price'].notna().sum())
        sectors    = int(df['sector'].nunique())

        _FEAT = [
            ('01', 'Screen 670+ companies with 20+ filters',          False),
            ('02', '10 years of P&amp;L, balance sheet &amp; cash flow', True),
            ('03', 'SSGR, FCF &amp; D/E computed automatically',       False),
            ('04', 'Live prices refreshed every hour',                  False),
            ('05', 'Track any stock from Screener.in instantly',        False),
        ]

        _left, _right = st.columns([5, 6], gap='large')

        with _left:
            st.markdown(
                '<div style="padding:40px 0 24px 0">'
                '<div style="font-size:36px;font-weight:800;letter-spacing:-1px;color:#f1f5f9;line-height:1.2">'
                'Smarter research.<br>Long-term conviction.</div>'
                '<div style="font-size:14px;color:#64748b;margin-top:12px;line-height:1.6">'
                'A private platform for deep-dive analysis on Indian equities — '
                'financials, quality scores and live market data in one place.'
                '</div>'
                '</div>',
                unsafe_allow_html=True
            )

            # Numbered feature list
            feat_html = '<div style="margin:8px 0 28px 0">'
            for num, label, active in _FEAT:
                num_clr  = '#818cf8' if active else 'rgba(255,255,255,0.18)'
                lbl_clr  = '#f1f5f9' if active else '#64748b'
                fw       = '700'     if active else '400'
                feat_html += (
                    f'<div style="display:flex;align-items:center;gap:18px;padding:10px 0;'
                    f'border-bottom:1px solid rgba(255,255,255,0.05)">'
                    f'<span style="font-size:18px;font-weight:700;color:{num_clr};min-width:28px">{num}</span>'
                    f'<span style="font-size:14px;font-weight:{fw};color:{lbl_clr}">{label}</span>'
                    f'</div>'
                )
            feat_html += '</div>'
            st.markdown(feat_html, unsafe_allow_html=True)

            # Stat badges
            st.markdown(
                f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:20px;margin-bottom:32px">'
                f'<span style="background:rgba(129,140,248,0.12);border:1px solid rgba(129,140,248,0.25);'
                f'border-radius:20px;padding:5px 14px;font-size:12px;color:#a5b4fc;font-weight:600">'
                f'{total_cos}+ Companies</span>'
                f'<span style="background:rgba(16,217,143,0.10);border:1px solid rgba(16,217,143,0.22);'
                f'border-radius:20px;padding:5px 14px;font-size:12px;color:#34d399;font-weight:600">'
                f'10Y Financial History</span>'
                f'<span style="background:rgba(245,166,35,0.10);border:1px solid rgba(245,166,35,0.22);'
                f'border-radius:20px;padding:5px 14px;font-size:12px;color:#f5a623;font-weight:600">'
                f'{sectors} Sectors</span>'
                f'</div>',
                unsafe_allow_html=True
            )

            st.markdown(
                '<div style="font-size:11px;color:#334155;padding-top:8px">'
                'Built for private use &nbsp;·&nbsp; Data: Screener.in &amp; Yahoo Finance &nbsp;·&nbsp; Not financial advice'
                '</div>',
                unsafe_allow_html=True
            )

        with _right:
            # ── NH 10-year summary ──
            _nh_con = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
            _nh_years_df = pd.read_sql(
                "SELECT year FROM screener_annual_pl "
                "WHERE company_code='NH' AND metric='Sales+' AND year LIKE 'Mar%' "
                "ORDER BY CAST(SUBSTR(year,-4) AS INTEGER) DESC LIMIT 10",
                _nh_con
            )
            _nh_years = _nh_years_df['year'].tolist()

            def _nh_vals(table, metric):
                if not _nh_years:
                    return {}
                placeholders = ','.join(['?'] * len(_nh_years))
                _df = pd.read_sql(
                    f"SELECT year, CAST(REPLACE(REPLACE(value,'%',''),',','') AS REAL) as v "
                    f"FROM {table} WHERE company_code='NH' AND metric=? AND year IN ({placeholders})",
                    _nh_con, params=[metric] + _nh_years
                )
                return dict(zip(_df['year'], _df['v']))

            _nh_sales  = _nh_vals('screener_annual_pl', 'Sales+')
            _nh_profit = _nh_vals('screener_annual_pl', 'Net Profit+')
            _nh_opm    = _nh_vals('screener_annual_pl', 'OPM %')
            _nh_roce   = _nh_vals('screener_ratios',    'ROCE %')
            _nh_eps    = _nh_vals('screener_annual_pl', 'EPS in Rs')

            # Cash flow data (last 6 Mar years for cumulative FCF table)
            _nh_6y = _nh_years[:6]  # newest 6
            def _nh_cf_vals(metric):
                if not _nh_6y:
                    return {}
                placeholders = ','.join(['?'] * len(_nh_6y))
                _df = pd.read_sql(
                    f"SELECT year, CAST(REPLACE(value,',','') AS REAL) as v "
                    f"FROM screener_cash_flow WHERE company_code='NH' AND metric=? AND year IN ({placeholders})",
                    _nh_con, params=[metric] + _nh_6y
                )
                return dict(zip(_df['year'], _df['v']))

            def _nh_pl_vals_6y(metric):
                if not _nh_6y:
                    return {}
                placeholders = ','.join(['?'] * len(_nh_6y))
                _df = pd.read_sql(
                    f"SELECT year, CAST(REPLACE(value,',','') AS REAL) as v "
                    f"FROM screener_annual_pl WHERE company_code='NH' AND metric=? AND year IN ({placeholders})",
                    _nh_con, params=[metric] + _nh_6y
                )
                return dict(zip(_df['year'], _df['v']))

            _nh_cfo_d    = _nh_cf_vals('Cash from Operating Activity+')
            _nh_inv_d    = _nh_cf_vals('Cash from Investing Activity+')
            _nh_oinc_d   = _nh_pl_vals_6y('Other Income+')
            _nh_int_d    = _nh_pl_vals_6y('Interest')
            _nh_mktcap   = pd.read_sql(
                "SELECT market_cap FROM derived_metrics_analysis WHERE company_code='NH'",
                _nh_con
            )['market_cap'].iloc[0] if True else None
            _nh_con.close()

            # Cumulative 6Y sums
            _sum_cfo   = sum(v for v in _nh_cfo_d.values() if v is not None)
            _sum_inv   = sum(v for v in _nh_inv_d.values() if v is not None)
            _sum_oinc  = sum(v for v in _nh_oinc_d.values() if v is not None)
            _sum_int   = sum(v for v in _nh_int_d.values() if v is not None)
            _capex     = abs(_sum_inv)
            _fcf_core  = _sum_cfo - _capex
            _fcf_plus  = _fcf_core - _sum_int + _sum_oinc
            _mktcap_cr = (_nh_mktcap or 0)
            _pct_mktcap = (_fcf_plus / _mktcap_cr * 100) if _mktcap_cr else None

            # Build header row (years, newest first)
            _yr_labels = [y.replace('Mar ', "'") for y in _nh_years]
            _hdr = ''.join(
                f'<th style="padding:3px 7px;text-align:right;color:#64748b;font-size:10px;'
                f'font-weight:600;white-space:nowrap">{y}</th>'
                for y in _yr_labels
            )

            def _row(label, data_dict, fmt='cr', color=None):
                cells = ''
                _prev = None
                for yr in _nh_years:
                    v = data_dict.get(yr)
                    if v is None:
                        cells += '<td style="padding:3px 7px;text-align:right;color:#475569;font-size:11px">—</td>'
                        _prev = None
                        continue
                    if fmt == 'cr':
                        txt = f'{v:,.0f}'
                    elif fmt == 'pct':
                        txt = f'{v:.0f}%'
                    elif fmt == 'eps':
                        txt = f'{v:.1f}'
                    else:
                        txt = str(v)
                    if color == 'profit':
                        clr = '#10d98f' if v > 0 else '#f06067'
                    elif color == 'trend' and _prev is not None:
                        clr = '#10d98f' if v >= _prev else '#f06067'
                    else:
                        clr = '#f1f5f9'
                    cells += f'<td style="padding:3px 7px;text-align:right;color:{clr};font-size:11px;font-weight:500">{txt}</td>'
                    _prev = v
                lbl_cell = f'<td style="padding:3px 7px;color:#94a3b8;font-size:10px;font-weight:600;white-space:nowrap;text-transform:uppercase;letter-spacing:0.5px">{label}</td>'
                return f'<tr style="border-bottom:1px solid rgba(255,255,255,0.04)">{lbl_cell}{cells}</tr>'

            _tbl_html = (
                '<div style="margin-top:24px">'
                '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);'
                'border-radius:12px;padding:14px 14px 10px">'
                '<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px">'
                '<div style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:1.5px">'
                '10-Year Summary</div>'
                '<div style="font-size:10px;color:#475569">NH · Narayana Hrudayalaya · ₹ Crores</div>'
                '</div>'
                '<div style="overflow-x:auto">'
                '<table style="width:100%;border-collapse:collapse">'
                f'<thead><tr><th style="padding:3px 7px;text-align:left"></th>{_hdr}</tr></thead>'
                '<tbody>'
                + _row('Sales',      _nh_sales,  'cr',  'trend')
                + _row('Net Profit', _nh_profit, 'cr',  'profit')
                + _row('OPM %',      _nh_opm,    'pct', 'trend')
                + _row('ROCE %',     _nh_roce,   'pct', 'trend')
                + _row('EPS (₹)',    _nh_eps,    'eps', 'profit')
                +
                '</tbody></table></div>'
                '<div style="font-size:10px;color:#334155;margin-top:8px">Source: Screener.in</div>'
                '</div></div>'
            )
            st.markdown(_tbl_html, unsafe_allow_html=True)

            # ── 6-Year FCF Summary card ──
            def _fcf_row(label, value, desc, indent=False, fmt='cr'):
                if value is None:
                    val_s, clr = '—', '#475569'
                elif fmt == 'pct':
                    val_s = f'{value:+.1f}%'
                    clr = '#10d98f' if value >= 0 else '#f06067'
                else:
                    val_s = f'₹{value:,.0f} Cr'
                    clr = '#10d98f' if value >= 0 else '#f06067'
                prefix = '└ ' if indent else ''
                lbl_fw = '600' if indent else '400'
                return (
                    f'<tr style="border-bottom:1px solid rgba(255,255,255,0.04)">'
                    f'<td style="padding:6px 10px;color:#cbd5e1;font-size:11px;font-weight:{lbl_fw}">'
                    f'{prefix}{label}</td>'
                    f'<td style="padding:6px 10px;text-align:right;color:{clr};font-size:12px;'
                    f'font-weight:700;white-space:nowrap;min-width:90px">{val_s}</td>'
                    f'<td style="padding:6px 10px;color:#475569;font-size:10px;line-height:1.4">{desc}</td>'
                    f'</tr>'
                )

            _mktcap_s = f'₹{_mktcap_cr:,.0f} Cr' if _mktcap_cr else '—'
            _n_years  = len(_nh_6y)
            _yr_range = f'{_nh_6y[-1]} – {_nh_6y[0]}' if _nh_6y else ''

            _fcf_tbl = (
                '<div style="margin-top:12px">'
                '<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);'
                'border-radius:12px;padding:14px 14px 10px">'
                '<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px">'
                f'<div style="font-size:11px;font-weight:700;color:#818cf8;text-transform:uppercase;letter-spacing:1.5px">'
                f'{_n_years}-Year FCF Summary (₹ Crores)</div>'
                f'<div style="font-size:10px;color:#475569">NH · {_yr_range}</div>'
                '</div>'
                f'<div style="font-size:11px;color:#64748b;margin-bottom:8px">Market Cap: '
                f'<span style="color:#f1f5f9;font-weight:600">{_mktcap_s}</span></div>'
                '<table style="width:100%;border-collapse:collapse">'
                '<tbody>'
                + _fcf_row('CFO', _sum_cfo, 'Cash generated from core business operations')
                + _fcf_row('Capex', _capex, 'Money spent on plant, equipment &amp; expansion (absolute of investing CF)')
                + _fcf_row('Free Cash Flow from core business', _fcf_core,
                           'CFO − Capex = discretionary surplus after capital expenditure. '
                           'If negative, company is funding capex via debt or equity.')
                + _fcf_row('Other Income', _sum_oinc,
                           'Non-operating income — interest earned, dividends received, asset sales.')
                + _fcf_row('Interest Paid', _sum_int,
                           'Finance cost deducted to get true shareholder surplus.')
                + _fcf_row(f'Available Cash Surplus in last {_n_years} years including debt (in bank)', _fcf_plus,
                           'True surplus available to shareholders after capex, debt servicing &amp; non-core income.')
                + (_fcf_row('% of Market Cap', _pct_mktcap, 'Higher = more cash generated vs company size', indent=True, fmt='pct') if _pct_mktcap is not None else '')
                +
                '</tbody></table>'
                '<div style="font-size:10px;color:#334155;margin-top:8px">Source: Screener.in · Cumulative totals</div>'
                '</div></div>'
            )
            st.markdown(_fcf_tbl, unsafe_allow_html=True)

            st.markdown('<div style="margin-top:20px"></div>', unsafe_allow_html=True)
            _gap, _btn_col = st.columns([3, 1])
            with _btn_col:
                st.button(
                    'Get Started →', type='primary', use_container_width=True,
                    on_click=lambda: st.session_state.update({'nav_tab': 'Company Analysis'})
                )

    # ─────────────────────────────────────────────────────
    # Company Analysis
    # ─────────────────────────────────────────────────────
    elif _nav == 'Company Analysis':
        st.markdown(
            f'<div style="display:inline-flex;align-items:center;gap:8px;padding:5px 14px;'
            f'background:rgba(129,140,248,0.08);border:1px solid rgba(129,140,248,0.2);'
            f'border-radius:20px;margin-bottom:12px">'
            f'{_source_badge}'
            f'</div>',
            unsafe_allow_html=True
        )
        render_company_detail(filtered_df)

    # ─────────────────────────────────────────────────────
    # Filtered Companies
    # ─────────────────────────────────────────────────────
    elif _nav == 'Filtered Companies':
        section_header("Overview")
        render_kpi_cards(df, filtered_df)

        # Build context badge for screener section
        if search_query:
            _screener_badge = f'"{search_query}" · {len(filtered_df)} matches'
        else:
            _screener_badge = f"{len(filtered_df)} companies"
        section_header("Screener", _screener_badge)

        # Build display DataFrame
        display_df = filtered_df[[
            'company_code', 'company_name', 'sector', 'industry',
            'current_price', 'price_change_pct', 'updated_at', 'week_52_high', 'week_52_low',
            'sentiment_rating', 'pe_ratio', 'book_value', 'peg_ratio', 'roce', 'market_cap', 'sales_growth_5y',
            'ssgr', 'ssgr_prev', 'year1_sales_growth', 'year2_sales_growth',
            'qoq_profit_growth', 'qoq_profit_growth_prev', 'yoy_profit_growth', 'yoy_sales_growth',
            'latest_quarter', 'prev_quarter',
            'promoter_trend_display',
            'npm', 'total_fcf', 'fcf_cfo_ratio', 'debt_to_equity',
            'created_at', 'source', 'exchange',
        ]].copy().reset_index(drop=True)

        # Compute "new company" flag (added within last 7 days)
        _now = datetime.now()
        created_dt = pd.to_datetime(display_df['created_at'], errors='coerce', format='mixed')
        display_df['is_new'] = (
            created_dt.notna() &
            ((_now - created_dt).dt.total_seconds() <= 7 * 24 * 3600)
        )
        display_df['First Added'] = created_dt.apply(
            lambda x: x.strftime('%d %b %Y') if pd.notna(x) else 'N/A'
        )
        display_df['company_name'] = display_df.apply(
            lambda r: f"🆕 {r['company_name']}" if r['is_new'] else r['company_name'], axis=1
        )
        display_df['Source'] = display_df['source'].apply(
            lambda x: 'MANUAL' if x == 'manual' else 'SYNC'
        )

        # Capture new company info before display_df is slimmed
        _new_count = int(display_df['is_new'].sum())
        _new_names = (
            display_df[display_df['is_new']]['company_name']
            .str.replace('🆕 ', '', regex=False).tolist()
        )

        company_codes = display_df['company_code'].tolist()

        def _row_currency(row):
            return '$' if row.get('exchange') in _us_markets else '₹'

        display_df['cmp'] = display_df.apply(
            lambda x: format_price(x['current_price'], x['price_change_pct'], x['updated_at'],
                                   currency=_row_currency(x)), axis=1
        )
        display_df['52w_range'] = display_df.apply(
            lambda x: f"{_row_currency(x)}{x['week_52_high']:.0f} / {x['week_52_low']:.0f}"
            if pd.notna(x['week_52_high']) and pd.notna(x['week_52_low']) else "N/A", axis=1
        )
        display_df['sentiment_rating'] = display_df['sentiment_rating'].apply(render_stars)
        display_df['pe_ratio']         = display_df['pe_ratio'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        display_df['pb_ratio']         = display_df.apply(
            lambda x: round(x['current_price'] / x['book_value'], 2)
            if pd.notna(x['current_price']) and pd.notna(x['book_value']) and x['book_value'] > 0
            else None, axis=1
        )
        display_df['pb_ratio']         = display_df['pb_ratio'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        display_df['peg_ratio']        = display_df['peg_ratio'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")

        def format_roce(val):
            if pd.isna(val): return "N/A"
            emoji = "🟢" if val >= 20 else ("🟡" if val >= 15 else "🔴")
            return f"{emoji} {val:.1f}%"

        display_df['roce']             = display_df['roce'].apply(format_roce)
        display_df['market_cap'] = display_df.apply(
            lambda r: (f"{r['market_cap']:.0f} Cr" if pd.notna(r['market_cap']) else "N/A")
            if r.get('exchange') in _us_markets
            else (f"₹{r['market_cap']:.0f} Cr" if pd.notna(r['market_cap']) else "N/A"),
            axis=1
        )
        display_df['sales_growth_5y']  = display_df['sales_growth_5y'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")

        def format_ssgr(val):
            if pd.isna(val): return "N/A"
            emoji = "🟢" if val > 0 else "🔴"
            return f"{emoji} {val:.1f}%"

        display_df['ssgr']               = display_df['ssgr'].apply(format_ssgr)
        display_df['ssgr_prev']          = display_df['ssgr_prev'].apply(format_ssgr)
        display_df['year1_sales_growth'] = display_df['year1_sales_growth'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
        display_df['year2_sales_growth'] = display_df['year2_sales_growth'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
        display_df['npm']                = display_df['npm'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")

        def format_qoq_with_quarter(row, val_col, quarter_col):
            val     = row[val_col]
            quarter = row[quarter_col]
            if pd.isna(val): return "N/A"
            emoji = "🟢" if val >= 0 else "🔴"
            q_str = quarter.replace(' ', '-') if isinstance(quarter, str) else "?"
            return f"{emoji} {val:.1f}%, {q_str}"

        display_df['qoq_profit_growth']      = display_df.apply(
            lambda r: format_qoq_with_quarter(r, 'qoq_profit_growth', 'latest_quarter'), axis=1
        )
        display_df['qoq_profit_growth_prev'] = display_df.apply(
            lambda r: format_qoq_with_quarter(r, 'qoq_profit_growth_prev', 'prev_quarter'), axis=1
        )
        display_df['yoy_profit_growth'] = display_df['yoy_profit_growth'].apply(
            lambda x: f"{'🟢' if x >= 0 else '🔴'} {x:.1f}%" if pd.notna(x) else "N/A"
        )
        display_df['yoy_sales_growth']  = display_df['yoy_sales_growth'].apply(
            lambda x: f"{'🟢' if x >= 0 else '🔴'} {x:.1f}%" if pd.notna(x) else "N/A"
        )
        display_df['total_fcf'] = display_df.apply(
            lambda r: format_number(r['total_fcf'], unit='M')
            if r.get('exchange') in _us_markets
            else format_number(r['total_fcf']),
            axis=1
        )

        def format_fcf_cfo(val):
            if pd.isna(val): return "N/A"
            emoji = "🟢" if val >= 25 else "🔴"
            return f"{emoji} {val:.1f}%"

        display_df['fcf_cfo_ratio']  = display_df['fcf_cfo_ratio'].apply(format_fcf_cfo)
        display_df['debt_to_equity'] = display_df['debt_to_equity'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")

        display_df['company_code'] = display_df.apply(
            lambda r: (
                f"https://finance.yahoo.com/quote/{r['company_code']}/"
                if r.get('exchange') in _us_markets
                else f"https://www.screener.in/company/{r['company_code']}/"
            ) if pd.notna(r['company_code']) else "",
            axis=1
        )

        display_df = display_df[[
            'company_code', 'company_name', 'sector', 'industry', 'cmp', '52w_range',
            'sales_growth_5y', 'sentiment_rating', 'Source', 'pe_ratio', 'pb_ratio', 'peg_ratio', 'roce',
            'fcf_cfo_ratio', 'ssgr', 'ssgr_prev', 'qoq_profit_growth', 'qoq_profit_growth_prev',
            'yoy_profit_growth', 'yoy_sales_growth',
            'promoter_trend_display',
            'market_cap', 'npm',
            'total_fcf', 'debt_to_equity',
            'First Added',
        ]]
        # exchange col was used for per-row logic above; not displayed

        _promoter_col = 'Promoter Holding'
        display_df.columns = [
            'Code', 'Company', 'Sector', 'Industry', 'CMP', '52W High/Low',
            '5Y CAGR', 'Sentiment', 'Source', 'P/E', 'P/B', 'PEG', 'ROCE',
            'FCF/CFO', 'SSGR', 'SSGR (Prev)', 'QoQ Profit', 'Prev QoQ', 'Y-o-Y Profit', 'Y-o-Y Sales',
            _promoter_col,
            'Market Cap (Cr)', 'NPM %',
            'FCF (10Y)', 'D/E',
            'First Added',
        ]

        if _new_count > 0:
            with st.expander(
                f"🆕 **{_new_count} new {'company' if _new_count == 1 else 'companies'} added in the last 7 days**",
                expanded=False
            ):
                st.write(', '.join(_new_names))

        display_df.insert(0, '🗑️', False)

        edited_df = st.data_editor(
            display_df,
            use_container_width=True,
            height=600,
            disabled=[c for c in display_df.columns if c != '🗑️'],
            column_config={
                "🗑️": st.column_config.CheckboxColumn(
                    "🗑️",
                    help="Check to delete this company from all tables",
                    width="small",
                ),
                "Code": st.column_config.LinkColumn(
                    "Code",
                    help="Click to view company on Screener.in",
                    display_text="https://www.screener.in/company/(.*?)/",
                    width=80
                ),
                "First Added": st.column_config.TextColumn(
                    "First Added",
                    help="Date when company was first added to the database. 🆕 in Company name = added within last 7 days.",
                    width="small"
                ),
                "Source": st.column_config.TextColumn(
                    "Source",
                    help="SYNC = added via screener filter job | MANUAL = manually added via Add Stock form",
                    width="small"
                ),
                "CMP": st.column_config.TextColumn(
                    "CMP",
                    help="Current Market Price with change percentage. Timestamp shows last Yahoo Finance update (IST).",
                    width=200
                ),
                "Sentiment": st.column_config.TextColumn(
                    "Sentiment",
                    help="Market sentiment based on price position in 52-week range: ⭐⭐⭐⭐⭐ (80-100%) | ⭐⭐⭐⭐ (60-80%) | ⭐⭐⭐ (40-60%) | ⭐⭐ (20-40%) | ⭐ (0-20%)",
                    width="small"
                ),
                "P/B": st.column_config.TextColumn(
                    "P/B",
                    help="Price to Book Value ratio (CMP / Book Value per share).",
                    width="small"
                ),
                "ROCE": st.column_config.TextColumn(
                    "ROCE",
                    help="Return on Capital Employed. 🟢 ≥20% (Excellent) | 🟡 15-20% (Good) | 🔴 <15% (Poor)",
                    width="small"
                ),
                "FCF/CFO": st.column_config.TextColumn(
                    "FCF/CFO",
                    help="Free Cash Flow / Cash from Operations. 🟢 ≥25% (Low capex) | 🔴 <25% (High capex)",
                    width="small"
                ),
                "SSGR": st.column_config.TextColumn(
                    "SSGR",
                    help="Sustainable Sales Growth Rate (latest 3 years). 🟢 >0% | 🔴 ≤0%",
                    width="small"
                ),
                "SSGR (Prev)": st.column_config.TextColumn(
                    "SSGR (Prev)",
                    help="Sustainable Sales Growth Rate (previous 3 years). Compare with SSGR to see trend.",
                    width="small"
                ),
                "QoQ Profit": st.column_config.TextColumn(
                    "QoQ Profit",
                    help="Quarter-over-Quarter profit growth. 🟢 Increased | 🔴 Decreased",
                    width="medium"
                ),
                "Prev QoQ": st.column_config.TextColumn(
                    "Prev QoQ",
                    help="Previous Quarter-over-Quarter profit growth.",
                    width="medium"
                ),
                "Y-o-Y Profit": st.column_config.TextColumn(
                    "Y-o-Y Profit",
                    help="Year-over-Year profit growth. 🟢 Increased | 🔴 Decreased",
                    width="small"
                ),
                "Y-o-Y Sales": st.column_config.TextColumn(
                    "Y-o-Y Sales",
                    help="Year-over-Year sales growth. 🟢 Increased | 🔴 Decreased",
                    width="small"
                ),
                "Promoter Holding": st.column_config.TextColumn(
                    "Promoter Holding",
                    help="Promoter holding trend (last 4 quarters). 🟢 Stable/Increased | 🟡 Decreased <10% | 🔴 Decreased ≥10%",
                    width="medium"
                ),
            }
        )

        checked_indices = edited_df[edited_df['🗑️']].index.tolist()
        if checked_indices:
            confirm_delete_dialog(company_codes[checked_indices[0]])

    # ─────────────────────────────────────────────────────
    # Track Stock
    # ─────────────────────────────────────────────────────
    elif _nav == 'Track Stock':
        _, center_col, _ = st.columns([0.3, 3.4, 0.3])
        with center_col:
            st.markdown(
                '<div style="margin:28px 0 14px 0;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.07)">'
                '<span style="font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:2px">'
                'Add a Company</span></div>',
                unsafe_allow_html=True
            )

            st.markdown("""
                <style>
                div[data-testid="stForm"] input::placeholder {
                    color: rgba(255,255,255,0.2) !important;
                    opacity: 1 !important;
                }
                div[data-testid="stForm"] button[kind="secondaryFormSubmit"] {
                    background: linear-gradient(135deg, #f5a623 0%, #f06067 100%) !important;
                    color: #fff !important;
                    border: none !important;
                    border-radius: 10px !important;
                    font-weight: 700 !important;
                    font-size: 13px !important;
                    letter-spacing: 0.5px !important;
                    box-shadow: 0 4px 14px rgba(245,166,35,0.35) !important;
                    transition: all 0.2s ease !important;
                    margin-top: 4px !important;
                }
                div[data-testid="stForm"] button[kind="secondaryFormSubmit"]:hover {
                    box-shadow: 0 6px 20px rgba(245,166,35,0.55) !important;
                    transform: translateY(-1px) !important;
                }
                </style>
            """, unsafe_allow_html=True)

            _form_col, _ = st.columns([1.6, 1])
            with _form_col:
                with st.form("add_stock_form_tab", clear_on_submit=True):
                    url_col, btn_col = st.columns([4, 1])
                    with url_col:
                        screener_url = st.text_input(
                            "Screener.in URL",
                            placeholder="https://www.screener.in/company/TCS/",
                            label_visibility="collapsed"
                        )
                    with btn_col:
                        submitted = st.form_submit_button("+ Add", use_container_width=True)

            if submitted:
                if not screener_url.strip():
                    st.error("Please paste a screener.in URL.")
                else:
                    # ── Session-level cooldown ────────────────────────────────
                    _last = st.session_state.get("_last_add_ts")
                    if _last:
                        _elapsed = (datetime.now() - _last).total_seconds()
                        if _elapsed < _COOLDOWN_SECS:
                            st.markdown(
                                f'<div style="padding:12px 16px;border-radius:10px;'
                                f'background:rgba(240,96,103,0.08);border:1px solid rgba(240,96,103,0.2);'
                                f'font-size:13px;color:#f06067">'
                                f'Please wait <b>{int(_COOLDOWN_SECS - _elapsed) + 1}s</b> before submitting again.</div>',
                                unsafe_allow_html=True
                            )
                            st.stop()

                    # ── IP-based rate limit ───────────────────────────────────
                    _client_ip = _get_client_ip()
                    _allowed, _reason = check_rate_limit(_client_ip)
                    if not _allowed:
                        st.markdown(
                            f'<div style="padding:12px 16px;border-radius:10px;'
                            f'background:rgba(240,96,103,0.08);border:1px solid rgba(240,96,103,0.2);'
                            f'font-size:13px;color:#f06067">🚫 {_reason}</div>',
                            unsafe_allow_html=True
                        )
                        st.stop()

                    code, err = parse_screener_url(screener_url)
                    if err:
                        st.error(err)
                    else:
                        record_rate_limit(_client_ip)
                        st.session_state["_last_add_ts"] = datetime.now()
                        ok = True
                        stock_dir = os.path.dirname(os.path.abspath(__file__))

                        # Stage renderer
                        _ph = st.empty()
                        _stages = [
                            ['Downloading 10-year financial history from Screener.in', 'active'],
                            ['Storing P&L, balance sheet & cash flow data',            'pending'],
                            ['Fetching live price & market cap from Yahoo Finance',    'pending'],
                            ['Computing growth rates, FCF, valuation & quality scores','pending'],
                        ]
                        _icon_html = {
                            'pending': '<span style="width:18px;height:18px;border-radius:50%;border:2px solid #334155;display:inline-block;flex-shrink:0"></span>',
                            'active':  '<span style="width:18px;height:18px;border-radius:50%;border:2px solid #f5a623;border-top-color:transparent;display:inline-block;flex-shrink:0;animation:spin 0.8s linear infinite"></span>',
                            'done':    '<span style="width:18px;height:18px;border-radius:50%;background:#10d98f;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;font-size:11px;color:#0b0e1a;font-weight:700">✓</span>',
                            'error':   '<span style="width:18px;height:18px;border-radius:50%;background:#f06067;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;font-size:11px;color:#fff;font-weight:700">✕</span>',
                        }
                        _text_colors = {'pending': '#5a6a7e', 'active': '#f1f5f9', 'done': '#f1f5f9', 'error': '#f06067'}

                        def _render_stages():
                            rows = ''.join(
                                f'<div style="display:flex;align-items:center;gap:12px;padding:11px 0;'
                                f'border-bottom:1px solid rgba(255,255,255,0.05)">'
                                f'{_icon_html[s]}'
                                f'<span style="font-size:13px;color:{_text_colors[s]};font-family:Inter,sans-serif">{lbl}</span>'
                                f'</div>'
                                for lbl, s in _stages
                            )
                            _ph.markdown(
                                f'<style>@keyframes spin{{to{{transform:rotate(360deg)}}}}</style>'
                                f'<div style="background:#0f172a;border:1px solid rgba(255,255,255,0.08);'
                                f'border-radius:12px;padding:2px 20px;margin-top:12px">{rows}</div>',
                                unsafe_allow_html=True
                            )

                        _render_stages()

                        # Stage 1 — screener.in sync
                        _proc = subprocess.Popen(
                            [sys.executable,
                             os.path.join(stock_dir, 'discover_new_companies.py'),
                             '--companies', code],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1
                        )
                        for _line in _proc.stdout:
                            _ll = _line.lower()
                            if any(k in _ll for k in ('saving', 'inserting', 'updating', 'stored', 'written')):
                                _stages[0][1] = 'done'
                                _stages[1][1] = 'active'
                                _render_stages()
                        _proc.wait()

                        # Verify the company actually landed in the DB
                        _sync_ok = False
                        if _proc.returncode == 0:
                            _chk = get_connection().execute(
                                "SELECT 1 FROM screener_companies WHERE company_code = ?", (code,)
                            ).fetchone()
                            _sync_ok = _chk is not None

                        if not _sync_ok:
                            _stages[0][1] = 'error'
                            _stages[1][1] = 'error'
                            _render_stages()
                            st.markdown(
                                f'<div style="margin-top:12px;padding:12px 16px;border-radius:10px;'
                                f'background:rgba(240,96,103,0.08);border:1px solid rgba(240,96,103,0.2);'
                                f'font-size:13px;color:#f06067">'
                                f'Could not find <b>{code}</b> on Screener.in. '
                                f'Check the URL and make sure the company code is correct.</div>',
                                unsafe_allow_html=True
                            )
                        else:
                            _stages[0][1] = 'done'
                            _stages[1][1] = 'done'
                            _stages[2][1] = 'active'
                            _render_stages()

                            # Stage 2 — live price from Yahoo Finance
                            _proc2 = subprocess.run(
                                [sys.executable,
                                 os.path.join(stock_dir, 'fetch_market_data.py'),
                                 '-i', 'yahoo-daily-change', '--companies', code],
                                capture_output=True
                            )
                            _stages[2][1] = 'done' if _proc2.returncode == 0 else 'error'
                            _stages[3][1] = 'active'
                            _render_stages()

                            # Stage 3 — derived metrics
                            _proc3 = subprocess.run(
                                [sys.executable,
                                 os.path.join(stock_dir, 'compute_growth_metrics.py')],
                                capture_output=True
                            )
                            if _proc3.returncode == 0:
                                _stages[3][1] = 'done'
                                _render_stages()
                                st.markdown(
                                    f'<div style="margin-top:12px;padding:12px 16px;border-radius:10px;'
                                    f'background:rgba(16,217,143,0.08);border:1px solid rgba(16,217,143,0.2);'
                                    f'font-size:13px;color:#10d98f">'
                                    f'<b>{code}</b> added — here\'s a quick look:</div>',
                                    unsafe_allow_html=True
                                )
                                st.cache_data.clear()
                                _fresh_df = load_data()
                                render_company_detail(_fresh_df, preselect_code=code)
                                st.session_state["_tracked_code"] = code
                            else:
                                _stages[3][1] = 'error'
                                _render_stages()
                                st.markdown(
                                    f'<div style="margin-top:12px;padding:12px 16px;border-radius:10px;'
                                    f'background:rgba(245,166,35,0.08);border:1px solid rgba(245,166,35,0.2);'
                                    f'font-size:13px;color:#f5a623">'
                                    f'<b>{code}</b> synced but metrics calculation failed. Will retry on next cron run.</div>',
                                    unsafe_allow_html=True
                                )

            # ── Add to Portfolio button (persists via session state) ──
            _tc = st.session_state.get("_tracked_code")
            if _tc and st.user.is_logged_in:
                _user_email = st.user.email
                _in_pf = _tc in get_user_portfolio_codes(_user_email, st.user.name)
                st.markdown('<div style="margin-top:20px"></div>', unsafe_allow_html=True)
                _pf_btn_col, _ = st.columns([1, 3])
                with _pf_btn_col:
                    if _in_pf:
                        st.success(f"✓ {_tc} is in your portfolio")
                        if st.button("Remove from my portfolio", use_container_width=True, key="rm_pf"):
                            remove_from_user_portfolio(_tc, _user_email)
                            st.rerun()
                    else:
                        if st.button(f"＋ Add {_tc} to my portfolio", type="primary",
                                     use_container_width=True, key="add_pf"):
                            if add_to_user_portfolio(_tc, _user_email):
                                st.rerun()


    # ─────────────────────────────────────────────────────
    # User Portfolio
    # ─────────────────────────────────────────────────────
    elif _portfolio_tab_name and _nav == _portfolio_tab_name:
        _user_email = st.user.email
        _user_pf_codes = get_user_portfolio_codes(_user_email, st.user.name)

        section_header(_portfolio_tab_name, f"{len(_user_pf_codes)} stocks")

        if not _user_pf_codes:
            st.markdown(
                '<div style="text-align:center;padding:60px 0">'
                '<div style="font-size:36px;margin-bottom:12px">📋</div>'
                '<div style="font-size:16px;font-weight:600;color:#f1f5f9;margin-bottom:6px">Your portfolio is empty</div>'
                '<div style="font-size:13px;color:#64748b">Go to Track Stock, analyse a company, and click<br>'
                '<b style="color:#94a3b8">＋ Add to my portfolio</b></div>'
                '</div>',
                unsafe_allow_html=True
            )
        else:
            _pf_df = df[df['company_code'].isin(_user_pf_codes)].copy().reset_index(drop=True)

            # ── Format for display ──
            def _pf_currency(row):
                return '$' if row.get('exchange') in _us_markets else '₹'

            def _fmt_mcap(x):
                if pd.isna(x):
                    return "N/A"
                if x >= 100000:
                    return f"₹{x/100000:.1f}L Cr"
                return f"₹{x:,.0f} Cr"

            _pf_df['CMP'] = _pf_df.apply(
                lambda x: format_price(x['current_price'], x['price_change_pct'],
                                       x['updated_at'], currency=_pf_currency(x)), axis=1
            )
            _pf_df['P/E'] = _pf_df['pe_ratio'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
            _pf_df['Mkt Cap'] = _pf_df['market_cap'].apply(_fmt_mcap)
            _pf_df['SSGR'] = _pf_df['ssgr'].apply(
                lambda x: ("🟢 " if pd.notna(x) and x > 0 else "") + (f"{x:.1f}%" if pd.notna(x) else "N/A")
            )
            _pf_df['FCF (10Y)'] = _pf_df['fcf_category'].apply(
                lambda x: "🟢 Positive" if x == "Positive" else (x if pd.notna(x) else "N/A")
            )
            _pf_df['YoY Sales'] = _pf_df['yoy_sales_growth'].apply(
                lambda x: ("🟢 " if pd.notna(x) and x > 0 else "") + (f"{x:+.1f}%" if pd.notna(x) else "N/A")
            )
            _pf_df['Promoter'] = _pf_df['promoter_holding'].apply(
                lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
            )
            _pf_df['52W Position'] = _pf_df['sentiment_rating'].apply(render_valuation)

            _pf_display = _pf_df[[
                'company_code', 'company_name', 'sector',
                'CMP', 'P/E', 'Mkt Cap', 'SSGR', 'FCF (10Y)', 'YoY Sales', 'Promoter', '52W Position'
            ]].rename(columns={'company_code': 'Code', 'company_name': 'Company', 'sector': 'Sector'}).copy()

            st.markdown(
                '<div style="font-size:11px;color:#475569;margin-bottom:6px">'
                'Click any checkbox to view company details below</div>',
                unsafe_allow_html=True
            )
            _pf_event = st.dataframe(
                _pf_display,
                use_container_width=True,
                height=min(500, max(120, len(_pf_display) * 38 + 42)),
                on_select="rerun",
                selection_mode="single-row",
                hide_index=True,
                column_config={
                    "Code":    st.column_config.TextColumn("Code",    width=80),
                    "Company": st.column_config.TextColumn("Company", width=200),
                    "Sector":  st.column_config.TextColumn("Sector",  width=120),
                    "CMP":     st.column_config.TextColumn("CMP",     width=160),
                    "SSGR":       st.column_config.TextColumn("SSGR",       help="Self-Sustainable Growth Rate — 🟢 means positive (company can fund its own growth)"),
                    "FCF (10Y)":  st.column_config.TextColumn("FCF (10Y)",  help="Cumulative Free Cash Flow over last 10 years — 🟢 means positive"),
                    "YoY Sales":  st.column_config.TextColumn("YoY Sales",  help="Year-on-Year Sales Growth (latest quarter vs same quarter last year) — 🟢 means growing"),
                    "52W Position": st.column_config.TextColumn("52W Position", help="Where current price sits in the 52-week high/low range"),
                }
            )

            # Company detail on row click
            _sel_rows = _pf_event.selection.rows if _pf_event else []
            if _sel_rows:
                _sel_code = _pf_display.iloc[_sel_rows[0]]['Code']
                st.markdown(
                    f'<div style="margin:28px 0 10px;padding-bottom:8px;'
                    f'border-bottom:1px solid rgba(255,255,255,0.07)">'
                    f'<span style="font-size:11px;font-weight:700;color:#94a3b8;'
                    f'text-transform:uppercase;letter-spacing:2px">{_sel_code} — Analysis</span></div>',
                    unsafe_allow_html=True
                )
                render_company_detail(df, preselect_code=_sel_code)


    # ─────────────────────────────────────────────────────
    # ADMIN — visible only to amit.balode@gmail.com
    # ─────────────────────────────────────────────────────
    elif _nav == 'Admin' and _is_admin:
        section_header('Admin', 'All users and their portfolios')
        conn = get_connection()
        _all_users = conn.execute(
            "SELECT id, name, email, created_at FROM users ORDER BY created_at"
        ).fetchall()

        if not _all_users:
            st.info("No users registered yet.")
        else:
            for _uid, _uname, _uemail, _ucreated in _all_users:
                _stocks = conn.execute(
                    """SELECT ups.company_code, c.company_name, ups.added_at
                       FROM user_portfolio_stocks ups
                       LEFT JOIN screener_companies c ON c.company_code = ups.company_code
                       WHERE ups.user_id = ?
                       ORDER BY ups.added_at""",
                    (_uid,)
                ).fetchall()

                _display_name = _uname or '(no name)'
                _registered = pd.to_datetime(_ucreated, format='mixed').strftime('%d %b %Y, %I:%M %p') if _ucreated else 'N/A'

                with st.expander(f"{_display_name} — {_uemail}  ·  {len(_stocks)} stocks  ·  joined {_registered}", expanded=True):
                    if not _stocks:
                        st.caption("No stocks in portfolio.")
                    else:
                        _admin_df = pd.DataFrame(_stocks, columns=['Code', 'Company', 'Added'])
                        _admin_df['Added'] = pd.to_datetime(_admin_df['Added'], format='mixed').dt.strftime('%d %b %Y, %I:%M %p')
                        st.dataframe(_admin_df, use_container_width=True, hide_index=True)

    # ─────────────────────────────────────────────────────
    # FAQ
    # ─────────────────────────────────────────────────────
    elif _nav == 'FAQ':
        _faqs = [
            ('What is SSGR (Self-Sustainable Growth Rate)?',
             '#818cf8',
             'SSGR is the maximum rate at which a company can grow its sales using only its own internal resources — without borrowing more money or issuing new shares.',
             [
                 ('Formula', 'SSGR = [(1 − Dep%) + NFAT × NPM × (1 − DPR)] − 1'),
                 ('Dep%',    'Depreciation as % of Net Fixed Assets — reflects asset wear'),
                 ('NFAT',    'Net Fixed Asset Turnover = Sales ÷ Net Fixed Assets — asset efficiency'),
                 ('NPM',     'Net Profit Margin = Net Profit ÷ Sales — profitability'),
                 ('DPR',     'Dividend Payout Ratio — portion of profit paid as dividends'),
                 ('Key rule', 'If SSGR > actual sales growth → company is self-funding its growth (good). If SSGR < sales growth → company needs external debt or equity to fund growth (watch out).'),
                 ('Credit', '<a href="https://www.vijaymalik.com" target="_blank" style="color:#818cf8;text-decoration:none;font-weight:600">Dr. Vijay Malik</a> — formula and framework sourced from his research on self-sustainable growth. Highly recommended reading at <a href="https://www.vijaymalik.com" target="_blank" style="color:#818cf8;text-decoration:none">vijaymalik.com</a>'),
             ]),
            ('What is Free Cash Flow (FCF)?',
             '#34d399',
             'FCF is the cash a company actually generates after spending on maintaining and growing its fixed assets. It tells you how much real cash is left over for shareholders.',
             [
                 ('Core FCF', 'CFO (Cash from Operations) − Capex (Capital Expenditure)'),
                 ('CFO', 'Cash generated from day-to-day business operations'),
                 ('Capex', 'Money spent on buying or upgrading physical assets (machines, buildings)'),
                 ('FCF + Other Income', 'Core FCF minus interest paid, plus other non-operating income'),
                 ('Positive FCF', 'Company generates more cash than it spends — a sign of quality'),
                 ('FCF/CFO %', 'What % of operating cash flow survives after Capex. Higher is better.'),
             ]),
            ('What is Sentiment Rating (1–5 stars)?',
             '#f5a623',
             'Sentiment measures where the current stock price sits within its 52-week range. A low rating means the stock is near its yearly low — potentially a better entry point.',
             [
                 ('Formula', 'Position = (CMP − 52W Low) ÷ (52W High − 52W Low) × 100'),
                 ('⭐⭐⭐⭐⭐ (5)', 'Price is in top 20% of 52-week range — very bullish momentum'),
                 ('⭐⭐⭐⭐ (4)', 'Price in 60–80% of range — bullish'),
                 ('⭐⭐⭐ (3)', 'Price in 40–60% of range — neutral'),
                 ('⭐⭐ (2)', 'Price in 20–40% of range — bearish'),
                 ('⭐ (1)', 'Price in bottom 20% of range — very bearish / potential entry zone'),
             ]),
            ('What is P/E Ratio?',
             '#a5b4fc',
             'Price-to-Earnings ratio tells you how much investors are willing to pay for every ₹1 of a company\'s annual profit. A high P/E means high expectations.',
             [
                 ('Formula', 'P/E = Market Cap ÷ Net Profit  (or CMP ÷ EPS)'),
                 ('Source', 'Yahoo Finance (trailing twelve months). Screener data used as fallback.'),
                 ('< 15',  'Generally considered cheap — but check why'),
                 ('15–30', 'Reasonable for most sectors'),
                 ('> 50',  'Expensive — shown in orange as a caution signal in this portal'),
                 ('Caution', 'P/E is meaningless if profits are negative or very small'),
             ]),
            ('What is PEG Ratio?',
             '#f472b6',
             'PEG adjusts P/E for growth. A company with a high P/E but very fast growth can still be cheap on a PEG basis.',
             [
                 ('Formula', 'PEG = P/E ÷ Annual Earnings Growth Rate (%)'),
                 ('< 1',  'Potentially undervalued relative to growth'),
                 ('1–2',  'Fairly valued'),
                 ('> 3',  'Expensive relative to growth — shown in orange in this portal'),
                 ('Limitation', 'Relies on growth estimates which can be wrong. Use alongside other metrics.'),
             ]),
            ('What is Debt / Equity (D/E) Ratio?',
             '#fb923c',
             'D/E measures how much of a company\'s operations are funded by debt versus shareholder equity. Higher debt means higher financial risk.',
             [
                 ('Formula', 'D/E = Total Borrowings ÷ (Equity Capital + Reserves)'),
                 ('Source', 'Pulled live from Yahoo Finance during daily fundamentals update'),
                 ('< 0.5', 'Low debt — shown in green in this portal'),
                 ('0.5–1', 'Moderate debt — acceptable for most sectors'),
                 ('> 1',   'High debt — shown in red. Scrutinise interest coverage.'),
                 ('Note', 'Capital-intensive sectors (infra, utilities) naturally carry more debt — compare within sector.'),
             ]),
            ('What is ROCE (Return on Capital Employed)?',
             '#34d399',
             'ROCE measures how efficiently a company uses all its capital (both debt and equity) to generate profit. It is a better quality indicator than ROE alone.',
             [
                 ('Formula', 'ROCE = EBIT ÷ Capital Employed × 100'),
                 ('Capital Employed', 'Total Assets − Current Liabilities'),
                 ('≥ 20%', 'Excellent — shown with green dot in this portal'),
                 ('15–20%', 'Good — yellow dot'),
                 ('< 15%', 'Poor — red dot'),
                 ('Key rule', 'ROCE should consistently be higher than the cost of borrowing. If ROCE < interest rate on debt, the company is destroying value.'),
             ]),
            ('What is Promoter Holding & Trend?',
             '#94a3b8',
             'Promoter holding is the percentage of shares owned by the founders and controlling shareholders. Changes in promoter holding are a strong qualitative signal.',
             [
                 ('Promoter Holding', '% of total shares held by promoters/founders'),
                 ('Trend — Increased', 'Promoters bought more shares in last 4 quarters — confidence signal'),
                 ('Trend — Stable', 'Holding unchanged — neutral'),
                 ('Trend — Decreased Minor', 'Small reduction (< 10%) — watch but not alarming'),
                 ('Trend — Decreased 10%+', 'Large reduction — significant red flag'),
                 ('Pledge', 'Pledged promoter shares (not shown here) add additional risk — check Screener.in directly'),
             ]),
            ('What is 5-Year Sales CAGR?',
             '#a5b4fc',
             'Compound Annual Growth Rate of sales over the last 5 years. Measures how consistently a company has grown its top line.',
             [
                 ('Formula', 'CAGR = (Latest Sales ÷ Sales 5 Years Ago) ^ (1/5) − 1'),
                 ('> 20%', 'Strong consistent growth'),
                 ('10–20%', 'Decent growth'),
                 ('< 10%', 'Slow or stagnant — dig deeper'),
                 ('Source', 'Calculated inline in the portal from Screener annual P&L data'),
             ]),
            ('What is CFO vs Net Profit?',
             '#34d399',
             'Net Profit (PAT) is the accounting profit. CFO (Cash from Operations) is the actual cash generated. Great companies have CFO ≥ Net Profit consistently.',
             [
                 ('Green CFO row', 'CFO > Net Profit — company collects cash better than it reports profit (quality sign)'),
                 ('Red CFO row', 'CFO < Net Profit — profit may include receivables not yet collected (red flag)'),
                 ('Why it matters', 'Accounting profits can be massaged. Cash is harder to fake.'),
             ]),
        ]

        st.markdown(
            '<div style="margin-bottom:24px">'
            '<div style="font-size:11px;font-weight:700;color:#f472b6;text-transform:uppercase;letter-spacing:2px">Glossary &amp; FAQ</div>'
            '<div style="font-size:22px;font-weight:700;color:#f1f5f9;margin-top:6px">Key financial terms explained</div>'
            '<div style="font-size:13px;color:#64748b;margin-top:4px">Everything you see in this portal — defined in plain English</div>'
            '</div>',
            unsafe_allow_html=True
        )

        for i, (q, color, summary, points) in enumerate(_faqs):
            with st.expander(q, expanded=(i == 0)):
                st.markdown(
                    f'<div style="font-size:13px;color:#94a3b8;margin-bottom:14px;'
                    f'padding-left:12px;border-left:3px solid {color}">{summary}</div>',
                    unsafe_allow_html=True
                )
                rows_html = ''.join(
                    f'<tr>'
                    f'<td style="padding:7px 14px 7px 0;font-size:12px;font-weight:600;color:#64748b;'
                    f'white-space:nowrap;vertical-align:top;width:160px">{k}</td>'
                    f'<td style="padding:7px 0;font-size:13px;color:#cbd5e1">{v}</td>'
                    f'</tr>'
                    for k, v in points
                )
                st.markdown(
                    f'<table style="width:100%;border-collapse:collapse">{rows_html}</table>',
                    unsafe_allow_html=True
                )


if __name__ == "__main__":
    main()
