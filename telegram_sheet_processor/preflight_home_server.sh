#!/usr/bin/env bash
set -u

echo "== Host =="
hostname || true
uname -a || true

echo
echo "== Docker =="
if command -v docker >/dev/null 2>&1; then
  docker --version
else
  echo "docker is not installed or not in PATH"
fi

echo
echo "== Docker Compose =="
if docker compose version >/dev/null 2>&1; then
  docker compose version
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose --version
else
  echo "docker compose is not available"
fi

echo
echo "== Ports =="
if command -v ss >/dev/null 2>&1; then
  ss -lntp 2>/dev/null | grep -E ':(80|443|8010)\b' || true
elif command -v netstat >/dev/null 2>&1; then
  netstat -lntp 2>/dev/null | grep -E ':(80|443|8010)\b' || true
else
  echo "ss/netstat not available"
fi

echo
echo "== Project files =="
ls -la

