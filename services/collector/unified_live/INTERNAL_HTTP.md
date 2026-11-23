# NAS 내부 HTTP: Compose 설정으로 연결

별도 승인 JSON, 컨테이너 ID 등록,5분 만료,검토 파일 갱신 감독자는 더 이상 필요하지 않다.
내부 HTTP는 명시된 Docker 서비스와 포트,설정된 단일 내부 서브넷의 직접 연결로 제한한다.
외부 상품/API의 HTTPS·TLS·공개 IP pinning 정책은 변경하지 않았다.

## 기존 차단 원인

6df7d22의 InternalPolicy는 COLLECTOR_INTERNAL_HTTP_APPROVED,network ID,관리자 파일,만료시간,
정확한 collector/backend ID·IP·hostname·멤버,백엔드 단일 네트워크/비공개 포트를 모두 요구했다.
파일을 주기적으로 갱신하지 않거나 컨테이너가 재생성되면 차단됐다. NAS의 정상적인 다중 네트워크
API와 기존 Compose 배치에도 맞지 않았다. 이 조건들은 현재 전송 경로에서 제거했다.
legacy issue_review/refresh 도구는 호환 보존용이며 현재 전송의 승인 수단이 아니다. 실행할 필요가 없다.

## 최소 설정

기존 token/소스·저장·가격·backend owner 설정은 그대로 사용한다. 추가적인 HTTP 승인 절차는 없다.

```dotenv
COLLECTOR_BACKEND_TRANSPORT=internal_http
COLLECTOR_BACKEND_BASE_URL=http://api:8000
COLLECTOR_DELIVERY_APPROVED=yes
```

COLLECTOR_DELIVERY_APPROVED는 기존 전송 활성화 설정이다. 이미yes라면 주소·전송 모드만 지정한다.
기본 배포값은 여전히 no/HTTPS이므로 설치만으로 운영 데이터가 전송되지 않는다.
인증은 기존 KKULPICK_BACKEND_TOKEN_FILE을 사용한다. 토큰을 URL/명령 인자/로그/Git에 넣지 않는다.

내부 네트워크 기본값:

```dotenv
COLLECTOR_INTERNAL_SUBNET=172.30.240.0/24
COLLECTOR_INTERNAL_NETWORK_NAME=kkulpick-collector-ingest
```

서브넷이 NAS 기존망과 겹치면 두 값과 실제 Compose IPAM을 함께 맞춘다. 런타임은 임의의 사설망을
추측해 허용하지 않는다. 직접 실행할 때도 COLLECTOR_INTERNAL_SUBNET을 명시한다. Compose는 위 기본값을 전달한다.
HTTP는 명시적 포트가 있는 단일 Docker 서비스 이름만 허용한다(api/api_service 등). IP literal,
localhost,host.docker.internal,공인호스트/FQDN,credential/query/path prefix는 거부한다.

## Docker 연결 조건

기존 독립 collector Compose와 internal-http.override.yaml을 함께 사용한다.
override는 driver=bridge,internal=true,지정 IPAM 서브넷의 내부망을 선언한다. 외부 상품 수집을 위한
기존 default 망은 함께 유지한다. worker는 내부망에서 API로,외부 수집은 기존 HTTPS 경로로 통신한다.
승인 파일 mount와 network ID/컨테이너 ID 설정은 없다. 기존 상태·Outbox·secret volume은 유지된다.

백엔드도 이 내부망에 연결하고 api라는 이름 또는 명시한 alias를 부여한다. 백엔드의 기존 DB/웹
네트워크 연결을 유지할 수 있다. 백엔드의 네트워크 개수나 전체 컨테이너 ID를 크롤러가 검사하지 않는다.
팀 API Compose 담당자가 참고할 연결 예시는 다음과 같다. 이번 작업에서 팀원 코드/NAS에는 적용하지 않는다.

```yaml
services:
  api: # 실제 팀 서비스 이름에 맞춤
    networks:
      default: {}
      collector_ingest:
        aliases: [api]
networks:
  collector_ingest:
    external: true
    name: kkulpick-collector-ingest
```

collector override가 먼저 만든 내부망을 API 측은 참조한다. API 이름과 alias의 중복/충돌을 피한다.
internal_ingest에 신뢰하는 collector와 API만 연결한다. 이 망의 HTTP 경로를 인터넷에 port publish하거나
불특정 컨테이너가 Docker daemon으로 망에 참가할 수 있게 하지 않는다. API의 기존 공개 웹 경로와
collector의 내부 주소는 별개다. 관리자 설정과 Docker daemon 접근 통제가 신뢰 경계다.

