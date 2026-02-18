#!/usr/bin/env python3
"""
Update All Derived Metrics (Refactored)
Centralized script to calculate and update all metrics in derived_metrics_analysis table

Metrics Updated:
1. Q-o-Q Profit Growth (from screener_quarterly)
2. Y-o-Y Profit Growth (from screener_quarterly)
3. Y-o-Y Sales Growth (from screener_quarterly)
4. ROCE - Return on Capital Employed (from screener_ratios)
5. Promoter Holding & Trend (from screener_shareholding)
6. Sentiment Rating (from screener_daily_prices - price position in 52-week range)
"""

from datetime import datetime

# Import common libraries
from lib import (
    get_database_connection,
    setup_logger,
    get_all_companies,
    get_timestamp,
    is_valid_value,
    clean_numeric_string,
    safe_float_convert,
    calculate_percentage_change,
    calculate_growth_rate,
    format_progress,
    format_percentage
)

from constants import (
    TABLE_QUARTERLY,
    TABLE_ANNUAL_PL,
    TABLE_BALANCE_SHEET,
    TABLE_CASH_FLOW,
    TABLE_RATIOS,
    TABLE_SHAREHOLDING,
    TABLE_DAILY_PRICES,
    TABLE_DERIVED,
    MIN_QUARTERS_FOR_QOQ,
    MIN_QUARTERS_FOR_YOY,
    MIN_QUARTERS_FOR_PROMOTER_TREND,
    PROMOTER_DECREASE_MAJOR_THRESHOLD,
    PROGRESS_UPDATE_INTERVAL,
    COMMIT_INTERVAL,
    QUARTER_ORDER_DESC
)


# ==============================================================================
# SECTION 1: PROFIT GROWTH (Q-o-Q and Y-o-Y)
# ==============================================================================

def calculate_profit_growth(cursor, company_code):
    """
    Calculate Q-o-Q and Y-o-Y profit growth from screener_quarterly

    Args:
        cursor: Database cursor
        company_code (str): Company code

    Returns:
        tuple: (qoq_growth, qoq_prev, yoy_growth, latest_quarter, prev_quarter)
    """
    cursor.execute(f"""
        SELECT quarter, value
        FROM {TABLE_QUARTERLY}
        WHERE company_code = ? AND metric = 'Net Profit+'
        ORDER BY {QUARTER_ORDER_DESC}
        LIMIT 5
    """, (company_code,))

    results = cursor.fetchall()

    if len(results) < MIN_QUARTERS_FOR_QOQ:
        return None, None, None, None, None

    try:
        # Parse quarters
        quarters_data = []
        for quarter, value in results:
            if is_valid_value(value):
                clean_value = clean_numeric_string(value)
                quarters_data.append((quarter, safe_float_convert(clean_value)))

        if len(quarters_data) < MIN_QUARTERS_FOR_QOQ:
            return None, None, None, None, None

        latest_quarter = quarters_data[0][0]
        prev_quarter = quarters_data[1][0]
        latest_profit = quarters_data[0][1]
        previous_profit = quarters_data[1][1]

        # Q-o-Q: Latest vs Previous Quarter
        qoq_growth = calculate_percentage_change(latest_profit, previous_profit)

        # Q-o-Q Previous: Previous Quarter vs Quarter Before That
        qoq_prev = None
        if len(quarters_data) >= MIN_QUARTERS_FOR_QOQ + 1:
            qoq_prev = calculate_percentage_change(quarters_data[1][1], quarters_data[2][1])

        # Y-o-Y: Latest vs 4 Quarters Ago
        yoy_growth = None
        if len(quarters_data) >= MIN_QUARTERS_FOR_YOY:
            year_ago_profit = quarters_data[4][1]
            yoy_growth = calculate_percentage_change(latest_profit, year_ago_profit)

        return qoq_growth, qoq_prev, yoy_growth, latest_quarter, prev_quarter

    except Exception:
        return None, None, None, None, None


# ==============================================================================
# SECTION 2: SALES GROWTH (Y-o-Y)
# ==============================================================================

