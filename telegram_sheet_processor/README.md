# Korean Stock Precision Connector

국내 개별 종목의 차트/지표 데이터 연동 실패를 줄이기 위한 경량 데이터 커넥터입니다.

1차 데이터 공급자 전략은 `PRIMARY_DATA_PROVIDER_STRATEGY.md`를 기준으로 합니다.

## 해결 방식
- `FinanceDataReader`로 국내 종목 일봉 OHLCV를 수집합니다.
- `pykrx`로 KRX 계열 데이터를 보조 조회해 기준일과 종가를 비교 검증합니다.
- 수집 데이터는 `data/cache/`에 CSV로 저장해 API 실패 시 캐시로 대체합니다.
- 데이터 신선도 기준은 최신 거래일 기준 2일 이내입니다.
- 두 데이터 소스의 최신 날짜가 1일 초과로 다르거나 종가 차이가 0.5%를 넘으면 추천을 차단합니다.
- SMA20/SMA60, EMA12/EMA26, RSI14, MACD, ATR14, 거래량 평균을 계산합니다.
- Plotly HTML 차트를 `outputs/charts/`에 생성합니다.
- 데이터 품질 경고와 전략 점수를 `outputs/precision_results.json`, `outputs/reports/precision_report.md`로 저장합니다.

## 실행
```powershell
pip install -r requirements.txt
python scripts/market_data.py --watchlist data/watchlist.json --days 260 --force
```

## n8n / MCP HTTP API
기존 CLI 분석 엔진은 유지하면서, n8n의 HTTP Request 노드가 호출할 수 있는 API 서버를 추가했습니다.

스크린샷처럼 아래 오류가 나면 API 파라미터 문제가 아니라 Telegram/n8n 웹훅 주소 문제입니다.
```text
bad webhook: Failed to resolve host
```

해결 기준:
- Telegram이 접근해야 하는 Webhook URL에는 `localhost`, 내부 Docker 서비스명, 사설 IP만 쓰면 안 됩니다.
- 홈서버는 공인 도메인, Cloudflare Tunnel, ngrok, reverse proxy 중 하나로 외부에서 해석 가능한 HTTPS URL을 설정해야 합니다.
- 단, 이 주식 API 자체는 기존 `8010` 포트를 그대로 사용합니다.

로컬 실행:
```powershell
python scripts/api_server.py
```

PowerShell 실행 스크립트:
```powershell
Copy-Item .env.example .env
.\start_stock_api.ps1
```

상태 점검:
```powershell
.\check_stock_api.ps1
```

Docker 실행:
```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose logs -f stock-api
```

Linux 홈서버 Docker 실행:
```bash
cd telegram_sheet_processor
cp .env.example .env
./start_stock_api.sh
```

외부 HTTPS 공개가 필요하면 Cloudflare Tunnel을 권장합니다.
```powershell
# Cloudflare Zero Trust에서 tunnel token을 만든 뒤 .env에 입력
# CLOUDFLARED_TOKEN=...
docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml up -d --build
```

Linux 홈서버에서 Cloudflare Tunnel 실행:
```bash
cd telegram_sheet_processor
cp .env.example .env
nano .env
# CLOUDFLARED_TOKEN=... 입력
chmod +x start_stock_api.sh start_stock_api_cloudflare.sh check_stock_api.sh
./start_stock_api_cloudflare.sh
```

상세 절차는 `CLOUDFLARE_LINUX_DOCKER_SETUP.md`를 참고하세요.

Cloudflare Tunnel Public Hostname 설정:
- Public hostname: 사용하려는 도메인. 예: `stock-api.example.com`
- Service type: `HTTP`
- Service URL: `http://stock-api:8010`
- n8n 외부 호출 URL 예: `https://stock-api.example.com/health`

공유기에서 `8010`을 직접 인터넷에 여는 방식은 권장하지 않습니다. 외부 공개는 Cloudflare Tunnel, ngrok, reverse proxy 중 하나를 사용하세요.

DuckDNS를 이미 사용 중이면 `jongchul-server.duckdns.org`도 가능합니다. 단, DuckDNS는 DNS만 제공하므로 HTTPS 인증서는 별도로 처리해야 합니다.

중요: Cloudflare Tunnel의 Public Hostname은 보통 Cloudflare가 관리하는 도메인을 사용해야 가장 단순합니다. `jongchul-server.duckdns.org`는 DuckDNS가 관리하는 도메인이라 Cloudflare Tunnel Public Hostname으로 바로 쓰기 어려울 수 있습니다. 이 경우:
- Cloudflare에 등록한 별도 도메인을 사용하거나
- DuckDNS + Caddy + 공유기 80/443 포트포워딩을 사용하거나
- 테스트용으로 ngrok을 사용합니다.