```sh
# 설정 검증 예. 이번 작업에서 NAS 배포는 하지 않는다.
docker compose --env-file <runtime.env> -p kkulpick-collectors-v2 \
  -f services/collector/unified_live/deploy/compose.yaml \
  -f services/collector/unified_live/deploy/internal-http.override.yaml --profile ebay config -q
```

기본 배포 스크립트는 기본 HTTPS compose를 사용하므로 HTTP 배포 시 위 override를 명시한다.
기존 NAS8개 서비스와 /volume1/docker/swproject 및 test-v1은 이번 작업에서 접속·변경하지 않았다.

## 파일 없는 런타임 검증

1. HTTP 모드와 기존 전송 활성화가 켜져 있고,요청 origin이 환경변수의 정확한 서비스/포트와 일치해야 한다.
2. 설정 서브넷은 한정된 RFC1918 IPv4 CIDR(/16~30)이어야 한다.0/0·공인망·loopback·link-local은 거부한다.
3. Docker embedded DNS(127.0.0.11)를 사용한다. /etc/hosts/extra_hosts/host-gateway 대체 주소는 거부한다.
4. DNS 답은 하나의 IPv4이고 해당 서브넷 안이어야 한다. 공인 IP·다른 사설망·혼합 답은 거부한다.
5. Linux kernel route가 정확히 그 서브넷의 on-link 경로여야 한다. gateway/default/loopback 경로는 거부한다.
6. 실제 인터페이스는 kernel이 보고하는 veth이며,IP와 netmask도 서브넷과 일치해야 한다.
   host network/물리 LAN/bridge/VPN/macvlan 경로는 허용하지 않는다. Docker socket은 mount하지 않는다.
7. 확인한 source IP를 bind하고 대상 IP에 pinning한다. 연결 후 peer/source를 확인한 뒤 토큰을 보낸다.
8. 같은 서비스의 컨테이너 IP가 바뀌면 pool을 비우고 새 주소로 연결한다. ID 재등록이나 승인 파일은 필요 없다.
   DNS 준비 지연은503으로 기존 재시도에 넘기며,설정/경로 위반은 기존 hold 정책을 유지한다.
9. 리다이렉트·proxy·다른 origin/port/route로 토큰을 전달하지 않는다. Observation v2는 그대로다.

컨테이너 내부의 kernel 경로만으로 Docker의 Internal 플래그나 전체 신뢰 멤버를 조회할 수는 없다.
따라서 실제 격리는 Compose의 internal:true와 제한된 네트워크 연결/daemon 접근 통제가 강제한다.
런타임은 실제 veth/직접 경로까지 검증하지만 이것을 Docker 관리자 권한에 대한 암호학적 증명으로
보고하지 않는다. internal:false인 다른 망으로 override를 임의 대체하지 않는다.
지원 범위는 Linux Docker의 user-defined IPv4 bridge/veth다. host/macvlan/rootless 대체 드라이버,
IPv6 다중 주소 또는 직접Windows 실행에서는 HTTP를 자동 허용하지 않는다.

## 유지되는 데이터 처리와 마이그레이션

상품 URL은 계속 HTTPS다. 백엔드 HTTP/HTTPS에 따라 v2 body,source/listing/variant,event key,
ACK/중복/신규·변경 비교/영구 큐가 달라지지 않는다. 가격·저장 권한과 토큰 인증도 유지한다.
COLLECTOR_INTERNAL_HTTP_APPROVED/NETWORK_ID/NETWORK_REVIEW_FILE/INTERNAL_REVIEW_DIR은 새 전송에서
읽지 않는다. 예전 refresh-internal-review 감독을 새 워커 때문에 시작할 필요가 없다.
기존401/403/409/불확실 응답으로 저장된 hold는 자동 삭제하지 않는다. 이전 파일 만료와 실제 인증 오류가
같은 old hold 코드로 기록됐을 수 있으므로 기존 hold가 있으면 원인을 한 번 확인해야 한다. 큐/원장을 지우지 않는다.
이후 정상 DNS 재생성이나 시간 경과만으로 별도 승인 hold가 새로 생기지는 않는다.

검증: 외부 HTTPS 회귀,파일 없는 실제 Docker veth 경로,다중 네트워크 API/collector,
FastAPI→SQLite,503 재시도/신규·변경/미변경/replay/redirect/공인HTTP 차단을 독립적으로 확인한다.
운영 NAS/PG 및 실제 공급자 API는 사용하지 않는다.
