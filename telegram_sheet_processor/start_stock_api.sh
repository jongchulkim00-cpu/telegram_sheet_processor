#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
. ./scripts/compose_lib.sh

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Review it before enabling realtime providers."
fi

compose up -d --build
compose ps

echo
echo "Local API:"
echo "  http://127.0.0.1:8010/health"
echo "  http://127.0.0.1:8010/source-status"