DuckDNS + Caddy 예시:
```powershell
Copy-Item Caddyfile.duckdns.example Caddyfile
notepad Caddyfile
docker compose -f docker-compose.yml -f docker-compose.duckdns-caddy.yml up -d --build
```

`Caddyfile` 예:
```text
{
    email your-email@example.com
}

jongchul-server.duckdns.org {
    reverse_proxy stock-api:8010
}
```

공유기/방화벽에서 필요한 포트:
- 외부 `80` -> 홈서버 `80`
- 외부 `443` -> 홈서버 `443`
- 내부 n8n만 쓸 때는 `8010`만 내부망에서 열면 됩니다.

외부에서 사용할 URL 예:
```text
https://asset.jongchul-server.duckdns.org/health
https://asset.jongchul-server.duckdns.org/validate-report
```

주의:
- DuckDNS 도메인이 현재 집 공인 IP를 정확히 가리켜야 합니다.
- 통신사/공유기에서 80/443 인바운드를 막으면 Caddy 인증서 발급이 실패할 수 있습니다.
- 이 경우 Cloudflare Tunnel 또는 ngrok이 더 쉽습니다.

기본 주소:
```text
http://localhost:8010
```

홈서버/LAN에서 n8n이 호출할 주소 예:
```text
http://192.168.1.12:8010
```

운영 원칙:
- 새 포트를 추가하지 않습니다.
- 기존 분석 API는 `8010`만 사용합니다.
- 데이터는 최신 거래일 기준 2일 이내일 때만 정상 신선도로 취급합니다.
- 2일을 초과하면 `decision`은 `DATA_STALE`, `tradable`은 `false`가 되며 추천 문장을 만들면 안 됩니다.
- 2일을 초과한 캐시는 기본적으로 사용하지 않습니다. 외부 공급자 조회가 실패해도 과거 캐시를 조용히 쓰지 않고 오류로 막습니다.
- 보조 데이터 소스와 가격/날짜가 맞지 않으면 `decision`은 `DATA_MISMATCH`, `tradable`은 `false`가 되며 추천 문장을 만들면 안 됩니다.
- AI 보고서에 표시된 현재가가 검증 종가와 0.5% 넘게 다르면 `CLAIM_MISMATCH`로 보고서 발송을 막아야 합니다.
- 보고서 날짜는 `analysis_date`, 실제 지표/차트 기준일은 `data_as_of`를 사용합니다.
- 주말/휴일에는 `analysis_date`와 `data_as_of`가 다를 수 있습니다. 예: 2026-07-12 일요일 분석이면 최신 거래일은 보통 2026-07-10입니다.
- KIS 같은 실시간 현재가 API가 연결되기 전에는 `현재 시세`라는 표현을 쓰지 않고 `최근 거래일 종가`라고 표기합니다.
- Perplexity 같은 실시간 검색형 LLM은 참고 채널일 수 있지만 가격 원장으로 사용하지 않습니다. 가격 원장은 KIS/KRX 계열 API만 사용합니다.
- KIS 자격증명이 없을 때 현재가 확인이 필요하면 네이버 금융 공개 현재가를 보조로 사용합니다. 단, 이 값은 브로커급 실시간이 아니라 공개 지연/현재 웹 시세로 표기합니다.

사용자가 준비해야 하는 것:
- 홈서버 내부 IP 확인. 예: `192.168.1.12`
- Windows 방화벽 또는 Docker 호스트에서 `8010` 접근 허용
- n8n HTTP Request 노드의 URL을 `http://홈서버IP:8010/...` 형식으로 설정
- 외부 Telegram/Webhook 연결은 공인 HTTPS 주소 준비. 예: Cloudflare Tunnel/ngrok/reverse proxy
- 키움증권을 쓸 경우 Docker 내부 직접 실행이 아니라 Windows Kiwoom Bridge를 별도로 띄우고 `.env`의 `KIWOOM_BRIDGE_URL`에 입력
- Linux Docker 홈서버 + PC 상시 운영 불가 조건에서는 키움 실시간 연동은 보류하고 `KIWOOM_ENABLED=false`로 둡니다.
- 실시간 KIS 현재가를 쓸 경우 `.env`에 `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO` 입력

