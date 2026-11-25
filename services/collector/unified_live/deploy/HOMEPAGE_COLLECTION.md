# 홈페이지 URL 기반 HTML 수집 — 로컬 개발 브랜치 안내

기준: `719cb8e8dc6c017d7a8dfde84c2e1a2e59bab176`. 개발 브랜치: `feat/collector-homepage-html-20261125`.
이번 작업은 로컬 커밋 전용이다. GitHub Push·NAS 접속/배포·운영 PostgreSQL 변경은 하지 않았다. 이 브랜치는 별도 승인 전 원격에서 pull할 수 없다.

## 실행되는 경로

`homepage --watch`가 한 URL로 프로필을 만들고 기존 Registry에 등록한 후 기존 `unified_live --provider url --watch`를 실행한다. 별도의 Discovery나 두 번째 스케줄러를 만들지 않았다.

홈페이지 → 실제 HTML 카테고리 링크 → 상품 목록/명시된 다음 페이지·robots에 공개된 사이트맵 → 상세페이지 → 기존 JSON-LD/Microdata/OG/CSS 정규화 → ChangeDelivery → Observation Outbox·Extension 큐 → 기존 백엔드 전송 경로이다.

- `homepage_crawl=true`는 새 홈페이지 탐색을 켜는 명시적 옵션이다. 기존 프로필은 기존 실행 경로와 체크포인트 identity를 유지한다.
- 카페24·고도몰·메이크샵·Shopify는 HTML generator/스크립트/클래스/실제 링크 형태를 근거로 구분한다. 충돌하면 ambiguous이며 플랫폼명만으로 권한이나 데이터 값을 추론하지 않는다.
- 플랫폼별 목록·상세 URL, 명시적 상품 카드 링크, 의미 있는 navigation 카테고리를 따라간다. 같은 출처만 허용하고 로그인/회원/장바구니/결제/API/비밀 query·nofollow 링크는 제외한다.
- 사이트맵은 robots.txt가 실제 공개한 같은 출처 URL만 사용한다. 외부 loc·DTD/ENTITY를 거부한다. 무한한 날짜·페이지 URL을 합성하지 않는다.
- 일반 상품은 기본 7,200초이며 제공자의 더 긴 최소 주기가 우선한다. `max_pages_per_cycle`은 홈페이지 모드의 전체 탐색 페이지 한도, `max_products_per_cycle`은 발견한 상세 상품 한도이다. 전체 카탈로그를 매 주기 빠짐없이 확인한다는 의미가 아니다.
- 기존 요청 원장·robots·rate/budget/Retry-After·체크포인트·소스 lock·Outbox를 그대로 사용한다. 네트워크 결과 불확실 hold를 초기화하거나 자동 우회하지 않는다.
- HTML/CSS 오류 항목은 격리하고 다음 작업을 계속한다. CAPTCHA·로그인 요구는 해당 소스를 중지한다. 브라우저 abort가 원래의 예산 대기 오류를 숨기지 않도록 원인을 보존한다.
- JSON-LD가 우선이고 명시된 OG 가격·통화, 상품 영역 제목·동일 상품명 alt 이미지, 검토된 CSS를 보조로 쓴다. EUC-KR/CP949는 HTTP/meta에 명시된 경우만 엄격히 해독한다. 임의 인코딩·가격·통화·재고·신품 상태를 생성하지 않는다.
- 새 홈페이지 모드에서 seller_name은 백엔드 v2의 추가 필수값으로 강제하지 않는다. 없는 판매처명은 None이며 source URL을 법적 상호로 만들지 않는다. 이전 모드의 판매처 품질 정책은 유지한다.
- Observation 조건을 충족하고 전송 권한이 있는 상품만 기존 큐에 들어간다. Extension은 Observation 처리 후 별도 ACK·재시도·중복 방지를 사용한다. 원문에 없는 필드는 생략한다.

## 외부 검증 범위와 제한

상업 쇼핑몰의 저장·재사용 권한을 임의 생성하지 않았다. 공개적으로 수집기 시험을 허용하는 **실제 외부 데모 사이트** 두 곳에서 홈페이지부터 탐색했다. 이 사이트의 상품은 허구의 테스트 카탈로그이며 실제 판매 실적이나 상업몰 운영 성공으로 보고하지 않는다.

