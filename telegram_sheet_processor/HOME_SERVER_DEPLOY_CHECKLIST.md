# Home Server Deploy Checklist

현재 외부 상태:

```text
asset.jongchul-server.duckdns.org -> 220.118.145.56
https://asset.jongchul-server.duckdns.org/health -> 502 Bad Gateway
http://192.168.1.12:8010/health -> connection failed
```

해석:

```text
DuckDNS/DNS: 정상
NPM/HTTPS: 정상 도달
stock-api: 192.168.1.12:8010에서 미응답
```

따라서 NPM 설정을 더 만지기 전에 홈서버 Linux에서 stock-api 컨테이너를 먼저 살려야 합니다.

## 1. 홈서버에 접속

```bash
ssh 사용자명@192.168.1.12
```

또는 홈서버 터미널에서 직접 진행합니다.

## 2. 프로젝트 폴더로 이동

```bash
cd telegram_sheet_processor
```

폴더가 없다면 현재 PC의 `telegram_sheet_processor` 폴더를 홈서버로 복사해야 합니다.

예:

```bash
scp -r telegram_sheet_processor 사용자명@192.168.1.12:~/
```

Windows PC에서 패키지로 전송하려면:

```powershell
cd "C:\Users\jongc\OneDrive\문서\New project 2\telegram_sheet_processor"
.\package_for_home_server.ps1
.\deploy_to_home_server.ps1 -SshTarget "사용자명@192.168.1.12"
```

PowerShell 실행 정책 때문에 스크립트가 막히면 아래처럼 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\package_for_home_server.ps1
powershell -ExecutionPolicy Bypass -File .\deploy_to_home_server.ps1 -SshTarget "사용자명@192.168.1.12"
```

위 스크립트는 다음을 수행합니다.

```text
1. 배포 ZIP 생성
2. 홈서버로 업로드
3. 홈서버에서 압축 해제
4. docker compose up -d --build stock-api
5. 502 진단 실행
```

## 3. .env 생성

```bash
cp -n .env.example .env
```

현재 운영 권장값:

```env
ALLOW_STALE_CACHE=false
KIWOOM_ENABLED=false
```

## 4. stock-api 재빌드/실행

먼저 홈서버 환경을 점검합니다.

```bash
chmod +x preflight_home_server.sh
./preflight_home_server.sh
```

```bash
docker compose up -d --build stock-api
```

상태 확인:

```bash
docker compose ps
docker logs --tail 80 telegram-sheet-stock-api
```

정상이라면 `telegram-sheet-stock-api` 컨테이너가 `Up` 상태여야 합니다.

## 5. 내부 API 확인

홈서버에서:

```bash
curl -i http://127.0.0.1:8010/health
curl -i http://192.168.1.12:8010/health
```

두 명령 모두 아래처럼 보여야 합니다.

```json
{"ok":true,...}
```

## 6. 외부 NPM 확인

```bash
curl -i https://asset.jongchul-server.duckdns.org/health
```

정상이면 `502 Bad Gateway`가 아니라 `ok:true` JSON이 나와야 합니다.

## 7. 한 번에 수리/진단

```bash
chmod +x repair_stock_api_502.sh diagnose_stock_api_502.sh
./repair_stock_api_502.sh https://asset.jongchul-server.duckdns.org
```

더 짧게 실행하려면:

```bash
chmod +x HOME_SERVER_MANUAL_COMMANDS.sh
./HOME_SERVER_MANUAL_COMMANDS.sh
```

실패하면 출력의 어느 단계에서 실패했는지 확인합니다.

분기:

```text
127.0.0.1:8010 실패
-> stock-api 컨테이너 실행/빌드 문제

127.0.0.1:8010 성공, 192.168.1.12:8010 실패
-> Docker 포트 바인딩 또는 홈서버 방화벽 문제

내부 둘 다 성공, 외부만 502
-> NPM Proxy Host upstream 설정 문제
```

방화벽이 의심되면 홈서버에서:

```bash
chmod +x open_linux_firewall_stock_api.sh
./open_linux_firewall_stock_api.sh 8010
```

관리자 권한이 필요하면 `sudo` 비밀번호를 입력합니다.

## NPM 설정 최종값

```text
Domain Names: asset.jongchul-server.duckdns.org
Scheme: http
Forward Hostname / IP: 192.168.1.12
Forward Port: 8010
Access List: Public
Block Common Exploits: ON
Websocket Support: OFF
```

SSL:

```text
Force SSL: ON
HTTP/2: ON
HSTS: OFF
DNS Challenge: OFF
```
