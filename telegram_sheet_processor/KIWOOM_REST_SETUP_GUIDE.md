# Kiwoom REST Bridge Setup Guide

This project supports a small HTTP bridge that the Linux home-server stock API
can call. The bridge starts in mock mode and can later call Kiwoom REST API
directly.

## 1. Local Bridge Modes

### Mock Mode

Use this first to verify networking.

```powershell
pip install fastapi uvicorn requests
$env:KIWOOM_BRIDGE_MODE="mock"
python .\kiwoom_rest_bridge_example.py
```

Test on the bridge machine:

```powershell
curl http://localhost:8080/health
curl http://localhost:8080/quote/399720
```

### Kiwoom REST Mode

Use environment variables. Do not put real keys in the source code.

```powershell
$env:KIWOOM_BRIDGE_MODE="rest"
$env:KIWOOM_REST_BASE_URL="https://mockapi.kiwoom.com"
$env:KIWOOM_REST_APP_KEY="your_app_key"
$env:KIWOOM_REST_APP_SECRET="your_app_secret"
python .\kiwoom_rest_bridge_example.py
```

For production, change the base URL:

```powershell
$env:KIWOOM_REST_BASE_URL="https://api.kiwoom.com"
```

The bridge uses:

- Token endpoint: `POST /oauth2/token`
- Stock basic info endpoint: `POST /api/dostk/stkinfo`
- API ID: `ka10001`
- Request body: `{"stk_cd": "005930"}`

## 2. Expose the Bridge to the Home Server

Choose one:

- LAN-only: `http://192.168.1.50:8080/quote/{ticker}`
- Reverse proxy: `https://kiwoom-bridge.example.com/quote/{ticker}`
- Tunnel: Cloudflare Tunnel or ngrok

For the first test, LAN is simplest. Make sure Windows Firewall allows inbound
TCP 8080 from the home server.

## 3. Configure the Home Server

Edit `/opt/telegram_sheet_processor/.env` on the home server:

```env
KIWOOM_ENABLED=true
KIWOOM_REST_ENABLED=true
KIWOOM_REST_QUOTE_URL=http://192.168.1.50:8080/quote/{ticker}
KIWOOM_REST_METHOD=GET
KIWOOM_REST_TIMEOUT_SECONDS=10
```

Then restart:

```bash
cd /opt/telegram_sheet_processor
docker compose up -d --build
```

## 4. Verify from the Home Server

```bash
curl http://192.168.1.50:8080/health
curl http://192.168.1.50:8080/quote/399720
curl -X POST http://localhost:8010/quote \
  -H "Content-Type: application/json" \
  -d '{"ticker":"399720","force":true}'
```

Expected `/source-status` once configured:

```json
{
  "kiwoom_rest_realtime": {
    "enabled": true,
    "configured": true,
    "quote_url_configured": true
  }
}
```

## 5. Security Notes

- Rotate keys if they were pasted into chat, screenshots, or plain text.
- Keep real keys only in `.env` or OS environment variables.
- Prefer LAN or a protected tunnel. Do not expose the bridge publicly without
  authentication or network restrictions.
