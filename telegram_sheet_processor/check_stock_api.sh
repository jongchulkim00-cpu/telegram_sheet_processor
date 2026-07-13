#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8010}"

echo "Checking ${BASE_URL}/health"
curl -fsS "${BASE_URL}/health"
echo
echo

echo "Checking ${BASE_URL}/source-status"
curl -fsS "${BASE_URL}/source-status"
echo
echo

echo "Checking ${BASE_URL}/cache-audit?tickers=039030,011790"
curl -fsS "${BASE_URL}/cache-audit?tickers=039030,011790"
echo

