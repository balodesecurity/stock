#!/usr/bin/env python3
"""
Stock Analysis Portal - Interactive UI
Built with Streamlit
"""

import os
import re
import subprocess
import sys
import streamlit as st
import pandas as pd
import sqlite3
from constants import DATABASE_PATH

# Page configuration
st.set_page_config(
    page_title="Stock Analysis Portal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 5px;
    }
    h1 {
        color: #1f77b4;
    }
    .star-rating {
        font-size: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Database connection
@st.cache_resource
def get_connection():
    conn = sqlite3.connect(str(DATABASE_PATH), check_same_thread=False)
    # Ensure enabled column exists in screener_companies
    try:
        conn.execute("ALTER TABLE screener_companies ADD COLUMN enabled INTEGER DEFAULT 1")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
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
            ) as sales_growth_5y
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

    # Fill NULL promoter_trend_display with "N/A"
    df['promoter_trend_display'] = df['promoter_trend_display'].fillna("N/A")

    # Calculate derived columns
    df['avg_3yr_growth'] = (df['year1_sales_growth'] + df['year2_sales_growth'] + df['year3_sales_growth']) / 3
    # Calculate price change %
    df['price_change_pct'] = df.apply(
        lambda x: ((x['current_price'] - x['previous_close']) / x['previous_close'] * 100)
        if pd.notna(x['current_price']) and pd.notna(x['previous_close']) and x['previous_close'] > 0
        else None, axis=1
    )

    return df

def render_stars(rating):
    """Render star rating as emoji"""
    if pd.isna(rating):
        return ""
    stars = int(rating)
    return "★" * stars + "☆" * (5 - stars)

def format_number(num):
    """Format large numbers"""
    if pd.isna(num):
        return "N/A"
    if abs(num) >= 10000:
        return f"₹{num/1000:.1f}k Cr"
    elif abs(num) >= 1000:
        return f"₹{num:.0f} Cr"
    else:
        return f"₹{num:.1f} Cr"

def format_price(price, change_pct, updated_at=None):
    """Format price with change percentage and update time"""
    if pd.isna(price):
        return "N/A"

    # Format timestamp in IST
    time_str = ""
    if pd.notna(updated_at):
        try:
            from datetime import datetime
            import pytz

            if isinstance(updated_at, str):
                dt = datetime.fromisoformat(updated_at)
            else:
                dt = updated_at

            # Convert to IST if not already
            ist = pytz.timezone('Asia/Kolkata')
            if dt.tzinfo is None:
                dt = ist.localize(dt)
            else:
                dt = dt.astimezone(ist)

            time_str = f" [{dt.strftime('%d-%b %I:%M %p')}]"
        except:
            pass

    if pd.isna(change_pct):
        return f"₹{price:.2f}{time_str}"
    emoji = "🟢" if change_pct >= 0 else "🔴"
    return f"{emoji} ₹{price:.2f} ({change_pct:+.2f}%){time_str}"

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
        'portfolios',
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