Windows 방화벽 `8010` 허용:
```powershell
# 관리자 PowerShell에서 실행
.\open_firewall_8010_admin.ps1
```

PowerShell 실행 정책 때문에 `.ps1` 실행이 막히면:
```powershell
powershell -ExecutionPolicy Bypass -File .\open_firewall_8010_admin.ps1
```

상태 확인:
```powershell
curl http://localhost:8010/health
```

데이터 공급자 상태 확인:
```powershell
curl http://localhost:8010/source-status
```

`realtime_source.configured=false`이면 보고서에서 `현재 시세`, `실시간 데이터`, `현재가` 표현을 사용하지 않습니다.

공개 현재가 텔레그램 전송:
```powershell
curl -X POST http://localhost:8010/quote `
  -H "Content-Type: application/json" `
  -d "{\"symbol\":\"399720\",\"force\":true}"
```

n8n 연결 순서:
1. HTTP Request 노드: `POST https://asset.jongchul-server.duckdns.org/quote`
2. JSON Body:
```json
{
  "symbol": "399720",
  "force": true
}
```
3. Code 노드에 `scripts/n8n_code_quote_message.js` 내용을 넣습니다.
4. Telegram 노드 Text에는 `={{ $json.text }}`를 넣습니다.

현재 KIS 자격증명이 없으면 이 메시지는 `실시간 현재가`가 아니라 `공개 현재가`로 표시됩니다. KIS가 설정되어 `broker_realtime_enabled=true`가 되면 실시간 표현을 사용할 수 있습니다.

캐시 상태 확인:
```powershell
curl "http://localhost:8010/cache-audit?tickers=039030,011790"
```

캐시 정책:
- `stale=true`인 캐시는 기본 사용 금지
- `ALLOW_STALE_CACHE=false`가 기본값
- 진단 목적일 때만 환경변수 `ALLOW_STALE_CACHE=true`로 실행
- 운영 보고서에서는 stale cache를 사용하지 않습니다.

가격 공급자 우선순위:
1. KIS Open API: 실시간 현재가, 자격증명 필요
2. 네이버 금융 공개 현재가: 자격증명 없는 공개 현재가 보조 채널
3. pykrx: KRX 기반 최근 거래일 종가/일봉
4. FinanceDataReader: fallback

LLM/검색형 답변은 가격 원장으로 쓰지 않습니다.

단일 종목 분석:
```powershell
curl -X POST http://localhost:8010/analyze `
  -H "Content-Type: application/json" `
  -d "{\"ticker\":\"196170\",\"name\":\"알테오젠\",\"target_price\":380000,\"stop_loss\":290000,\"days\":260}"
```

n8n HTTP Request 노드 설정 예:
- Method: `POST`
- URL: `http://192.168.1.12:8010/analyze`
- Body Content Type: `JSON`
- Body:
```json
{
  "ticker": "196170",
  "name": "알테오젠",
  "target_price": 380000,
  "stop_loss": 290000,
  "days": 260,
  "force": false
}
```

응답은 항상 JSON입니다. 실패해도 워크플로우가 중간에서 죽지 않도록 `ok: false`와 `error`를 반환합니다.

미국 Hot 기술주 재조회:
```powershell
curl -X POST http://localhost:8010/hot-tech `
  -H "Content-Type: application/json" `
  -d "{\"days\":260,\"force\":false}"
```

n8n에서 아래와 같은 메시지가 나올 상황:
```text
데이터 공급자 측 지연으로 NVDA, TSLA, AAPL, MSFT, AMD를 재조회하겠습니다.
```

이 경우 AI가 추측 문장을 만들지 말고 HTTP Request 노드가 아래 엔드포인트를 호출하도록 라우팅하세요.
```text
POST http://192.168.1.12:8010/hot-tech
```

Body:
```json
{
  "days": 260,
  "force": false
}
```

`error_count`가 0보다 크면 해당 종목은 추천에서 제외하고, `errors` 내용을 텔레그램에 그대로 알려야 합니다.

국내 온디바이스 AI 테마 재조회:
```powershell
curl -X POST http://localhost:8010/theme/on-device-ai `
  -H "Content-Type: application/json" `
  -d "{\"days\":260,\"force\":false}"
```

포함 종목:
- 가온칩스 `399720`
- 제주반도체 `080220`
- 오픈엣지테크놀로지 `394280`
- 칩스앤미디어 `094360`
- 퀄리타스반도체 `432720`

