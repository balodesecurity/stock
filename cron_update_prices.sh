#!/bin/bash
# Hourly quick price update (9 AM - 3 PM, Mon-Fri)
source /Users/abalode/personnel/venv/bin/activate
cd /Users/abalode/personnel/stock
python fetch_market_data.py -i yahoo-daily-change >> logs/update_prices_cron.log 2>&1
