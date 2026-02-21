#!/usr/bin/env python3
"""
Screener.in Financial Report Downloader
Downloads and parses financial data from screener.in company pages
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import sys
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin


class ScreenerDownloader:
    """Downloads and parses financial reports from screener.in"""

    BASE_URL = "https://www.screener.in"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def _has_valid_financial_data(self, data: Dict) -> bool:
        """Check if at least one financial section has real column values (not just metric names)."""
        for key in ('quarterly_results', 'annual_profit_loss', 'balance_sheet'):
            rows = data.get(key) or []
            for row in rows:
                # A valid row has more than just the metric name key ('')
                if len(row) > 1:
                    return True
        return False

    def download_company_data(self, company_code: str, report_type: str = "consolidated",
                              max_retries: int = 5, retry_delay: float = 3.0) -> Dict:
        """
        Download financial data for a company

        Args:
            company_code: Stock symbol (e.g., 'NH', 'RELIANCE')
            report_type: 'consolidated', 'standalone', or '' (base URL)
            max_retries: Number of times to retry if page returns empty table data
            retry_delay: Seconds to wait between retries

        Returns:
            Dictionary containing all parsed financial data
        """
        if report_type:
            url = f"{self.BASE_URL}/company/{company_code}/{report_type}/"
        else:
            url = f"{self.BASE_URL}/company/{company_code}/"
        print(f"Fetching data from: {url}")

        for attempt in range(1, max_retries + 1):
            try:
                response = self.session.get(url)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"Error fetching data (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
                return {}

            soup = BeautifulSoup(response.content, 'lxml')

            # Extract company name
            company_name = self._extract_company_name(soup)

            # Extract sector and industry from peer-comparison section
            sector_industry = self._extract_sector_industry(soup)

            data = {
                'company_code': company_code,
                'company_name': company_name,
                'report_type': report_type,
                'url': url,
                'sector': sector_industry['sector'],
                'industry': sector_industry['industry'],
                'quarterly_results': self._extract_quarterly_results(soup),
                'annual_profit_loss': self._extract_annual_pl(soup),
                'balance_sheet': self._extract_balance_sheet(soup),
                'cash_flow': self._extract_cash_flow(soup),
                'ratios': self._extract_ratios(soup),
                'shareholding': self._extract_shareholding(soup),
            }

            if self._has_valid_financial_data(data):
                if attempt > 1:
                    print(f"  ✓ Got valid data on attempt {attempt}/{max_retries}")
                return data

            print(f"  ⚠ Attempt {attempt}/{max_retries}: table data appears empty (JS not loaded?), retrying in {retry_delay}s...")
            if attempt < max_retries:
                time.sleep(retry_delay)

        print(f"  ✗ All {max_retries} attempts returned empty table data for {company_code}")
        return data

    def _extract_company_name(self, soup: BeautifulSoup) -> str:
        """Extract company name from page"""
        title = soup.find('h1')
        if title:
            return title.get_text(strip=True)
        return "Unknown"

    def _extract_table(self, soup: BeautifulSoup, section_id: str) -> Optional[pd.DataFrame]:
        """Extract a table from a specific section"""
        section = soup.find('section', id=section_id)
        if not section:
            return None

        table = section.find('table')
        if not table:
            return None

        # Extract headers
        headers = []
        header_row = table.find('thead')
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all('th')]

        # Extract rows
        rows = []
        tbody = table.find('tbody')
        if tbody:
            for tr in tbody.find_all('tr'):
                row = [td.get_text(strip=True) for td in tr.find_all('td')]
                if row:
                    rows.append(row)

        if not rows:
            return None

        # Create DataFrame
        if headers:
            df = pd.DataFrame(rows, columns=headers)
        else:
            df = pd.DataFrame(rows)

        return df

    def _extract_quarterly_results(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract quarterly results table"""
        df = self._extract_table(soup, 'quarters')
        if df is not None:
            return df.to_dict(orient='records')
        return None

    def _extract_annual_pl(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract annual profit & loss statement"""
        df = self._extract_table(soup, 'profit-loss')
        if df is not None:
            return df.to_dict(orient='records')
        return None

    def _extract_balance_sheet(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract balance sheet"""
        df = self._extract_table(soup, 'balance-sheet')
        if df is not None:
            return df.to_dict(orient='records')
        return None

    def _extract_cash_flow(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract cash flow statement"""
        df = self._extract_table(soup, 'cash-flow')
        if df is not None:
            return df.to_dict(orient='records')
        return None

    def _extract_ratios(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract financial ratios"""
        df = self._extract_table(soup, 'ratios')
        if df is not None:
            return df.to_dict(orient='records')
        return None

    def _extract_shareholding(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract shareholding pattern"""
        df = self._extract_table(soup, 'shareholding')
        if df is not None:
            return df.to_dict(orient='records')
        return None

    def _extract_sector_industry(self, soup: BeautifulSoup) -> Dict[str, Optional[str]]:
        """Extract sector and industry from peer-comparison section.

        Screener.in provides a 4-level classification hierarchy via <a> tags
        with title attributes: Broad Sector, Sector, Broad Industry, Industry.
        We extract Sector and Industry.
        """
        result = {'sector': None, 'industry': None}

        section = soup.find('section', id='peers')
        if not section:
            return result

        for a_tag in section.find_all('a', title=True):
            title = a_tag.get('title', '').strip()
            text = a_tag.get_text(strip=True)
            if title == 'Sector' and text:
                result['sector'] = text
            elif title == 'Industry' and text:
                result['industry'] = text

        return result

    def save_to_json(self, data: Dict, filename: str):
        """Save data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Data saved to {filename}")

    def save_to_csv(self, data: Dict, prefix: str = "output"):
        """Save each section to separate CSV files"""
        company_code = data.get('company_code', 'unknown')

        sections = [
            'quarterly_results',
            'annual_profit_loss',
            'balance_sheet',
            'cash_flow',
            'ratios',
            'shareholding'
        ]

        for section in sections:
            section_data = data.get(section)
            if section_data:
                df = pd.DataFrame(section_data)
                filename = f"{prefix}_{company_code}_{section}.csv"
                df.to_csv(filename, index=False)
                print(f"Saved {section} to {filename}")

    def print_summary(self, data: Dict):
        """Print a formatted summary of the data"""
        print("\n" + "="*80)
        print(f"Company: {data.get('company_name', 'Unknown')}")
        print(f"Code: {data.get('company_code', 'Unknown')}")
        print(f"Report Type: {data.get('report_type', 'Unknown')}")
        print(f"Sector: {data.get('sector', 'N/A')}")
        print(f"Industry: {data.get('industry', 'N/A')}")
        print("="*80)

        sections = [
            ('Quarterly Results', 'quarterly_results'),
            ('Annual P&L', 'annual_profit_loss'),
            ('Balance Sheet', 'balance_sheet'),
            ('Cash Flow', 'cash_flow'),
            ('Ratios', 'ratios'),
            ('Shareholding', 'shareholding'),
        ]

        for section_name, section_key in sections:
            section_data = data.get(section_key)
            if section_data:
                print(f"\n{section_name}:")
                print(f"  Records: {len(section_data)}")
                if section_data:
                    print(f"  Fields: {', '.join(section_data[0].keys())}")
            else:
                print(f"\n{section_name}: No data available")

        print("\n" + "="*80)


def main():
    """Main function to run the scraper"""
    if len(sys.argv) < 2:
        print("Usage: python screener_downloader.py <COMPANY_CODE> [consolidated|standalone]")
        print("Example: python screener_downloader.py NH consolidated")
        sys.exit(1)

    company_code = sys.argv[1]
    report_type = sys.argv[2] if len(sys.argv) > 2 else "consolidated"

    downloader = ScreenerDownloader()
    data = downloader.download_company_data(company_code, report_type)

    if not data:
        print("Failed to download data")
        sys.exit(1)

    # Print summary
    downloader.print_summary(data)

    # Save to files
    json_filename = f"{company_code}_{report_type}_data.json"
    downloader.save_to_json(data, json_filename)
    downloader.save_to_csv(data, prefix=company_code)

    print(f"\nData downloaded successfully for {company_code}")


if __name__ == "__main__":
    main()
