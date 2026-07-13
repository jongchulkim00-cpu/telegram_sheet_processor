#!/usr/bin/env bash
set -euo pipefail

# Run this on the Linux home server, inside the telegram_sheet_processor directory.

echo "== Prepare .env =="
if [ ! -f ".env" ]; then
  cp .env.example .env
fi

echo "== Make scripts executable =="
chmod +x *.sh scripts/*.sh

echo "== Preflight =="
./preflight_home_server.sh

echo "== Build and start stock-api =="
./repair_stock_api_502.sh https://asset.jongchul-server.duckdns.org