def calculate_yoy_sales(cursor, company_code):
    """
    Calculate Y-o-Y sales growth from screener_quarterly
    Falls back to Revenue+ for financial companies that don't have Sales+

    Args:
        cursor: Database cursor
        company_code (str): Company code

    Returns:
        float: Y-o-Y sales growth percentage
    """
    cursor.execute(f"""
        SELECT quarter, value
        FROM {TABLE_QUARTERLY}
        WHERE company_code = ? AND metric = 'Sales+'
        ORDER BY {QUARTER_ORDER_DESC}
        LIMIT 5
    """, (company_code,))

    results = cursor.fetchall()

    # Fall back to Revenue+ for financial companies
    if len(results) < MIN_QUARTERS_FOR_YOY:
        cursor.execute(f"""
            SELECT quarter, value
            FROM {TABLE_QUARTERLY}
            WHERE company_code = ? AND metric = 'Revenue+'
            ORDER BY {QUARTER_ORDER_DESC}
            LIMIT 5
        """, (company_code,))
        results = cursor.fetchall()

    if len(results) < MIN_QUARTERS_FOR_YOY:
        return None

    try:
        quarters_data = []
        for quarter, value in results:
            if is_valid_value(value):
                clean_value = clean_numeric_string(value)
                quarters_data.append(safe_float_convert(clean_value))

        if len(quarters_data) < MIN_QUARTERS_FOR_YOY:
            return None

        latest_sales = quarters_data[0]
        year_ago_sales = quarters_data[4]

        return calculate_growth_rate(latest_sales, year_ago_sales)

    except Exception:
        return None


# ==============================================================================
# SECTION 3: ROCE (Return on Capital Employed)
# ==============================================================================

def get_latest_roce(cursor, company_code):
    """
    Get latest ROCE value from screener_ratios

    Args:
        cursor: Database cursor
        company_code (str): Company code

    Returns:
        float: ROCE percentage
    """
    cursor.execute(f"""
        SELECT value, year
        FROM {TABLE_RATIOS}
        WHERE company_code = ? AND metric = 'ROCE %'
        ORDER BY year DESC
        LIMIT 1
    """, (company_code,))

    result = cursor.fetchone()

    if result:
        roce_str, year = result
        try:
            roce_value = float(roce_str.replace('%', '').strip())
            return roce_value
        except ValueError:
            return None

    return None


# ==============================================================================
# SECTION 4: PROMOTER HOLDING & TREND
# ==============================================================================

def calculate_promoter_trend(cursor, company_code):
    """
    Calculate promoter holding trend from last 4 quarters

    Args:
        cursor: Database cursor
        company_code (str): Company code

    Returns:
        tuple: (trend_category, trend_display, latest_holding)

    Trend Categories:
        - stable_or_increased: No decrease or increase
        - decreased_minor: Decreased but less than 10%
        - decreased_10_plus: Decreased by 10% or more
    """
    cursor.execute(f"""
        SELECT quarter, value
        FROM {TABLE_SHAREHOLDING}
        WHERE company_code = ? AND metric = 'Promoters+'
        ORDER BY {QUARTER_ORDER_DESC}
        LIMIT 4
    """, (company_code,))

    results = cursor.fetchall()

    if len(results) < MIN_QUARTERS_FOR_PROMOTER_TREND:
        return None, None, None

    try:
        # Parse holdings
        holdings = []
        for quarter, value in results:
            if is_valid_value(value):
                clean_value = value.replace('%', '').replace(',', '').strip()
                holdings.append(float(clean_value))

        if len(holdings) < MIN_QUARTERS_FOR_PROMOTER_TREND:
            return None, None, None

        latest = holdings[0]
        oldest = holdings[-1]

        change = latest - oldest
        change_pct = (change / oldest * 100) if oldest > 0 else 0

        # Determine trend
        if change >= 0:
            trend = 'stable_or_increased'
            trend_display = f"🟢 {latest:.1f}%"
        elif change_pct <= PROMOTER_DECREASE_MAJOR_THRESHOLD:
            trend = 'decreased_10_plus'
            trend_display = f"🔴 {latest:.1f}% ({change:+.1f}%)"
        else:
            trend = 'decreased_minor'
            trend_display = f"🟡 {latest:.1f}% ({change:+.1f}%)"

        return trend, trend_display, latest

    except Exception:
        return None, None, None


# ==============================================================================
# SECTION 5: FCF METRICS (Free Cash Flow)
# ==============================================================================

