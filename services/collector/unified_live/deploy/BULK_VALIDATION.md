# 대량 후보 발굴 → 허용 대상 배치 검증 → 기존 Fleet — 2026-11-25

## 이번 실제 결과

국내 중심 디렉터리·Cafe24/MakeShop/Shopify 공개 자료에서 후보를 모았다. 초기 158개 DNS 도메인 중 광고/소개 링크가 섞인 자료의 76개 도메인을 제외하고 플랫폼 카테고리 자료를 추가해 고유 후보 146개를 확보했다. 실제 공개 DNS 확인이지 146개 사이트의 상품 페이지 요청 또는 한국 소재지 확인이 아니다. 해외몰과 서비스·중고 거래 후보가 포함되며 국가 분류는 미확정이다. 고도몰 자료 경로는 네트워크 결과 불확실 hold로 중단해 재요청/우회하지 않았고 분류를 임의 생성하지 않았다.

상품 검증은 공개적으로 테스트를 허용한 외부 데모 3개를 같은 배치로 실행했다. Books to Scrape 3개, TestingURL 1개, WebScraper 3개에서 이름·가격·이미지 URL·상품 URL 추출을 확인했다. 필수값 통과는 0개다. 상태·판매처 및 일부 통화/재고 상태 해석이 부족해 전송하지 않았다. 상용몰 실상품 성공·실제 중고 매물 조회·자동 활성화는 모두 0개다. 성공 CSV는 헤더만 있다. 이를 로컬 fixture 성공과 합치지 않았다.

## 재사용 경로와 권한

bulk_discover는 기존 MetadataHTTP/공개 HTTPS·DNS/robots 정책을 사용한다. 운영자가 지정한 공개 publisher URL/선택자만 조회하며 로그인/유료 전체목록/비공개 API/HTTP 전환을 우회하지 않는다. publisher별 로컬 metadata_read_approved와 상품 test_allowed/저장·재사용 권한은 별개다. 같은 publisher 도메인은 단일 writer/요청 원장을 공유하고, 다른 도메인은 최대 4개 동시 실행한다. DNS 검증 후보는 비활성 Discovery 등록만 가능하다.

bulk는 기존 Parser/analysis/표준 Chromium과 Registry/Discovery/Fleet registration을 사용한다. 승인된 시작/카테고리/사이트맵/목록/상세를 유한 탐색한다. 상품 오류는 다음 상품으로, 사이트 오류는 다음 사이트로 진행한다. source_requests는 이번 실행의 증가분이며 lifetime_source_requests는 영속 원장의 누적이다. uncertain/robots/접근 차단/요청 제한은 우회하거나 원장을 삭제하지 않는다.

상태: DISCOVERED → ACCESS_REVIEW 또는 PERMITTED → PARSER_READY → VERIFIED/INCOMPLETE/BLOCKED/FAILED. PERMITTED는 permission_status의 범위(lookup_test_only 또는 storage_reuse_confirmed)와 함께 읽는다. ACTIVE는 실제 품질 통과, 로컬 activation_approved=true, 유효 systematic_collection/storage/reuse 권한, backend owner/price 승인 및 실행 가능한 프로필/등록을 모두 만족한 경우다. ACTIVE는 아직 DB ACK라는 뜻이 아니다. 별도 전송 스위치가 있다. 외부 데모는 저장 권한을 추론하지 않고 자동 활성화 대상에서도 제외한다.

## 배치 실행

예제 JSON은 기본 비활성/만료 상태다. 운영자가 실제 근거를 확인한 설정만 Git 밖에 작성한다. API 키·토큰은 JSON이 아니라 기존 환경변수/시크릿으로 관리한다.

```sh
python -m services.collector.unified_live.bulk_discover --publishers /run/publishers.json --state-dir /state/directories --output /outputs/candidates.json
# 허용한 공개 metadata만 읽으려면 위 명령에 --live 추가
python -m services.collector.unified_live.bulk --candidates /outputs/candidates.json --approvals /run/approvals.json --state-dir /state/bulk --output-dir /outputs
# 허용된 실제 일괄 조회: --live
# 반복/저장/재사용까지 승인된 상용 소스의 프로필 등록: --live --activate
```

입력 candidates는 url/domain/reference/platform/sample_kind를 가진 JSON 배열이다. bulk_discover 출력은 공개 DNS 존재 확인을 포함한다. sample_kind는 external_commercial_candidate / external_demo / local_fixture로 구분한다. 권한 파일은 정확한 domain별 mapping이며 reference/terms_reference/expires_at/allowed_uses/allowed_hosts/test_allowed/start_urls/selectors와 요청 한도를 포함한다. API가 있는 eBay·YES24·도매꾹, 접근 미승인 국내 중고 플랫폼을 일반 HTML로 우회하지 않는다.

