#!/bin/bash
# Daily fundamentals + derived metrics (12 PM, Mon-Fri)
source /Users/abalode/personnel/venv/bin/activate
cd /Users/abalode/personnel/stock
python fetch_market_data.py -i yahoo-price-and-recent-quarter >> logs/update_fundamentals_cron.log 2>&1
python compute_growth_metrics.py >> logs/update_fundamentals_cron.log 2>&1