def calculate_fcf_metrics(cursor, company_code):
    """
    Calculate FCF metrics from annual cash flow data
    FCF = Operating Cash Flow - Investing Cash Flow (outflow)

    Args:
        cursor: Database cursor
        company_code (str): Company code

    Returns:
        tuple: (total_fcf, fcf_cfo_ratio, avg_annual_fcf, fcf_category)
    """
    # Get cash flow data from screener_cash_flow table
    cursor.execute(f"""
        SELECT metric, year, value
        FROM {TABLE_CASH_FLOW}
        WHERE company_code = ? AND metric IN ('Cash from Operating Activity+', 'Cash from Investing Activity+')
        ORDER BY year DESC
    """, (company_code,))

    results = cursor.fetchall()

    if not results:
        return None, None, None, None

    try:
        # Group by year
        years_data = {}
        for metric, year, value in results:
            if year and 'TTM' not in year:
                if year not in years_data:
                    years_data[year] = {}
                years_data[year][metric] = value

        # Get latest 3 years
        sorted_years = sorted(years_data.keys(), reverse=True)[:3]

        total_cfo = 0
        total_fcf = 0

        for year in sorted_years:
            year_data = years_data[year]
            if 'Cash from Operating Activity+' in year_data and 'Cash from Investing Activity+' in year_data:
                try:
                    cfo = float(str(year_data['Cash from Operating Activity+']).replace(',', ''))
                    investing = float(str(year_data['Cash from Investing Activity+']).replace(',', ''))

                    # FCF = Operating Cash Flow - Investing Cash Outflow
                    # Investing is usually negative (outflow), so FCF = CFO + Investing
                    fcf = cfo + investing

                    total_cfo += cfo
                    total_fcf += fcf
                except:
                    continue

        if total_cfo == 0:
            return None, None, None, None

        # Calculate FCF/CFO ratio
        # When both FCF and CFO are negative, ratio appears positive but is misleading - force negative
        fcf_cfo_ratio = (total_fcf / total_cfo) * 100 if total_cfo != 0 else None
        if fcf_cfo_ratio is not None and total_fcf < 0 and total_cfo < 0:
            fcf_cfo_ratio = -abs(fcf_cfo_ratio)

        # Calculate average annual FCF
        avg_annual_fcf = total_fcf / len(sorted_years) if total_fcf and len(sorted_years) > 0 else None

        # Categorize FCF
        fcf_category = None
        if total_fcf > 0:
            fcf_category = 'Positive'
        elif total_fcf < 0:
            fcf_category = 'Negative'
        else:
            fcf_category = 'Zero'

        return (
            total_fcf if total_fcf != 0 else None,
            fcf_cfo_ratio,
            avg_annual_fcf,
            fcf_category
        )

    except Exception:
        return None, None, None, None


# ==============================================================================
# SECTION 6: NPM (Net Profit Margin)
# ==============================================================================

def calculate_npm(cursor, company_code):
    """
    Calculate Net Profit Margin from annual P&L
    NPM = (Net Profit / Sales) * 100

    Args:
        cursor: Database cursor
        company_code (str): Company code

    Returns:
        float: Net Profit Margin percentage (3-year average)
    """
    cursor.execute(f"""
        SELECT metric, year, value
        FROM {TABLE_ANNUAL_PL}
        WHERE company_code = ? AND metric IN ('Sales+', 'Revenue+', 'Net Profit+')
        ORDER BY year DESC
    """, (company_code,))

    results = cursor.fetchall()

    if not results:
        return None

    try:
        # Group by year
        years_data = {}
        for metric, year, value in results:
            if year and 'TTM' not in year:
                if year not in years_data:
                    years_data[year] = {}
                years_data[year][metric] = value

        # Get latest 3 years
        sorted_years = sorted(years_data.keys(), reverse=True)[:3]

        npm_values = []
        for year in sorted_years:
            year_data = years_data[year]
            # Use Sales+ if available, fall back to Revenue+ for financial companies
            sales_key = 'Sales+' if 'Sales+' in year_data else 'Revenue+'
            if sales_key in year_data and 'Net Profit+' in year_data:
                sales = float(str(year_data[sales_key]).replace(',', ''))
                net_profit = float(str(year_data['Net Profit+']).replace(',', ''))

                if sales and sales != 0:
                    npm = (net_profit / sales) * 100
                    npm_values.append(npm)

        if npm_values:
            return sum(npm_values) / len(npm_values)  # Average NPM

        return None

    except Exception:
        return None


# ==============================================================================
# SECTION 7: DEBT TO EQUITY
# ==============================================================================

def calculate_debt_to_equity(cursor, company_code):
    """
    Calculate Debt to Equity ratio from balance sheet
    Debt/Equity = Borrowings / (Equity Capital + Reserves)

    Args:
        cursor: Database cursor
        company_code (str): Company code

    Returns:
        float: Debt to Equity ratio (3-year average)
    """
    cursor.execute(f"""
        SELECT metric, year, value
        FROM {TABLE_BALANCE_SHEET}
        WHERE company_code = ? AND (metric IN ('Borrowings+', 'Equity Capital', 'Reserves') OR metric LIKE 'Borrowing%')
        ORDER BY year DESC
    """, (company_code,))

    results = cursor.fetchall()

    if not results:
        return None

    try:
        # Group by year
        years_data = {}
        for metric, year, value in results:
            if year and 'TTM' not in year:
                if year not in years_data:
                    years_data[year] = {}

                # Normalize metric names
                if 'Borrow' in metric:
                    years_data[year]['Borrowings'] = value
                elif metric == 'Equity Capital':
                    years_data[year]['Equity'] = value
                elif metric == 'Reserves':
                    years_data[year]['Reserves'] = value

        # Get latest 3 years
        sorted_years = sorted(years_data.keys(), reverse=True)[:3]

        de_values = []
        for year in sorted_years:
            year_data = years_data[year]
            borrowings = year_data.get('Borrowings', '0')
            equity = year_data.get('Equity', '0')
            reserves = year_data.get('Reserves', '0')

            try:
                borrowings_val = float(str(borrowings).replace(',', ''))
                equity_val = float(str(equity).replace(',', ''))
                reserves_val = float(str(reserves).replace(',', ''))

                total_equity = equity_val + reserves_val
                if total_equity and total_equity != 0:
                    de_ratio = borrowings_val / total_equity
                    de_values.append(de_ratio)
            except:
                continue

        if de_values:
            return sum(de_values) / len(de_values)  # Average D/E

        return None

    except Exception:
        return None


