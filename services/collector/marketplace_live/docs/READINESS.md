# 소량 연결 테스트 실행 안내

정정: 현재 해외 Shopping 공급자는 SearchAPI.io가 아닌 Serper.dev입니다.
최신 명령과 키 로딩 방법은 `SERPER.md`를 사용하세요. 이 문서의 SearchAPI
명령은 이전 기록이며 live 진입점에서 차단됩니다. YES24/eBay 안내는 유지합니다.

상품 API 실호출·운영 DB 적재·Push·NAS 배포는 수행하지 않았습니다.
API 키 발급 사실은 확인받았으며 키 값은 읽거나 복사하지 않았습니다.

## 1. 환경변수 입력

저장소 루트 `C:\Users\junse\Python\swproject`의 PowerShell에서 실행합니다.
Python은 의존성이 설치된 기존 `.venv\Scripts\python.exe`를 사용할 수 있습니다.
아래의 `python`은 그 환경의 Python으로 치환하거나 활성화하세요.

```powershell
Set-Location C:\Users\junse\Python\swproject
$collectorPrivateDir = Join-Path $env:LOCALAPPDATA 'KkulPick\collector'
New-Item -ItemType Directory -Path $collectorPrivateDir -Force | Out-Null
Copy-Item services/collector/marketplace_live/lookup.example.json "$collectorPrivateDir\lookup.local.json"
$env:KKULPICK_MARKETPLACE_CONFIG = "$collectorPrivateDir\lookup.local.json"
$env:KKULPICK_MARKETPLACE_STATE_DIR = "$collectorPrivateDir\state"

# 공급자별로 필요한 것만 선택해 실행. 값은 숨김 입력이며 셸 인자에 넣지 않음.
. .\services\collector\marketplace_live\Set-CollectorEnvironment.ps1 -Source yes24_api
. .\services\collector\marketplace_live\Set-CollectorEnvironment.ps1 -Source searchapi_google_shopping
. .\services\collector\marketplace_live\Set-CollectorEnvironment.ps1 -Source ebay_browse
```

YES24는 `YES24_API_KEY`, SearchAPI는 `SEARCHAPI_API_KEY`, eBay는
`EBAY_CLIENT_ID`와 `EBAY_CLIENT_SECRET`입니다. eBay Marketplace는 환경변수가
아니라 설정의 `marketplace_id`이며 생략 시 EBAY_US입니다. SearchAPI의 gl/hl도
설정 값입니다. `.env`를 다른 프로젝트에서 자동으로 읽지 않습니다.

조회 테스트에는 `KKULPICK_BACKEND_TOKEN`이 필요하지 않습니다. 별도의 팀 API
저장 승인을 받은 경우만 위 스크립트에 `-IncludeBackendToken`을 추가합니다.
현재 프로세스 환경만 설정하며 레지스트리·파일·명령행에 키를 기록하지 않습니다.
전체 환경변수나 Docker의 확장된 환경 설정을 로그로 출력하지 마세요.

`lookup.local.json`의 소스별 queries[0], allowed_product_hosts, currencies,
실제 계정의 호출 한도, 권한 reference/만료 시각을 확인합니다. 조회 모드는
rights.allowed_uses에 lookup만 있으면 되며 YES24에 별도 DB 축적 권한을 넣을
필요가 없습니다. 초기 reference/만료 값은 비어 있거나 만료 상태여서 실행이
차단됩니다. 실제 조회 이용조건/승인 기록의 근거를 넣어야 합니다.

SearchAPI는 실제 플랜의 보수적인 요청당 최대 단가 `cost_per_request`,
`max_cost_per_month`, `max_units_per_month`를 반드시 설정합니다. 예제의 0은
유료 호출을 막는 초기값이며, 키 발급만으로 비용 예산을 임의 지정하지 않습니다.
조회 모드는 기존 enabled=false를 내부적으로 일회 활성화하지만 backend 관련
설정은 무조건 false로 덮어쓰며 DB 클라이언트를 생성하지 않습니다.

기존 watch가 같은 키를 사용했다면 동일한 상태 루트/원장을 사용하세요. 새 상태
디렉터리로 갈아타 예산을 초기화하면 안 됩니다. NAS 이전 시 원장 전체를 이관합니다.

## 2. 키 없이 Mock 실행

```text
python -m services.collector.marketplace_live.probe --source yes24_api --mock --max-products 3 --state-dir <mock-state-root>
python -m services.collector.marketplace_live.probe --source searchapi_google_shopping --mock --max-products 3 --state-dir <mock-state-root>
python -m services.collector.marketplace_live.probe --source ebay_browse --mock --max-products 3 --state-dir <mock-state-root>
```

