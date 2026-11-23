# eBay 상세조회 보충 및 소량 재검증

## 확인한 원인과 수정

지난 실제 검증 결과는 OAuth 1회 + 검색 1회, 상품 3개 중 성공 0 / 보류 3이었다.
세 상품 모두 availability가 없거나 해석되지 않았고, 두 상품은 condition도 해석되지 않았다.
당시 원본 상품 데이터는 저장하지 않아 정확한 conditionId/문자열을 소급 판단할 수 없다.
기존 검색 응답 전용 작업 스크립트는 getItem을 호출하지 않았다.

공식 검색 ItemSummary에도 condition과 conditionId가 정의되어 있다. 검색 결과가 이 필드를
항상 채운다거나 estimatedAvailabilities까지 제공한다고 가정하지 않는다. 저장소의 Adapter.detail,
Worker 상세 작업, bounded_lookup 상세조회 경로를 재사용한다. eBay 상세조회 ID를 호출 전에
검증하고 응답 ID가 요청 ID와 다르면 거부한다. 상세 응답에 빠진 최신 가격/재고를 검색값으로
덮어 채우지 않는다. 기존 요청 예산, 영속 원장, 체크포인트, 재시도, 중복 키 및 7200초 주기를 유지한다.

conditionId=1000 → new. 2750/2990/3000/3010/4000/5000/6000 → used이며 세부 등급은 RAM
condition_detail에 구분한다. Graded/Ungraded는 마모 상태와 다르므로 보류한다.
카테고리별로 의미가 달라지는 2750/3000/4000에 상태 문자열까지 없으면 보류한다.
ID가 아예 없을 때만 미국 사이트의 정확한 공식 문자열로 보충한다. 명시적인 null/미지 ID,
알려진 ID와 알려진 문자열의 충돌은 보류한다. new other/open box(1500), 결함 신품(1750),
각종 refurbished(2000/2010/2020/2030/2500), parts(7000)는 별도 세부 상태로 보존하지만
현 v2가 그 정보를 전달할 수 없어 보류한다. 단순 new/used로 위장해 전송하지 않는다.

IN_STOCK/LIMITED_STOCK → available, OUT_OF_STOCK → out_of_stock.
itemEndDate가 관측 시각 이전이면 ended. 종료 시각 오류, 모르는 상태, 구매 가능/불가 충돌,
명시 상태와 추정 수량의 모순은 보류한다. IN_STOCK과 LIMITED_STOCK은 구매 가능 판정이 같으므로
혼재해도 허용한다. 수량만 있고 상태가 없으면 구매 가능으로 추측하지 않는다.

stock_quantity는 항상 null이다. eBay의 estimatedAvailableQuantity/estimatedRemainingQuantity와
MORE_THAN 임계값은 실제 확정 수량이 아니다. RAM quantity_estimates에 배송 옵션별로 남기고,
합산하거나 0/1로 채우지 않는다. 새 메타데이터는 v2 body에 추가하지 않으며 원래 observation_key
계산과 이미 저장된 body를 변경하지 않는다. 판매처도 현 v2 계약상 RAM 검사 대상이다.

## 오프라인 실행

PowerShell, 저장소 루트에서 실행한다. 다음 mock 명령은 키가 필요 없으며 외부 HTTP와 DB를 사용하지 않는다.
예제 상품 3개 중 완전한 2개는 전송 불가 synthetic 대기열에, 재고 상태가 빠진 1개는 보류된다.

```powershell
Set-Location C:\Users\junse\Python\swproject
.\.venv\Scripts\python.exe -m services.collector.marketplace_live.probe --source ebay_browse --mock --max-products 3 --state-dir C:\Users\junse\Documents\Codex\2026-11-21\swproject-services-collector-domeggook-live-api\work\ebay-offline-example
```

## 실제 소량 재검증 준비 (현재 실행 금지, 별도 승인 필요)