# ==============================================================================
# SECTION 8: ANNUAL SALES GROWTH (Year 1, Year 2)
# ==============================================================================

def calculate_annual_sales_growth(cursor, company_code):
    """
    Calculate year-over-year sales growth for last 2 years from annual P&L

    Args:
        cursor: Database cursor
        company_code (str): Company code

    Returns:
        tuple: (year1_sales_growth, year2_sales_growth)
    """
    cursor.execute(f"""
        SELECT year, value
        FROM {TABLE_ANNUAL_PL}
        WHERE company_code = ? AND metric = 'Sales+'
        ORDER BY year DESC
    """, (company_code,))

    results = cursor.fetchall()

    # Fall back to Revenue+ for financial companies
    if not results:
        cursor.execute(f"""
            SELECT year, value
            FROM {TABLE_ANNUAL_PL}
            WHERE company_code = ? AND metric = 'Revenue+'
            ORDER BY year DESC
        """, (company_code,))
        results = cursor.fetchall()

    if not results:
        return None, None

    try:
        # Filter out TTM, get numeric values
        sales_data = []
        for year, value in results:
            if year and 'TTM' not in year and value and value != '-':
                sales_val = float(str(value).replace(',', ''))
                sales_data.append((year, sales_val))

        if len(sales_data) < 2:
            return None, None

        # Year 1 growth (most recent year vs previous)
        year1_growth = ((sales_data[0][1] - sales_data[1][1]) / sales_data[1][1]) * 100 if sales_data[1][1] != 0 else None

        # Year 2 growth (previous year vs year before that)
        year2_growth = None
        if len(sales_data) >= 3:
            year2_growth = ((sales_data[1][1] - sales_data[2][1]) / sales_data[2][1]) * 100 if sales_data[2][1] != 0 else None

        return year1_growth, year2_growth

    except Exception:
        return None, None


# ==============================================================================
# SECTION 9: SSGR (Self-Sustainable Growth Rate)
# ==============================================================================

