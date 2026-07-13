# Cloudflare Tunnel + Linux Docker Setup

목표:

```text
https://사용자도메인
  -> Cloudflare Tunnel
  -> stock-api Docker service
  -> http://stock-api:8010
```

## 1. .env 준비

```bash
cd telegram_sheet_processor
cp .env.example .env
nano .env
```

Cloudflare Tunnel token을 입력합니다.

```env
CLOUDFLARED_TOKEN=...
ALLOW_STALE_CACHE=false
KIWOOM_ENABLED=false
```

## 2. Cloudflare Zero Trust 설정

Cloudflare dashboard에서 Tunnel을 만들고 Public Hostname을 설정합니다.

권장 설정:

```text
Public hostname: stock-api.your-domain.com
Service type: HTTP
Service URL: http://stock-api:8010
```

DuckDNS를 Cloudflare Tunnel에 직접 연결하려면 Cloudflare가 해당 DNS zone을 관리해야 합니다.
DuckDNS만 사용 중이라면 Cloudflare Tunnel public hostname으로는 Cloudflare에 등록된 도메인을 쓰는 쪽이 가장 단순합니다.

도메인이 Cloudflare에 없다면 선택지는 두 가지입니다.

- Cloudflare에 관리 중인 도메인을 사용한다.
- 임시/테스트는 ngrok을 사용한다.

## 3. 실행

```bash
chmod +x start_stock_api.sh start_stock_api_cloudflare.sh check_stock_api.sh
./start_stock_api_cloudflare.sh
```

## 4. 점검

내부 점검:

```bash
./check_stock_api.sh http://127.0.0.1:8010
```

외부 점검:

```bash
curl https://stock-api.your-domain.com/health
curl https://stock-api.your-domain.com/source-status
```

## 5. n8n URL

외부 공개 URL:

```text
https://stock-api.your-domain.com/validate-report
```

내부 Docker/LAN URL:

```text
http://192.168.1.12:8010/validate-report
```

## Kiwoom Note

홈서버가 Linux Docker이고 Windows PC 상시 운영이 어렵다면 Kiwoom OpenAPI+ 실시간 연동은 현재 운영 조건에 맞지 않습니다.

현재 운영 권장값:

```env
KIWOOM_ENABLED=false
```

실시간 표현은 금지하고, 공개 현재가 또는 최근 거래일 종가 기준으로 보고서를 작성합니다.

