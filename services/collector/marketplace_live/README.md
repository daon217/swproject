# YES24 · Serper.dev · eBay 수집 통합

현재 해외 Shopping 공급자는 **Serper.dev**입니다. 소스 ID는
`serper_google_shopping`, 키는 `SERPER_API_KEY`, 요청은
`POST https://google.serper.dev/shopping` + `X-API-KEY`입니다.
실행 방법은 `docs/SERPER.md`를 우선 참고하세요. 아래 SearchAPI 관련 내용은
기존 작업 기록으로 보존합니다. SearchAPI live/watch/DB 진입점은 차단되며
기존 코드·테스트·원장·체크포인트를 Serper 기록으로 바꾸거나 삭제하지 않습니다.

소량 조회 테스트는 새 `probe` 명령을 사용합니다. `--mock`은 키 없이 최대 3개의
합성 상품을 정규화해 전송 불가능한 mock 큐에 넣고, `--plan`은 읽기 전용 사전
확인, `--live`는 공급자별 별도 승인 후 조회만 수행합니다. 실제 조회는 상품 본문을
저장하거나 DB에 전송하지 않습니다. 특히 YES24는 DB 적재 테스트에서 차단합니다.
환경변수 입력·공급자별 명령·결과 해석은 `docs/READINESS.md`를 참고하세요.
기존 아래 watch 경로의 체계적 수집/저장 권한 요구는 그대로 유지됩니다.

기존 도매꾹 코드를 수정하지 않는 별도 패키지입니다. 실제 API, 운영 DB,
GitHub Push, NAS 배포는 이번 작업에서 실행하지 않았습니다. 모든 예시는 기본 비활성입니다.

## 조사와 재사용

`swproject` 작업 트리, 추적 파일, 로컬 Git 전체 이력의 해당 파일명과
`origin/main` 수집기 목록을 조사했습니다. YES24·eBay 구현은 이 저장소에
없고 handoff 문서에서 이전 원본을 참조하고 있었습니다.

원본 `ai-shopping-search-unified/collection_engine/korean_marketplaces.py`의
`native_observation`과 `backend/collectors/ebay.py`의 OAuth 캐시·무효화·토큰
발급 메서드를 재사용했습니다. `vendor/PROVENANCE.json`에 원본 해시와 범위를
기록했습니다. 원본 프로젝트는 수정하지 않았습니다. 그 원본의 일반 Product
기본값·float 가격 변환과 dotenv 자동 탐색은 가져오지 않았습니다.

SearchAPI 구현은 작업 트리·로컬 이력과 위 원본 프로젝트에서 발견되지 않아
공식 Google Shopping 문서에 맞춰 새 어댑터를 추가했습니다.

`domeggook_live`의 Observation 검증, HTTP backend transport, durable outbox
재시도 엔진, 원자적 파일 저장, OS 파일 잠금을 직접 가져와 재사용합니다.
공통 계약이나 팀 API 담당자 파일은 변경하지 않았습니다.

## 구현 상태와 데이터 한계

| 수집기 | 구현 | 현재 전송 조건 |
| --- | --- | --- |
| YES24 | 공식 itemList 검색·itemDetail 상세, 상품번호 일치 검사, 기존 엄격한 v2 정규화 재사용 | 별도 체계적 수집·DB 저장 계약, 그리고 실제 응답의 통화·SKU·상태·재고가 필요 |
| SearchAPI.io | Google Shopping 검색·페이지 처리, Bearer 키, 판매처별 offer 분리 | 실제 통화·상태·재고, 직접 판매처 URL, 원본 데이터 저장·재사용 권한이 필요 |
| eBay Browse | 기존 application OAuth 캐시/갱신·한 번의 401 재인증, 검색·getItem 상세 | Buy API 운영 권한과 라이선스, 고정가·지원 상태·재고·통화가 확인된 결과만 전송 |

YES24 공개 예제의 `salePrice`, `itemStatus`, `itemId`, `title`, `link`는
정규화하지만, 공개 예제에 없는 통화·condition·SKU를 만들어 채우지 않습니다.
`판매중`은 condition=new와 같은 뜻이 아닙니다. 기존 엄격한 normalizer를
통과하지 못하면 부족한 필드별 건수만 기록하고 상품 본문은 저장·전송하지 않습니다.

