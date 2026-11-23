# Serper.dev Shopping 연결·운영 준비

공급자 정정 후 현재 소스는 `serper_google_shopping`입니다.
실제 공급자 요청·팀 DB 적재·Push·NAS 배포는 승인 전 실행하지 않았습니다.
기존 SearchAPI 전용 코드와 테스트는 이전 결과 재현용으로 보존하며 운영 CLI의
live/watch/DB 전송 경로는 차단합니다. 이전 원장·outbox·checkpoint도 그대로 둡니다.

## 키 확인 및 로딩

기존 `C:\Users\junse\Python\ai-shopping-search-unified\.env`에서 변수 이름
`SERPER_API_KEY`를 확인했습니다. 이름이 이미 표준과 같아 파일을 바꾸지 않습니다.
`swproject/.env`에는 이 변수 이름이 없고 현재 프로세스 환경에도 주입되지 않았습니다.
이 확인은 실제 키의 유효성을 API로 검증한 결과가 아닙니다.

명시적인 `--env-file`은 해당 파일에서 **SERPER_API_KEY 하나만** 현재 Python
프로세스로 읽습니다. YES24 키·eBay 키·팀 토큰 등 다른 값은 가져오지 않습니다.
원본 파일/셸 사용자 환경/레지스트리/저장소에 키를 쓰지 않으며 키를 출력하지 않습니다.
동일 키가 중복되거나 기존 프로세스 키와 충돌하면 값 노출 없이 중단합니다.
키를 새 설정 파일로 복사하거나 채팅·명령 인자에 붙여넣을 필요가 없습니다.

## 설정

저장소 루트 `C:\Users\junse\Python\swproject`에서 기존 venv를 사용합니다.
`serper.lookup.example.json`을 저장소 밖의 비공개 `serper.lookup.local.json`으로
복사하고 실제 승인된 설정을 입력합니다. API 키는 JSON에 넣지 않습니다.

- queries[0]: 승인받을 실제 검색어. 기본 operator-approved query는 예제입니다.
- gl/hl: 검색 국가·언어. 기본 us/en이며 통화나 상품 상태의 증거로 쓰지 않습니다.
- allowed_product_hosts: 허용된 실제 판매처 host. merchant.example.test는 Mock용입니다.
- currencies: 허용되는 실제 상품 통화. 가격의 `$`만으로 USD를 만들어 내지 않습니다.
- rights.reference/expires_at/allowed_uses: 실제 조회 권한 근거와 유효기간.
  단발 probe는 lookup만 요구하며 watch의 systematic_collection/storage/reuse 요구는 유지됩니다.
- credits_per_request: 계정의 Shopping 요청 1회에 대한 보수적인 크레딧 예약량.
- max_units_per_month: 최근 31일까지 포함한 크레딧 한도.
- cost_per_request/cost_currency/max_cost_per_month: 요청 1회 최대 비용·통화·비용 상한.
  실제 계정 플랜과 승인 범위로 설정합니다. 예제의 0은 미설정 차단값이며 무료를 뜻하지 않습니다.

실제 크레딧/비용을 계정에 확인하지 않은 채 임의의 저렴한 값을 넣지 않습니다.
성공 응답이 예약량보다 큰 credits를 보고하면 실제 보고량을 원장에 반영하고
추가 요청을 보류합니다. 다른 프로그램이 같은 키를 쓰는 사용량은 이 로컬
원장으로 알 수 없으므로 계정 차원의 잔액/사용 제한도 확인해야 합니다.

## 키 없는 Mock

```powershell
& .\.venv\Scripts\python.exe -m services.collector.marketplace_live.probe --source serper_google_shopping --mock --max-products 3 --state-dir <mock-state-root>
```

HTTP 공급자만 합성으로 대체하고 실제 Adapter → Serper 정규화 → 필수 검사 →
전송 불가능한 Mock outbox를 검증합니다. 새 Mock 상태에서는 정상 2개·보류 1개·
대기 2개, 실제 공급자/DB HTTP 0회를 기대합니다. 정상 fixture의 통화·상태·재고는
SYNTHETIC 데이터이며 Serper 실제 응답에 항상 있다는 뜻이 아닙니다.

## Plan 및 별도 승인 후 한 번 조회

먼저 실제 요청 없이 사전 검증합니다.

```powershell
& .\.venv\Scripts\python.exe -m services.collector.marketplace_live.probe --source serper_google_shopping --plan --max-products 3 --config <private-serper.lookup.local.json> --env-file C:\Users\junse\Python\ai-shopping-search-unified\.env
```

