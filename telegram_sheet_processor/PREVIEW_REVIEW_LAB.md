# Preview / Review Lab

## 목적

Preview / Review Lab은 자동매매 조건을 바로 실전에 쓰기 전에 과거 차트로 예습/복습하는 검증 프로그램이다.

핵심 목표는 다음과 같다.

- 매수, 준비, 축소, 회피 신호가 과거 차트의 어디에서 발생했는지 확인한다.
- 각 신호 이후 10거래일 동안 실제 가격이 어떻게 움직였는지 수치화한다.
- BUY/PREPARE 신호의 양수 마감 확률, 평균 수익, 평균 최대 상승/하락을 계산한다.
- 10만원 초기 자동주문 기준에 맞지 않는 고가 종목은 review-only로 분리한다.
- 향후 Kiwoom REST 30분봉 데이터가 붙으면 실제 진입 타이밍 검증으로 확장한다.

## 현재 구축 범위

- 일봉 기반 과거 검증
- 단일 종목 리뷰
- 종목명/종목코드 검색
- 50개 이하 배치 리뷰
- HTML 차트 생성
- JSON 신호 로그 생성
- 기존 stock-api 8010 포트 안에서 동작

별도 포트는 필요하지 않다.

## 진행 체크리스트

### 완료

- [x] 기존 stock-api 8010 포트 안에 Preview/Review UI 추가
- [x] 단일 종목 일봉 리뷰 API 추가
- [x] 50개 이하 배치 리뷰 API 추가
- [x] 차트 HTML 생성
- [x] 신호 JSON 로그 생성
- [x] BUY/PREPARE/REDUCE/AVOID/HOLD/WAIT 신호 분류
- [x] 10거래일 후 확률/평균수익/최대상승/최대하락 요약
- [x] 종목명/종목코드 검색
- [x] 종목코드 또는 종목명 입력 시 나머지 자동기입
- [x] 10만원 초기 자동주문 기준 표시
- [x] UI에서 관심종목 50개 이하 배치 리뷰 실행
- [x] 리뷰 결과를 종목별로 비교하는 표 추가
- [x] 검색 결과에 현재가/10만원 자동주문 가능 여부 표시
- [x] UI에서 완료/진행/다음 작업 체크리스트 확인
- [x] 관심종목 리스트 저장/불러오기
- [x] 관심종목 섹터/테마 1차 분류
- [x] 코스피/코스닥 벤치마크 대비 상대강도 계산 API/UI

### 진행 중

- [ ] 섹터 지수/테마 대표군 상대강도 비교

### 다음 단계

- [ ] 거래대금/수급/뉴스/공시 점수 결합
- [ ] 조건별 백테스트 성과 지표 강화
- [ ] Kiwoom REST 30분봉 데이터 연결
- [ ] 30분봉 실제 진입 타이밍 검증
- [ ] 승인형 주문 1주 운영 로그
- [ ] 소액 자동주문 2주 운영 로그

## 홈서버 접속

브라우저에서 다음 주소를 연다.

```text
https://asset.jongchul-server.duckdns.org/review-ui
```

로컬 또는 내부망에서는 다음 주소를 사용할 수 있다.

```text
http://192.168.1.12:8010/review-ui
```

## API

### 단일 종목 리뷰

```http
POST /preview-review
Content-Type: application/json
```

```json
{
  "ticker": "080220",
  "name": "제주반도체",
  "days": 260,
  "force": false
}
```

응답 핵심 필드:

- `review.summary`: WAIT/HOLD/BUY/PREPARE/REDUCE/AVOID 발생 횟수
- `review.probability_10d`: 신호별 10거래일 후 확률/성과
- `review.decision_summary`: 주요 신호 요약
- `review.chart_url`: 생성된 차트 URL
- `review.signals`: 날짜별 신호 로그

### 종목 검색

```http
GET /stocks/search?q=한미&limit=20
```

검색 기준:

