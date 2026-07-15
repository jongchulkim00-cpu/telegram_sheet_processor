# Telegram Sheet Processor

이 리포지토리는 금융 투자 분석 자동화 파이프라인 템플릿을 포함합니다.

## 구조
- `telegram_sheet_processor/`: 실제 프로젝트 워크스페이스
- `README.md`: 최상위 프로젝트 설명
- `.gitignore`: Git 무시 항목

## 기본 실행
1. `cd "telegram_sheet_processor"`
2. 필요한 패키지 설치
3. 스크립트 실행

## Preview / Review Lab
- 홈서버에서 과거 차트 기반 매수/매도/관망 신호를 검증하는 화면을 제공합니다.
- 기존 stock-api 포트 안에서 동작하므로 별도 포트가 필요하지 않습니다.
- 상세 내용은 `telegram_sheet_processor/PREVIEW_REVIEW_LAB.md`를 참고하세요.

접속 예:
```text
https://asset.jongchul-server.duckdns.org/review-ui
```

## 초기화
- `git init`
- `.gitignore` 추가
- `.git` 정보는 이 저장소 내부에 유지됩니다

## 주의
- API 키 및 시크릿은 `.env` 또는 환경 변수로 관리하세요.
