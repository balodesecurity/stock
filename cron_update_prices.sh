#!/bin/bash
# Hourly quick price update (9 AM - 3 PM, Mon-Fri)
source /home/amitbalode/personnel/venv/bin/activate
cd /home/amitbalode/personnel/stock
python update_stock_prices_v2.py >> logs/update_prices_cron.log 2>&1
