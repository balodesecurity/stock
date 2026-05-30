#!/bin/bash
# Daily company sync from screener filter (11 AM)
source /home/amitbalode/personnel/venv/bin/activate
cd /home/amitbalode/personnel/stock
python sync_new_companies.py >> logs/sync_companies_cron.log 2>&1
