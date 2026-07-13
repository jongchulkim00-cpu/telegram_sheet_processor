# n8n Stock Workflow Audit And Node Plan

점검일: 2026-07-13

## 현재 워크플로우 상태

- 워크플로우명: `My workflow`
- 활성 상태: 비활성
- n8n 컨테이너: 정상 실행
- n8n REST API: 인증 필요로 직접 조회 불가
- 내부 DB 읽기 전용 점검: 완료
- stock API: `https://asset.jongchul-server.duckdns.org` 정상

## 발견된 핵심 문제

1. `AI Agent (Router)`가 최종 답변을 만든 뒤 바로 `Code in JavaScript`와 Telegram/Postgres로 이동한다.
2. stock API `8010`의 `/quote`, `/analyze`, `/validate-report`가 워크플로우 본선에 직접 연결되어 있지 않다.
3. 기존 `mcp-stock-analyze`는 `http://192.168.1.12:8085/analyze`를 사용한다. 이 경로는 현재 만든 가격/날짜 검증 게이트를 우회할 수 있다.
4. 기존 Code 노드는 `<json>...</json>`만 파싱하고, 가격/기준일 검증 결과를 확인하지 않는다.
5. `Insert rows in a table`은 `trading_log`에 최소 필드만 저장한다. `data_as_of`, `freshness_status`, `validation_status`, `verified_price`가 빠져 있어 사후 추적성이 약하다.
6. `mcp_media_transcriber` 노드에 Groq API 키가 평문으로 저장되어 있다. 반드시 n8n Credential 또는 환경변수로 옮기고 기존 키는 회전해야 한다.
7. 일부 도구 설명에 `2026-07-12` 같은 고정 날짜가 남아 있어 AI가 과거 날짜를 답변에 재사용할 위험이 있다.

## 목표 구조

정보 취합은 아래처럼 역할을 분리한다.

```text
Telegram Trigger
  -> AI Agent Router
      -> stock-source-status     GET  /source-status
      -> stock-quote-current     POST /quote
      -> stock-analyze-verified  POST /analyze
      -> mcp-news-crawler        POST /news
      -> mcp-macro-economics     POST /macro
      -> mcp-media-transcriber   POST /transcribe
  -> Build Validate Report Body
  -> Validate Report            POST /validate-report
  -> Price Guard Code
  -> IF can_publish
       true  -> Prepare DB Rows -> Insert Postgres -> Send Telegram
       false -> Send Guard Message Telegram
```

## GET 노드 역할

### 1. stock-source-status

- Method: `GET`
- URL: `https://asset.jongchul-server.duckdns.org/source-status`
- 역할:
  - KIS 실시간 API 설정 여부 확인
  - Kiwoom 브릿지 설정 여부 확인
  - `실시간 현재가` 표현 사용 가능 여부 판단
- 사용 규칙:
  - `realtime_source.configured=false`이면 "실시간 현재가" 금지
  - `public_quote.configured=true`이면 "공개 현재가" 표현 사용

### 2. stock-health

- Method: `GET`
- URL: `https://asset.jongchul-server.duckdns.org/health`
- 역할:
  - API 생존 확인
  - `analysis_date` 확인
- 사용 규칙:
  - 워크플로우 시작 시 한 번 호출
  - 실패 시 분석 중단

### 3. stock-cache-audit

- Method: `GET`
- URL 예:

```text
https://asset.jongchul-server.duckdns.org/cache-audit?tickers=399720,011790,039030
```

- 역할:
  - stale cache 확인
  - 최근 조회 종목의 캐시 기준일 확인
- 사용 규칙:
  - `stale_count > 0`이면 해당 종목 추천 금지

## POST 노드 역할

### 1. stock-quote-current

- Method: `POST`
- URL: `https://asset.jongchul-server.duckdns.org/quote`
- Body:

```json
{
  "symbol": "={{ $json.symbol || $json.ticker }}",
  "force": true
}
```

- 역할:
  - 단일 종목 공개 현재가 조회
  - Telegram 단문 가격 응답 생성
- 출력 핵심:
  - `quote.quote_price`
  - `quote.analysis_date`
  - `quote.data_as_of`
  - `quote.quote_label`
  - `quote.broker_realtime_enabled`
  - `quote.message`

### 2. stock-analyze-verified

- Method: `POST`
- URL: `https://asset.jongchul-server.duckdns.org/analyze`
- Body:

```json
{
  "symbol": "={{ $json.symbol || $json.ticker }}",
  "force": true,
  "days": 260
}
```

