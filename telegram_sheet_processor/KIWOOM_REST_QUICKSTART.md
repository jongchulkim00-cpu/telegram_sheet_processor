# Kiwoom REST Quickstart

This is the short path for testing the Kiwoom bridge before enabling it in the
home-server stock API.

## 1. Start Bridge In Mock Mode

On the PC that will run the bridge:

```powershell
cd "C:\Users\jongc\OneDrive\문서\New project 2\telegram_sheet_processor"
pip install fastapi uvicorn requests
$env:KIWOOM_BRIDGE_MODE="mock"
python .\scripts\kiwoom_rest_bridge_example.py
```

Test locally:

```powershell
curl http://localhost:8080/health
curl http://localhost:8080/quote/399720
```

Expected quote source:

```text
kiwoom_bridge_mock
```

## 2. Test From Home Server

Replace the IP with the bridge PC IP.

```bash
curl http://192.168.1.50:8080/health
curl http://192.168.1.50:8080/quote/399720
```

If this fails, check:

- Windows firewall inbound TCP 8080
- PC and home server are on the same LAN
- Bridge process is still running

## 3. Enable Home Server Stock API

Edit `/opt/telegram_sheet_processor/.env`:

```env
KIWOOM_ENABLED=true
KIWOOM_REST_ENABLED=true
KIWOOM_REST_QUOTE_URL=http://192.168.1.50:8080/quote/{ticker}
KIWOOM_REST_METHOD=GET
KIWOOM_REST_TIMEOUT_SECONDS=10
```

Restart:

```bash
cd /opt/telegram_sheet_processor
docker compose up -d --build
```

Check:

```bash
curl http://localhost:8010/source-status
curl -X POST http://localhost:8010/quote \
  -H "Content-Type: application/json" \
  -d '{"ticker":"399720","force":true}'
```

## 4. Switch Bridge To Kiwoom REST Mode

Use environment variables. Do not hard-code keys in Python files.

```powershell
$env:KIWOOM_BRIDGE_MODE="rest"
$env:KIWOOM_REST_BASE_URL="https://mockapi.kiwoom.com"
$env:KIWOOM_REST_APP_KEY="your_app_key"
$env:KIWOOM_REST_APP_SECRET="your_app_secret"
python .\scripts\kiwoom_rest_bridge_example.py
```

After mock API tests pass, switch to production:

```powershell
$env:KIWOOM_REST_BASE_URL="https://api.kiwoom.com"
```

## 5. Security

- Rotate any key that was pasted into chat, screenshots, or plain text.
- Store real keys only in `.env` or OS environment variables.
- Prefer LAN-only or a protected tunnel.
