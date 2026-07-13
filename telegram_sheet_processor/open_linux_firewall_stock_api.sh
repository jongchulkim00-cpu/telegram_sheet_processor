#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8010}"

echo "Opening TCP ${PORT} for stock-api if a supported firewall is active."

if command -v ufw >/dev/null 2>&1; then
  echo "Detected ufw."
  sudo ufw allow "${PORT}/tcp"
  sudo ufw status
  exit 0
fi

if command -v firewall-cmd >/dev/null 2>&1; then
  echo "Detected firewalld."
  sudo firewall-cmd --add-port="${PORT}/tcp" --permanent
  sudo firewall-cmd --reload
  sudo firewall-cmd --list-ports
  exit 0
fi

echo "No ufw or firewalld detected."
echo "If LAN access to ${PORT} still fails, check host firewall or NAS security settings manually."