- 종목코드 정확 일치
- 종목명 정확 일치
- 종목코드 앞자리 일치
- 종목명 앞부분 일치
- 종목코드/종목명 포함

UI에서는 검색 결과를 선택하면 종목코드와 종목명이 자동으로 채워진다.

### 배치 리뷰

```http
POST /preview-review-batch
Content-Type: application/json
```

```json
{
  "days": 260,
  "force": false,
  "items": [
    {"ticker": "080220", "name": "제주반도체"},
    {"ticker": "399720", "name": "가온칩스"}
  ]
}
```

배치 리뷰는 관찰 종목 정책에 맞춰 최대 50개까지만 처리한다.

### 관심종목 저장/불러오기

```http
GET /review-watchlist
POST /review-watchlist
Content-Type: application/json
```

```json
{
  "items": [
    {"ticker": "080220", "name": "제주반도체"},
    {"ticker": "399720", "name": "가온칩스"}
  ]
}
```

저장 위치는 `data/review_watchlist.json`이며, 중복 종목은 자동 제거하고 최대 50개까지만 유지한다.

### 섹터/테마 분류

```http
GET /review-sectors
```

현재 관심종목을 대상으로 1차 정적 규칙 기반 분류를 수행한다.

응답 핵심 필드:

- `items`: 종목별 대표 테마, 섹터, 시장, 분류 신뢰도
- `groups`: 테마별 종목 수와 종목 목록
- `classification_source`: 현재 분류 방식

주의: 현재 분류는 자동매매 판단용 확정 데이터가 아니라 리뷰 편의용 1차 분류다. 다음 단계에서 KRX 업종, 섹터 지수 상대강도, 뉴스/공시/수급 점수를 붙여 신뢰도를 높인다.

### 시장 대비 상대강도

```http
GET /review-relative-strength?days=260
```

관심종목을 시장 벤치마크와 비교한다.

- KOSPI 종목: `KS11`
- KOSDAQ 종목: `KQ11`
- UNKNOWN: 일단 `KS11`

응답 핵심 필드:

- `relative_strength.20d`: 최근 약 20거래일 종목 수익률 - 벤치마크 수익률
- `relative_strength.60d`: 중기 상대강도
- `relative_strength.120d`: 장기 상대강도
- `label`: `strong_outperform`, `outperform`, `inline`, `underperform`, `strong_underperform`, `unavailable`

주의: 상대강도는 후보군 필터다. 자동매매 매수 신호가 아니다. 시장 대비 계속 약한 종목은 후보군에서 낮은 우선순위로 돌리고, 시장 대비 강한 종목만 차트 타이밍 검증 대상으로 유지한다.

## 신호 의미

| 신호 | 의미 |
| :--- | :--- |
| PREPARE | Stochastic 과매도권에서 %K/%D 차이가 좁혀지는 매수 준비 |
| BUY | 추세 지지 상태에서 Stochastic 상향 교차와 거래량 조건 충족 |
| REDUCE | 고거래량 반락 또는 돌파 실패 가능성 |
| AVOID | 하락 추세 또는 SMA20 하향 이탈 |
| HOLD | 추세는 유지되지만 정밀 트리거 없음 |
| WAIT | 지표 준비 부족 또는 우위 없음 |

## 중요한 제한

현재 버전은 일봉 예습/복습용이다.

따라서 다음을 금지한다.

- 일봉 리뷰 결과만으로 자동주문 실행
- 30분봉 데이터 없이 실제 진입 타이밍 확정
- 과거 검증 없이 수익 확률을 임의 생성

## 다음 확장

1. Kiwoom REST 30분봉 데이터 연결
2. 섹터/지수 상대강도 추가
3. 거래대금/수급/뉴스/공시 점수 결합
4. 조건별 백테스트 리포트 강화
5. 일간/주간 자동 업데이트
6. 승인형 주문 1주 운영
7. 소액 자동주문 2주 운영