- [Oxylabs sandbox](https://sandbox.oxylabs.io/): 공개 홈페이지가 수집 솔루션 테스트 사용을 허용한다. 홈페이지 → 목록 → 상세 3건에서 상품명·실제 OG 가격/통화·이미지 URL을 추출했다. 원문에 신품·중고 상태가 없어 3건 모두 Observation 보류이다.
- [web-scraping.dev](https://web-scraping.dev/): 공개 스크래핑 학습/시험 사이트이다. 홈페이지부터 상세 3건을 방문했으나 AggregateOffer 가격 범위·여러 옵션이 있다. 최저가를 단일 옵션 가격으로 바꾸지 않아 3건을 보류했다.
- 실제 외부 상품의 유효 Observation·Extension ACK·운영 DB 적재는 모두 0건이다. 사이트 접근 성공과 필수 필드 충족/DB 반영 성공을 구분한다.
- 카페24·고도몰·메이크샵·Shopify 인식은 이 작업에서 합성 템플릿으로 회귀 검증했다. 해당 플랫폼의 상업몰 실수집 권한/성공을 확인한 것은 아니다.
- 실제 브라우저 JavaScript 실행 및 HTTP ACK는 격리 Docker의 합성 쇼핑몰에서 검증했다. 외부 JavaScript 쇼핑몰 검증으로 합산하지 않는다.
- 요청 원장을 보존했고 전송은 껐다. 테스트 목적의 제한적 자료 확인을 상업적 재사용·주기 수집 승인으로 해석하지 않는다. 수치·정확한 오류는 HOMEPAGE_VALIDATION_RESULTS.json 참고.

현재 가장 큰 운영 계약 장애는 `condition=unknown` 표현 불가다. 그 값이 없는 사이트에서 new를 만들거나 기존 API 기본값 new에 기대어 누락 전송하지 않는다. 별도 HOMEPAGE_CONTRACT_GAPS.md에 변경안을 정리했다.

## URL 하나로 등록·실행

아래는 관리자가 향후 실행할 명령이다. 이번 작업에서는 운영 대상으로 실행하지 않았다. API 키는 필요하지 않지만 **실제 수집·저장·재사용 권한 정책**은 필요하다.

```bash
# 먼저 disabled 예시 정책을 비공개 운영 설정으로 복사하고 실제 권한/한도/만료를 확인한다.
python -m services.collector.unified_live.homepage --url https://approved-shop.example.com/ --policy /run/homepage-policy.json --state-dir /state --plan
# 등록만: HTTP를 요청하지 않는다. 다른 등록 프로필은 덮어쓰지 않는다.
python -m services.collector.unified_live.homepage --url https://approved-shop.example.com/ --policy /run/homepage-policy.json --state-dir /state --register
# 권한·실행 승인 확인 후 한 명령으로 등록하고 기존 워커를 지속 실행한다.
python -m services.collector.unified_live.homepage --url https://approved-shop.example.com/ --policy /run/homepage-policy.json --state-dir /state --watch
```

정책 파일의 필수 운영 판단:

- `enabled=true`, rights.reference/terms_reference/expires_at, allowed_uses의 lookup/systematic_collection/storage/reuse. 실제 증빙 없이 값을 승인 상태로 채우지 않는다.
- 백엔드 대기열까지 만들려면 기존 backend_enabled/backend_owner_approved/price_semantics_confirmed가 실제 확인돼야 한다. 기본 예시는 모두 false이며 이를 자동 해제하지 않는다.
- 원재료/알레르기 원문 보관은 evidence_storage와 해당 사용권한을 별도 확인한다. 기존 식품 게이트를 유지한다.
- requests_per_hour/requests_per_24h/request_interval_seconds, 탐색/상품 한도와 provider_min_interval_seconds는 사이트 정책에 맞춘다.
- 스킨이 특수하면 기존 `selectors`를 제공한다. 다중 옵션/집계 오퍼는 별도 옵션 식별 근거가 필요하며 자동 분해하지 않는다.

초기 로컬 수집·전송 준비 시 `COLLECTOR_RUN_APPROVED=yes`, **`COLLECTOR_DELIVERY_APPROVED=no`**로 둔다. 유효 상품은 허가된 대기열에 보관하되 실전송은 하지 않는다. --plan/--register 자체는 외부 HTTP를 수행하지 않는다.

## 향후 NAS 설정 — 지금은 배포 금지

새 선택형 Compose profile `homepage`를 추가했다. 기존 719cb8e 서비스 8개를 재시작하거나 수정하지 않았다.

```ini
COLLECTOR_HOMEPAGE_URL=https://approved-shop.example.com/
COLLECTOR_RUN_APPROVED=yes
COLLECTOR_DELIVERY_APPROVED=no
COLLECTOR_BACKEND_TRANSPORT=internal_http
COLLECTOR_BACKEND_BASE_URL=http://api:8000
# 실제 backend의 등록 목록과 동일한 복사본. 자동 허용 목록 확장이 아님.
COLLECTOR_BACKEND_CATALOG_HOSTS=approved-shop.example.com
COLLECTOR_BACKEND_CATALOG_CURRENCIES=KRW
```

- `CONFIG_DIR/homepage-policy.json`을 `/run/homepage-policy.json:ro`로, `MASTER_STATE_DIR/homepage`를 `/state`로 연결한다. 시크릿은 기존 backend token 파일만 사용한다. 사이트 API 키는 마운트하지 않는다.
- JavaScript가 필요한 허용 사이트는 정책 render_javascript=true와 기존 browser.override.yaml의 homepage 서비스를 사용한다. 표준 Chromium이며 stealth·CAPTCHA/로그인 우회가 없다. 외부 CDN·POST·웹소켓 등 허용되지 않은 리소스가 필요한 사이트는 보류한다.
- 선택형 internal-http.override.yaml에도 homepage 서비스를 추가했다. 실제 관리자 설정에 따라 사용하고 기존 운영 Docker 네트워크를 임의 변경하지 않는다. 원격 HTTP 주소·리다이렉트·토큰 처리 원칙은 719cb8e와 같다.
- 다수 사이트는 기존 Fleet 또는 별도 collector 서비스로 격리한다. Fleet은 기존 Discovery 검증·local grant를 통과한 사이트의 approval에 homepage_crawl=true와 실제 시작 URL/한도를 지정해야 한다. homepage --register만으로 DiscoveryStore 등록·Fleet 활성화가 자동 완료되는 것은 아니며, 단일 URL은 --watch가 직접 실행 경로다. 별도 Compose 인스턴스는 상태·heartbeat 볼륨을 분리한다. 동일 소스에 동시 writer를 띄우지 않는다.
- `registry.json`, homepage_profiles 설정, 소스별 URL 체크포인트·요청 원장·backend_outbox.json·content_checkpoint.json·delivery_extras.json을 보존한다. 권한/프로필/context가 다른 기록은 자동 덮어쓰기나 reset하지 않는다.
- backend의 URL host/currency/image-host 목록 및 Observation·extensions·listing-checks API가 실제 배포돼 있어야 한다. 준비가 완료된 뒤 별도 전송 승인을 받는다.
- 미래 배포 전 `docker compose --profile homepage ... config`로 정적 검증하고 새 수집기만 선택 갱신한다. 이번 로컬 브랜치는 Push하지 않았으므로 **별도 Push·배포 지시 전 NAS에서 사용하지 않는다.**

## 재검증

회귀 테스트는 기존 전체 수집기 테스트에 홈페이지 경로·플랫폼 분류·사이트맵·중복/가격/재고 변경·7200초 스케줄·문자셋·challenge 중단·브라우저 예산 오류 보존을 추가했다.

테스트 전용 브라우저 이미지에서:

```bash
COLLECTOR_NETWORK_LAB=synthetic_only python -m services.collector.unified_live.devtest.homepage_lab
```

network_mode=none에서 테스트 TLS 쇼핑몰, 실제 Chromium, 별도 FastAPI/SQLite fixture만 실행한다. 프로덕션 SafeHTTP에는 사설 IP 예외나 인증서 검증 비활성화를 추가하지 않았다. 테스트 전용 loopback pin은 이 명시적 lab 모듈에만 있다. 이 fixture가 실제 팀 PostgreSQL 트랜잭션의 동등성을 증명하는 것은 아니다.
