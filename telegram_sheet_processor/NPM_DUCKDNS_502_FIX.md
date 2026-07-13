# NPM DuckDNS 502 Fix

현재 증상:

```text
https://asset.jongchul-server.duckdns.org/health
-> 502 Bad Gateway
```

이 뜻은 다음 중 하나입니다.

1. Nginx Proxy Manager는 외부 HTTPS 요청을 받고 있다.
2. 하지만 뒤쪽 `http://192.168.1.12:8010` stock-api에 연결하지 못한다.

즉 DNS/SSL은 대부분 통과했고, 문제는 upstream API입니다.

## 1. stock-api 컨테이너 확인

홈서버 Linux에서:

```bash
cd telegram_sheet_processor
docker compose ps
docker logs --tail 80 telegram-sheet-stock-api
```

컨테이너가 없다면:

```bash
cp .env.example .env
docker compose up -d --build stock-api
```

## 2. 내부 API 확인

홈서버에서:

```bash
curl -i http://127.0.0.1:8010/health
curl -i http://192.168.1.12:8010/health
```

정상이라면 JSON에 `"ok":true`가 나와야 합니다.

## 3. NPM Proxy Host 확인

NPM 기본 설정:

```text
Domain Names: asset.jongchul-server.duckdns.org
Scheme: http
Forward Hostname / IP: 192.168.1.12
Forward Port: 8010
Access List: Public
Block Common Exploits: ON
Websockets Support: OFF
```

NPM이 같은 Docker 네트워크에서 실행 중이고 `stock-api` 서비스를 직접 볼 수 있게 구성했다면 아래도 가능합니다.

```text
Forward Hostname / IP: stock-api
Forward Port: 8010
```

하지만 NPM이 별도 compose/별도 네트워크라면 `stock-api` 이름을 해석하지 못합니다. 이 경우 현재처럼 홈서버 LAN IP를 사용하세요.

```text
Forward Hostname / IP: 192.168.1.12
Forward Port: 8010
```

SSL:

```text
Request a new SSL Certificate
Force SSL: ON
HTTP/2 Support: ON
HSTS: OFF
DNS Challenge: OFF
```

## 4. 전체 진단 스크립트

```bash
chmod +x diagnose_stock_api_502.sh
./diagnose_stock_api_502.sh https://asset.jongchul-server.duckdns.org
```

## 5. 가장 흔한 원인

이 프로젝트의 Docker 실행은 `scripts.api_server:app`으로 실행합니다.
따라서 Python import 경로가 맞지 않으면 컨테이너가 바로 종료되고 NPM은 502를 냅니다.

현재 코드는 Docker 실행과 로컬 실행을 모두 지원하도록 수정되어 있습니다.

## 6. 성공 기준

홈서버에서 아래가 먼저 성공해야 합니다.

```bash
curl -i http://127.0.0.1:8010/health
curl -i http://192.168.1.12:8010/health
```

그 다음 외부 주소가 성공해야 합니다.

```bash
curl -i https://asset.jongchul-server.duckdns.org/health
```