실제 Adapter.search/detail → 정규화 → 필수 필드 검사 → 기존 Outbox.stage를
사용합니다. credential_reader와 공급자 HTTP만 SYNTHETIC으로 대체합니다.
각 공급자는 정상 2개, 누락 1개를 제공하므로 새 mock 상태에서 success=2,
failed=0, held=1, queue_pending=2가 기대 결과입니다. 실제 provider/backend
HTTP는 모두 0입니다. mock-only 경로의 synthetic_only outbox는 운영 Outbox가
읽어 전송하지 못하도록 검사하며, mock flush 자체도 금지합니다.

## 3. 공급자별 사전 확인 및 승인 후 실제 조회

아래 plan 명령은 HTTP·상태 쓰기 없이 설정/키 존재 여부만 확인합니다.

```text
python -m services.collector.marketplace_live.probe --source yes24_api --plan --max-products 3
python -m services.collector.marketplace_live.probe --source searchapi_google_shopping --plan --max-products 3
python -m services.collector.marketplace_live.probe --source ebay_browse --plan --max-products 3
```

**각 공급자에 대해 실제 요청 승인을 별도로 받은 뒤에만** 해당 한 줄을 실행합니다.

```text
python -m services.collector.marketplace_live.probe --source yes24_api --live --max-products 3
python -m services.collector.marketplace_live.probe --source searchapi_google_shopping --live --max-products 3
python -m services.collector.marketplace_live.probe --source ebay_browse --live --max-products 3
```

| 공급자 | 정상 소량 실행의 최대 요청 구성 |
| --- | --- |
| YES24 | 검색 1회(pageSize≤3), 선택된 서로 다른 상품 최대 3개의 상세조회. 추가 페이지 없음 |
| SearchAPI | 검색 1회, 반환 결과 중 처음 최대 3개만 검사. 추가 페이지·상세·merchant URL 접근 없음 |
| eBay | application OAuth 필요 시 1회, 검색 1회(limit≤3), 최대 3개 getItem. 토큰 캐시와 제한된 401 재인증 적용 |

검색 결과가 3개보다 적으면 부족한 수를 채우려고 추가 조회하지 않습니다.
SearchAPI의 서버 반환 개수는 3개로 제한되지 않습니다. 사용자가 선택한 범위대로
한 검색 응답의 처음 최대 3개만 검사하고 나머지 row의 필드를 열거나 정규화·
저장하지 않습니다. 이 선택은 실제 요청 승인을 뜻하지 않습니다.

원장/간격/일일/시간/비용 한도를 그대로 적용합니다. 로컬 요청 간격을 기다리는
것 외에는 실패 HTTP를 자동 재전송하지 않고 종료합니다. 429/불확실 결과는
next_allowed_at과 원장 차감을 보존합니다. 기존 watch의 권한 검사도 완화하지 않습니다.

실제 조회는 상품명·판매처·가격·원문 URL·응답 본문·토큰을 파일/로그로 출력하지
않습니다. 검사 결과와 집계만 last_lookup_summary.json에 저장합니다.
YES24는 이 경로에서 outbox 생성과 backend HTTP가 모두 금지됩니다.

## 4. 결과 읽기와 필드 매핑

결과 JSON의 success/failed/held, hold_reasons, products[].checks,
provider_HTTP_attempts, backend_HTTP_requests, last_collection_at,
last_success_at, last_failure_at을 확인합니다. success는 필수 검사 통과이며
DB 적재 성공을 뜻하지 않습니다. 검색 호출 자체 실패도 failed에 표시되므로
selected_count와 함께 해석합니다. 데이터 보류와 HTTP 실패는 별도로 셉니다.
실조회 종료 코드는 0=전부 통과, 1=보류/실패 결과 있음, 2=사전 차단입니다.
Mock은 의도한 누락 사례가 있어도 테스트 정상 종료로 0을 반환합니다.

| 검사 항목 | 공급자 필드 → 공통 결과 → Observation |
| --- | --- |
| 상품번호 | YES24 itemId / Google product_id / eBay REST itemId → product_number → source_listing_id + variant_key |
| 상품명 | YES24 title / Shopping title / eBay title → name → name |
| 가격 | salePrice / extracted_price / price.value → Decimal 문자열 → price |
| 통화 | 실제 currency / currency / price.currency → currency → currency; 기호·국가로 추정하지 않음 |
| 상태 | 실제 condition / condition / 지원 conditionId 매핑 → condition → condition; unknown/refurbished/open-box를 임의 new/used로 바꾸지 않음 |
| 재고 | 실제 availability / availability / estimatedAvailabilityStatus → availability → availability; 수량 필드는 현재 v2에 없음 |
| 판매처 | seller / seller / seller.username → seller → 현재 v2에서 제외, RAM 검사용 |
| URL | link / 허용 판매처 직접 link / itemWebUrl → url → url; redirect를 따라가지 않음 |

