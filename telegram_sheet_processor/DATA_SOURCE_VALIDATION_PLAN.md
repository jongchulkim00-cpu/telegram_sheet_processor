# 데이터 소스 비교 검증 계획

분석 기준일: 2026-07-12

## 목표

현재 시스템은 `FinanceDataReader` 기반 일봉 데이터를 사용한다. 최신성 검사는 들어갔지만, 동일 종목의 가격과 기준일을 다른 데이터 소스와 대조하는 검증 계층은 아직 없다.

목표는 기존 API 포트 `8010`을 유지하면서 다음 문제를 줄이는 것이다.

- 보고서 생성일과 실제 캔들 기준일 불일치
- 종목코드 오인식
- 단일 데이터 소스 장애 또는 지연
- 과거 가격을 최신 가격처럼 사용하는 오류

## 검토한 후보

### 1. FinanceDataReader

- 현재 사용 중인 기본 소스
- 장점: 설치와 사용이 간단하고 KRX/KOSPI/KOSDAQ 리스팅, 국내/해외 종목, 지수, 환율 등을 폭넓게 지원
- 한계: 실시간 호가/체결 검증용으로 쓰기에는 부족하고, 내부적으로 외부 웹 데이터 의존도가 있다
- 역할: 기본 일봉 OHLCV 수집 소스 유지
- 참고: https://github.com/FinanceData/FinanceDataReader

### 2. pykrx

- KRX 데이터를 스크래핑하는 오픈소스 라이브러리
- 장점: 국내시장 검증 보조 소스로 적합, KRX 기반 종목/가격 대조에 유용
- 한계: 일부 인증 필요 데이터는 `KRX_ID`, `KRX_PW` 환경변수가 필요할 수 있고, 스크래핑 기반이라 사이트 변경 영향을 받을 수 있음
- 역할: FinanceDataReader 결과의 `data_as_of`, `close`, 종목명, 시장 구분 검증
- 참고: https://github.com/sharebook-kr/pykrx

### 3. 한국투자증권 KIS Open API

- 공식 증권사 API
- 장점: 실시간/준실시간 조회, REST와 WebSocket 샘플, 국내주식 시세 API, 인증/토큰 구조 제공
- 한계: 계좌, 앱키, 앱시크릿, HTS ID 등 사용자 인증 정보 필요
- 역할: 실시간 조회가 필요한 최종 단계의 신뢰 소스
- 참고: https://apiportal.koreainvestment.com/
- 샘플 코드: https://github.com/koreainvestment/open-trading-api

## 권장 구조

1. 기본 수집: FinanceDataReader
2. 보조 검증: pykrx
3. 실시간 검증: KIS Open API, 인증 정보 준비 후 선택 적용

기존 시스템을 흔들지 않기 위해 처음에는 1번과 2번만 적용한다. KIS는 별도 포트를 만들지 않고 기존 API에 Provider만 추가하는 방식으로 둔다.

## 최소 검증 규칙

### Freshness Check

- `analysis_date`: 요청/분석 날짜
- `data_as_of`: 실제 OHLCV 최신 캔들 날짜
- `data_age_days`: `analysis_date - data_as_of`
- `data_age_days > 2`이면 `DATA_STALE`, `tradable=false`

### Cross Source Check

동일 종목을 두 소스에서 조회한 뒤 다음을 비교한다.

- 종목코드 일치 여부
- 종목명 일치 여부
- 시장 구분 일치 여부
- 최신 캔들 날짜 일치 여부
- 종가 차이율

권장 기준:

- 최신 캔들 날짜 차이: 0~1 거래일 이내
- 종가 차이율: 0.5% 이내
- 기준 초과 시 `DATA_MISMATCH`, `tradable=false`

### Code Identity Check

종목명과 종목코드가 어긋나면 추천하지 않는다.

예:

- `432320`: KB스타리츠
- `432720`: 퀄리타스반도체

## 구현 제안

안전한 1차 구현:

- `requirements.txt`에 `pykrx` 추가
- `scripts/market_data.py`에 `fetch_with_pykrx()` 추가
- `compare_sources()` 함수 추가
- API 응답에 `validation` 블록 추가
- 불일치 시 `decision=DATA_MISMATCH`, `tradable=false`

추후 2차 구현:

- KIS Open API 인증 파일 또는 환경변수 방식 추가
- 실시간 현재가 검증용 Provider 추가
- 단, 실시간 조회는 계정 정보가 필요하므로 사용자 승인 후 진행

## n8n 운영 규칙

- Telegram 응답에는 `generated_at`이 아니라 `data_as_of`를 지표 기준일로 표시한다.
- `tradable=false`이면 종목 추천/목표가/손절가 문장을 만들지 않는다.
- `DATA_STALE`, `DATA_MISMATCH`, `NO_DATA`는 사용자에게 원인과 재조회 가능 여부만 알려준다.

