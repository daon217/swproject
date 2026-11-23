# 외부 HTTPS / 내부 백엔드 HTTP 분리

외부 상품/API와 내부 ingestion은 다른 정책이다. 상품 URL·Observation v2의 URL은 계속 HTTPS다.
기존 전송은 HTTPS와 명시적 loopback 테스트만 허용했으며, 일반 NAS 내부 HTTP는 지원하지 않았다.
기존 loopback 테스트 예외를 운영 내부 HTTP 승인으로 사용하지 않는다.

## 기본값

- COLLECTOR_DELIVERY_APPROVED=no. source 권한/가격/백엔드 owner 검사도 그대로 필요하다.
- COLLECTOR_BACKEND_TRANSPORT=https, COLLECTOR_BACKEND_BASE_URL은 비워두면 기존 backend_delivery.base_url.
- COLLECTOR_INTERNAL_HTTP_APPROVED=no, COLLECTOR_INTERNAL_NETWORK_ID 비어 있음, 검토 파일 없음.
- NAS 네트워크를 확인하지 못했으므로 모든 배포 예제의 HTTP 운영 전송은 비활성이다.
- 실제 NAS `/volume1/docker/swproject`, 별도 test-v1 release와 기존8개 컨테이너/네트워크는 변경하지 않는다.

## 외부 수집 HTTPS 유지·보강

unified_live.policy/url/transport의 HTTPS·권한·TLS hostname·공개 IP pinning·robots·원장/예산은 유지한다.
도매꾹·고정 API의 기본 requests session에도 공개 DNS/IP pinning을 적용한다. DNS의 답 중 하나라도
private/loopback/link-local이면 차단하며 검증한 주소로 접속하고 원래 hostname으로 TLS를 검증한다.
HTTP·proxy·verify=False는 거부한다. redirect를 따라가지 않으므로 HTTP downgrade나 다른 호스트에
키를 재전달하지 않는다. 테스트에서 주입한 Fake session은 모의 경계이며 운영 기본 session과 구분한다.
백엔드 환경변수는 상품/API endpoint나 상품 URL 정규화에 사용하지 않는다.

## 내부 HTTP가 허용되는 조건

다음 조건이 모두 필요하다. 사설 IP/localhost라는 사실만으로 허용하지 않는다.

1. 수집·저장·가격·owner 승인과 별도 COLLECTOR_DELIVERY_APPROVED=yes.
2. COLLECTOR_BACKEND_TRANSPORT=internal_http, COLLECTOR_INTERNAL_HTTP_APPROVED=yes.
3. COLLECTOR_BACKEND_BASE_URL은 검토된 Docker DNS 서비스명과 명시 포트의 origin만 사용.
   예: http://ingest-api:8000. IP literal/localhost/userinfo/query/fragment/경로 prefix는 거부한다.
4. 관리자 소유 검토 파일과 COLLECTOR_INTERNAL_NETWORK_ID가 실제 inspect의 full network ID와 일치.
5. 검토 자료는 Internal=true/bridge/local/IPv4, 정확히 신뢰된 container ID 집합, endpoint IP와 alias,
   비특권·cap_drop ALL·publish된 포트 없음·Docker socket 없음을 확인해야 한다.
   ingest 서비스는 해당 내부망에만 연결한다. 외부 API와 양방향으로 붙은 일반 NAS API를 무조건 승인하지 않는다.
6. 실행 시 DNS가 정확히 승인된 backend IP 하나로 해석되고, Linux 직접 연결 route의 인터페이스가
   승인된 collector IP를 소유해야 한다. gateway/default route/다른 source IP는 거부한다.
7. 검증 IP에 source IP를 bind해 접속하고 peer/source를 확인한다. 토큰은 그 뒤에 전송한다.
   요청마다 재사용 연결도 검토 파일·만료·DNS·route를 재검사한다. endpoint 변경은 검토 후 재시작이 필요하다.
8. redirect는 따라가지 않는다. session은 proxy/env 상속을 끄고 origin/port/고정 Observation route만 허용한다.
9. 검토 파일은 관리자 소유 디렉터리를 read-only로 mount한다. 그룹/기타 쓰기를 거부한다.
   파일은 최대5분 유효하다. host 측 감독자가 약30초마다 inspect를 재확인하고 실패 시 approved=false로 취소한다.

