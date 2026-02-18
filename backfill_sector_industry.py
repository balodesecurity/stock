#!/usr/bin/env python3
"""
Backfill script: populate sector and industry columns in
derived_metrics_analysis from screener.in peer-comparison data.

Supports pause/resume by caching HTML pages to disk. On re-run, reads
from cached files instead of hitting screener.in again.

Only processes companies that are missing sector/industry in the DB.
"""

import sqlite3
import time
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screener_downloader import ScreenerDownloader
from constants import DATABASE_PATH, BASE_DIR

# Directory to cache screener HTML pages
CACHE_DIR = BASE_DIR / 'cache' / 'screener_html'


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Only get companies that still need sector/industry
    cursor.execute("""
        SELECT company_code FROM derived_metrics_analysis
        WHERE sector IS NULL OR sector = '' OR industry IS NULL OR industry = ''
        ORDER BY company_code
    """)
    companies = [row[0] for row in cursor.fetchall()]
    total = len(companies)

    if total == 0:
        print("All companies already have sector/industry. Nothing to backfill.")
        conn.close()
        return

    print(f"Found {total} companies to backfill")

    downloader = ScreenerDownloader()
    from bs4 import BeautifulSoup

    updated = 0
    failed = 0
    from_cache = 0
    from_web = 0

    for i, code in enumerate(companies, 1):
        print(f"[{i}/{total}] {code} ... ", end="", flush=True)

        cache_file = CACHE_DIR / f"{code}.html"

        try:
            if cache_file.exists():
                # Read from cached file on disk
                html_content = cache_file.read_bytes()
                from_cache += 1
                source = "cache"
            else:
                # Fetch from screener.in and save to disk
                url = f"{downloader.BASE_URL}/company/{code}/consolidated/"
                response = downloader.session.get(url, timeout=15)
                response.raise_for_status()
                html_content = response.content

                # Save to cache for future runs
                cache_file.write_bytes(html_content)
                from_web += 1
                source = "web"

                # Rate limit only for web requests
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
                print(f"[{source}] sector={sector}, industry={industry}")
            else:
                print(f"[{source}] no sector/industry found")

        except Exception as e:
            failed += 1
            print(f"ERROR: {e}")

    conn.close()
    print(f"\nDone. Updated: {updated}, Failed: {failed}, Total: {total}")
    print(f"From cache: {from_cache}, From web: {from_web}")


if __name__ == "__main__":
    main()