현재 YES24/Shopping 기본 응답에는 필수 통화·SKU·상태·재고가 없을 수 있습니다.
seller까지 검사하며, 빠진 값은 보류하고 운영 수집기에서도 전송하지 않습니다.
판매처가 RAM에 있어도 현재 DB 계약에는 보존되지 않는 점은 별도
SELLER_CONTRACT_PROPOSAL.md를 참고하세요. 팀원 코드/DB는 수정하지 않았습니다.

## 5. 조회와 분리된 팀 DB 전송 테스트

실제 상품 조회는 DB용 파일을 내보내지 않습니다. 저장 허가가 확인된 별도
Observation과 실제 판매처 증거를 묶은 JSON 배열(1~3개)을 운영자가 준비한 뒤에만
사용할 수 있습니다. 각 항목은 `{"observation": {"...": "완전한 v2 본문"},
"seller": "실제 제공된 판매처 이름"}` 형식입니다. 판매처는 사전 검사에만 쓰며
현행 v2 본문에 넣지 않습니다. 이 형식 설명은 완전한 제출 payload가 아닙니다.
누락 필드·누락 판매처·잘못된 source·본문의 알 수 없는 seller 필드는 거부합니다.
이 명령은 공급자 API를 호출하지 않습니다.

```text
python -m services.collector.marketplace_live.delivery_probe --source ebay_browse --plan
python -m services.collector.marketplace_live.delivery_probe --source searchapi_google_shopping --plan
# 별도의 운영 DB 적재 승인을 받은 후에만:
python -m services.collector.marketplace_live.delivery_probe --source ebay_browse --live --payload-file <approved-json-array>
```

YES24는 이 명령의 --live에서도 토큰·설정을 읽기 전에 항상 차단합니다.
해외 소스는 backend_enabled/backend_owner_approved/price_semantics_confirmed,
storage/reuse/systematic_collection 권한과 KKULPICK_BACKEND_TOKEN이 필요합니다.
현재 v2는 seller를 저장하지 않는다는 한계를 결과에 표시합니다.

별도 delivery-probe 큐를 사용해 무관한 운영 outbox를 flush하지 않습니다.
한 호출은 기존 정책대로 POST 최대 1개를 처리합니다. remaining pending이면
같은 payload로 재실행하거나 상태를 검토합니다. run ID/body/key를 유지합니다.
재시도 시 --source나 payload를 바꾸거나 이전 본문을 덮어쓰지 않습니다.

## 6. 상태·Docker·NAS

```text
python -m services.collector.marketplace_live --source ebay_browse --status
```

성공/실패/보류 제품 수, 마지막 수집/성공/실패 시각, provider/DB hold,
최근 조회 요약을 읽기 전용으로 표시합니다. 이전 체크포인트에 새 시각이 없으면
null로 표시하며 과거 수집 시각을 만들어 내지 않습니다. 실제 DB 적용 수는
backend ack 집계로 별도 확인합니다.

deploy/compose.yaml은 도매꾹·YES24·SearchAPI·eBay를 독립 서비스/환경파일/
상태 mount로 나눕니다. 도매꾹 소스와 기존 배포 파일은 변경하지 않습니다.
YES24 서비스는 기본 --plan이며 자동 저장/무한 조회를 시작하지 않습니다.
해외 자동 수집은 별도로 승인된 collection config에만 --watch를 적용합니다.
주기는 최소 7,200초이며 원장과 outbox를 보존합니다.

외부 env_file에는 공급자별 키만 넣습니다. YES24 env에는 backend 토큰을 넣지
않습니다. NAS 상태 디렉터리의 UID/GID 10001 접근과 로컬 파일 잠금/원자적
rename을 확인해야 합니다. 기존 도매꾹 state를 빈 volume으로 교체하지 마세요.
모든 compose 변수는 inactive profile에도 파싱될 수 있으므로 .env.example의
경로 변수를 모두 준비합니다. 비밀파일은 저장소 밖에 두고 접근 권한을 제한합니다.

Docker 실행과 NAS 배포는 미수행입니다. Docker가 없는 이 환경에서는 YAML/
경로/서비스 분리와 PowerShell 구문을 정적으로 점검합니다. 실제 이미지 빌드와
컨테이너·NAS 기동 검증은 해당 환경에서 승인 후 남아 있습니다.