검토 파일은 암호학적 Docker 증명이 아니라 관리자 신뢰 경계의 짧은 수명 증명이다. worker에 Docker socket을
노출하지 않는다. 런타임에서 Docker membership 자체를 직접 조회하지 않으므로 관리자 측 신뢰된 갱신·감시가
필수다. 신뢰할 수 없는 사용자가 Docker daemon 권한을 갖거나 임의 컨테이너를 연결할 수 있으면 HTTP 사용을
승인하지 않는다. 그 경우 분리된 ingest service와 관리자 접근 통제/방화벽 또는 TLS가 선행되어야 한다.

## 검토 파일 생성·취소

collector_ops.internal_network.issue_review는 network/container inspect 스냅샷을 검증하는 순수 함수다.
CLI는 다음 형식이며 Docker 상태를 변경하지 않는다. --admin-network-review-confirmed와 독립 reference는
관리자의 실제 접근 통제·멤버 검토 후에만 넣는다. 실패 시 기존 긍정 검토 파일도 approved=false로 갱신한다.

```sh
python -m services.collector.collector_ops.internal_network \
  --network-inspect /private-review/network.json \
  --collector-inspect /private-review/collector.json \
  --backend-inspect /private-review/backend.json \
  --trusted-container-id <full-collector-id> --trusted-container-id <full-ingest-id> \
  --service ingest-api --port 8000 --review-reference <approved-admin-record> \
  --admin-network-review-confirmed \
  --output /volume1/docker/kkulpick-collectors-v2/network-review/internal-network-review.json
```

inspect 자료에서 Config.Env/비밀값은 수집하지 않는다. 필요한 Id/Hostname/State/HostConfig/NetworkSettings/Mounts만
보존한다. 실제 검토 파일·인프라 inspect·secrets는 Git에 넣지 않는다. 갱신 파일을 atomic rename하므로 파일 하나가
아닌 디렉터리 전체를 read-only로 mount해야 worker가 최신 inode를 읽을 수 있다.

## Compose 준비 — 지금 실행하지 않음

기본 compose는 새 네트워크를 만들거나 기존 NAS 네트워크에 연결하지 않는다. internal-http.override.yaml은
관리자가 이미 격리를 확인한 external network만 참조한다. external:true는 Compose 밖에서 관리한다는 뜻으로,
인터넷 공개 허용이라는 뜻이 아니다. 실제 network의 Internal=true는 검토 생성 시 별도로 검사한다.

승인 후 필요한 값:

```
COLLECTOR_BACKEND_TRANSPORT=internal_http
COLLECTOR_BACKEND_BASE_URL=http://ingest-api:8000
COLLECTOR_INTERNAL_HTTP_APPROVED=yes
COLLECTOR_INTERNAL_NETWORK_NAME=<reviewed-existing-network-name>
COLLECTOR_INTERNAL_NETWORK_ID=<full-reviewed-network-id>
INTERNAL_REVIEW_DIR=/volume1/docker/kkulpick-collectors-v2/network-review
COLLECTOR_DELIVERY_APPROVED=yes
```

서비스별 collector IP/container ID가 다르므로 하나의 검토 파일을 여러 컨테이너에 공유하지 않는다.
override는 INTERNAL_REVIEW_DIR 아래 domeggook/serper/ebay/yes24/url/fleet/public_feed별 디렉터리를 read-only mount한다. 각 worker에 맞는 검토 파일을 발급해야 한다.
한 fleet 컨테이너의 child는 같은 net namespace이므로 동일 검토를 사용할 수 있다.
API token은 계속 KKULPICK_BACKEND_TOKEN_FILE secret, 상태/원장/Outbox volume과 기존 소스별 예산은 유지한다.

```sh
# 관리자가 별도 release에서 검토할 정적 검사 예. 이번 작업에서 NAS 실행하지 않음.
docker compose --env-file <reviewed-runtime.env> -p kkulpick-collectors-v2 \
  -f services/collector/unified_live/deploy/compose.yaml \
  -f services/collector/unified_live/deploy/internal-http.override.yaml --profile ebay config -q
```