주의: `432320`은 퀄리타스반도체가 아니라 `KB스타리츠`입니다. 온디바이스 AI 테마 분석에서는 `432720`만 사용하세요.

응답 필드 해석:
- `generated_at`: API 응답 생성 시각입니다. 지표 기준일이 아닙니다.
- `analysis_date`: 분석을 요청한 날짜입니다.
- `data_as_of`: OHLCV/RSI/SMA/MACD가 계산된 최신 캔들 날짜입니다.
- `data_age_days`: `analysis_date - data_as_of`입니다.
- `freshness_status`: `fresh`, `stale`, `empty` 중 하나입니다.
- `tradable`: `false`이면 추천/매수/목표가 문장을 만들면 안 됩니다.
- `validation`: FinanceDataReader와 pykrx의 기준일/종가 비교 결과입니다.
- `validation.status`: `matched`이면 두 소스가 허용 범위 안에서 일치합니다.

검증 기준:
- 최신 캔들 날짜 차이 허용치: 1일
- 종가 차이 허용치: 0.5%
- 초과 시 `DATA_MISMATCH`

AI 보고서 현재가 검증:
```powershell
curl -X POST http://localhost:8010/verify-prices `
  -H "Content-Type: application/json" `
  -d "{\"claims\":[{\"ticker\":\"000660\",\"name\":\"SK하이닉스\",\"claimed_price\":2180000},{\"ticker\":\"196170\",\"name\":\"알테오젠\",\"claimed_price\":315000}],\"days\":260,\"force\":false}"
```

사용 규칙:
- AI가 만든 표/보고서를 텔레그램으로 보내기 전에 `/verify-prices`를 먼저 호출합니다.
- `claim_status`가 `matched`인 행만 그대로 사용할 수 있습니다.
- `CLAIM_MISMATCH`가 하나라도 있으면 해당 종목의 현재가/RSI/점수/전략 문장을 API 결과 기준으로 다시 작성해야 합니다.
- `generated_at`은 응답 생성 시각이고, 주가 기준일은 항상 `data_as_of`입니다.
- 보고서에 현재가가 없더라도 `buy_low`, `buy_high`, `target_price`, `stop_loss`가 있으면 반드시 함께 검증합니다.
- 검증 종가보다 낮은 목표가, 검증 종가와 3% 넘게 떨어진 "현 구간" 매수 범위는 `strategy_mismatch`로 차단합니다.

가온칩스처럼 현재가 없이 전략 가격만 있는 보고서 검증 예:
```json
{
  "claims": [
    {
      "ticker": "399720",
      "name": "가온칩스",
      "buy_low": 31000,
      "buy_high": 32500,
      "target_price": 40000,
      "stop_loss": 28000
    }
  ],
  "days": 260,
  "force": false
}
```

AI 보고서 최종 발송 검증:
```powershell
curl -X POST http://localhost:8010/validate-report `
  -H "Content-Type: application/json" `
  -d "{\"report_text\":\"가온칩스(399720) 현재 시세 32,500원, 매수 구간 31,500원 ~ 32,500원, 목표가 42,000원, 손절가 27,500원\",\"days\":260,\"force\":false}"
```

`/validate-report`는 긴 보고서 본문에서 아래 항목을 자동 추출합니다.
- 6자리 종목코드
- 현재가/현재 시세
- 매수 구간
- 목표가
- 손절가
- 뉴스/공시/센티먼트 주장의 출처 URL 존재 여부

발송 규칙:
- `publishable=false`이면 텔레그램 발송 금지
- `report_guard_status=blocked`이면 `blocking_reasons`를 기준으로 보고서 재작성
- 뉴스/공시/센티먼트 주장이 있는데 URL이 없으면 문맥 점수는 검증 실패로 취급

n8n HTTP Request 노드 설정:
- Method: `POST`
- 외부 URL: `https://asset.jongchul-server.duckdns.org/validate-report`
- 내부 예비 URL: `http://192.168.1.12:8010/validate-report`
- Body Content Type: `JSON`
- JSON Body:
```json
{
  "report_text": "={{ $json.output || $json.text || $json.message }}",
  "days": 260,
  "force": false
}
```

AI Agent 출력 필드가 일정하지 않으면 HTTP Request 앞에 Code 노드를 하나 두고 `scripts/n8n_code_validate_report_body.js` 내용을 사용하세요.

서버는 n8n 편의를 위해 아래 필드도 자동으로 보고서 본문으로 인식합니다.
- `report_text`
- `output`
- `text`
- `message`
- `result`
- `data.output`
- `json.output`

