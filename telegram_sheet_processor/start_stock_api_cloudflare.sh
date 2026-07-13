#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
. ./scripts/compose_lib.sh

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
  echo "Edit .env and set CLOUDFLARED_TOKEN before running this script again."
  exit 1
fi

if ! grep -q "^CLOUDFLARED_TOKEN=.\+" ".env"; then
  echo "CLOUDFLARED_TOKEN is empty in .env."
  echo "Create a Cloudflare Tunnel token and set:"
  echo "  CLOUDFLARED_TOKEN=..."
  exit 1
fi

compose -f docker-compose.yml -f docker-compose.cloudflare.yml up -d --build
compose -f docker-compose.yml -f docker-compose.cloudflare.yml ps

echo
echo "Cloudflare Tunnel started. Check your public hostname in Cloudflare Zero Trust."
