# 중고 상품 수집 프로필

기존 수집기 파일을 수정하지 않고 eBay Used와 국내 중고시장 Mock을 추가한다.
기본 동작은 사전 계획이며 상품 API/팀 API를 호출하지 않는다.

## 구현 범위

| 프로필 | 실행 상태 | 공통 규격 |
| --- | --- | --- |
| ebay_used | 기존 Production OAuth/Browse/getItem/Worker/Outbox 재사용. 별도 승인 및 유효 권한 설정 후 실행 가능 | 기존 source=ebay_browse, ID/key 그대로, used 상품만 v2 생성 |
| bunjang | 공식 제휴 Open API는 확인했지만 이 프로젝트의 계약/권한/키가 없음. 운영 경로 없음 | 합성 canonical DTO와 공식 카탈로그 필드 Mock만 제공. DB 전송 금지 |
| joongna | 공식 상품 수집 API entitlement 및 저장/재사용 승인 미확인. 운영 경로 없음 | 합성 canonical DTO만 제공. 실제 API 규격이라고 주장하지 않음. DB 전송 금지 |

eBay 검색은 buyingOptions:{FIXED_PRICE},conditions:{USED},conditionIds:{2750|2990|3000|3010|4000|5000|6000}를
사용한다. broad USED 필터만 신뢰하지 않고 상세조회 후 기존 상태 정규화 및 used 조건을 다시 검사한다.
신품은 used 범위 밖으로, 리퍼/개봉품/부품용은 상태 계약 미지원으로 보류한다.
이전 eBay 상태 보완의 Graded/Ungraded 보호, 종료 시각, LIMITED_STOCK, 재고 충돌 검사를 그대로 재사용한다.
확정 재고 미상은 null이고 추정치/임계값을 확정 수량으로 바꾸지 않는다.
--plan은 주기 수집의 요청 예산·페이지 크기·재시도 정책을 표시한다. 이전 최대 5회 소량 조회 probe와
다른 실행 모드이며, 주기 예산에는 OAuth와 재시도가 모두 포함된다. 예제는 주기 6/시간 12/24시간 100회이다.
이 예산 설정 자체는 실제 실행 승인이 아니며 공급자의 계정 할당량과 일치하는지 운영자가 확인해야 한다.

## 실행 명령 (저장소 루트)

```powershell
Set-Location C:\Users\junse\Python\swproject
$python = '.\.venv\Scripts\python.exe'
$state = 'C:\기존설정\marketplace-state' # 기존 ebay_browse 폴더의 부모 경로
$profile = 'C:\비공개설정\ebay-used.local.json'
$keys = 'C:\Users\junse\Python\ai-shopping-search-unified\.env'

# 키가 필요 없는 오프라인 Mock. 실제 상태와 별도 디렉터리 사용.
& $python -m services.collector.used_market_live --provider ebay_used --mock --state-dir C:\Mock상태경로
& $python -m services.collector.used_market_live --provider bunjang --mock --state-dir C:\Mock상태경로
& $python -m services.collector.used_market_live --provider joongna --mock --state-dir C:\Mock상태경로

# 키 값은 출력하지 않음. 실제 네트워크 호출 없음.
& $python -m services.collector.used_market_live --provider ebay_used --plan --config $profile --env-file $keys
& $python -m services.collector.used_market_live --provider ebay_used --status --state-dir $state
& $python -m services.collector.used_market_live --provider bunjang --status --state-dir C:\Mock상태경로
& $python -m services.collector.used_market_live --provider joongna --plan
```

ebay_used.example.json을 Git 추적 밖의 비공개 설정으로 복사한다. collection_profile=ebay_used와
source=ebay_browse를 모두 유지한다. 기본 enabled=false, DB/소유자/가격 확인 false, 권한 근거 없음이다.
실제 수집 승인 후에만 enabled를 켜고 조회+주기 수집 권한 근거와 유효기간을 기재한다.
키 발급과 이전 소량 조회 승인은 체계적 수집·DB 저장/재사용 허가를 대신하지 않는다.
DB 전송은 기존 storage/reuse 권한, 가격 기준 확인, backend_owner_approved 및 토큰 인증을 모두 요구한다.
YES24 등 다른 공급자의 권한 설정에는 영향을 주지 않는다.

```powershell
# 별도 실제 수집 승인 및 권한 검토 후에만 실행. 이번 개발에서는 실행하지 않음.
& $python -m services.collector.used_market_live --provider ebay_used --watch --config $profile --env-file $keys --state-dir $state
# 한 번의 작업 tick만 실행; OAuth/요청 간격 때문에 한 주기 완료와 같지 않음.
& $python -m services.collector.used_market_live --provider ebay_used --once --config $profile --env-file $keys --state-dir $state
```

--watch는 기존 Worker의 모든 작업이 끝난 시점부터 최소 7200초 후 다음 주기를 시작한다.
시간별/24시간별/주기별 요청 예산, 요청 간격, 401 복구, Retry-After, 불확실 결과의 지연,
중복 ID, 영속 작업 재개 및 Outbox 재시도를 재사용한다. 마지막 수집/성공/실패 시각과 상품 성공/보류/실패,
provider_failed_actions/provider_errors, hold, 대기열 상태는 --status에서 확인한다.
상품 성공은 기존 Worker 기준 대기열 준비 결과이며 DB 적재 성공과 같지 않다. backend_states를 함께 확인한다.
국내 Mock의 draft_ready는 정규화 초안 완성 수이며 운영 성공 수가 아니다. 계약이 없어 모든 초안은 보류된다.
status의 last_mock은 합성 결과이며 실제 수집 시각과 분리된다.