def add_to_static_portfolio(company_code):
    """Insert a company code into the Static portfolio in the DB. Returns (success, message)."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO portfolios (portfolio_name, company_code) VALUES ('Static', ?)",
            (company_code,)
        )
        conn.commit()
        return True, f"Added {company_code} to Static Portfolio."
    except Exception as e:
        return False, f"Failed to add {company_code}: {e}"


# Main app
def main():
    # Compact header with refresh button
    col_title, col_refresh = st.columns([6, 1])
    with col_title:
        st.markdown("## 📈 Stock Analysis Portal")
        st.caption("**Base Filter:** Interest Coverage > 3 • Sales Growth (10Y median) > 15% • Debt/Equity < 0.5 • Current Ratio > 1.25 • Net Cash Flow (LY) > 0 • Promoter Holding > 51% • FCF/CFO (3Y) > 1 • Market Cap > ₹10 Cr")
    with col_refresh:
        if st.button("🔄 Refresh"):
            st.cache_data.clear()

    # Sidebar filters
    st.sidebar.header("🔍 Filters")

    # Show disabled companies toggle
    show_disabled = st.sidebar.checkbox("Show disabled companies", value=False,
        help="Show companies no longer in the screener filter, portfolios, or static list")

    # Load data
    df = load_data(show_disabled=show_disabled)

    # Portfolio filter (dropdown)
    portfolio_filter = st.sidebar.selectbox(
        "💼 Portfolio Filter",
        options=["All Companies", "Amit's Portfolio", "Static Portfolio"],
        index=0,
        help="Filter by portfolio: All Companies, Amit's Portfolio (Paytmmoney), or Static Portfolio (custom watchlist)"
    )

    # Get portfolio company codes based on selection
    portfolio_codes = []
    if portfolio_filter == "Amit's Portfolio":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT company_code FROM portfolios WHERE portfolio_name = 'Paytmmoney'")
        portfolio_codes = [row[0] for row in cursor.fetchall()]
    elif portfolio_filter == "Static Portfolio":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT company_code FROM portfolios WHERE portfolio_name = 'Static'")
        portfolio_codes = [row[0] for row in cursor.fetchall()]

    st.sidebar.markdown("---")

    # Search filter
    search_query = st.sidebar.text_input(
        "🔎 Search Company",
        placeholder="Type company name or code...",
        help="Search by company name or code. Partial matches supported."
    )

    st.sidebar.markdown("---")

    # Adjust defaults based on portfolio filter
    default_max_pe = 5000 if portfolio_filter != "All Companies" else 100
    default_max_debt = 5.0 if portfolio_filter != "All Companies" else 1.0

    # Sentiment filter
    min_sentiment = st.sidebar.slider("Minimum Sentiment", 0, 5, 0)

    # P/E filter
    max_pe = st.sidebar.slider("Maximum P/E Ratio", 0, 5000, default_max_pe)

    # Industry filter
    industries = ['All'] + sorted(df['industry'].dropna().unique().tolist())
    selected_industry = st.sidebar.selectbox("Industry", industries)

    # Debt filter
    max_debt = st.sidebar.slider("Maximum Debt/Equity", 0.0, 5.0, default_max_debt)

    # Market cap filter (range slider in Crores)
    market_cap_range = st.sidebar.slider(
        "Market Cap Range (₹ Cr)",
        min_value=0,
        max_value=500000,
        value=(0, 500000),
        step=1000,
        format="₹%d Cr"
    )

    # 5-Year Sales Growth CAGR filter
    min_sales_growth_5y = st.sidebar.number_input(
        "Min Sales Growth 5Y CAGR (%)",
        min_value=0,
        max_value=100,
        value=0,
        step=1,
        help="Minimum 5-year sales CAGR (Compound Annual Growth Rate). Companies with less than 6 years of data are excluded."
    )

    # Promoter Holding filter
    min_promoter = st.sidebar.slider(
        "Min Promoter Holding (%)",
        0.0, 100.0, 0.0, step=5.0,
        help="Minimum promoter holding percentage. Companies without promoter data are included."
    )

    # FCF/CFO Ratio filter
    min_fcf_cfo = st.sidebar.slider(
        "Min FCF/CFO Ratio (%)",
        -100, 100, 0, step=5,
        help="Minimum Free Cash Flow / Cash from Operations ratio. Green threshold is 25%."
    )

    # Add Stock to Static Portfolio
    st.sidebar.markdown("---")
    st.sidebar.header("➕ Add Stock")
    with st.sidebar.form("add_stock_form", clear_on_submit=True):
        screener_url = st.text_input(
            "Screener.in Link",
            placeholder="screener.in/company/TCS/...",
        )
        st.caption("e.g. https://www.screener.in/company/TCS/consolidated/")
        submitted = st.form_submit_button("Add to Portfolio")
        if submitted:
            code, err = parse_screener_url(screener_url)
            if err:
                st.error(err)
            else:
                # Check if already in Static Portfolio (DB)
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM portfolios WHERE portfolio_name = 'Static' AND company_code = ?",
                    (code,)
                )
                if cursor.fetchone():
                    st.warning(f"{code} is already in the Static Portfolio.")
                else:
                    # Check if already exists in DB
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT company_code FROM derived_metrics_analysis WHERE company_code = ?",
                        (code,)
                    )
                    if cursor.fetchone():
                        st.warning(f"{code} already exists in the database.")
                    else:
                        ok, msg = add_to_static_portfolio(code)
                        if ok:
                            stock_dir = os.path.dirname(os.path.abspath(__file__))
                            # Download screener data + live price in one background process
                            subprocess.Popen(
                                [sys.executable, os.path.join(stock_dir, 'sync_new_companies.py'),
                                 '--companies', code],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                            )
                            st.success(msg + f" Syncing data for {code} in background — refresh in ~60 seconds.")
                        else:
                            st.error(msg)

    # Apply filters
    filtered_df = df.copy()

    # Search filter (applied first for better performance)
    if search_query:
        search_query_lower = search_query.lower()
        filtered_df = filtered_df[
            (filtered_df['company_name'].str.lower().str.contains(search_query_lower, na=False)) |
            (filtered_df['company_code'].str.lower().str.contains(search_query_lower, na=False))
        ]

    # Portfolio filter
    if portfolio_filter != "All Companies" and portfolio_codes:
        filtered_df = filtered_df[filtered_df['company_code'].isin(portfolio_codes)]

    # Sentiment filter (handle NULL)
    if min_sentiment > 0:
        filtered_df = filtered_df[(filtered_df['sentiment_rating'] >= min_sentiment) | (filtered_df['sentiment_rating'].isna())]

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

    # Market cap filter (range slider)
    min_cap, max_cap = market_cap_range
    if min_cap > 0 or max_cap < 500000:
        filtered_df = filtered_df[
            ((filtered_df['market_cap'] >= min_cap) & (filtered_df['market_cap'] <= max_cap)) |
            (filtered_df['market_cap'].isna())
        ]

    # 5-Year Sales Growth filter
    if min_sales_growth_5y > 0:
        filtered_df = filtered_df[
            (filtered_df['sales_growth_5y'].notna()) & (filtered_df['sales_growth_5y'] >= min_sales_growth_5y)
        ]

    # Promoter Holding filter
    if min_promoter > 0:
        filtered_df = filtered_df[
            (filtered_df['promoter_holding'] >= min_promoter) | (filtered_df['promoter_holding'].isna())
        ]

    # FCF/CFO Ratio filter
    if min_fcf_cfo != 0:
        filtered_df = filtered_df[
            (filtered_df['fcf_cfo_ratio'] >= min_fcf_cfo) | (filtered_df['fcf_cfo_ratio'].isna())
        ]

    # Create green indicator columns for sorting
    filtered_df['fcf_green'] = (filtered_df['fcf_cfo_ratio'] >= 25).astype(int)
    filtered_df['ssgr_green'] = (filtered_df['ssgr'] > 0).astype(int)
    filtered_df['qoq_green'] = (filtered_df['qoq_profit_growth'] > 0).astype(int)
    filtered_df['yoy_green'] = (filtered_df['yoy_profit_growth'] > 0).astype(int)
    filtered_df['yoy_sales_green'] = (filtered_df['yoy_sales_growth'] > 0).astype(int)

    # Create composite green score (0-5)
    filtered_df['green_score'] = (
        filtered_df['fcf_green'] +
        filtered_df['ssgr_green'] +
        filtered_df['qoq_green'] +
        filtered_df['yoy_green'] +
        filtered_df['yoy_sales_green']
    )

    # Sort by green score first, then by individual metrics
    filtered_df = filtered_df.sort_values(
        by=['green_score', 'fcf_cfo_ratio', 'ssgr', 'qoq_profit_growth', 'yoy_profit_growth', 'yoy_sales_growth'],
        ascending=[False, False, False, False, False, False],
        na_position='last'
    )

    # Tabs
    tab1, tab4 = st.tabs(["📊 Stock List", "📖 Documentation"])

    with tab1:
        st.subheader(f"Filtered Stocks ({len(filtered_df)} companies)")

        # Show portfolio filter indicator if active
        if portfolio_filter == "Amit's Portfolio":
            st.info(f"💼 Showing **Amit's Portfolio** companies ({len(filtered_df)} companies)")
        elif portfolio_filter == "Static Portfolio":
            st.info(f"⭐ Showing **Static Portfolio** companies ({len(filtered_df)} companies)")

        # Show search indicator if active
        if search_query:
            st.info(f"🔎 Showing results for: **{search_query}** ({len(filtered_df)} matches)")

        # Display table
        display_df = filtered_df[[
            'company_code', 'company_name', 'sector', 'industry',
            'current_price', 'price_change_pct', 'updated_at', 'week_52_high', 'week_52_low',
            'sentiment_rating', 'pe_ratio', 'book_value', 'peg_ratio', 'roce', 'market_cap', 'sales_growth_5y',
            'ssgr', 'ssgr_prev', 'year1_sales_growth', 'year2_sales_growth',
            'qoq_profit_growth', 'qoq_profit_growth_prev', 'yoy_profit_growth', 'yoy_sales_growth', 'latest_quarter', 'prev_quarter',
            'promoter_trend_display',
            'npm', 'total_fcf', 'fcf_cfo_ratio', 'debt_to_equity',
        ]].copy().reset_index(drop=True)

        # Capture company codes before URL conversion (used for delete)
        company_codes = display_df['company_code'].tolist()

        # Format columns
        display_df['cmp'] = display_df.apply(lambda x: format_price(x['current_price'], x['price_change_pct'], x['updated_at']), axis=1)
        display_df['52w_range'] = display_df.apply(
            lambda x: f"₹{x['week_52_high']:.0f} / {x['week_52_low']:.0f}"
            if pd.notna(x['week_52_high']) and pd.notna(x['week_52_low']) else "N/A", axis=1
        )
        display_df['sentiment_rating'] = display_df['sentiment_rating'].apply(render_stars)
        display_df['pe_ratio'] = display_df['pe_ratio'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")

        # Calculate P/B ratio (Price / Book Value)
        display_df['pb_ratio'] = display_df.apply(
            lambda x: round(x['current_price'] / x['book_value'], 2)
            if pd.notna(x['current_price']) and pd.notna(x['book_value']) and x['book_value'] > 0
            else None, axis=1
        )
        display_df['pb_ratio'] = display_df['pb_ratio'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")

        display_df['peg_ratio'] = display_df['peg_ratio'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")

        # Format ROCE with color indicator
        def format_roce(val):
            if pd.isna(val):
                return "N/A"
            if val >= 20:
                emoji = "🟢"
            elif val >= 15:
                emoji = "🟡"
            else:
                emoji = "🔴"
            return f"{emoji} {val:.1f}%"

        display_df['roce'] = display_df['roce'].apply(format_roce)
        display_df['market_cap'] = display_df['market_cap'].apply(lambda x: f"₹{x:.0f}" if pd.notna(x) else "N/A")
        display_df['sales_growth_5y'] = display_df['sales_growth_5y'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")

        # Format SSGR with color indicator
        def format_ssgr(val):
            if pd.isna(val):
                return "N/A"
            emoji = "🟢" if val > 0 else "🔴"
            return f"{emoji} {val:.1f}%"

        display_df['ssgr'] = display_df['ssgr'].apply(format_ssgr)
        display_df['ssgr_prev'] = display_df['ssgr_prev'].apply(format_ssgr)
        display_df['year1_sales_growth'] = display_df['year1_sales_growth'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
        display_df['year2_sales_growth'] = display_df['year2_sales_growth'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
        display_df['npm'] = display_df['npm'].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")

        # Format Q-o-Q profit with color indicator and quarter label
        def format_qoq_with_quarter(row, val_col, quarter_col):
            val = row[val_col]
            quarter = row[quarter_col]
            if pd.isna(val):
                return "N/A"
            emoji = "🟢" if val >= 0 else "🔴"
            q_str = quarter if pd.notna(quarter) else "?"
            # Convert "Sep 2025" to "Sep-2025"
            q_str = q_str.replace(' ', '-') if isinstance(q_str, str) else q_str
            return f"{emoji} {val:.1f}%, {q_str}"

        # Format Y-o-Y profit with color indicator
        def format_yoy_profit(val):
            if pd.isna(val):
                return "N/A"
            emoji = "🟢" if val >= 0 else "🔴"
            return f"{emoji} {val:.1f}%"

        # Format Y-o-Y sales with color indicator
        def format_yoy_sales(val):
            if pd.isna(val):
                return "N/A"
            emoji = "🟢" if val >= 0 else "🔴"
            return f"{emoji} {val:.1f}%"

        display_df['qoq_profit_growth'] = display_df.apply(lambda r: format_qoq_with_quarter(r, 'qoq_profit_growth', 'latest_quarter'), axis=1)
        display_df['qoq_profit_growth_prev'] = display_df.apply(lambda r: format_qoq_with_quarter(r, 'qoq_profit_growth_prev', 'prev_quarter'), axis=1)
        display_df['yoy_profit_growth'] = display_df['yoy_profit_growth'].apply(format_yoy_profit)
        display_df['yoy_sales_growth'] = display_df['yoy_sales_growth'].apply(format_yoy_sales)
        display_df['total_fcf'] = display_df['total_fcf'].apply(format_number)

        # Format FCF/CFO with color indicator
        def format_fcf_cfo(val):
            if pd.isna(val):
                return "N/A"
            emoji = "🟢" if val >= 25 else "🔴"
            return f"{emoji} {val:.1f}%"

        display_df['fcf_cfo_ratio'] = display_df['fcf_cfo_ratio'].apply(format_fcf_cfo)
        display_df['debt_to_equity'] = display_df['debt_to_equity'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "N/A")

        # Create screener.in links with company code as URL
        display_df['company_code'] = display_df['company_code'].apply(
            lambda x: f"https://www.screener.in/company/{x}/" if pd.notna(x) else ""
        )

        # Select and order columns for display
        display_df = display_df[[
            'company_code', 'company_name', 'sector', 'industry', 'cmp', '52w_range',
            'sentiment_rating', 'pe_ratio', 'pb_ratio', 'peg_ratio', 'roce',
            'fcf_cfo_ratio', 'ssgr', 'ssgr_prev', 'qoq_profit_growth', 'qoq_profit_growth_prev', 'yoy_profit_growth', 'yoy_sales_growth',
            'promoter_trend_display',
            'market_cap', 'sales_growth_5y', 'npm',
            'total_fcf', 'debt_to_equity',
        ]]

        # Rename columns
        display_df.columns = [
            'Code', 'Company', 'Sector', 'Industry', 'CMP', '52W High/Low',
            'Sentiment', 'P/E', 'P/B', 'PEG', 'ROCE',
            'FCF/CFO', 'SSGR', 'SSGR (Prev)', 'QoQ Profit', 'Prev QoQ', 'Y-o-Y Profit', 'Y-o-Y Sales',
            'Promoter Holding',
            'Market Cap (Cr)', '5Y CAGR', 'NPM %',
            'FCF (10Y)', 'D/E',
        ]

        # Add delete checkbox column at the front
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
                "CMP": st.column_config.TextColumn(
                    "CMP",
                    help="Current Market Price with change percentage. Timestamp in square brackets shows when price was last updated from Yahoo Finance (IST).",
                    width=200
                ),
                "Sentiment": st.column_config.TextColumn(
                    "Sentiment",
                    help="Market sentiment based on price position in 52-week range: ⭐⭐⭐⭐⭐ (80-100% - Very Bullish, near 52W high) | ⭐⭐⭐⭐ (60-80% - Bullish) | ⭐⭐⭐ (40-60% - Neutral) | ⭐⭐ (20-40% - Bearish) | ⭐ (0-20% - Very Bearish, near 52W low)",
                    width="small"
                ),
                "P/B": st.column_config.TextColumn(
                    "P/B",
                    help="Price to Book Value ratio (CMP / Book Value per share). Lower P/B may indicate undervaluation.",
                    width="small"
                ),
                "ROCE": st.column_config.TextColumn(
                    "ROCE",
                    help="Return on Capital Employed. 🟢 Green: ≥20% (Excellent) | 🟡 Yellow: 15-20% (Good) | 🔴 Red: <15% (Poor)",
                    width="small"
                ),
                "FCF/CFO": st.column_config.TextColumn(
                    "FCF/CFO",
                    help="Free Cash Flow / Cash from Operations ratio. 🟢 Green: ≥25% (Low capex, cash cow) | 🔴 Red: <25% (High capex)",
                    width="small"
                ),
                "SSGR": st.column_config.TextColumn(
                    "SSGR",
                    help="Sustainable Sales Growth Rate (latest 3 years). 🟢 Green: >0% (Positive growth) | 🔴 Red: ≤0% (Negative/zero growth)",
                    width="small"
                ),
                "SSGR (Prev)": st.column_config.TextColumn(
                    "SSGR (Prev)",
                    help="Sustainable Sales Growth Rate (previous 3 years). Compare with current SSGR to see trend.",
                    width="small"
                ),
                "QoQ Profit": st.column_config.TextColumn(
                    "QoQ Profit",
                    help="Quarter-over-Quarter profit growth (latest quarter vs previous). Shows growth % and quarter. 🟢 Profit increased | 🔴 Profit decreased",
                    width="medium"
                ),
                "Prev QoQ": st.column_config.TextColumn(
                    "Prev QoQ",
                    help="Previous Quarter-over-Quarter profit growth. Shows growth % and quarter. Compare with QoQ Profit to spot trend direction.",
                    width="medium"
                ),
                "Y-o-Y Profit": st.column_config.TextColumn(
                    "Y-o-Y Profit",
                    help="Year-over-Year profit growth. 🟢 Green: Profit increased vs same quarter last year | 🔴 Red: Profit decreased",
                    width="small"
                ),
                "Y-o-Y Sales": st.column_config.TextColumn(
                    "Y-o-Y Sales",
                    help="Year-over-Year sales growth. 🟢 Green: Sales increased vs same quarter last year | 🔴 Red: Sales decreased",
                    width="small"
                ),
                "Promoter Holding": st.column_config.TextColumn(
                    "Promoter Holding",
                    help="Promoter holding trend (last 4 quarters). 🟢 Green: Stable or increased | 🟡 Yellow: Decreased <10% | 🔴 Red: Decreased ≥10%",
                    width="medium"
                ),
            }
        )

        # Handle per-row delete — open dialog for first checked row
        checked_indices = edited_df[edited_df['🗑️']].index.tolist()
        if checked_indices:
            confirm_delete_dialog(company_codes[checked_indices[0]])

        # Download button
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name="filtered_stocks.csv",
            mime="text/csv"
        )

    with tab4:
        st.subheader("📖 Stock Analysis Portal Documentation")

        # Overview
        st.markdown("## 🎯 Overview")
        st.markdown("""
        This portal analyzes **277 Indian stocks** using data from:
        - **Screener.in**: Historical financial statements (10+ years)
        - **Yahoo Finance**: Live market prices and latest quarterly data
        """)

        # Data Sources
        st.markdown("## 📊 Data Sources")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Screener.in")
            st.markdown("""
            **Updates:** Daily at 6 AM (checks for new companies)

            **Data Includes:**
            - Quarterly Results (10+ years)
            - Annual P&L Statements
            - Balance Sheets
            - Cash Flow Statements
            - Financial Ratios (ROCE, ROE, etc.)
            - Shareholding Patterns (Promoters, FIIs, DIIs)

            **Script:** `sync_new_companies.py`
            """)

        with col2:
            st.markdown("### Yahoo Finance")
            st.markdown("""
            **Quick Updates:** Hourly (9 AM - 3 PM, Mon-Fri)
            - Current price, day high/low
            - 52-week high/low
            - Trading volume

            **Full Updates:** Daily at 6 PM (Mon-Fri)
            - Latest quarterly sales, profits
            - Operating/free cash flows
            - EPS, interest, expenses

            **Script:** `update_stock_prices_v2.py`
            """)

        # Database Structure
        st.markdown("## 🗄️ Database Structure")
        st.markdown("**Database:** `derived_metrics_analysis.db` (SQLite)")

        col_db1, col_db2 = st.columns(2)

        with col_db1:
            st.markdown("### 📦 Primary Tables")
            st.markdown("*Raw data from sources (append-only)*")

            primary_tables = {
                "screener_quarterly": "Quarterly financial data (Sales, Profit, Cash Flow)",
                "screener_annual_pl": "Annual Profit & Loss statements",
                "screener_cash_flow": "Annual Cash Flow statements",
                "screener_balance_sheet": "Annual Balance Sheets",
                "screener_ratios": "Financial Ratios (ROCE, ROE, Debtor Days)",
                "screener_shareholding": "Shareholding patterns (Promoters, FIIs, DIIs)",
                "screener_daily_prices": "Daily stock prices from Yahoo Finance (time-series)",
                "screener_companies": "Company metadata (names, URLs)",
                "portfolios": "User portfolios (Amit Portfolio: 18 stocks)"
            }

            for table, desc in primary_tables.items():
                st.markdown(f"- **`{table}`**  \n  {desc}")

        with col_db2:
            st.markdown("### 🎯 Derived Table")
            st.markdown("*Calculated metrics only*")

            st.markdown("""
            - **`derived_metrics_analysis`**
              Summary table with calculated metrics:
              - FCF/CFO ratios, growth rates
              - Q-o-Q and Y-o-Y profit/sales growth
              - Promoter trends, ROCE, debt ratios
              - Green scores, sentiment ratings
              - 277 companies total
              - Prices fetched via JOIN with screener_daily_prices
            """)

        st.markdown("---")
        st.markdown("### 📊 Data Flow Diagram")

        st.code("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                            DATA SOURCES                                       ║
╠═══════════════════════════════════╦══════════════════════════════════════════╣
║        SCREENER.IN                ║         YAHOO FINANCE                     ║
║   (Historical Financial Data)     ║       (Live Market Data)                  ║
╚═══════════════╤═══════════════════╩══════════════╤═══════════════════════════╝
                │                                   │
                │ Daily 6 AM                        │ Hourly + Daily 6 PM
                │ sync_new_companies.py             │ update_stock_prices_v2.py
                ▼                                   ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                         PRIMARY TABLES (Raw Data)                             │
├───────────────────────────────────────────────────────────────────────────────┤
│  📦 screener_quarterly         - Sales, Profit, Cash Flow (Quarterly)         │
│  📦 screener_annual_pl         - Annual P&L                                   │
│  📦 screener_cash_flow         - Annual Cash Flow                             │
│  📦 screener_balance_sheet     - Annual Balance Sheet                         │
│  📦 screener_ratios            - ROCE, ROE, Debtor Days                       │
│  📦 screener_shareholding      - Promoters, FIIs, DIIs                        │
│  📦 screener_daily_prices      - Live prices, volume, 52w high/low            │
│  📦 screener_companies         - Metadata                                     │
│  📦 portfolios                 - User portfolios                              │
└───────────────────────────┬───────────────────────────────────────────────────┘
                            │
                            │ Calculation Script (Daily 6 PM):
                            │  • update_derived_metrics.py
                            │    (unified script for all metrics)
                            ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                    DERIVED TABLE (Calculated Metrics Only)                    │
├───────────────────────────────────────────────────────────────────────────────┤
│  🎯 derived_metrics_analysis                                                  │
│                                                                               │
│     CALCULATED FROM PRIMARY TABLES:                                           │
│      • fcf_cfo_ratio          ← Sum 10Y from screener_quarterly              │
│      • qoq_profit_growth      ← Calculated from screener_quarterly           │
│      • yoy_profit_growth      ← Calculated from screener_quarterly           │
│      • yoy_sales_growth       ← Calculated from screener_quarterly           │
│      • promoter_trend         ← 4Q analysis from screener_shareholding       │
│      • roce                   ← From screener_ratios                         │
│      • debt_to_equity         ← From screener_balance_sheet                  │
│      • green_score            ← Composite metric (0-5)                       │
│      • sentiment_rating       ← Based on 52-week range                       │
│                                                                               │
│     PRICES (via JOIN):                                                        │
│      • Portal JOINs with screener_daily_prices for current prices            │
│                                                                               │
│     YAHOO → SCREENER QUARTERLY (Daily 6 PM):                                 │
│      • Sales+, Net Profit+    ← Latest 3 quarters to screener_quarterly     │
│      • Operating Cash Flow+   ← Latest 3 quarters to screener_quarterly     │
│      • Free Cash Flow+        ← Latest 3 quarters to screener_quarterly     │
└───────────────────────────┬───────────────────────────────────────────────────┘
                            │
                            ▼
                   ┌────────────────────┐
                   │  STREAMLIT PORTAL  │
                   │   (This UI)        │
                   └────────────────────┘
        """, language="text")

        # Calculated Metrics
        st.markdown("## 🧮 Calculated Metrics")

        metrics_data = {
            "FCF/CFO Ratio": "Free Cash Flow / Operating Cash Flow (10-year average)",
            "Q-o-Q Profit Growth": "Quarter-over-Quarter profit growth",
            "Y-o-Y Profit Growth": "Year-over-Year profit growth (vs same quarter last year)",
            "Y-o-Y Sales Growth": "Year-over-Year sales growth (vs same quarter last year)",
            "SSGR": "Sustainable Sales Growth Rate",
            "Promoter Trend": "4-quarter promoter holding trend (🟢 stable/up, 🟡 -<10%, 🔴 -≥10%)",
            "Sentiment Rating": "Star rating based on position in 52-week range",
            "Green Score": "Composite score (0-5) based on FCF/CFO, SSGR, Q-o-Q, Y-o-Y profit, Y-o-Y sales"
        }

        st.markdown("**Metrics calculated from raw data:**")
        for metric, desc in metrics_data.items():
            st.markdown(f"- **{metric}**: {desc}")

        st.markdown("""
        **Calculation Script:** `update_derived_metrics.py`
        - Unified script that calculates all metrics from primary tables
        - Runs daily at 6 PM after fundamentals update
        - Processes 277 companies in ~1 second
        """)

        # Update Schedule
        st.markdown("## ⏰ Automated Update Schedule")

        schedule_df = pd.DataFrame([
            {"Time": "6:00 AM", "Frequency": "Daily", "Task": "Sync new companies from Screener.in filter", "Script": "sync_new_companies.py", "Duration": "~2 min"},
            {"Time": "9 AM - 3 PM", "Frequency": "Hourly", "Task": "Quick price updates (7 fields to screener_daily_prices)", "Script": "update_stock_prices_v2.py", "Duration": "~30 sec"},
            {"Time": "6:00 PM (Step 1)", "Frequency": "Daily (Mon-Fri)", "Task": "Fundamentals update (11 fields to screener_quarterly)", "Script": "update_stock_prices_v2.py --fundamentals", "Duration": "~5-10 min"},
            {"Time": "6:00 PM (Step 2)", "Frequency": "Daily (Mon-Fri)", "Task": "Recalculate all derived metrics", "Script": "update_derived_metrics.py", "Duration": "~1 sec"}
        ])

        st.dataframe(schedule_df, use_container_width=True, hide_index=True)

        # Key Scripts
        st.markdown("## 🔧 Key Scripts")

        scripts_data = {
            "stock_portal.py": "Main Streamlit UI application (this portal)",
            "update_stock_prices_v2.py": "Yahoo Finance data sync (quick + full modes)",
            "sync_new_companies.py": "Sync new companies from Screener.in",
            "screener_downloader.py": "Download data from Screener.in for specific company",
            "import_screener_to_sqlite.py": "Import JSON data into SQLite tables",
            "update_yoy_sales.py": "Calculate Y-o-Y sales growth from quarterly data",
            "update_promoter_holding.py": "Calculate promoter holding trends",
            "update_roce.py": "Extract ROCE from Screener ratios"
        }

        for script, desc in scripts_data.items():
            st.markdown(f"- **`{script}`**: {desc}")

        # Filters Applied
        st.markdown("## 🔍 Base Filters")
        st.markdown("""
        **All stocks in portal pass these criteria:**
        - Interest Coverage > 3
        - Sales Growth (10Y median) > 15%
        - Debt/Equity < 0.5
        - Current Ratio > 1.25
        - Net Cash Flow (LY) > 0
        - Promoter Holding > 51%
        - FCF/CFO (3Y) > 1
        - Market Cap > ₹10 Cr

        Source: [Screener.in Filter](https://www.screener.in/screens/3474068/vm/)
        """)

        # Color Coding
        st.markdown("## 🎨 Color Coding Guide")

        color_guide = {
            "FCF/CFO": "🟢 ≥25% (Cash cow) | 🔴 <25% (High capex)",
            "SSGR": "🟢 >0% (Growth) | 🔴 ≤0% (Decline)",
            "Q-o-Q/Y-o-Y Profit": "🟢 Positive | 🔴 Negative",
            "Y-o-Y Sales": "🟢 Positive | 🔴 Negative",
            "ROCE": "🟢 ≥20% (Excellent) | 🟡 15-20% (Good) | 🔴 <15% (Poor)",
            "Promoter Holding": "🟢 Stable/Increased | 🟡 Decreased <10% | 🔴 Decreased ≥10%"
        }

        for metric, guide in color_guide.items():
            st.markdown(f"- **{metric}**: {guide}")

        # Sorting Logic
        st.markdown("## 📈 Sorting Logic")
        st.markdown("""
        **Default Sort (Green Score Descending):**
        1. **Green Score** (0-5): Number of positive indicators
           - FCF/CFO ≥25%
           - SSGR >0%
           - Q-o-Q Profit >0%
           - Y-o-Y Profit >0%
           - Y-o-Y Sales >0%
        2. **Secondary**: FCF/CFO ratio (descending)
        3. **Tertiary**: SSGR (descending)
        4. **Quaternary**: Q-o-Q, Y-o-Y profit, Y-o-Y sales (descending)

        **Result**: Stocks with all 5 green indicators appear first
        """)

        # Data Flow
        st.markdown("## 🔄 Data Flow Diagram")
        st.code("""
        SCREENER.IN                        YAHOO FINANCE
             │                                  │
             │ (Daily 6 AM)                     │ (Hourly + Daily 6 PM)
             ▼                                  ▼
        screener_*                        derived_metrics_analysis
        tables                            table (prices)
             │                                  │
             │ (Calculate metrics)              │
             ▼                                  ▼
        derived_metrics_analysis ◄────────────────────────┘
        table (complete)
             │
             ▼
        STREAMLIT PORTAL
        (This UI)
        """, language="text")

        # Logs
        st.markdown("## 📝 Logs Location")
        st.markdown("""
        All automated scripts log to: `/Users/abalode/personnel/stock/logs/`

        **Log Files:**
        - `sync_companies_YYYYMMDD.log` - New company sync
        - `yahoo_sync_YYYYMMDD.log` - Yahoo Finance updates (if used)
        - Cron logs: `cron_price_update.log`, `cron_fundamentals_update.log`
        """)

        # Contact & Setup
        st.markdown("## 🚀 Development Setup")
        st.markdown("""
        **Environment:**
        ```bash
        # Activate virtual environment
        source venv/bin/activate

        # Run portal
        streamlit run stock_portal.py --server.port 8501

        # Manual updates
        python update_stock_prices_v2.py --force
        python update_stock_prices_v2.py --fundamentals --force
        python sync_new_companies.py
        ```

        **Dependencies:** `requirements.txt` (pandas, streamlit, yfinance, beautifulsoup4, etc.)

        **Database Backup:**
        ```bash
        cp derived_metrics_analysis.db derived_metrics_analysis.db.backup_$(date +%Y%m%d)
        ```
        """)

        st.markdown("---")
        st.markdown("*Last Updated: February 2026 | Built with Streamlit + Python*")

if __name__ == "__main__":
    main()
