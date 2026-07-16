#!/bin/bash
# Monthly Screener.in annual data refresh (1st of each month, 2 AM)
# Re-scrapes annual P&L, balance sheet, and cash flow for all enabled Indian companies.
# Runs separately from the daily --yahoo-price-and-recent-quarter cron (which only updates quarterly data via Yahoo).
source /home/amitbalode/personnel/venv/bin/activate
cd /home/amitbalode/personnel/stock
python discover_new_companies.py --rescrape-annual-all >> logs/refresh_annual_$(date +%Y%m%d).log 2>&1
