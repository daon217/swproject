# 운영 웹 수집 및 HTTP 전송 수정 — 2026-11-24

이 문서는 배포 준비 안내다. 이번 작업은 NAS, 운영 PostgreSQL, 실제 쇼핑몰을 변경하거나 호출하지 않았다.

## 확인된 원인

* collector_ops preflight는 JSON 설정의 HTTPS URL만 검사했다. 실제 전송은 환경변수 URL 우선이라 실행 전 검사와 충돌했다.
* fleet 자식 환경변수 허용 목록에서 BACKEND_TRANSPORT/BASE_URL이 누락됐다.
* 기존 URL 워커는 검색 템플릿/검색어가 필수였다. 직접 상품 URL만 등록하면 시작할 수 없었다.
* discovery 품질 검사는 로컬 CSS 선택자를 무시했다. 승인된 CSS 전용 사이트도 품질 확인에 실패할 수 있었다.
* ItemList URL 문자열/단순 URL 객체, 카드 선택자, 일부 이미지·네이티브 보충 필드가 처리되지 않았다.
* 후보 등록은 실행 승인이 아니다. 기본 seed와 URL 예시는 비활성/권한 대기다. 검색 후보만 추가한 상태, 만료된 이용 권한, 상품 품질 미검증, 별도 fleet 미실행은 계속 수집되지 않는다.

## 최소 백엔드 설정

```ini
COLLECTOR_BACKEND_TRANSPORT=internal_http
COLLECTOR_BACKEND_BASE_URL=http://192.168.0.254:8000
COLLECTOR_DELIVERY_APPROVED=yes
COLLECTOR_RUN_APPROVED=yes
```

위 주소는 NAS 관리자가 제시한 예다. 관리자가 실제 FastAPI 주소와 접근 경로를 설정한다. Docker 서비스 이름을 이용할 수 있다면 `http://api:8000`도 가능하다. 별도 HTTP 승인 파일/서브넷 등록/컨테이너 사전 등록은 요구하지 않는다. HTTP는 암호화되지 않으므로 관리자가 신뢰하는 네트워크에서 사용한다. 환경변수 URL이 JSON backend_delivery.base_url보다 우선한다. TLS CA 설정은 HTTPS 백엔드에만 적용한다.

토큰은 기존 Docker secret `KKULPICK_BACKEND_TOKEN_FILE`로 주입한다. 소스 API 키는 각 공급자 secret을 유지한다. 상품 이용·저장·재사용 권한, backend_enabled/backend_owner_approved/price_semantics_confirmed는 독립된 기존 조건이다. YES24의 지속 저장 권한이 없다면 전송/운영 활성화를 승인하지 않는다. URL, 토큰을 로그로 출력하지 않는다.

## API 없는 사이트 수동 등록

기존 `deploy/config/url.json` 또는 `deploy/config/url.direct.example.json`을 Git 밖 config 디렉터리로 복사한다. `start_urls`에 허용된 목록/상세 HTTPS URL을 지정한다. 검색 기반은 기존 search_url_template/queries를 그대로 사용할 수 있다. 두 방식을 병용할 수도 있다. 호스트는 allowed_product_hosts 단일 값과 일치해야 한다. selectors는 실제 HTML을 확인한 CSS만 지정한다. 통화·상태·판매처가 불명확하면 보류한다. 재고 수량은 임의 생성하지 않는다.

```sh
python -m services.collector.unified_live --provider url --config /run/config.json --state-dir /state --plan
python -m services.collector.unified_live --provider url --config /run/config.json --state-dir /state --watch
python -m services.collector.unified_live --provider url --state-dir /state --status
```

`--once`는 한 tick만 실행한다. 목록→상세→재시도를 완료하는 데 여러 tick이 필요하므로 운영에는 `--watch`를 사용한다. status/heartbeat에서 hold, pending_tasks, tracked_items, totals, content_changes, backend ACK를 확인한다. 일반 7200초/중고 60초는 최소 주기이며 사이트 제한·robots·요청 예산 때문에 더 늦어질 수 있다.

