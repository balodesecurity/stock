#!/bin/bash
# Daily fundamentals + derived metrics (12 PM, Mon-Fri)
source /home/amitbalode/personnel/venv/bin/activate
cd /home/amitbalode/personnel/stock
python update_stock_prices_v2.py --fundamentals --force >> logs/update_fundamentals_cron.log 2>&1
python update_derived_metrics.py >> logs/update_fundamentals_cron.log 2>&1