- 역할:
  - OHLCV, RSI, SMA, MACD, score 계산
  - pykrx와 FinanceDataReader 교차 검증
- 출력 핵심:
  - `result.latest_close`
  - `result.analysis_date`
  - `result.data_as_of`
  - `result.freshness_status`
  - `result.validation.status`
  - `result.db_row`

### 3. stock-validate-report

- Method: `POST`
- URL: `https://asset.jongchul-server.duckdns.org/validate-report`
- Body:

```json
{
  "report_text": "={{ $json.output || $json.text || $json.message || $json.telegram_message }}",
  "force": true
}
```

- 역할:
  - 최종 보고서의 날짜, 현재가, 매수구간, 목표가, 손절가 검증
  - 전송 가능 여부 결정
- 사용 규칙:
  - `publishable=true`일 때만 Telegram/Postgres 진행
  - `publishable=false`이면 `blocking_reasons`를 사용자에게 전송

### 4. mcp-news-crawler

- Method: `POST`
- URL: `http://192.168.1.12:8085/news`
- 역할:
  - 뉴스/공시/센티먼트 보조 분석
- 사용 규칙:
  - 가격 원장으로 사용 금지
  - 뉴스 주장에는 URL 또는 근거를 포함

### 5. mcp-macro-economics

- Method: `POST`
- URL: `http://192.168.1.12:8085/macro`
- 역할:
  - 거시경제 컨텍스트 보조 분석
- 사용 규칙:
  - 가격/RSI/MACD 값을 만들면 안 됨

### 6. mcp-media-transcriber

- Method: `POST`
- URL: `http://192.168.1.12:8099/transcribe`
- 역할:
  - 영상/오디오에서 투자 관련 문장 추출
- 수정 필요:
  - Groq API 키를 노드 본문에 직접 저장하지 말 것
  - n8n Credential 또는 환경변수 사용
  - 기존 노출 키는 회전 권장

## Code 노드 역할

### 1. Build Validate Report Body

파일: `scripts/n8n_code_validate_report_body.js`

- AI Agent 출력에서 보고서 본문을 추출
- `/validate-report` 요청 본문 생성

### 2. Price Guard

파일: `scripts/n8n_code_price_guard.js`

- `/validate-report` 또는 `/verify-prices` 결과를 확인
- `can_publish` 생성
- 실패 시 `guard_message` 생성

### 3. Quote Message

파일: `scripts/n8n_code_quote_message.js`

- `/quote` 결과를 Telegram 텍스트로 변환

### 4. Postgres Rows

파일: `scripts/n8n_code_postgres_rows.js`

- `/analyze`, `/analyze-batch`, `/theme/*` 결과를 DB 저장용 row로 변환
- 긴 텍스트가 `varchar(10)`에 들어가지 않게 방지

## Postgres 저장 권장 테이블

기존 `trading_log`는 최소 필드만 저장한다. 장기 운영에는 `stock_analysis_results` 테이블을 권장한다.

스키마 파일:

```text
scripts/postgres_stock_analysis_schema.sql
```

저장 권장 필드:

- `symbol`
- `decision`
- `score`
- `technical_score`
- `analysis_date`
- `data_as_of`
- `data_age_days`
- `freshness_status`
- `validation_status`
- `latest_close`
- `provider`
- `rsi14`
- `sma20`
- `sma60`
- `macd_histogram`
- `raw_json`

## 최종 차단 조건

아래 조건 중 하나라도 해당하면 Telegram 전송 금지:

1. `/validate-report.publishable=false`
2. 보고서 `분석 기준일`이 API `analysis_date`와 다름
3. 보고서 가격과 API 검증 가격 차이 0.5% 초과
4. `freshness_status != fresh`
5. `validation.status != matched`
6. KIS 미설정 상태에서 "실시간 현재가" 표현 사용
7. API 호출 없이 AI가 가격/지표를 생성

## 우선순위 수정 제안

1. AI Agent 시스템 프롬프트에 `scripts/n8n_ai_agent_stock_guard_prompt.md` 내용 추가
2. 기존 `mcp-stock-analyze`를 `8010/analyze` 기반 `stock-analyze-verified`로 교체
3. `/validate-report`를 AI Agent 뒤 본선에 추가
4. `Price Guard` + IF 노드로 Telegram/Postgres 전송 차단
5. Groq API 키를 Credential/환경변수로 이동 후 기존 키 회전
6. `trading_log` 대신 `stock_analysis_results` 저장 구조로 확장