## 발견 → 실행

discovery에 사이트별 로컬 grants를 전달한다. 실제 CSS 사이트에는 selectors, 검색 폼 없는 사이트에는 fleet grants의 start_urls를 지정한다. JS 사이트는 grants의 render_javascript=true와 유효한 lookup/terms 권한을 명시해야 한다. discovery는 같은 출처의 제한된 GET 리소스만 렌더링하고 품질 검사한다. robots·예산·차단 정책을 적용한다. CAPTCHA/로그인/접근 통제 우회는 없다.

fleet는 동일한 grants와 discovery 영속 상태를 읽어 품질/저장·재사용/관리자·가격 승인을 만족한 사이트만 자식 프로세스로 실행한다. `activation_wait_reasons`로 남은 조건을 확인한다. discovery와 fleet 두 프로필을 모두 실행해야 한다. 기존 active config와 다른 설정은 자동 덮어쓰지 않고 configuration_change_review로 남긴다. 중단된 요청 원장도 자동 초기화하지 않는다.

## Docker 배포 안내 — 관리자가 실행

기존 운영 서비스 8개를 일괄 재시작하지 않는다. 별도 collector Compose 프로젝트에서 필요한 서비스만 갱신한다. 기존 state/outbox/secret/config 볼륨을 보존한다. `down -v`, 체크포인트 삭제, 강제 reset은 사용하지 않는다.

```sh
git pull --ff-only origin 'part/최준서-collector'
docker compose --env-file /secure/collector.env -f services/collector/unified_live/deploy/compose.yaml --profile url config --quiet
docker compose --env-file /secure/collector.env -f services/collector/unified_live/deploy/compose.yaml --profile url run --rm --no-deps url python -m services.collector.unified_live --provider url --config /run/config.json --state-dir /state --plan
```

검토한 결과와 승인 후에만 해당 url 서비스를 build/up 한다. JS가 필요하면 browser.override.yaml을 추가한다. 이 override는 url뿐 아니라 fleet/discovery에도 실제 Playwright 이미지를 적용한다. 브라우저 이미지 빌드에 앞서 기본 collector 이미지를 빌드해야 한다. 기존 internal-http.override.yaml의 네트워크는 선택 사항이며 애플리케이션의 사전 승인 조건이 아니다. 운영 네트워크 연결은 서버 관리자 담당이다.

API 수집기 사전 검사는 동일한 환경변수로 `python -m services.collector.collector_ops --provider ebay --config /run/config.json --state-dir /state --plan`처럼 실행한다. YES24도 provider만 yes24로 변경한다. plan은 외부 요청을 하지 않는다. 통과해도 공급자별 호출·저장 권한 승인을 대신하지 않는다.

## 검증 범위와 남은 제한

실제 외부 사이트 성공을 주장하지 않는다. 도매꾹 NAS 적재 및 eBay Production 과거 성공은 사용자 보고이며 이번 재호출 결과가 아니다. 전체 Python 테스트는 네트워크를 차단해 실행한다. 별도 Docker network=none 랩은 생성된 로컬 TLS 쇼핑몰, 실제 Chromium/XHR, HTML/JSON-LD/CSS 목록→상세, 내부 HTTP FastAPI/임시 SQLite ACK를 검증한다. test 진입점만 .test 호스트를 loopback에 핀하며 운영 transport/policy에는 사설주소 예외가 없다.

공통 Observation v2가 표현하지 못하는 리퍼·개봉·식품 확장, seller/매칭 확장 영속 저장은 기존 API 계약 협의가 필요하다. 상품 상태·통화·판매처를 공개 페이지에서 확인할 수 없는 상품, 동적 로그인/봇 차단 사이트, 번개장터·중고나라의 미확인 제휴 권한은 계속 보류/비활성이다. JS 렌더링 성공이 모든 쇼핑몰 지원을 의미하지 않는다.