Google Shopping 기본 응답도 통화 코드·condition·재고를 항상 제공하지
않습니다. `$` 또는 `gl=us`, 검색어의 new/used, 검색 노출 사실로 이 값을
추정하지 않습니다. Google 암호화 redirect/product_link를 판매처 URL로
대체하지 않으며, 허용된 직접 판매처 `link`가 필요합니다. 여러 판매처의
동일 Google product_id는 판매처+원본 URL의 해시로 offer를 구분합니다.
이는 판매처 SKU가 아닌 파생 식별자입니다. URL이 바뀌면 동일 offer라고
추정 병합하지 않습니다. 추가 유료 상세 API는 자동 호출하지 않습니다.

eBay는 native REST itemId의 listing 번호와 전체 variant ID를 보존합니다.
고정가만 허용하고 1000=new, 3000/4000/5000/6000=used로 제한합니다.
open-box/refurbished/parts나 불명확한 재고는 기본값으로 바꾸지 않습니다.

정규화 결과의 상품번호·이름·가격·통화·판매처·URL·상태는 RAM에서 확인할 수
있습니다. 현재 팀 Observation v2는 seller 필드를 허용하지 않습니다.
판매처는 RAM에서만 보존하고 strict v2 HTTP 본문에서는 제외합니다. 판매처의
PostgreSQL 저장은 backend 담당자의 계약 확장 합의가 필요합니다. 다른 필드에
판매처를 숨겨 넣지 않습니다.

## 인증·권한·비용

환경변수: `YES24_API_KEY`, `SEARCHAPI_API_KEY`, `EBAY_CLIENT_ID`,
`EBAY_CLIENT_SECRET`, `KKULPICK_BACKEND_TOKEN`. 팀 backend 쪽 발급 토큰은
서버의 `COLLECTOR_TOKEN`과 일치해야 합니다. 값은 명령 인자·로그·원장·설정에
넣지 않습니다. eBay application token은 메모리에만 저장합니다.

`config.example.json`을 외부의 `config.local.json`으로 복사하고 실제 승인된
검색 범위·API allowance·키 등급·비용 상한·허용 판매처 host·통화를 입력합니다.
권한 `rights.reference`, `expires_at`, `allowed_uses`의 lookup,
systematic_collection, storage, reuse는 실제 계약의 근거가 있어야 합니다.
로컬 플래그는 권한을 발급하지 않습니다.

YES24 공개 약관은 별도 DB를 만드는 체계적 축적을 제한합니다. 따라서 이
자동 수집 경로는 `exception_agreement_reference`가 있는 별도 허가 없이는
시작하지 않습니다. 일반 키만 있다고 허용되지 않습니다. 임시 on-demand
캐싱과 이 장기 수집 경로를 같은 권한으로 취급하지 않습니다.

SearchAPI 유료 검색은 `max_units_per_month`, 문자열 `cost_per_request`,
문자열 `max_cost_per_month`를 명시해야 활성화됩니다. 실패·타임아웃도 보수적으로
1단위와 설정한 최대 비용으로 예약 차감합니다. 달 경계 차이를 피하려고
최근 31일 전체 예약까지 포함합니다. actual 플랜의 credit 단가/최대 비용으로
설정하고 자동 초과 과금도 계정에서 제한해야 합니다. 이 원장은 다른 앱이나
작업자가 같은 계정에서 쓰는 크레딧까지 알 수 없습니다.

`backend_enabled`, `backend_owner_approved`, `price_semantics_confirmed`와
저장·재사용 권한이 확인된 완전한 Observation만 outbox에 기록합니다. 필수 값이
없으면 `incomplete_native_fields`와 누락 건수로 확인합니다. 원본 응답은 저장하지
않습니다. 저장 권한 만료 시 남은 outbox 본문도 폐기합니다.

## 상태·실행

저장소 루트에서 실행합니다. `KKULPICK_MARKETPLACE_CONFIG`와
`KKULPICK_MARKETPLACE_STATE_DIR`는 각각 외부 설정 파일과 전용 상태 디렉터리의
절대 경로입니다. 기존 도매꾹 data 경로를 재사용하지 마세요.