기존 prepare/deploy 스크립트는 기본 HTTPS compose만 사용한다. 내부 HTTP override를 쓰는 운영 절차는
관리자가 명시적으로 적용해야 하며, 기존8개 NAS 서비스를 재시작하거나 네트워크를 임의 생성/변경하지 않는다.
5분 검토 만료·endpoint 변경 시 송신은 차단되지만 영속 payload/key/원장은 유지된다.

## ACK·중복·재시도 및 검증

HTTP/HTTPS는 동일 Observation v2·source/listing/variant·run/event key와 ACK 정책을 사용한다.
신규/변경/미변경 처리와 immutable payload, Retry-After/backoff/상한을 재사용한다. 알려진 정책 거부/redirect는
hold, 기존 transient 오류는 같은 body/key로 재시도한다. 직접 PostgreSQL 접속/DDL/INSERT는 추가하지 않았다.
실제 외부 상품 요청 대신 모의 HTTPS/TLS/DNS/redirect 테스트를 사용한다. 별도 로컬 Docker lab에서는
Internal=true 네트워크와 FastAPI/SQLite 테스트 저장소로 실제 HTTP/ACK/중복/재시도를 확인한다.
로컬 검증은 NAS 도달성·기존 NAS API 버전·접근 통제·운영 PG 저장 완료를 증명하지 않는다.

관리자 협의: 신뢰된 network/container/image ID, 접근 가능한 Docker 관리자, 격리 ingest alias/port,
검토 갱신 감독자·재시작 절차, token 범위/source/host/currency·가격·저장권한과 최종 API route/ACK.

공식 근거: [Docker network isolation](https://docs.docker.com/engine/network/),
[Compose networking](https://docs.docker.com/compose/how-tos/networking/),
[urllib3 HTTPS connection](https://github.com/urllib3/urllib3/blob/main/src/urllib3/connection.py).

## 관리자 검토 갱신 도우미

deploy/refresh-internal-review.sh는 승인된 단일 collector/ingest 쌍의 정확한 ID를 받아 local Linux daemon의
inspect만 약30초마다 읽는다. 새 멤버/공개 포트/네트워크 변경/검사 실패/감독 종료 시 승인 파일을 취소한다.
Config.Env는 읽지 않으며 API key가 든 inspect를 파일로 저장하지 않는다. worker에는 socket을 mount하지 않는다.
REVIEW_NETWORK_ID/COLLECTOR_ID/BACKEND_ID 대신 실제 변수명은 REVIEW_NETWORK_ID, REVIEW_COLLECTOR_ID,
REVIEW_BACKEND_ID, REVIEW_SERVICE, REVIEW_PORT, REVIEW_REFERENCE, REVIEW_OUTPUT_DIR, REVIEW_PYTHON이다.
REVIEW_PYTHON은 해당 모듈/기존 의존성이 설치된 관리자 전용 절대 경로여야 한다. NAS에 Python/감독 서비스가
준비됐다고 가정하지 않는다. 스크립트는 해당 release의 루트에서 관리자 검토 후 실행한다. 이번 NAS 실행은0이다.

기본 도우미는 정확히 두 컨테이너만 신뢰한다. 여러 worker를 같은 망에 넣으려면 관리자 소유 REVIEW_TRUSTED_IDS_FILE에
승인된 full container ID를 한 줄씩 명시한다. 전체 망 멤버와 정확히 일치해야 하며 각 worker별 감독·검토 파일은 여전히 분리한다.
단순히 worker를 늘리고 검사 조건을 해제하지 않는다. 관리자 전용 디렉터리의 검토 파일은 worker가 읽을 수 있게
원자적 교체 전에0644로 설정한다. 임시 inspect는0700 디렉터리에 보관한다. 감독 Python 모듈은 표준 라이브러리만 사용한다.
Docker 재시작은 같은 ID/endpoint면 갱신되나 컨테이너 재생성으로 ID/IP가 바뀌면 재검토 후 재시작해야 한다.