### n8n 가격 검증 게이트 권장 연결

텔레그램으로 보내기 전에는 아래 순서로 연결하세요.

1. `AI Agent (Router)`가 보고서 초안을 생성합니다.
2. `Code in JavaScript` 노드에 `scripts/n8n_code_validate_report_body.js` 내용을 넣어 `/validate-report` 요청 본문을 만듭니다.
3. `HTTP Request` 노드가 `POST https://asset.jongchul-server.duckdns.org/validate-report`를 호출합니다.
4. 다음 `Code in JavaScript` 노드에 `scripts/n8n_code_price_guard.js` 내용을 넣습니다.
5. `IF` 노드에서 `={{ $json.can_publish }}`가 `true`일 때만 Telegram 전송/Postgres 저장으로 보냅니다.
6. `false`이면 `={{ $json.guard_message }}`를 텔레그램으로 보내거나 AI Agent에 재작성 요청으로 되돌립니다.

검증 실패 예:
```text
가격/기준일 검증 실패: 전송을 차단했습니다.
- 399720 / claimed 32,500 / verified 48,800 / as_of 2026-07-13 / diff 33.40%
```

이 흐름을 쓰면 과거 가격, stale cache, 소스 간 가격 불일치가 있는 보고서는 발송되지 않습니다.

외부 주소 점검:
```powershell
.\check_stock_api.ps1 -BaseUrl "https://asset.jongchul-server.duckdns.org"
```

Linux 홈서버에서는:
```bash
./check_stock_api.sh https://asset.jongchul-server.duckdns.org
```

`502 Bad Gateway`가 나오면 NPM은 살아 있지만 뒤쪽 stock-api가 연결되지 않는 상태입니다.
이 경우 `NPM_DUCKDNS_502_FIX.md`를 보고 홈서버에서 아래를 실행하세요.

```bash
cd telegram_sheet_processor
chmod +x diagnose_stock_api_502.sh
./diagnose_stock_api_502.sh https://asset.jongchul-server.duckdns.org
```

재빌드까지 한 번에 하려면:

```bash
cd telegram_sheet_processor
chmod +x repair_stock_api_502.sh
./repair_stock_api_502.sh https://asset.jongchul-server.duckdns.org
```

현재처럼 `https://asset.jongchul-server.duckdns.org/health`가 502이고 `http://192.168.1.12:8010/health`가 연결 실패면 `HOME_SERVER_DEPLOY_CHECKLIST.md` 순서대로 stock-api 컨테이너부터 실행하세요.

현재 PC에서 홈서버 SSH/TCP 접근이 막혀 있으면 `PORTAINER_DEPLOY.md`를 보고 Portainer 또는 홈서버 콘솔에서 직접 배포하세요.

## n8n Postgres 저장 오류 해결
`Insert rows in a table` 노드에서 아래 오류가 나면:
```text
value too long for type character varying(10)
```

원인은 긴 AI 답변이나 긴 JSON이 `varchar(10)` 컬럼으로 들어갔기 때문입니다.

해결 순서:
1. HTTP Request 노드 다음 `Code in JavaScript` 노드에 `scripts/n8n_code_postgres_rows.js` 내용을 넣습니다.
2. Postgres Insert 노드는 Code 노드 출력의 필드만 저장합니다.
3. 테이블은 `scripts/postgres_stock_analysis_schema.sql` 기준으로 만들거나, 기존 긴 텍스트 컬럼을 `TEXT`로 변경합니다.

API 응답에는 DB 저장 전용 필드가 포함됩니다.
- 단일 분석: `result.db_row`
- 배치/Hot 분석: `db_rows`

`db_rows`는 `symbol`, `decision`처럼 짧아야 하는 필드를 미리 잘라서 Postgres `varchar(10)` 오류를 방지합니다.

## 산출물
- `outputs/precision_results.json`
- `outputs/reports/precision_report.md`
- `outputs/charts/*_chart.html`
- `data/cache/*_ohlcv.csv`

## 남은 실시간 문제
실시간 호가/분봉까지 정밀하게 받으려면 증권사 API가 필요합니다.
다음 중 하나를 연결하면 됩니다.
- 한국투자증권 KIS OpenAPI
- 키움 OpenAPI+
- 대신 CYBOS

필요 정보:
- 사용할 증권사 API
- 실시간/분봉/일봉 중 필요한 주기
- 자동 매매 여부가 아니라 조회 전용인지 여부