def calculate_ssgr(cursor, company_code, year_offset=0):
    """
    Calculate SSGR (Self-Sustainable Growth Rate) based on Dr. Vijay Malik's formula
    SSGR = [(1 - Dep%) + NFAT × NPM × (1-DPR)] - 1

    Args:
        cursor: Database cursor
        company_code (str): Company code
        year_offset (int): Number of years to skip before picking 3 years.
            0 = latest 3 years (current), 3 = previous 3 years.

    Returns:
        float: SSGR percentage (3-year average calculation)
    """
    # Get annual P&L data (include Revenue+ as fallback for financial companies)
    cursor.execute(f"""
        SELECT metric, year, value
        FROM {TABLE_ANNUAL_PL}
        WHERE company_code = ? AND metric IN ('Sales+', 'Revenue+', 'Net Profit+', 'Depreciation', 'Dividend Payout %')
        ORDER BY year DESC
    """, (company_code,))

    pl_results = cursor.fetchall()

    # Get balance sheet data
    cursor.execute(f"""
        SELECT metric, year, value
        FROM {TABLE_BALANCE_SHEET}
        WHERE company_code = ? AND (metric LIKE '%Fixed Assets%' OR metric LIKE '%Net Block%')
        ORDER BY year DESC
    """, (company_code,))

    bs_results = cursor.fetchall()

    if not pl_results or not bs_results:
        return None

    try:
        # Group P&L data by year
        years_pl = {}
        for metric, year, value in pl_results:
            if year and 'TTM' not in year:
                if year not in years_pl:
                    years_pl[year] = {}
                years_pl[year][metric] = value

        # Group Balance Sheet data by year
        years_bs = {}
        for metric, year, value in bs_results:
            if year and 'TTM' not in year:
                if year not in years_bs:
                    years_bs[year] = {}
                # Use any metric that contains "Fixed Assets" or "Net Block"
                if 'Fixed Assets' in metric or 'Net Block' in metric:
                    years_bs[year]['NFA'] = value

        # Get up to 3 years starting after year_offset
        all_sorted_years = sorted(set(years_pl.keys()) & set(years_bs.keys()), reverse=True)
        sorted_years = all_sorted_years[year_offset:year_offset + 3]

        if len(sorted_years) < 1:
            return None

        # Calculate SSGR components for each year
        sales_list = []
        net_profit_list = []
        depreciation_list = []
        nfa_list = []
        dpr_list = []

        for year in sorted_years:
            try:
                # Use Sales+ if available, fall back to Revenue+ for financial companies
                sales_str = years_pl[year].get('Sales+') or years_pl[year].get('Revenue+', '0')
                sales = float(str(sales_str).replace(',', ''))
                net_profit = float(str(years_pl[year].get('Net Profit+', '0')).replace(',', ''))
                depreciation = float(str(years_pl[year].get('Depreciation', '0')).replace(',', ''))
                nfa = float(str(years_bs[year].get('NFA', '0')).replace(',', ''))
                dpr_str = str(years_pl[year].get('Dividend Payout %', '0')).replace('%', '').replace(',', '').strip()
                dpr = float(dpr_str) if dpr_str else 0

                if sales > 0 and net_profit > 0 and nfa > 0:
                    sales_list.append(sales)
                    net_profit_list.append(net_profit)
                    depreciation_list.append(depreciation)
                    nfa_list.append(nfa)
                    dpr_list.append(dpr)
            except:
                continue

        if len(sales_list) < 1:
            return None

        # Calculate 3-year averages
        avg_sales = sum(sales_list) / len(sales_list)
        avg_net_profit = sum(net_profit_list) / len(net_profit_list)
        avg_depreciation = sum(depreciation_list) / len(depreciation_list)
        avg_nfa = sum(nfa_list) / len(nfa_list)
        avg_dpr_pct = sum(dpr_list) / len(dpr_list)

        if avg_nfa == 0 or avg_sales == 0:
            return None

        # Calculate SSGR components
        npm = avg_net_profit / avg_sales  # Net Profit Margin
        nfat = avg_sales / avg_nfa  # Net Fixed Asset Turnover
        dep_pct = avg_depreciation / avg_nfa  # Depreciation % of NFA
        dpr = avg_dpr_pct / 100  # Dividend Payout Ratio (as decimal)

        # SSGR = [(1 - Dep%) + NFAT × NPM × (1-DPR)] - 1
        ssgr = ((1 - dep_pct) + (nfat * npm * (1 - dpr))) - 1
        ssgr_pct = round(ssgr * 100, 2)  # Convert to percentage

        return ssgr_pct

    except Exception:
        return None


# ==============================================================================
# SECTION 10: SENTIMENT RATING (Price Position in 52-Week Range)
# ==============================================================================

def calculate_sentiment_rating(cursor, company_code):
    """
    Calculate sentiment rating (1-5 stars) based on current price position
    in 52-week range from screener_daily_prices

    Args:
        cursor: Database cursor
        company_code (str): Company code

    Returns:
        int: Sentiment rating (1-5 stars) or None

    Rating Scale:
        5 stars: 80-100% (Very Bullish, near 52W high)
        4 stars: 60-80%  (Bullish)
        3 stars: 40-60%  (Neutral)
        2 stars: 20-40%  (Bearish)
        1 star:  0-20%   (Very Bearish, near 52W low)
    """
    cursor.execute(f"""
        SELECT current_price, week_52_high, week_52_low
        FROM {TABLE_DAILY_PRICES}
        WHERE company_code = ?
        ORDER BY date DESC
        LIMIT 1
    """, (company_code,))

    result = cursor.fetchone()

    if not result:
        return None

    current_price, week_52_high, week_52_low = result

    # Validate data
    if not all([current_price, week_52_high, week_52_low]):
        return None

    if week_52_high <= week_52_low:
        return None

    try:
        # Calculate position in 52-week range (0-100%)
        price_range = week_52_high - week_52_low
        position = ((current_price - week_52_low) / price_range) * 100

        # Clamp to 0-100 range
        position = max(0, min(100, position))

        # Convert to 1-5 star rating
        if position >= 80:
            return 5  # Very Bullish
        elif position >= 60:
            return 4  # Bullish
        elif position >= 40:
            return 3  # Neutral
        elif position >= 20:
            return 2  # Bearish
        else:
            return 1  # Very Bearish

    except Exception:
        return None


# ==============================================================================
# SECTION 8: NET PROFIT, PE RATIO, PEG RATIO (from screener data as fallback)
# ==============================================================================

def calculate_net_profit(cursor, company_code):
    """
    Get latest annual net profit from screener_annual_pl.
    Falls back to Revenue+ for financial companies.

    Returns:
        float: Net profit in Crores, or None
    """
    cursor.execute(f"""
        SELECT value FROM {TABLE_ANNUAL_PL}
        WHERE company_code = ? AND metric = 'Net Profit+'
        ORDER BY {QUARTER_ORDER_DESC.replace('quarter', 'year')}
        LIMIT 1
    """, (company_code,))
    row = cursor.fetchone()
    if row and row[0]:
        val = safe_float_convert(clean_numeric_string(str(row[0])))
        if val is not None:
            return val
    return None


