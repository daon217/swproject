# NAS 백엔드: 명시적 URL로 일반 HTTP 전송

백엔드 전송은 외부 상품 수집과 독립적이다. internal_http 모드에서는 관리자가 설정한 URL로
일반 requests HTTP 연결을 사용한다. 승인 파일·갱신·ID/IP 등록·특정 서브넷·Docker DNS·veth·
라우팅·컨테이너/네트워크 구조 사전 검사는 더 이상 전송 경로에 없다.

## 서버 최소 설정

```dotenv
COLLECTOR_BACKEND_TRANSPORT=internal_http
COLLECTOR_BACKEND_BASE_URL=http://api:8000
COLLECTOR_DELIVERY_APPROVED=yes
```

api:8000은 예시다. 실제 서비스명,IP,FQDN,포트로 변경할 수 있다. 기본80 포트나 IPv6 주소도 지원한다.
URL은 반드시 환경변수에 명시한다. URL에는 scheme/host/선택 port만 지정하고,API route는 기존
/internal/v2/crawl-runs/{UUID}/observations를 사용한다. userinfo/query/fragment/path prefix는 넣지 않는다.
mode/URL/전송 활성화가 없으면 HTTP 전송을 시작하지 않는다. 설치 기본값은 HTTPS와 전송no다.
토큰은 기존 KKULPICK_BACKEND_TOKEN_FILE secret을 사용한다. 값을 URL/CLI/Git/로그에 넣지 않는다.
backend_enabled/owner/가격·저장 권한 등 기존 상품 처리 조건도 그대로 유지한다.

## 제거한 조건과 전송 방식

- COLLECTOR_INTERNAL_HTTP_APPROVED/NETWORK_ID/NETWORK_REVIEW_FILE,승인 파일 만료/갱신 요구 없음.
- container ID/hostname/IP 등록,단일 네트워크·멤버·published port 검사 없음.
- COLLECTOR_INTERNAL_SUBNET,고정 IPAM,private/public 주소 분류·Docker embedded DNS·hosts 파일 검사 없음.
- veth/직접 route/namespace/source bind/환경 사전 검사 없음. 일반 DNS와 OS 라우팅으로 접속한다.
- HTTP 경로는 COLLECTOR_CA_FILE도 요구하지 않는다. HTTPS 경로의 CA/인증서 검증은 유지한다.

과거 internal_network/container_route/refresh 도구는 호환 보존용이며 현재 backend_transport는 이를
import하거나 호출하지 않는다. 관련 프로세스를 새 크롤러 때문에 실행할 필요가 없다.
주소 유형이나 내부망 여부를 앱이 보증하지 않는다. 명시한 URL과 네트워크 접근 통제는 관리자의 설정이다.
수집된 상품의 URL/HTML/API 응답에서 백엔드 주소를 가져오지 않는다.

## 유지하는 전송 보안

1. HTTP는 internal_http 모드와 명시된 URL,기존 전송 활성화yes가 있어야 생성된다.
2. 세션은 설정된 정확한 scheme/host/port와 고정 Observation route로만 요청을 허용한다.
3. allow_redirects=False. 다른 호스트/포트/프로토콜/route로 토큰을 전달하지 않는다.
4. trust_env=False로 환경 proxy/.netrc 등 암묵적 인증 경로를 상속하지 않는다. 명시적 proxy도 거부한다.
5. HTTP wire debug는 꺼져 있으며 토큰/원본 예외는 상태·로그에 기록하지 않는다. close 시 Authorization을 제거한다.
6. HTTP와 HTTPS는 동일 v2 body/key/run/ACK/Outbox를 사용한다. 실패는 같은 key/body로 기존 상한·backoff에 따라 재시도한다.
7. 인증/충돌/redirect hold와 저장 권한 취소는 유지한다. 기존 hold/원장을 무조건 삭제하지 않는다.

## 외부 상품 수집은 변경하지 않음

외부 상품/API의 HTTPS 필수,TLS 검증,공개 IP pinning,HTTP 수집 차단,SSRF/DNS 방어,
API key/호출 예산,robots/접근 정책은 그대로다. backend 환경변수는 외부 수집 endpoint에 적용되지 않는다.
상품 URL과 백엔드 URL은 다른 필드다. 백엔드HTTP가 상품HTTP 수집을 허용하지 않는다.
신규/변경/중복,중고60초·일반7200초,식품/비전 매칭 메타데이터도 유지한다.

## Docker 설정

앱은 네트워크를 사전 승인하지 않는다. api라는 이름을 사용한다면 API와 worker가 해당 이름을
해석할 수 있는 망에 연결돼 있어야 한다. IP/FQDN 사용 시에는 해당 주소의 도달성을 관리자가 구성한다.
localhost는 일반적인 namespace 의미를 가지며,컨테이너에서는 그 컨테이너 자신을 가리킨다.

internal-http.override.yaml은 선택적 배포 예제로,내부 bridge를 선언하고 기존 egress 망은 유지한다.
서브넷은 Docker가 할당하며 앱에서 CIDR을 등록하지 않는다. 이 override나 특정 network 이름을
반드시 사용해야 하는 것은 아니다. API의 기존 DB/웹 네트워크 구성도 앱에서 제한하지 않는다.
기존 state/Outbox/secret volume은 보존한다. 이번 작업에서는 실제 NAS Compose/네트워크/서비스를 변경하지 않는다.

```sh
# 선택적 Compose 예제의 정적 검증. 이번 작업에서 NAS 실행하지 않음.
docker compose --env-file <runtime.env> -p kkulpick-collectors-v2 \
  -f services/collector/unified_live/deploy/compose.yaml \
  -f services/collector/unified_live/deploy/internal-http.override.yaml --profile ebay config -q
```

## 검증 경계

격리 로컬 FastAPI/SQLite에서 파일·ID·CIDR 사전 등록 없는 실제 HTTP,503 재시도,신규·변경·
미변경 생략·동일 요청 replay·redirect 미추적을 검증한다. 승인 파일과 subnet 환경변수는 주입하지 않는다.
기존 배포 제한의 legacy 유틸리티 테스트는 호환 보존용이며 현재 전송의 gate가 아니다.
테스트는 synthetic 데이터만 사용한다. NAS·운영 PostgreSQL·실제 공급자 API에는 접속하지 않는다.
