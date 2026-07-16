#!/bin/bash
# Daily company sync from screener filter (11 AM)
source /Users/abalode/personnel/venv/bin/activate
cd /Users/abalode/personnel/stock
python discover_new_companies.py >> logs/discover_new_companies_cron.log 2>&1