def calculate_pe_ratio(cursor, company_code, net_profit):
    """
    Compute PE ratio from current_price / EPS when Yahoo doesn't provide trailingPE.
    Uses TTM EPS from screener annual P&L, falling back to latest annual EPS.
    Also computes market_cap from PE * net_profit if market_cap is missing.
    Only used as a fallback — Yahoo's value (set in _save_price_data) takes priority.

    Returns:
        (pe_ratio, market_cap) tuple, either or both may be None
    """
    # Check if Yahoo already set pe_ratio
    cursor.execute(f"""
        SELECT pe_ratio, market_cap FROM {TABLE_DERIVED}
        WHERE company_code = ?
    """, (company_code,))
    row = cursor.fetchone()
    if not row:
        return None, None

    existing_pe, existing_mcap = row

    # If Yahoo already provided PE, don't override
    if existing_pe is not None and existing_pe != '':
        return None, None

    # Get current price
    cursor.execute(f"""
        SELECT current_price FROM {TABLE_DAILY_PRICES}
        WHERE company_code = ?
        ORDER BY date DESC LIMIT 1
    """, (company_code,))
    price_row = cursor.fetchone()
    if not price_row or not price_row[0]:
        return None, None
    current_price = float(price_row[0])
    if current_price <= 0:
        return None, None

    # Get EPS: try TTM first, then latest annual year
    eps = None

    # Try TTM EPS from annual P&L
    cursor.execute(f"""
        SELECT value FROM {TABLE_ANNUAL_PL}
        WHERE company_code = ? AND metric = 'EPS in Rs' AND year = 'TTM'
    """, (company_code,))
    ttm_row = cursor.fetchone()
    if ttm_row and ttm_row[0]:
        eps = safe_float_convert(clean_numeric_string(str(ttm_row[0])))

    # Fallback: latest annual EPS (skip TTM row)
    if eps is None or eps <= 0:
        cursor.execute(f"""
            SELECT value FROM {TABLE_ANNUAL_PL}
            WHERE company_code = ? AND metric = 'EPS in Rs' AND year <> 'TTM'
            ORDER BY {QUARTER_ORDER_DESC.replace('quarter', 'year')}
            LIMIT 1
        """, (company_code,))
        annual_row = cursor.fetchone()
        if annual_row and annual_row[0]:
            eps = safe_float_convert(clean_numeric_string(str(annual_row[0])))

    if not eps or eps <= 0:
        return None, None

    pe = round(current_price / eps, 2)

    # Also compute market_cap if missing: market_cap = PE * net_profit
    computed_mcap = None
    if (existing_mcap is None or existing_mcap == '') and net_profit and net_profit > 0:
        computed_mcap = round(pe * net_profit, 2)

    return pe, computed_mcap


def calculate_peg_ratio(cursor, company_code, pe_ratio_val, year1_sales_growth):
    """
    Compute PEG ratio from PE / year1_sales_growth when Yahoo doesn't provide pegRatio.
    Only used as a fallback — Yahoo's value takes priority.

    Args:
        cursor: Database cursor
        company_code: Company code
        pe_ratio_val: PE ratio (either from Yahoo or computed)
        year1_sales_growth: Year 1 sales growth percentage

    Returns:
        float: PEG ratio, or None if cannot compute
    """
    # Check if Yahoo already set peg_ratio
    cursor.execute(f"""
        SELECT peg_ratio, pe_ratio FROM {TABLE_DERIVED}
        WHERE company_code = ?
    """, (company_code,))
    row = cursor.fetchone()
    if not row:
        return None

    existing_peg, existing_pe = row

    # If Yahoo already provided PEG, don't override
    if existing_peg is not None and existing_peg != '':
        return None

    # Use the best available PE (Yahoo's existing or our computed one)
    pe = None
    if existing_pe is not None and existing_pe != '':
        try:
            pe = float(existing_pe)
        except (ValueError, TypeError):
            pass
    if pe is None and pe_ratio_val is not None:
        pe = pe_ratio_val

    if not pe or pe <= 0:
        return None

    # Use year1_sales_growth as growth rate
    if year1_sales_growth is not None:
        try:
            growth = float(year1_sales_growth)
            if growth > 0:
                return round(pe / growth, 2)
        except (ValueError, TypeError):
            pass

    return None


# ==============================================================================
# MAIN UPDATE FUNCTION
# ==============================================================================

