#!/usr/bin/env python3
"""
One-time backfill: import EDGAR financial history for existing US companies.
Run with --all to process all US companies, or pass tickers as args.
"""
import sys, os, time, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import DATABASE_PATH
from us_stock_downloader import USStockDownloader
from discover_new_companies import import_screener_data_to_db

def get_us_companies(limit=None):
    conn = sqlite3.connect(DATABASE_PATH)
    q = """
        SELECT company_code, company_name FROM screener_companies
        WHERE exchange IN ('NYSE','NASDAQ','AMEX') AND enabled = 1
        ORDER BY company_code
    """
    if limit:
        q += f" LIMIT {limit}"
    rows = conn.execute(q).fetchall()
    conn.close()
    return rows

def already_has_data(ticker):
    conn = sqlite3.connect(DATABASE_PATH)
    n = conn.execute(
        "SELECT COUNT(*) FROM screener_annual_pl WHERE company_code = ?", (ticker,)
    ).fetchone()[0]
    conn.close()
    return n > 0

def main():
    tickers_arg = [a for a in sys.argv[1:] if a != '--all']
    do_all      = '--all' in sys.argv

    if tickers_arg:
        companies = [(t.upper(), '') for t in tickers_arg]
    elif do_all:
        companies = get_us_companies()
    else:
        companies = get_us_companies(limit=15)

    dl = USStockDownloader()
    ok = failed = skipped = 0

    print(f"Backfilling EDGAR data for {len(companies)} US companies...\n")

    for i, (ticker, name) in enumerate(companies, 1):
        if already_has_data(ticker):
            print(f"[{i}/{len(companies)}] {ticker} — already has data, skipping")
            skipped += 1
            continue

        print(f"[{i}/{len(companies)}] {ticker} {name}")
        try:
            data = dl.download_company_data(ticker)
            if data and any(data.get(k) for k in ['annual_profit_loss', 'quarterly_results']):
                import_screener_data_to_db(ticker, data, source='sync')
                ok += 1
            else:
                print(f"  ✗ No data returned")
                failed += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed += 1

        time.sleep(0.5)  # respect EDGAR rate limit

    print(f"\n{'='*50}")
    print(f"Done: {ok} imported, {skipped} skipped (had data), {failed} failed")

if __name__ == '__main__':
    main()
