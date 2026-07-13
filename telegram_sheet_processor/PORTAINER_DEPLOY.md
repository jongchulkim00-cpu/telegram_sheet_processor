# Portainer Deploy Guide

현재 PC에서 `192.168.1.12`로 SSH/TCP 접근이 되지 않는 상태라면, 홈서버의 Portainer UI 또는 NAS 콘솔에서 직접 배포하는 방식이 가장 빠릅니다.

## 1. Stack 생성

Portainer에서:

```text
Stacks -> Add stack
Name: stock-api
```

아래 compose를 붙여 넣습니다.

```yaml
services:
  stock-api:
    build: .
    container_name: telegram-sheet-stock-api
    environment:
      API_HOST: 0.0.0.0
      API_PORT: 8010
      ALLOW_STALE_CACHE: "false"
      KIWOOM_ENABLED: "false"
    ports:
      - "8010:8010"
    volumes:
      - ./data:/app/data
      - ./outputs:/app/outputs
    restart: unless-stopped
```

주의: Portainer Stack에서 `build: .`를 쓰려면 프로젝트 파일이 홈서버에 있어야 합니다.

## 2. 프로젝트 파일 업로드

현재 PC에서 만든 배포 파일:

```text
outputs/stock-api-deploy.zip
```

이 파일을 홈서버의 예시 경로에 업로드합니다.

```text
/home/root/telegram_sheet_processor
```

또는 본인 홈 디렉터리:

```text
~/telegram_sheet_processor
```

홈서버 콘솔에서:

```bash
cd ~/telegram_sheet_processor
unzip -o stock-api-deploy.zip || python3 -m zipfile -e stock-api-deploy.zip .
chmod +x *.sh scripts/*.sh
cp -n .env.example .env
./repair_stock_api_502.sh https://asset.jongchul-server.duckdns.org
```

## 3. 성공 확인

홈서버에서:

```bash
curl -i http://127.0.0.1:8010/health
curl -i http://192.168.1.12:8010/health
curl -i https://asset.jongchul-server.duckdns.org/health
```

## 4. NPM 설정

```text
Domain: asset.jongchul-server.duckdns.org
Scheme: http
Forward Hostname/IP: 192.168.1.12
Forward Port: 8010
Access: Public
Block Common Exploits: ON
Websocket: OFF
```

SSL:

```text
Force SSL: ON
HTTP/2: ON
HSTS: OFF
DNS Challenge: OFF
```

## 5. 현재 증상별 의미

```text
외부 접속 실패
-> 공유기 443/NPM 컨테이너/도메인 문제

외부 502
-> NPM은 살아 있고 stock-api upstream이 죽어 있음

192.168.1.12:8010 실패
-> stock-api 컨테이너가 안 떠 있거나 8010 포트가 안 열림
```

