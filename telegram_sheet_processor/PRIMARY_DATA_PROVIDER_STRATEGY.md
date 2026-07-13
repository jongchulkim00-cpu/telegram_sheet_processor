# 1차 데이터 공급자 전략

작성 기준일: 2026-07-12

## 결론

현재 문제의 본질은 검증 로직 부족만이 아니라, AI가 보고서 생성 과정에서 검증되지 않은 가격/뉴스/전략 문장을 직접 만들어내는 것이다.

근본 해결 방향은 다음과 같다.

1. 가격/차트 데이터는 AI가 만들지 않는다.
2. 가격/차트 데이터는 신뢰 가능한 공급자 API에서만 가져온다.
3. 뉴스/공시/센티먼트는 원문 URL이 있는 자료만 사용한다.
4. AI는 데이터 생성자가 아니라, 공급자 API 결과를 해석하는 역할만 맡긴다.

Perplexity 같은 실시간 검색형 LLM은 보조 참고 채널로만 사용한다. 가격의 1차 원장은 KIS/KRX 계열 API여야 한다.

## 데이터 종류별 권장 공급자

### 1. 현재가/실시간 시세

우선순위:

1. 한국투자증권 KIS Open API
2. 다른 증권사 API
3. KRX/pykrx/FinanceDataReader는 실시간이 아니라 일봉/검증 보조로 사용

이유:

- KIS Open API는 REST와 WebSocket 방식을 제공한다.
- REST는 현재가 조회, 일봉/분봉 조회에 적합하다.
- WebSocket은 실시간 체결/호가 수신에 적합하다.
- 단, App Key, App Secret, HTS ID, 계좌 정보가 필요하다.

운영 원칙:

- 실시간 분석 문구를 쓰려면 KIS 현재가를 기준값으로 사용한다.
- KIS 연결 전에는 `현재 시세` 대신 `최근 거래일 종가`라고 표기한다.
- KIS가 실패하면 추천을 중단하고 `PRICE_SOURCE_UNAVAILABLE`로 반환한다.

참고:

- https://apiportal.koreainvestment.com/
- https://github.com/koreainvestment/open-trading-api

### 2. 공식 일봉/종가/시장 데이터

우선순위:

1. KRX 정보데이터시스템
2. pykrx
3. FinanceDataReader fallback

역할:

- 장마감 후 기준 가격
- OHLCV 일봉
- 코스피/코스닥 종목 목록
- 시장 구분

운영 원칙:

- 장중에는 `종가`와 `현재가`를 구분한다.
- 주말/휴일에는 최신 거래일 `data_as_of`를 명시한다.
- 일봉 분석은 `data_as_of` 기준으로만 작성한다.

참고:

- https://data.krx.co.kr/
- https://github.com/sharebook-kr/pykrx
- https://github.com/FinanceData/FinanceDataReader

### 3. 공시

우선순위:

1. OpenDART
2. KIND

역할:

- 사업보고서/분기보고서/반기보고서
- 주요사항보고서
- 지분공시
- 증권신고서
- 상장법인 공시 원문

운영 원칙:

- `최근 공시에 따르면`이라는 문장은 OpenDART 또는 KIND 원문 링크가 있을 때만 사용한다.
- 출처 URL 없이 `수주 잔고 사상 최대`, `고객사 다변화`, `삼성 협력 강화` 같은 문장을 생성하지 않는다.
- 공시가 없으면 `공시 기반 근거 없음`으로 표시한다.

참고:

- https://opendart.fss.or.kr/intro/main.do
- https://kind.krx.co.kr/

### 4. 뉴스/미디어 센티먼트

우선순위:

1. 유료 뉴스 API 또는 공식 제휴 뉴스 API
2. 네이버 뉴스 검색 API
3. RSS/검색 기반 크롤러

운영 원칙:

- 뉴스 점수는 기사 제목, 발행일, 언론사, URL이 저장된 경우에만 계산한다.
- 최근성 기준은 기본 7일, 사용자가 요청하면 30일로 확장한다.
- URL 없는 센티먼트 점수는 저장하지 않는다.
- 뉴스 원문과 공시 원문을 섞지 않는다.

## 추천 아키텍처

### KIS 연결 전

기존 포트 `8010` 유지.

```text
Telegram/n8n
  -> /analyze 또는 /theme/*
  -> pykrx/KRX 일봉 + FinanceDataReader 보조
  -> OpenDART/KIND 공시
  -> 뉴스 API/RSS
  -> 보고서 생성
  -> /validate-report 최종 차단
```

이 단계에서는 `현재 시세`라는 표현을 쓰지 않고 `최근 거래일 종가`만 사용한다.

### KIS 연결 후

기존 포트 `8010` 유지.

```text
Telegram/n8n
  -> /quote/{ticker}       # KIS 현재가
  -> /ohlcv/{ticker}       # KRX/pykrx 일봉
  -> /disclosures/{ticker} # OpenDART/KIND
  -> /news/{ticker}        # URL 있는 뉴스
  -> /analyze-verified     # 위 데이터만 조합
```

이 단계에서만 `현재 시세`라는 표현을 허용한다.

## 시스템 규칙

AI 에이전트는 아래 필드를 직접 생성하면 안 된다.

- 현재가
- RSI
- SMA20/SMA60
- MACD
- 거래량
- 목표가
- 손절가
- 뉴스 센티먼트 점수
- 공시 기반 촉매제

AI가 할 수 있는 일:

- API가 반환한 수치를 설명한다.
- API가 반환한 공시/뉴스 URL을 요약한다.
- 데이터가 없으면 추천하지 않는다.

## 구현 우선순위

### 1단계: 표현 교정

- KIS 연결 전에는 `현재 시세` 금지
- `최근 거래일 종가(data_as_of)`만 허용
- `/validate-report`에서 `현재 시세` 표현이 KIS 현재가 없이 등장하면 차단

### 2단계: OpenDART 공시 연동

필요 정보:

- OpenDART API Key

추가 기능:

- `/disclosures/{ticker}`
- 최근 공시 목록
- 공시 제목/일자/URL 저장

### 3단계: KIS 현재가 연동

필요 정보:

- KIS App Key
- KIS App Secret
- HTS ID
- 실전/모의투자 구분
- 조회 전용 여부 확인

추가 기능:

- `/quote/{ticker}`
- `/intraday/{ticker}`
- 장중 현재가 기준 분석

### 4단계: 뉴스 소스 연동

필요 정보:

- 사용할 뉴스 API
- 무료/유료 여부
- 검색 대상 언론/기간

추가 기능:

- `/news/{ticker}`
- 기사 URL 기반 센티먼트
- 출처 없는 문장 차단

## 최종 운영 원칙

가장 중요한 규칙:

```text
데이터가 없는 보고서는 만들지 않는다.
출처 없는 가격은 쓰지 않는다.
출처 없는 뉴스는 점수화하지 않는다.
KIS 연결 전에는 현재가라는 말을 쓰지 않는다.
```
