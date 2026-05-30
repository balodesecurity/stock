#!/bin/bash
# Full stock sync — runs all 3 crons in sequence
# Usage: bash cron_full_sync.sh

set -e

STOCK_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$STOCK_DIR"

echo "======================================"
echo "STOCK FULL SYNC — $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================"

echo ""
echo "[1/3] Syncing companies from Screener.in..."
bash cron_sync_companies.sh
echo "      Done."

echo ""
echo "[2/3] Updating fundamentals + derived metrics..."
bash cron_update_fundamentals.sh
echo "      Done."

echo ""
echo "[3/3] Updating prices..."
bash cron_update_prices.sh
echo "      Done."

echo ""
echo "======================================"
echo "SYNC COMPLETE — $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================"
