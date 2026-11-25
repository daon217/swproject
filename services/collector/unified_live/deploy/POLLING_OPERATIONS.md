# 자동 발견 및 중고 폴링 운영 안내 — 2026-11-25

## 운영 범위

소스별 실제 접근·수집·저장·재사용 권한을 로컬 grants로 확인한 사이트만 자동 실행한다. robots 허용이나 공개 링크만으로 저장·재사용 권한을 승인하지 않는다. API 키가 없는 HTML 사이트도 JSON-LD/CSS/OG/표준 Chromium으로 처리한다. 기본 구성은 비활성이며 이 변경이 운영 승인을 대신하지 않는다.

사이트 후보는 기존 seed/운영자 디렉터리, 게시된 JSON API catalog linkset 또는 운영자가 검토한 HTML 디렉터리 선택자에서 추가된다. 임의 검색엔진 탐색·인터넷 전체 스캔은 하지 않는다. 새 후보는 비활성이다. 링크에서 토큰·설정·승인값을 가져오지 않는다. HTML 디렉터리는 해당 publisher grants에 discovery_links_selector를 지정한다(최대 20개 링크, 공개 HTTPS만 후보 등록, 다른 출처는 자동 요청하지 않음).

## 이번 운영 결함 수정

* discovery watch는 이전에 유휴 대기까지 공유 잠금을 점유했다. 이제 초기 등록과 각 tick만 잠그고 잠금 안에서 최신 registry를 다시 읽는다. fleet도 잠금 획득 후 registry를 읽어 오래된 snapshot을 덮어쓰지 않는다.
* 유효한 lookup/terms 권한과 명시적인 start_urls가 있으면 해당 목록/상세를 품질 검사한다. 검색 폼이 없어도 가능하다. 현재 품질 검사 성공 여부를 갱신하며 이전 성공만으로 계속 활성화하지 않는다.
* 목록에서 방문한 상세의 JSON-LD/CSS 능력이 어댑터 선택으로 전달된다. OG type만 있는 홈페이지는 상품 상세 증거로 취급하지 않는다.
* 한 페이지의 파싱 실패 또는 명확한 5xx 재시도 소진은 해당 task만 보류하고 나머지 상품·다음 주기를 계속한다. 최근 50개 실패의 URL 해시/시각/사유를 기록한다. 원문 URL·응답·토큰을 오류 로그에 넣지 않는다.
* 권한 만료, CAPTCHA/로그인/robots, SSRF/DNS 차단 및 결과 불확실 요청은 계속 전역 hold다. 원장·체크포인트를 지우거나 무조건 자동 재전송하지 않는다. 재시도 소진으로 큐에서 빠진 상품은 다음 목록/refresh에서 다시 확인할 수 있다. 모든 상품의 매 주기 재확인을 보장하지 않는다.

## 최소 설정

```ini
COLLECTOR_BACKEND_TRANSPORT=internal_http
COLLECTOR_BACKEND_BASE_URL=http://192.168.0.254:8000
COLLECTOR_RUN_APPROVED=yes
COLLECTOR_DELIVERY_APPROVED=yes
KKULPICK_BACKEND_TOKEN_FILE=/run/secrets/kkulpick_backend_token
DISCOVERY_METADATA_APPROVED=yes
```

주소는 관리자가 정한 실제 FastAPI 주소로 바꾼다. 별도 HTTP 승인 파일은 필요 없다. 내부 HTTP는 관리자 신뢰 경로에서만 사용한다. 외부 수집은 여전히 공개 HTTPS/TLS/핀된 DNS/robots/예산을 사용한다. 백엔드 리다이렉트 및 다른 호스트 토큰 전송은 차단한다. 전송 승인이 없으면 Outbox만 유지하고 전송하지 않는다.

`deploy/config/discovery-grant.example.json`을 Git 밖 config 디렉터리로 복사하고 실제 marketplace ID로 grants를 작성한다. ID는 discovery registry에서 확인한다. allowed_hosts, 유효한 reference/terms_reference/expires_at/allowed_uses(lookup, systematic_collection, storage, reuse), backend_enabled/backend_owner_approved/price_semantics_confirmed, currencies가 필요하다. start_urls 또는 search_url_template/queries를 지정하고 실제 사이트 선택자만 등록한다. JS가 필요하면 render_javascript=true와 해당 리소스 접근 권한을 확인한다. 요청·페이지·상품 한도를 높일 때 공급자 정책을 먼저 확인한다.

서버 관리자는 기존 collector Compose 프로젝트의 필요한 프로필만 갱신한다. 기존 NAS 서비스 8개를 일괄 재시작하거나 운영 네트워크를 변경하지 않는다. state/outbox/secret/config 볼륨을 보존하고 down -v/reset/체크포인트 삭제를 하지 않는다.

```sh
git pull --ff-only origin 'part/최준서-collector'
docker compose --env-file /secure/collector.env -f services/collector/unified_live/deploy/compose.yaml --profile discovery --profile fleet config --quiet
```

