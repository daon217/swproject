# 카탈로그 관측 v2 · 2026-11-16 보완

제공: 백엔드 / 소비: 수집기(내부 쓰기), 웹·추천(공개 조회). 기존 v2 관측 필드를 유지한다. 상세정보 신규 필드는 실제 수집 계약 확정 후 추가한다. 실시간 OpenAPI는 실행 중 API의 `/openapi.json`과 `/docs`에 있다.

- 수집: `POST /internal/v2/crawl-runs/{run_id}/observations`. Bearer 수집 토큰 필수. 64 KiB 요청 상한. run_id는 수집처별 UUID.
- 식별: source + source_listing_id + variant_key. URL 변경에도 동일한 ID를 유지한다.
- 중복: source + observation_key. 새 관측은 새 키, 동일 전송 재시도는 동일 키/본문.
- 시각: observed_at은 시간대 포함 실제 수집 시각. 현재 수신 시각으로 재작성 금지.
- 응답 확장: change_kind(created/updated/unchanged/stale/failed/not_found/quarantined), changed_fields(변경 컬럼명 배열). 기존 state/error_code/offer_id/observation_id 보존.
- HTTP: 201 관측 생성, 200 같은 관측 재전송, 409 키/실행 충돌, 422 형식 오류, 401 수집 인증 실패, 413 본문 초과. 201이어도 state=quarantine이면 적용되지 않은 것.
- 조회: `GET /v2/offers?selected_domain=product|food`, condition=new|used|unknown|all(기본 all), availability=available|out_of_stock|ended|suspect|all(기본 available), 선택 source/currency, limit 최대100, after 커서.
- **condition(신품·중고 상태)**: `new` | `used` | `unknown`. 생략하면 `new`(기존 호환). 판매처가 신품·중고를 표시하지 않으면 `unknown`을 보낸다. `unknown` 관측은 이전 관측이 확인한 `new`/`used`를 덮어쓰지 않는다. 필터: 전체 `all`=new+used+unknown(기본값), 새 상품만 `new`, 중고만 `used`, 미확인만 `unknown`. 기본 추천(`/v2/recommendations/basic`)도 new+used+unknown. 상품 카드에는 `condition`이 포함되며 `unknown`은 신품으로 표시하지 않고 '상태 미확인'으로 표시한다. 개인 맞춤 AI 추천은 회원이 설정한 '중고 포함' 여부를 따른다. 식품은 `used` 불가.
- 조회 응답 확장: condition,availability,source_listing_id,last_seen_at,last_checked_at,last_changed_at. 기존 필드 유지. 가격은 소수 문자열, 통화는 원본 통화, 배송비 NULL은 미확인.
- 변경점: 수집 시 갱신 정책으로 24시간 자동 숨김 제거. 마지막 확인 시각을 표시해야 하며 최신 가격/재고를 보증하지 않는다.
- 이름/설명/배송비 미제공 시 기존 값 유지. 명시적 null은 허용된 description/shipping_fee만 지움. 통화 변경 시 미제공 배송비는 미확인으로 전환.
- not_found는 suspect, timeout/blocked/error는 기록만. 파일에서 누락된 상품은 삭제하지 않는다.
- 부가 정보: `POST /internal/v2/crawl-runs/{run_id}/extensions`의 `matching_profile`은 brand·category·image_url·image_urls만 저장한다. 바코드(gtin)·부품번호(mpn)·모델명/번호·색상·사이즈·옵션·제조사·판매자 값은 받기만 하고 저장하지 않는다(2026-11-27, 사용하는 기능이 없어 DB에서 제거). 같은 상품 찾기 `GET /v2/offers/{id}/matches`도 호출하는 곳이 없어 제거했다. 식품 성분 근거(`food_evidence`)는 그대로다.

가상 신규 예시:
```json
{"schema_version":2,"source":"demo","observation_key":"demo:check:1","observed_at":"2026-11-15T00:00:00+00:00","result":"success","selected_domain":"product","source_listing_id":"demo-product-1","variant_key":"default","condition":"new","name":"가상 상품","price":"12000","currency":"KRW","availability":"available","url":"https://store.example.test/p/1","field_presence":["name","price","currency","availability","url"]}
```
다음 관측은 식별값을 유지하고 observation_key/observed_at을 새로 지정한다. 예를 들어 price=11000, URL=/p/1-new, availability=out_of_stock이면 기존 offer_id를 유지하며 해당 필드를 갱신한다. 상세 규칙과 실행은 [가이드](../docs/backend/CATALOG_INGESTION.md)를 따른다.