```text
python -m services.collector.marketplace_live --status
python -m services.collector.marketplace_live --source ebay_browse --status
```

`--status` 및 모드 생략은 읽기 전용이며 상품 API·토큰을 읽거나 상태 파일을
생성하지 않습니다. 실제 호출·저장을 승인받은 후에만:

```text
python -m services.collector.marketplace_live --watch
python -m services.collector.marketplace_live --source yes24_api --once
```

`--once`는 한 번의 bounded scheduler tick입니다. 검색 후 상세 작업은
체크포인트에 남으며 다음 tick/watch가 이어받습니다. `--watch`는 세 소스를
순차적으로 독립 진행하며, 완료한 소스는 최소 7,200초 뒤 새 주기를 시작합니다.
각 소스는 별도 원장·outbox·잠금·체크포인트·다음 실행 시각을 가집니다.
전체 한도보다 남은 작업이 많으면 다음 2시간 예산 구간에서 이어갑니다.
한 소스의 접근 거부/불완전 데이터/예산 소진은 다른 소스의 원장을 변경하지 않습니다.

운영 HTTP는 이 경로만 사용합니다:
`POST /internal/v2/crawl-runs/{run_id}/observations`.
직접 SQL·DB 드라이버를 import하지 않습니다. 팀 backend에서
`CATALOG_URL_HOSTS`와 `CATALOG_CURRENCIES`를 승인된 공급자 값으로 설정해야 합니다.
이 패키지는 backend 설정을 자동 변경하지 않습니다.

## 재시도·복구

- 모든 provider/OAuth 요청은 발송 전에 영속 예약합니다. 키·URL·원본 상품값은
  원장에 저장하지 않고 요청 해시·시간·결과·차감액만 남깁니다.
- 분리된 시간/24시간/주기 한도와 request interval을 적용합니다. 전체 원장을
  잘라내지 않습니다. Query/market/page size 변경으로 기존 checkpoint를 초기화하지 않습니다.
- 429와 Retry-After가 있는 503은 초 또는 HTTP 날짜의 전체 마감 시각을 존중합니다.
  네트워크 결과 불확실/중단 예약은 최소 7,200초 보류하며 기존 차감을 유지합니다.
- 일반 일시 실패는 지연 후 재시도하되 작업당 최대 3회입니다. 인증/redirect/
  스키마 hold는 검토 없이 해제하지 않습니다. 요청 이력/outbox 유실도 초기화하지 않습니다.
- 팀 API 전송은 기존 엔진의 최대 5회 지수 지연과 immutable body/key/run ID를
  재사용합니다. 수집 대기 중에도 flush합니다. 401/403/409는 hold입니다.
  서버의 source+observation_key 유일성 계약이 응답 유실 뒤 중복 적용을 막습니다.
- source별 writer lock은 OS가 종료 후 해제합니다. 동일 상태를 여러 호스트나
  잠금/원자 rename을 보장하지 않는 SMB/NFS에서 공유하지 마세요.
- SIGTERM/SIGINT는 다음 provider 요청/POST를 중단합니다. NAS 배포 파일이나
  운영 프로세스는 이 작업에서 변경·시작하지 않았습니다.

## 테스트

```text
python -m pytest services/collector/marketplace_live/tests -q
```

fixture는 SYNTHETIC이며 성공 응답 fixture의 추가 native 필드는 API에서
실제 제공된다는 증거가 아닙니다. 별도로 공식 예제처럼 필수 값이 없는 응답이
전송되지 않는 테스트를 포함합니다. 팀 계약 검증은 Pydantic models.py만
읽으며 FastAPI app/DB 엔진을 import하지 않습니다.

공식 참고 자료(2026-11-21 확인):

- https://developers.yes24.com/api-doc/goods-item-list
- https://developers.yes24.com/api-doc/goods-item-detail
- https://developers.yes24.com/support/terms
- https://www.searchapi.io/docs/google-shopping
- https://www.searchapi.io/pricing
- https://developer.ebay.com/develop/api/buy
- https://developer.ebay.com/develop/api/buy/api_call_limits

실제 키·권한·데이터·플랜·운영 endpoint의 유효성은 새 실호출로 검증하지 않았습니다.
