# n8n HTTP GET/POST Node Configs

이 문서는 n8n에서 직접 노드를 만들 때 사용하는 설정값입니다.

## A. AI Tool 노드

AI Agent가 필요한 정보를 직접 조회할 수 있게 붙이는 노드입니다.

### 1. stock-source-status

- Node type: `HTTP Request Tool`
- Method: `GET`
- URL:

```text
https://asset.jongchul-server.duckdns.org/source-status
```

- Tool Description:

```text
KIS/Kiwoom 실시간 API 설정 상태와 공개 현재가 사용 가능 여부를 확인한다.
보고서에서 "실시간 현재가" 표현을 써도 되는지 판단할 때 반드시 먼저 호출한다.
realtime_source.configured=false이면 "공개 현재가" 또는 "최근 거래일 종가(data_as_of)" 표현만 허용한다.
```

### 2. stock-quote-current

- Node type: `HTTP Request Tool`
- Method: `POST`
- URL:

```text
https://asset.jongchul-server.duckdns.org/quote
```

- Send Body: `true`
- Body Content Type: `JSON`
- Body:

```json
{
  "symbol": "={{ $fromAI('symbol', '6자리 한국 종목코드. 예: 399720', 'string') }}",
  "force": true
}
```

- Tool Description:

```text
단일 종목의 공개 현재가를 조회한다.
가격 답변, 단문 텔레그램 응답, 보고서 작성 전 현재 가격 확인에 사용한다.
응답의 quote.analysis_date, quote.data_as_of, quote.quote_price, quote.quote_label을 반드시 사용한다.
broker_realtime_enabled=false이면 "실시간 현재가"라고 말하지 않는다.
```

### 3. stock-analyze-verified

- Node type: `HTTP Request Tool`
- Method: `POST`
- URL:

```text
https://asset.jongchul-server.duckdns.org/analyze
```

- Send Body: `true`
- Body Content Type: `JSON`
- Body:

```json
{
  "symbol": "={{ $fromAI('symbol', '6자리 한국 종목코드. 예: 399720', 'string') }}",
  "days": 260,
  "force": true
}
```

- Tool Description:

```text
한국 종목의 OHLCV, RSI, SMA, MACD, score, data_as_of, validation.status를 조회한다.
기술 분석 보고서 작성 시 가격/RSI/MACD/이동평균은 반드시 이 도구 결과만 사용한다.
validation.status가 matched가 아니거나 freshness_status가 fresh가 아니면 추천하지 않는다.
```

### 4. stock-validate-report

- Node type: `HTTP Request Tool`
- Method: `POST`
- URL:

```text
https://asset.jongchul-server.duckdns.org/validate-report
```

- Send Body: `true`
- Body Content Type: `JSON`
- Body:

```json
{
  "report_text": "={{ $fromAI('report_text', '텔레그램 전송 직전의 최종 보고서 전체 본문', 'string') }}",
  "force": true
}
```

- Tool Description:

```text
최종 보고서의 분석 기준일, 현재가, 매수 구간, 목표가, 손절가를 검증한다.
publishable=false이면 텔레그램 전송을 절대 하지 않는다.
blocking_reasons를 사용자에게 보고하고 보고서를 다시 작성한다.
```

### 5. stock-cache-audit

- Node type: `HTTP Request Tool`
- Method: `GET`
- URL:

```text
https://asset.jongchul-server.duckdns.org/cache-audit?tickers={{ $fromAI('tickers', '쉼표로 구분한 6자리 종목코드 목록. 예: 399720,011790', 'string') }}
```

- Tool Description:

```text
종목별 캐시 기준일과 stale 여부를 확인한다.
stale_count가 0보다 크면 해당 종목 추천을 중단한다.
```

## B. 본선 HTTP Request 노드

AI Agent가 도구 호출을 누락해도 강제로 검증되도록 본선에 배치하는 노드입니다.

### 1. Validate Report Body Builder

- Node type: `Code`
- 위치: `AI Agent (Router)` 다음
- 코드: `scripts/n8n_code_validate_report_body.js`

### 2. Validate Report

- Node type: `HTTP Request`
- Method: `POST`
- URL:

```text
https://asset.jongchul-server.duckdns.org/validate-report
```

- Body Content Type: `JSON`
- Body:

```json
{
  "report_text": "={{ $json.report_text }}",
  "days": 260,
  "force": true
}
```

### 3. Price Guard

- Node type: `Code`
- 위치: `Validate Report` 다음
- 코드: `scripts/n8n_code_price_guard.js`

### 4. IF Can Publish

- Node type: `IF`
- 조건:

```text
Value 1: ={{ $json.can_publish }}
Operation: is true
```

- True branch:
  - DB row 변환
  - Postgres 저장
  - Telegram 전송

- False branch:
  - Telegram 전송 텍스트: `={{ $json.guard_message }}`

## C. Telegram 단문 현재가 조회 플로우

사용자가 "가온칩스 현재가"처럼 단순 가격을 물을 때 사용합니다.

```text
Telegram Trigger
  -> Code: symbol 추출
  -> HTTP Request: POST /quote
  -> Code: scripts/n8n_code_quote_message.js
  -> Telegram Send Message: ={{ $json.text }}
```

HTTP Request:

```text
POST https://asset.jongchul-server.duckdns.org/quote
```

Body:

```json
{
  "symbol": "={{ $json.symbol }}",
  "force": true
}
```

Telegram Text:

```text
={{ $json.text }}
```