기존 config/state 경로가 맞는지 확인한 후 해당 discovery/fleet 서비스만 build/up -d한다. restart:unless-stopped 및 --watch가 지속 실행/재시작을 담당한다. JS는 browser.override.yaml을 추가한다(기본 collector 이미지 먼저 build). discovery와 fleet를 모두 실행해야 발견→활성 워커가 이어진다. 이미 실행 중인 다른 설정을 자동 덮어쓰지 않는다. configuration_change_review가 보이면 현재 writer를 보존한 상태로 관리자가 설정 변경 절차를 결정한다.

수동 점검용 명령(Compose 자동 watch와 별도 중복 실행하지 않음):

```sh
python -m services.collector.unified_live.discovery --state-dir /state/discovery --directory /run/sites.json --grants /run/grants.json --plan
python -m services.collector.unified_live.fleet --state-dir /state/fleet --discovery-state /state/discovery --grants /run/grants.json --plan
python -m services.collector.unified_live --provider url --config /run/config.json --state-dir /state/url --plan
python -m services.collector.unified_live --provider url --state-dir /state/url --status
```

plan은 외부 요청을 하지 않는다. --once는 한 tick이며 전체 목록→상세 순회를 완료하지 않을 수 있다. 운영은 --watch다. status의 products_success/last_success_at은 수집/스테이징 결과이며 DB ACK를 의미하지 않는다. content_changes와 backend의 ACK/재시도/hold를 함께 확인한다.

## 중고 폴링

일반 7200초, 허용된 중고 60초는 이전 주기 완료 후 최소 간격이다. 출처 정책 최소 간격, 요청 원장·robots·429/5xx 대기·월/일/시간 예산이 우선한다. eBay는 기존 ebay_account 서비스 하나에서 일반/Used가 같은 ProviderHTTP·영속 원장·writer lock을 공유한다. 일반/Used 독립 프로세스를 동일 원장으로 중복 실행하지 않는다. 공유 한도는 두 설정 중 보수적인 값이다.

eBay Used는 공식 USED/conditionIds 필터와 getItem을 재사용한다. 최신 매물 탐색과 기존 매물 refresh 범위는 유한하다. polling_capacity가 요청 상한과 24시간 예산으로 연속 주기 가능성을 보여준다. true여도 OAuth·재시도·다른 프로필 사용량 때문에 보장되지 않는다. page_size=3, 검색 1페이지, refresh 1개라면 주기당 상한 5회이므로 60초 연속 상한은 7200회/일이며 일반 검색·OAuth·재시도는 별도 소비한다. 한도가 부족하면 실제 주기가 지연된다. 제공자 한도를 임의 증가시키지 않는다.

기본 ebay_used.json의 schedule.policy_reference는 비어 있으므로 60초는 현재 승인된 운영 설정이 아니다. 정책 및 계정 권한 확인 후 관리자가 근거와 최소 간격을 채운다. 번개장터/중고나라는 접근·데이터 계약 미확인으로 운영 차단을 유지한다.

판매 완료는 원문 SoldOut/itemEndDate 등 증거가 있을 때 ended로 전달한다. 검색 누락·404만으로 판매 완료라 하지 않는다. 예약은 native evidence/extension.listing_status=reserved, purchase_available=false로 구분하지만 현재 v2로는 보류한다. 실제 재고 수량이 없으면 null이며 eBay 추정 수량을 실제 수량으로 바꾸지 않는다.

## 검증의 구분

외부 Books to Scrape는 공식적으로 수집 테스트를 허용하는 가상 서점이며 상용 실상품 검증이 아니다. 이번 로컬 HTTPS 검증은 이름/가격 원문/이미지/URL 3개를 추출했으나 필수 상태·판매처·명시 통화 정규화가 부족해 3개 모두 보류했다. 상품 원문 HTML과 이미지는 영구 저장하지 않고 이미지 URL만 확인했다. 첫 실행의 보고서 인코딩 실패를 수정하여 기존 원장 보존 후 같은 대상만 재검사했고 누적 10회 요청(robots 404 포함)을 기록했다. 상품 변경은 조작하지 않았으므로 실제 외부 가격 변경은 검증하지 않았다.

network=none Docker 랩은 합성 카탈로그 → 로컬 TLS 쇼핑몰 → 실제 discovery/fleet 자식 프로세스 → v2 → HTTP FastAPI/임시 SQLite ACK를 검증한다. JSON-LD/CSS/실제 Chromium JS/XHR, 가격/판매 완료/예약/중복, 503/재시도/리다이렉트를 포함한다. 로컬 벽시계 60초 반복과 테스트 clock의 7200초 반복을 구분한다. 실사이트 장애 유발·가격 변경·2시간 장기 운영은 실행하지 않았다. 팀 DB 코드와 NAS는 변경하지 않았다.

공식 근거: https://sites.toscrape.com/ ; https://books.toscrape.com/ ; https://api.bgzt.guide/ ; https://api.bgzt.guide/api-10619068 ; https://common.joongna.com/static/terms/TermsOfService_new.html ; https://developer.ebay.com/api-docs/buy/static/api-browse.html
