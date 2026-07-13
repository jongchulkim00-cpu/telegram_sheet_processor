#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-https://asset.jongchul-server.duckdns.org}"

cd "$(dirname "$0")"
. ./scripts/compose_lib.sh

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "== Rebuilding stock-api =="
compose up -d --build stock-api

echo
echo "== Containers =="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo
echo "== Waiting for healthcheck =="
sleep 5

echo
echo "== stock-api logs =="
docker logs --tail 80 telegram-sheet-stock-api

echo
echo "== Internal health: localhost =="
curl -fsS http://127.0.0.1:8010/health
echo

echo
echo "== Internal health: LAN IP =="
curl -fsS http://192.168.1.12:8010/health
echo

echo
echo "== External health through NPM =="
curl -fsS "${BASE_URL}/health"
echo

echo
echo "All checks passed."