1. ebay.lookup.example.json을 Git 추적 밖의 비공개 ebay.lookup.local.json으로 복사한다.
2. rights.reference에 실제 조회 권한 근거, allowed_uses에 lookup, expires_at에 확인된 유효기간을 입력한다.
   배포/저장 권한을 주장하는 예제 값이나 가짜 계약을 넣지 않는다. enabled/backend_enabled 및
   backend_owner_approved/price_semantics_confirmed는 예제의 false 그대로 둔다. probe만 조회 권한으로 작동한다.
3. 기존 비공개 .env 경로를 명시한다. EBAY_CLIENT_ID, EBAY_CLIENT_SECRET만 읽는다.
   같은 키의 중복, 빈 값, 프로세스 환경과의 충돌은 중단하며 키를 출력하지 않는다.
   파일을 Git에 추가하거나 환경변수 전체를 출력하지 않는다.
4. --plan은 네트워크 요청 없이 권한/키 존재 여부, Production, EBAY_US, 검색어,
   OAuth 최대 1 + 검색 1 + getItem 최대 3 = 총 최대 5회를 표시한다.
   비용은 설정 예산이며 공급자 청구액 확인을 의미하지 않는다. 예제의 0은 무료 보장이 아니다.

```powershell
Set-Location C:\Users\junse\Python\swproject
$ebayConfig = 'C:\비공개설정경로\ebay.lookup.local.json'
$ebayEnv = 'C:\Users\junse\Python\ai-shopping-search-unified\.env'
.\.venv\Scripts\python.exe -m services.collector.marketplace_live.probe --source ebay_browse --plan --config $ebayConfig --env-file $ebayEnv --max-products 3
```

계획 결과 확인 후 **새로운 최대 5회 조회 승인을 받은 경우에만** 아래 명령을 실행한다.
지난 OAuth+검색 최대 2회 승인을 재사용하지 않는다. 기존 원장/대기열을 삭제하거나 초기화하지 않는다.
최초 상세조회 재검증용 독립 상태 디렉터리를 사용하고 이후 동일 검증의 재개에는 같은 원장을 보존한다.
서로 다른 상태 디렉터리도 eBay 계정 한도를 공유하므로 기존 호출량을 합쳐 확인한다.

```powershell
# 새 승인 후에만 실행. DB 전송 없음, 상세조회 최대 3개, 오류 시 중단, 재전송/401 재인증 없음.
.\.venv\Scripts\python.exe -m services.collector.marketplace_live.probe --source ebay_browse --live --config $ebayConfig --env-file $ebayEnv --max-products 3 --state-dir C:\Users\junse\Documents\Codex\2026-11-21\swproject-services-collector-domeggook-live-api\work\ebay-detail-approved
```

lookup은 backend 클라이언트/Outbox를 생성하지 않는다. provider_HTTP_attempts는 실제 원장 증가량이며,
provider_detail_calls는 상세 논리 작업 수이다. success는 조회 및 검사가 성공했다는 뜻이며 DB 적재가 아니다.
held, failed, hold_reasons 및 products[].checks/evidence로 원인을 확인한다. 원본 상품, 판매처명, 토큰은
lookup 결과 파일에 기록하지 않는다. OAuth 실패/검색 실패/상세 실패/429/불확실 오류 시 남은 호출을 중단한다.
일반 Worker의 기존 재시도 정책은 유지하고, eBay 소량 probe에만 인증 재시도를 끈다.

## 공식 근거

- Browse 공식 OpenAPI (ItemSummary, Item, EstimatedAvailability, getItem):
  https://developer.ebay.com/api-docs/master/buy/browse/openapi/3/buy_browse_v1_oas3.json
- 상태 ID 및 카테고리별 의미:
  https://developer.ebay.com/api-docs/sell/static/metadata/condition-id-values.html

테스트는 합성 데이터로 수행했다. 지난 실제 3개 상품이 수정 후 모두 통과하는지는 새 승인 후 상세조회로 확인해야 한다.
