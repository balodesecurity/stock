#!/usr/bin/env python3
"""
US Stock Downloader — Fetches financial history for US companies from SEC EDGAR.

Uses the EDGAR Company Facts API (one HTTP request per company) to pull the
complete XBRL fact history. Returns data in the same dict format as
ScreenerDownloader so it slots directly into import_screener_data_to_db().

Values are stored in USD millions. All derived metrics (SSGR, FCF/CFO, ROCE,
D/E) are ratios — the unit cancels out. Absolute values (market cap, PE) come
from yfinance via sync_companies.py.
"""

import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple

try:
    import edgar
except ImportError:
    edgar = None

EDGAR_IDENTITY = 'amit.balode@gmail.com'
EDGAR_API      = 'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'
EDGAR_HEADERS  = {'User-Agent': EDGAR_IDENTITY}

# ── Concept priority lists (first match with data wins) ───────────────────────

REVENUE    = ['RevenueFromContractWithCustomerIncludingAssessedTax',
              'Revenues', 'SalesRevenueNet', 'SalesRevenueGoodsNet',
              'RevenueFromContractWithCustomerExcludingAssessedTax']

NET_INCOME = ['NetIncomeLoss',
              'NetIncomeLossAvailableToCommonStockholdersBasic',
              'ProfitLoss']

OP_INCOME  = ['OperatingIncomeLoss']

OTHER_INC  = ['OtherNonoperatingIncomeExpense', 'NonoperatingIncomeExpense',
              'OtherIncome', 'OtherNonoperatingIncome']

INTEREST   = ['InterestExpenseNonoperating', 'InterestExpense',
              'InterestAndDebtExpense', 'InterestIncomeExpenseNet']

PBT        = ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
              'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
              'IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic']

TAX_EXP    = ['IncomeTaxExpenseBenefit']

OP_CF      = ['NetCashProvidedByUsedInOperatingActivities',
              'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations']
INV_CF     = ['NetCashProvidedByUsedInInvestingActivities',
              'NetCashProvidedByUsedInInvestingActivitiesContinuingOperations']

DEP        = ['DepreciationDepletionAndAmortization',
              'DepreciationAndAmortization', 'Depreciation',
              'DepreciationAmortizationAndAccretionNet']

DIVIDENDS  = ['PaymentsOfDividends', 'PaymentsOfDividendsCommonStock']

PPE_NET    = ['PropertyPlantAndEquipmentNet']

LT_DEBT    = ['LongTermDebtNoncurrent', 'LongTermDebt', 'LineOfCredit',
              'LongTermNotesPayable', 'SeniorNotes',
              'OperatingLeaseLiabilityNoncurrent']   # lease obligations for lease-only companies

ST_DEBT    = ['DebtCurrent', 'ShortTermBorrowings', 'NotesPayableCurrent',
              'OperatingLeaseLiabilityCurrent']      # current portion of lease obligations

EQUITY     = ['StockholdersEquity',
              'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest']

ASSETS     = ['Assets']
CURR_LIAB  = ['LiabilitiesCurrent']

# Single quarter: start→end duration must be ≤ this many days
_SINGLE_QTR_MAX_DAYS = 105