def update_all_metrics():
    """
    Update all derived metrics for all companies
    """

    logger = setup_logger('derived_metrics')

    conn = get_database_connection()
    cursor = conn.cursor()

    # Ensure new columns exist
    try:
        cursor.execute(f"ALTER TABLE {TABLE_DERIVED} ADD COLUMN qoq_profit_growth_prev REAL")
        conn.commit()
    except Exception:
        pass  # Column already exists

    # Get all companies
    companies = get_all_companies(conn)

    logger.info("=" * 100)
    logger.info("UPDATING ALL DERIVED METRICS")
    logger.info("=" * 100)
    logger.info(f"Started: {get_timestamp()}")
    logger.info(f"Companies: {len(companies)}")

    # Statistics
    stats = {
        'profit_growth': 0,
        'sales_growth': 0,
        'roce': 0,
        'promoter': 0,
        'sentiment': 0,
        'fcf': 0,
        'npm': 0,
        'debt_equity': 0,
        'annual_sales': 0,
        'ssgr': 0,
        'net_profit': 0,
        'pe_computed': 0,
        'peg_computed': 0,
        'no_data': 0
    }

    for idx, (company_code, company_name) in enumerate(companies, 1):

        # 1. Calculate Profit Growth (Q-o-Q and Y-o-Y)
        qoq_growth, qoq_prev, yoy_profit_growth, latest_quarter, prev_quarter = calculate_profit_growth(cursor, company_code)

        # 2. Calculate Sales Growth (Y-o-Y)
        yoy_sales_growth = calculate_yoy_sales(cursor, company_code)

        # 3. Get ROCE
        roce = get_latest_roce(cursor, company_code)

        # 4. Calculate Promoter Trend
        promoter_trend, promoter_trend_display, promoter_holding = calculate_promoter_trend(cursor, company_code)

        # 5. Calculate Sentiment Rating
        sentiment_rating = calculate_sentiment_rating(cursor, company_code)

        # 6. Calculate FCF Metrics
        total_fcf, fcf_cfo_ratio, avg_annual_fcf, fcf_category = calculate_fcf_metrics(cursor, company_code)

        # 7. Calculate NPM (Net Profit Margin)
        npm = calculate_npm(cursor, company_code)

        # 8. Calculate Debt to Equity
        debt_to_equity = calculate_debt_to_equity(cursor, company_code)

        # 9. Calculate Annual Sales Growth (Year 1, Year 2)
        year1_sales_growth, year2_sales_growth = calculate_annual_sales_growth(cursor, company_code)

        # 10. Calculate SSGR (current and previous year)
        ssgr = calculate_ssgr(cursor, company_code, year_offset=0)
        ssgr_prev = calculate_ssgr(cursor, company_code, year_offset=1)

        # 11. Calculate Net Profit (from annual P&L — fallback for Yahoo gaps)
        net_profit = calculate_net_profit(cursor, company_code)

        # 12. Calculate PE Ratio (from price/EPS — only if Yahoo didn't set it)
        pe_ratio_computed, market_cap_computed = calculate_pe_ratio(cursor, company_code, net_profit)

        # 13. Calculate PEG Ratio (from PE/growth — only if Yahoo didn't set it)
        peg_ratio_computed = calculate_peg_ratio(cursor, company_code, pe_ratio_computed, year1_sales_growth)

        # Update database
        cursor.execute(f"""
            UPDATE {TABLE_DERIVED}
            SET qoq_profit_growth = ?,
                qoq_profit_growth_prev = ?,
                yoy_profit_growth = ?,
                yoy_sales_growth = ?,
                latest_quarter = ?,
                roce = ?,
                promoter_holding = ?,
                promoter_trend = ?,
                promoter_trend_display = ?,
                sentiment_rating = ?,
                total_fcf = ?,
                fcf_cfo_ratio = ?,
                avg_annual_fcf = ?,
                fcf_category = ?,
                npm = ?,
                debt_to_equity = ?,
                year1_sales_growth = ?,
                year2_sales_growth = ?,
                ssgr = ?,
                ssgr_prev = ?,
                prev_quarter = ?
            WHERE company_code = ?
        """, (
            qoq_growth,
            qoq_prev,
            yoy_profit_growth,
            yoy_sales_growth,
            latest_quarter,
            roce,
            promoter_holding,
            promoter_trend,
            promoter_trend_display,
            sentiment_rating,
            total_fcf,
            fcf_cfo_ratio,
            avg_annual_fcf,
            fcf_category,
            npm,
            debt_to_equity,
            year1_sales_growth,
            year2_sales_growth,
            ssgr,
            ssgr_prev,
            prev_quarter,
            company_code
        ))

        # Update net_profit (always from screener data)
        if net_profit is not None:
            cursor.execute(f"""
                UPDATE {TABLE_DERIVED} SET net_profit = ?
                WHERE company_code = ?
            """, (net_profit, company_code))

        # Update pe_ratio and market_cap (only if Yahoo didn't provide them)
        if pe_ratio_computed is not None:
            cursor.execute(f"""
                UPDATE {TABLE_DERIVED} SET pe_ratio = ?
                WHERE company_code = ?
            """, (pe_ratio_computed, company_code))
        if market_cap_computed is not None:
            cursor.execute(f"""
                UPDATE {TABLE_DERIVED} SET market_cap = ?
                WHERE company_code = ?
            """, (market_cap_computed, company_code))

        # Update peg_ratio (only if Yahoo didn't provide it)
        if peg_ratio_computed is not None:
            cursor.execute(f"""
                UPDATE {TABLE_DERIVED} SET peg_ratio = ?
                WHERE company_code = ?
            """, (peg_ratio_computed, company_code))

        # Update statistics
        if qoq_growth is not None or yoy_profit_growth is not None:
            stats['profit_growth'] += 1
        if yoy_sales_growth is not None:
            stats['sales_growth'] += 1
        if roce is not None:
            stats['roce'] += 1
        if promoter_trend is not None:
            stats['promoter'] += 1
        if sentiment_rating is not None:
            stats['sentiment'] += 1
        if total_fcf is not None:
            stats['fcf'] += 1
        if npm is not None:
            stats['npm'] += 1
        if debt_to_equity is not None:
            stats['debt_equity'] += 1
        if year1_sales_growth is not None:
            stats['annual_sales'] += 1
        if ssgr is not None:
            stats['ssgr'] += 1
        if net_profit is not None:
            stats['net_profit'] += 1
        if pe_ratio_computed is not None:
            stats['pe_computed'] += 1
        if peg_ratio_computed is not None:
            stats['peg_computed'] += 1

        if all(x is None for x in [qoq_growth, yoy_profit_growth, yoy_sales_growth, roce, promoter_trend,
                                     sentiment_rating, total_fcf, npm, debt_to_equity, year1_sales_growth, ssgr]):
            stats['no_data'] += 1

        # Print progress
        if idx % PROGRESS_UPDATE_INTERVAL == 0 or idx == len(companies):
            # Format values for display
            qoq_str = format_percentage(qoq_growth)
            yoy_p_str = format_percentage(yoy_profit_growth)
            yoy_s_str = format_percentage(yoy_sales_growth)
            roce_str = f"{roce:.1f}%" if roce else "N/A"
            prom_str = promoter_trend_display if promoter_trend_display else "N/A"
            sent_str = f"{'⭐' * sentiment_rating}" if sentiment_rating else "N/A"

            progress = format_progress(idx, len(companies), company_code, company_name)
            logger.info(f"{progress} QoQ:{qoq_str:>8} YoY-P:{yoy_p_str:>8} YoY-S:{yoy_s_str:>8} "
                       f"ROCE:{roce_str:>6} Prom:{prom_str} Sent:{sent_str}")

        # Commit every N companies
        if idx % COMMIT_INTERVAL == 0:
            conn.commit()

    # Final commit
    conn.commit()
    conn.close()

    # Summary
    logger.info("=" * 100)
    logger.info("UPDATE SUMMARY")
    logger.info("=" * 100)
    logger.info(f"✓ Companies with Profit Growth data:    {stats['profit_growth']}/{len(companies)}")
    logger.info(f"✓ Companies with Sales Growth data:     {stats['sales_growth']}/{len(companies)}")
    logger.info(f"✓ Companies with Annual Sales data:     {stats['annual_sales']}/{len(companies)}")
    logger.info(f"✓ Companies with ROCE data:             {stats['roce']}/{len(companies)}")
    logger.info(f"✓ Companies with Promoter data:         {stats['promoter']}/{len(companies)}")
    logger.info(f"✓ Companies with Sentiment data:        {stats['sentiment']}/{len(companies)}")
    logger.info(f"✓ Companies with FCF data:              {stats['fcf']}/{len(companies)}")
    logger.info(f"✓ Companies with NPM data:              {stats['npm']}/{len(companies)}")
    logger.info(f"✓ Companies with Debt/Equity data:      {stats['debt_equity']}/{len(companies)}")
    logger.info(f"✓ Companies with SSGR data:             {stats['ssgr']}/{len(companies)}")
    logger.info(f"✓ Companies with Net Profit data:       {stats['net_profit']}/{len(companies)}")
    logger.info(f"✓ PE computed (fallback):               {stats['pe_computed']}/{len(companies)}")
    logger.info(f"✓ PEG computed (fallback):              {stats['peg_computed']}/{len(companies)}")
    logger.info(f"✗ Companies with no data:               {stats['no_data']}/{len(companies)}")
    logger.info(f"Completed: {get_timestamp()}")
    logger.info("=" * 100)


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    from lib import ScriptLock
    lock = ScriptLock('derived_metrics')
    if not lock.acquire():
        import sys
        sys.exit(0)
    try:
        update_all_metrics()
    finally:
        lock.release()
