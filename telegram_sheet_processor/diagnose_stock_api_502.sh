#!/usr/bin/env bash
set -u

BASE_URL="${1:-https://asset.jongchul-server.duckdns.org}"
cd "$(dirname "$0")"
. ./scripts/compose_lib.sh

echo "== Docker containers =="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo
echo "== stock-api logs =="
docker logs --tail 80 telegram-sheet-stock-api 2>&1 || true

echo
echo "== Internal stock-api from host =="
curl -i --max-time 10 http://127.0.0.1:8010/health || true

echo
echo "== LAN stock-api =="
curl -i --max-time 10 http://192.168.1.12:8010/health || true

echo
echo "== External proxy =="
curl -i --max-time 20 "${BASE_URL}/health" || true

echo
echo "If internal 8010 fails, start/rebuild stock-api:"
echo "  ./repair_stock_api_502.sh ${BASE_URL}"
echo
echo "If internal 8010 works but external proxy is 502, check NPM target:"
echo "  Forward Hostname/IP: 192.168.1.12"
echo "  Forward Port: 8010"
echo "  Scheme: http"