결과의 key 존재 여부, POST endpoint, 검색어, 예정 검색 1회, 최대 검사 3개,
예상 최대 비용/크레딧 예약량, 누락된 권한/예산을 검토합니다. plan은 상품 API를
호출하거나 키를 출력하지 않습니다.

그 계획으로 실제 Serper 요청 승인을 별도로 받은 뒤에만:

```powershell
& .\.venv\Scripts\python.exe -m services.collector.marketplace_live.probe --source serper_google_shopping --live --max-products 3 --config <private-serper.lookup.local.json> --env-file C:\Users\junse\Python\ai-shopping-search-unified\.env --state-dir <shared-marketplace-state-root>
```

요청은 `POST https://google.serper.dev/shopping`이며 X-API-KEY 헤더와 JSON의
q/gl/hl만 보냅니다. SearchAPI engine/api_key 쿼리, Bearer 인증을 사용하지 않습니다.
검색은 1회이고 처음 최대 3개만 검사합니다. 추가 페이지·상품 상세·판매처 페이지를
호출하지 않습니다. 서버가 더 많이 반환해도 나머지는 정규화·저장하지 않습니다.
로컬 request interval 대기 외에는 실패 POST를 자동으로 재전송하지 않습니다.
probe에서는 backend 설정을 무조건 비활성화하고 실제 상품 본문/outbox를 저장하지 않습니다.

## 필드 매핑과 보류

| Serper 원본 | 공통 결과 / Observation v2 |
| --- | --- |
| productId | source_listing_id. 판매처 SKU로 해석하지 않음 |
| source + link | 판매처 이름 + 원본 URL 해시로 variant_key를 만들어 서로 다른 판매처를 구분 |
| title | name |
| price | Decimal 가격 문자열. USD/US$ 등의 명시적 단위는 통화로 인정하고 `$` 단독은 통화 미확정 |
| source | RAM의 seller. Observation.source는 공급자 ID serper_google_shopping |
| link | 허용된 HTTPS 상품 URL만 사용 |
| 실제 currency/condition/availability가 제공된 경우 | 검증 후 currency/condition/availability; 없으면 None과 누락 사유 |

공식 기본 예제에는 productId/title/source/link/가격 문자열이 있지만 통화 코드,
condition, 재고가 없을 수 있습니다. delivery=Free shipping은 재고 증거가 아니고,
검색 노출이나 검색어의 new/used도 상품 상태를 증명하지 않습니다.
필수값 미달은 held로 보고하고 DB에 보내지 않습니다. 현재 v2는 판매처 자체를
DB에 보존하지 못하며 기존 SELLER_CONTRACT_PROPOSAL.md가 여전히 적용됩니다.

## 운영과 기존 기록

단발 probe와 watch는 같은 상태 루트의 serper_google_shopping 원장을 공유합니다.
기존 SearchAPI 원장을 Serper 원장으로 이름만 바꾸거나 합치지 않습니다. 공급자와
과금 계정이 다르기 때문입니다. 기존 원장은 보존하고 Serper는 별도 namespace로
운영합니다. 새 상태 루트를 반복 생성해 호출 예산을 초기화하지 마세요.

실제 수집·저장 및 운영 실행을 따로 승인받고 필요한 권한을 확인한 뒤에만:

```powershell
& .\.venv\Scripts\python.exe -m services.collector.marketplace_live --source serper_google_shopping --watch --config <approved-collection-config> --state-dir <shared-marketplace-state-root> --env-file C:\Users\junse\Python\ai-shopping-search-unified\.env
```

request interval, 시간/24시간/주기/크레딧/비용 한도, 최소 7,200초 주기,
checkpoint 복구, OS source lock, 동일 Observation body/key/run ID 재전송,
권한 만료/가격 기준 검사, source별 성공·실패·보류/마지막 시각을 유지합니다.
네트워크 결과 불확실 시 비용 차감을 남기고 최소 7,200초 보류합니다.

Docker 서비스명도 serper로 바뀝니다. 외부 SERPER_ENV_FILE에는 SERPER_API_KEY만
주입하고 기존 문서의 searchapi 서비스 명령은 사용하지 않습니다. Docker/NAS
배포는 이번 수정에서 실행하지 않았습니다. 도매꾹·YES24·eBay 원본 소스와 기존
테스트 파일은 수정하지 않았습니다.

참고: https://serper.dev/ 의 Shopping 공개 응답 예제. API endpoint와 인증 방식은
사용자가 제시한 Serper 연결 명세를 적용했습니다. 실호출 검증은 미수행입니다.