class USStockDownloader:
    """
    Downloads financial data for US stocks from SEC EDGAR Company Facts API.

    Analogous to ScreenerDownloader for Indian stocks — returns the same dict
    format so data flows into the same screener_* tables without modification.
    """

    MAX_ANNUAL_YEARS = 10
    MAX_QUARTERS     = 12

    def __init__(self, identity_email: str = EDGAR_IDENTITY):
        edgar.set_identity(identity_email)

    # ── Public API ─────────────────────────────────────────────────────────────

    def download_company_data(self, ticker: str) -> Dict:
        """
        Fetch full financial history for a US ticker from SEC EDGAR.

        Returns a dict compatible with import_screener_data_to_db():
          annual_profit_loss → screener_annual_pl
          balance_sheet      → screener_balance_sheet
          cash_flow          → screener_cash_flow
          quarterly_results  → screener_quarterly
          ratios             → screener_ratios  (ROCE %)
          shareholding       → []  (no US equivalent)
        """
        print(f"Fetching EDGAR data for: {ticker}")

        try:
            cik = self._get_cik(ticker)
        except Exception as e:
            print(f"  ✗ CIK lookup failed for {ticker}: {e}")
            return {}

        try:
            facts_json = self._fetch_facts(cik)
        except Exception as e:
            print(f"  ✗ EDGAR API failed for {ticker}: {e}")
            return {}

        company_name = facts_json.get('entityName', ticker)
        us_gaap = facts_json.get('facts', {}).get('us-gaap', {})
        if not us_gaap:
            print(f"  ✗ No US-GAAP facts for {ticker}")
            return {}

        annual_pl, balance_sheet, cash_flow, ratios = self._build_annual(us_gaap)
        quarterly = self._build_quarterly(us_gaap)

        n_data_points = sum(len(r) - 1 for r in annual_pl)
        print(f"  ✓ {ticker}: {len(annual_pl)} annual metrics "
              f"({n_data_points} data points), {len(quarterly)} quarterly metrics")

        return {
            'company_code':       ticker,
            'company_name':       company_name,
            'report_type':        'annual',
            'sector':             None,
            'industry':           None,
            'annual_profit_loss': annual_pl,
            'balance_sheet':      balance_sheet,
            'cash_flow':          cash_flow,
            'quarterly_results':  quarterly,
            'ratios':             ratios,
            'shareholding':       [],
        }

    # ── Annual (10-K) ──────────────────────────────────────────────────────────

    def _build_annual(self, us_gaap: Dict) -> Tuple:
        sales      = self._annual(us_gaap, *REVENUE)
        net_profit = self._annual(us_gaap, *NET_INCOME)
        op_income  = self._annual(us_gaap, *OP_INCOME)
        other_inc  = self._annual(us_gaap, *OTHER_INC)
        interest   = self._annual(us_gaap, *INTEREST, negate=True)   # stored as expense (positive)
        pbt        = self._annual(us_gaap, *PBT)
        tax_exp    = self._annual(us_gaap, *TAX_EXP)
        dep        = self._annual(us_gaap, *DEP)
        dividends  = self._annual(us_gaap, *DIVIDENDS, from_cf=True, negate=True)
        ppe        = self._annual(us_gaap, *PPE_NET, instant=True)
        lt_debt    = self._annual(us_gaap, *LT_DEBT, instant=True)
        st_debt    = self._annual(us_gaap, *ST_DEBT, instant=True)
        equity     = self._annual(us_gaap, *EQUITY, instant=True)
        assets     = self._annual(us_gaap, *ASSETS, instant=True)
        curr_liab  = self._annual(us_gaap, *CURR_LIAB, instant=True)
        op_cf      = self._annual(us_gaap, *OP_CF)
        inv_cf     = self._annual(us_gaap, *INV_CF)

        all_periods = sorted(
            set(sales) | set(net_profit) | set(op_cf),
            key=lambda p: datetime.strptime(p, '%b %Y'),
            reverse=True
        )[:self.MAX_ANNUAL_YEARS]

        pl_acc: Dict[str, Dict] = {}
        bs_acc: Dict[str, Dict] = {}
        cf_acc: Dict[str, Dict] = {}
        roce_acc: Dict[str, str] = {}

        for period in all_periods:
            s   = sales.get(period)
            np  = net_profit.get(period)
            d   = dep.get(period)
            dv  = dividends.get(period)
            oi  = op_income.get(period)
            oii = other_inc.get(period)
            int_= interest.get(period)
            pb  = pbt.get(period)
            tx  = tax_exp.get(period)
            oc  = op_cf.get(period)
            ic  = inv_cf.get(period)
            pp  = ppe.get(period)
            ta  = assets.get(period)
            cl  = curr_liab.get(period)
            eq  = equity.get(period)
            ld  = lt_debt.get(period)
            sd  = st_debt.get(period)

            # Dividend payout %
            div_pct = None
            if dv is not None and np and np > 0:
                div_pct = round(dv / np * 100, 2)

            # Tax % (stored as raw expense so portal can display correctly)
            tax_pct = None
            if tx is not None and pb and pb != 0:
                tax_pct = round(abs(tx) / abs(pb) * 100, 1)

            # Total borrowings = LT + ST debt
            borrow = None
            if ld is not None or sd is not None:
                borrow = (ld or 0) + (sd or 0)

            # ROCE % = Operating Income / Capital Employed * 100
            if oi is not None and ta is not None and cl is not None:
                cap_employed = ta - cl
                if cap_employed > 0:
                    roce_acc[period] = str(round(oi / cap_employed * 100, 2))

            # P&L — store all income statement lines so the financial table is complete
            self._set(pl_acc, 'Sales+',            period, self._m(s))
            self._set(pl_acc, 'Operating Profit',  period, self._m(oi))
            self._set(pl_acc, 'Other Income+',     period, self._m(oii))
            self._set(pl_acc, 'Interest',          period, self._m(int_))
            self._set(pl_acc, 'Depreciation',      period, self._m(d))
            self._set(pl_acc, 'Profit before tax', period, self._m(pb))
            self._set(pl_acc, 'Net Profit+',       period, self._m(np))
            if tax_pct is not None:
                self._set(pl_acc, 'Tax %',         period, str(tax_pct))
            if div_pct is not None:
                self._set(pl_acc, 'Dividend Payout %', period, str(div_pct))

            # Balance sheet
            self._set(bs_acc, 'Net Block+',    period, self._m(pp))
            self._set(bs_acc, 'Borrowings+',   period, self._m(borrow))
            self._set(bs_acc, 'Equity Capital', period, self._m(eq))

            # Cash flow
            self._set(cf_acc, 'Cash from Operating Activity+', period, self._m(oc))
            self._set(cf_acc, 'Cash from Investing Activity+', period, self._m(ic))

        return (
            self._to_rows(pl_acc),
            self._to_rows(bs_acc),
            self._to_rows(cf_acc),
            self._roce_rows(roce_acc),
        )

    # ── Quarterly (10-Q) ───────────────────────────────────────────────────────

    def _build_quarterly(self, us_gaap: Dict) -> List[Dict]:
        sales      = self._quarterly(us_gaap, *REVENUE)
        net_profit = self._quarterly(us_gaap, *NET_INCOME)
        op_cf      = self._quarterly(us_gaap, *OP_CF)
        inv_cf     = self._quarterly(us_gaap, *INV_CF)

        all_qtrs = sorted(
            set(sales) | set(net_profit),
            key=lambda p: datetime.strptime(p, '%b %Y'),
            reverse=True
        )[:self.MAX_QUARTERS]

        q_acc: Dict[str, Dict] = {}
        for period in all_qtrs:
            oc  = op_cf.get(period)
            ic  = inv_cf.get(period)
            fcf = (oc + ic) if (oc is not None and ic is not None) else None

            self._set(q_acc, 'Sales+',              period, self._m(sales.get(period)))
            self._set(q_acc, 'Net Profit+',         period, self._m(net_profit.get(period)))
            self._set(q_acc, 'Operating Cash Flow+', period, self._m(oc))
            self._set(q_acc, 'Free Cash Flow+',      period, self._m(fcf))

        return self._to_rows(q_acc)

    # ── Series Extraction ──────────────────────────────────────────────────────

    def _annual(self, us_gaap: Dict, *concepts,
                instant: bool = False, from_cf: bool = False,
                negate: bool = False) -> Dict[str, float]:
        """
        Build {period -> raw_usd} for annual data from 10-K filings.

        Merges ALL concepts in priority order: for each fiscal year end, the
        first concept (in the order given) that has data for that year wins.
        This handles companies that change XBRL tags over time (e.g., revenue
        concepts changed when ASC 606 was adopted in 2018-2019).

        instant=True  : balance sheet items (no start date in XBRL).
        negate=True   : flip sign (cash outflows are stored negative in EDGAR).
        Deduplicates within each concept by fiscal year end, keeping the most
        recently filed value.
        """
        merged: Dict[str, float] = {}  # end_date -> value

        for concept in concepts:
            if concept not in us_gaap:
                continue
            units = us_gaap[concept].get('units', {})
            entries = units.get('USD') or units.get('USD/shares') or []
            if not entries:
                continue

            if instant:
                annual = [e for e in entries
                          if e.get('form') == '10-K' and 'start' not in e]
            else:
                annual = [e for e in entries
                          if e.get('form') == '10-K' and e.get('fp') == 'FY']

            if not annual:
                continue

            # Deduplicate within this concept: keep most-recently-filed per year
            by_end: Dict[str, dict] = {}
            for e in annual:
                end = e['end']
                if end not in by_end or e['filed'] > by_end[end]['filed']:
                    by_end[end] = e

            # Fill merged only for years not yet covered by a higher-priority concept
            for end_date, e in by_end.items():
                if end_date not in merged:
                    val = float(e['val'])
                    if negate:
                        val = abs(val)
                    merged[end_date] = val

        return {self._period(end): val for end, val in merged.items()}

    def _quarterly(self, us_gaap: Dict, *concepts,
                   negate: bool = False) -> Dict[str, float]:
        """
        Build {period -> raw_usd} for single-quarter data from 10-Q filings.
        Merges all concepts in priority order (same strategy as _annual).
        Distinguishes single-quarter from YTD by duration (start→end ≤ 105 days).
        """
        merged: Dict[str, float] = {}

        for concept in concepts:
            if concept not in us_gaap:
                continue
            units = us_gaap[concept].get('units', {})
            entries = units.get('USD') or units.get('USD/shares') or []

            single = []
            for e in entries:
                if e.get('form') != '10-Q' or 'start' not in e:
                    continue
                days = (datetime.strptime(e['end'], '%Y-%m-%d') -
                        datetime.strptime(e['start'], '%Y-%m-%d')).days
                if days <= _SINGLE_QTR_MAX_DAYS:
                    single.append(e)

            if not single:
                continue

            by_end: Dict[str, dict] = {}
            for e in single:
                end = e['end']
                if end not in by_end or e['filed'] > by_end[end]['filed']:
                    by_end[end] = e

            for end_date, e in by_end.items():
                if end_date not in merged:
                    val = float(e['val'])
                    if negate:
                        val = abs(val)
                    merged[end_date] = val

        return {self._period(end): val for end, val in merged.items()}

    # ── Utilities ──────────────────────────────────────────────────────────────

    def _get_cik(self, ticker: str) -> str:
        return str(edgar.Company(ticker).cik).zfill(10)

    def _fetch_facts(self, cik: str) -> Dict:
        r = requests.get(EDGAR_API.format(cik=cik),
                         headers=EDGAR_HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()

    def _period(self, date_str: str) -> str:
        """'2025-12-31' → 'Dec 2025'"""
        return datetime.strptime(date_str[:10], '%Y-%m-%d').strftime('%b %Y')

    def _m(self, usd: Optional[float]) -> Optional[str]:
        """Raw USD → USD millions string."""
        if usd is None:
            return None
        return str(round(usd / 1_000_000, 2))

    def _set(self, acc: Dict, metric: str, period: str, value: Optional[str]):
        if value is None:
            return
        if metric not in acc:
            acc[metric] = {}
        acc[metric][period] = value

    def _to_rows(self, acc: Dict) -> List[Dict]:
        rows = []
        for metric, periods in acc.items():
            if not periods:
                continue
            row = {'': metric}
            row.update(periods)
            rows.append(row)
        return rows

    def _roce_rows(self, roce_acc: Dict) -> List[Dict]:
        if not roce_acc:
            return []
        row = {'': 'ROCE %'}
        row.update(roce_acc)
        return [row]