## 성공 프로필 지속 실행 연결

생성물: discovery/discovery_registry.json, registry/registry.json, profiles/<marketplace-id>.json, fleet-grants.json, domains/*/url_request_ledger.json, batch_results.json. 기존 프로필과 다른 변경은 임의 덮어쓰지 않고 review로 남긴다. 기존 worker/outbox/history는 초기화하지 않는다.

```sh
python -m services.collector.unified_live.fleet --state-dir /state/fleet --discovery-state /state/bulk/discovery --grants /state/bulk/fleet-grants.json --watch
```

기존 Compose fleet/discovery/browser 구성을 재사용한다. batch의 state와 생성 grants **부모 디렉터리**를 컨테이너에 마운트하고 위 경로를 설정해야 한다(단일 파일 bind mount는 atomic 교체를 반영하지 않을 수 있음). Fleet의 기존 restart:unless-stopped와 --watch가 자식 실행·재시작·중복 실행 방지를 담당한다. batch는 유한 검증/등록 명령이고 스스로 운영 백엔드 전송을 하지 않는다. 등록 후 Fleet가 권한·예산·스케줄을 다시 검사한다. 많은 미승인 후보의 평가도 lock 안에서 한 tick당 registry 1회 저장으로 처리한다.

일반 최소 7200초, 허용 중고 최소 60초이며 provider_min_interval_seconds/robots/예산이 우선한다. eBay 일반/Used는 기존 ebay_account 서비스 하나에서 요청 예산을 공유한다. 키 보유만으로 조회·저장·60초 반복 권한을 승인하지 않는다. 번개장터는 파트너 계약/키 및 데이터 범위가, 중고나라는 사전 승낙/승인 API가 필요하다.

```ini
COLLECTOR_BACKEND_TRANSPORT=internal_http
COLLECTOR_BACKEND_BASE_URL=http://192.168.0.254:8000
COLLECTOR_RUN_APPROVED=yes
COLLECTOR_DELIVERY_APPROVED=yes
KKULPICK_BACKEND_TOKEN_FILE=/run/secrets/kkulpick_backend_token
```

주소는 관리자가 실제 환경에 맞춘다. 이번 작업은 NAS/운영 PostgreSQL에 접근하지 않았다. 기존 서비스 일괄 재시작, 네트워크 임의 변경, down -v/reset은 하지 않는다. Observation v2/Outbox/ACK/재시도와 외부 HTTPS/TLS/SSRF 정책은 유지한다.

## 출력과 검증

export는 korean-mall-bulk-report.md / korean-mall-candidates.csv / korean-mall-success.csv / korean-mall-blocked.csv / used-marketplace-report.md / collector-runtime-guide.md를 함께 생성한다. 필수 CSV 열에 sample_kind·country_scope·robots_status 등을 추가해 출처와 제한을 구분한다. 성공 파일은 VERIFIED/ACTIVE 상용 후보만 포함한다. CSV 수식 삽입을 방어한다. 상품 원문/사진·개인정보를 보고서에 저장하지 않는다.

Python suite는 외부 소켓을 차단한다. devtest.bulk_lab은 network=none에서 합성 카탈로그 → 두 도메인 실제 로컬 TLS 상품 → Batch/프로필/Fleet grants → 실제 discovery/Fleet/자식 프로세스 → HTTP FastAPI/임시 SQLite ACK를 검증한다. 가격 변경·판매 완료·예약 보류·중복·503 재시도·리다이렉트 차단·실제 60초 반복과 7200초 테스트 clock을 포함한다. 이를 실제 중고 플랫폼 조회나 상용 가격 변경 검증으로 집계하지 않는다.

공식 허용/조사 근거: https://sites.toscrape.com/ ; https://testingurl.dev/ ; https://webscraper.io/test-sites ; https://api.bgzt.guide/ ; https://common.joongna.com/static/terms/TermsOfService_new.html

## 남은 조건

상용 146개 후보의 개별 상품 테스트·저장·재사용·요청 한도 근거는 아직 확인되지 않았다. 현재 사이트별 ACCESS_REVIEW 이유가 동일한 것은 이를 무단 상품 요청으로 추정하지 않았기 때문이다. 필수 condition/seller 등이 없는 경우 팀 API의 unknown 상태/판매처 선택성 확장이 필요하며 해당 팀원 코드는 변경하지 않았다. 원문에 없는 상태·통화·판매처·재고를 임의 생성해 성공 건수를 올리지 않는다. 고도몰 분류와 한국 소재지 확인은 추가 근거가 필요하다.