## 상태와 예산 보존

기존 marketplace 상태 루트를 반드시 그대로 지정한다. 다른 디렉터리를 만들어 기존 사용량을 우회하지 않는다.

- root/ebay_browse/request_ledger.json: 일반 eBay와 Used가 공유하는 기존 요청 기록.
- root/ebay_browse/lock: 계정 예산의 동시 변경을 막는 기존 writer lock.
- root/ebay_used/ebay_browse/checkpoint.json 및 backend_outbox.json: Used 전용 작업/대기열.
- root/mock-only/{provider}: 운영 전송이 불가능한 합성 테스트 결과만 보관.

일반 eBay와 Used를 같은 계정/상태 루트에서 동시에 실행하지 않는다. 기존 코드가 Used를 모르는 상태에서
별도 원장으로 예산을 두 배로 사용하는 것을 방지하기 위해 Used 실행은 기존 eBay lock도 소유한다.
동시 실행은 안전하게 차단되며 도매꾹/YES24/Serper 및 국내 Mock의 lock/상태에는 영향을 주지 않는다.
기존 eBay 대기열은 이동/초기화/자동 재작성하지 않는다. 그 대기열의 재전송은 일반 eBay 프로필에서 처리한다.
여러 NAS/호스트로 계정을 분산할 경우 이 파일 잠금만으로 전역 한도를 관리할 수 없으므로 단일 writer를 유지한다.

## 종료·삭제 처리

eBay는 검증된 itemEndDate 경과를 ended, OUT_OF_STOCK을 out_of_stock으로 구분한다.
검색에서 사라짐, 404/410, 403, 네트워크 오류만으로 판매 완료/삭제라고 단정하지 않는다.
그 경우 기존 값을 덮어쓰지 않고 실패/보류 기록과 기존 복구 정책을 유지한다.
기존 eBay 상품의 재조회 대상 목록/변경 피드가 없는 검색 기반 수집은 사라진 상품의 삭제를 완전히 탐지하지 못한다.
추후 승인된 refresh/feed 및 팀 tombstone 계약이 필요하다.

국내 canonical Mock에서 active=available, sold/deleted/inactive=ended이며 sale_status는 따로 보존한다.
reserved/unknown은 구매 가능 여부 미상으로 보류한다. 이 규칙은 향후 승인된 공급자 상태를 받은 경우의 초안이다.
실제 DOM/404/상품 누락으로 상태를 추측하는 코드나 DB DELETE는 없다.
DELETED는 공개 노출 중단·보유기간에 따른 제거가 필요하므로 단순 ended 저장만으로 삭제 의무가 해결되지 않는다.

## NAS Docker 준비

deploy/compose.ebay.yaml은 독립 eBay Used 컨테이너이며 기본 명령은 --status이다.
deploy/compose.mock.yaml은 국내 Mock 두 컨테이너로, 각각 network_mode=none 및 독립 named volume을 사용한다.
JSON 표기는 YAML 문서로 유효하며 Python 표준 JSON 파서로도 정적 검증할 수 있다.
이미지는 코드/공개 예제만 COPY하고 .env/운영 데이터/테스트 파일을 build context에서 제외한다.
UID 10001, 읽기 전용 루트, 별도 /state, SIGTERM 유예, 로그 용량 제한을 설정했다.

NAS에서 EBAY_ENV_FILE, MARKETPLACE_STATE_DIR, USED_CONFIG를 외부 경로로 지정하고 bind 상태 디렉터리를
UID 10001이 읽고 쓸 수 있도록 운영자가 준비한다. 기존 상태를 삭제하거나 새 빈 원장으로 대체하지 않는다.
KKULPICK_BACKEND_TOKEN은 DB 전송 별도 승인 후 외부 env 파일로만 제공한다.

```sh
# NAS 실행/이미지 빌드는 별도 승인 후. 저장소 루트 기준.
docker compose -f services/collector/used_market_live/deploy/compose.mock.yaml up --build
docker compose -f services/collector/used_market_live/deploy/compose.ebay.yaml config
docker compose -f services/collector/used_market_live/deploy/compose.ebay.yaml run --rm ebay-used
# 수집 승인 후에만 기본 status 명령을 watch로 변경하여 실행.
docker compose -f services/collector/used_market_live/deploy/compose.ebay.yaml run --rm ebay-used python -m services.collector.used_market_live --provider ebay_used --watch
```

기존 도매꾹/YES24/Serper Docker 구성은 수정하지 않았다. 별도 compose로 함께 관리할 수 있다.
개발 환경에는 Docker CLI/daemon이 없어 이미지 빌드/실제 컨테이너 실행은 검증하지 못했다.
정적 구성 검사와 동일 Python 진입점의 오프라인 실행으로 검증했으며 NAS 배포는 하지 않았다.
