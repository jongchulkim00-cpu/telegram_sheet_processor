VERSION 관리 및 GitHub 연동 가이드

목적
- 프로젝트를 GitHub로 관리하고 안전하게 배포/자동화 하기 위한 단계별 가이드입니다.

초기 설정 (로컬)
1. 로컬에서 Git 초기화
```bash
git init
git add .
git commit -m "chore: initial commit"
```

2. GitHub 원격 저장소 생성
- 방법 A (GitHub CLI 사용 권장):
```bash
# GitHub CLI 설치 후
gh repo create <OWNER>/<REPO> --public --source=. --remote=origin
# 또는
gh repo create <REPO> --public
```
- 방법 B (웹): GitHub에서 새 저장소 생성 → 제공되는 리모트 URL을 복사

3. 리모트 추가 및 푸시
```bash
git remote add origin git@github.com:<OWNER>/<REPO>.git
git branch -M main
git push -u origin main
```

브랜치 전략 (권장)
- `main`: 운영용(배포 가능한 안정 버전). 보호(branch protection) 설정 권장.
- `develop`: 통합 브랜치(기능 병합 전 테스트).
- `feature/*`: 새로운 기능 개발(예: `feature/playwright-youtube`).
- `fix/*` 또는 `hotfix/*`: 긴급 버그 수정.

커밋 규칙 (권장: Conventional Commits)
- 형식: `<type>(scope?): subject`
- 예: `feat(playwright): add youtube scraper for keywords`
- 타입 예시: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`

풀 리퀘스트(코드리뷰)
1. `feature` 브랜치에서 작업
2. 원격에 푸시: `git push -u origin feature/xxx`
3. GitHub에서 PR 생성 → 리뷰 요청 → CI 통과 → 병합
- 병합 방식: 팀 규칙에 맞춰 `squash` 또는 `merge` 사용

릴리즈 및 태깅
- 새 릴리즈 태그 만들기
```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```
- GitHub Releases 페이지에서 릴리즈 노트 작성

비밀(Secrets)과 환경 변수
- 로컬에서 `.env` 파일 사용 가능(커밋 금지)
- GitHub Actions용 시크릿: Repository > Settings > Secrets > Actions
- 예: `ALPHA_VANTAGE_KEY`, `YOUTUBE_API_KEY`
- 워크플로우에서 `${{ secrets.YOUTUBE_API_KEY }}` 형태로 사용

프롬프트/데이터 업데이트 워크플로우
- 프롬프트 파일은 `prompts/` 폴더에 보관합니다. 예: `prompts/master_prompt.md`
- 프롬프트 변경 시 커밋 메시지 예시: `chore(prompt): update master prompt - clarify youtube rules`
- PR 템플릿 또는 체크리스트에 `prompt review` 항목을 추가해 변경점의 영향도를 검토하세요.

간단한 명령 참고
```bash
# 현재 상태 확인
git status
# 변경 내용 스테이징
git add prompts/master_prompt.md
# 커밋
git commit -m "chore(prompt): update youtube scraping section"
# 새 브랜치 생성
git checkout -b feature/update-pipeline
# 원격에 푸시
git push -u origin feature/update-pipeline
```

운영 팁
- `main` 브랜치는 보호하고 직접 푸시 금지(PI로 병합).
- 민감한 데이터는 코드에 커밋하지 말 것(데이터, 키, 비밀).
- 정기적으로 `git pull --rebase`로 최신 변경 사항을 반영.

문제 해결
- 원격 설정이 잘못된 경우
```bash
git remote -v
git remote remove origin
git remote add origin git@github.com:<OWNER>/<REPO>.git
```
- 강제 푸시가 필요할 때(주의!)
```bash
git push --force-with-lease origin branch-name
```

참고: GitHub Actions CI 예시는 `.github/workflows/ci.yml`에 포함되어 있습니다. 필요하면 CI를 확장하여 테스트/빌드/배포 파이프라인을 구성하세요.
