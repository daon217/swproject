# 상품 인식·동일/유사/중고 추천 연계안 — 수집기 구현 / 팀 API 변경 제안

2026-11-23. 이번 변경은 수집기만 적용한다. 확장 프로그램·비전·검색·추천·API·SQL은 변경하지 않는다.
LLM, 이미지 다운로드, 임베딩 생성, 새 외부 API 요청을 추가하지 않았다. NAS 배포도 하지 않는다.

## 현재 저장소에서 실제 확인한 계약

- apps/extension, services/vision, services/recommendation에는 README만 있다. 확장의 DOM 추출 방식과
  실제 전송 payload/추천 worker 구현은 이 브랜치에서 검증할 수 없다. 팀 기능이 이미 연동됐다고 보고하지 않는다.
- services/api/kkulpick/analyses.py: POST /analyses는 JSON 또는 multipart로 page_url,
  page_session_id, page_revision, request_key, selected_domain과 선택 image 업로드를 받는다.
  AnalysisInput은 Strict이므로 임의 product 필드를 기존 요청에 추가하면 수용되지 않는다.
  worker의 Completion은 offer_ids와 warnings/ingredients/reasons/ranker를 받으며, 동일/유사 판정 필드는 없다.
- services/api/kkulpick/models.py: Observation v2 extra=forbid. 이름/설명/가격/통화/상태/URL은 지원하나
  브랜드/모델/GTIN/판매처/이미지/옵션은 없다. 미지원 필드를 v2 body에 넣지 않는다.
- services/api/kkulpick/vectors.py: model_id/revision/dimensions/template/prefix/normalize 계약을 등록하며,
  serving 모델 차원·유한값·content_version을 검사한다. 공개 상품 텍스트용이고 개인 OCR 입력용이 아니다.
  pgvector candidates는 후보 identity와 distance를 반환하며, 동일 상품 확정이나 가격·알레르기 판정이 아니다.
- 기존 GET /v2/offers는 condition=new/used/all 및 availability/source/currency 필터를 지원한다.
  실제 확장→추천→offer 결합 흐름과 NAS 배포 버전은 이번 작업에서 검증하지 않았다.

## 구현된 수집 메타데이터

schema_version=product-match-v1을 기존 listing-extension-v1.metadata와 독립 matching_checkpoint.json에 연결한다.
원본 observation key, listing ID, variant_key, v2 body, 기존 재시도/원장/스케줄은 유지한다.

| 필드 | 수집·정규화 규칙 |
|---|---|
| product_name/brand/manufacturer | native 텍스트/구조화 name만 정제. 제목에서 브랜드 추측 금지 |
| model_name/model_number/mpn | Schema model, 명시 modelNumber/MPN, 검토된 CSS, eBay native aspects |
| identifiers | check digit를 통과한 문자열 GTIN만 canonical14자리. 숫자 손실 복구/상품ID→GTIN 변환 금지 |
| image_url/image_urls | 실제 제공 이미지 URL만, 상대주소 해소, HTTPS/credential·private literal 검사, 중복제거/최대8 |
| color/size/options | native 색상/사이즈/용량/메모리/전압/포장수량. 충돌 값은 null/검토 사유 |
| category/description | 원문 카테고리와 정제 설명. description 저장은 별도 description_storage 허가 필요 |
| source_fields/evidence_origin/review_reasons | native 출처 경로·공급자·검토 사유. 비전 추정값과 혼합하지 않음 |
| variant_signature | 관측된 옵션의 비교용 hash. 거래 variant_key나 전역 상품 ID로 사용하지 않음 |

matching_checkpoint는 source/listing/variant, 상품 URL, 가격·통화, 상태·판매처, 최초 수집/마지막 확인/
마지막 변경 시각과 위 profile을 보존한다. storage/reuse 허가와 정상 큐 수용 이후에만 저장한다.
도매꾹의 별도 field grant를 일반 rights로 임의 승격하지 않는다. 기존 도매꾹 row의 native 필드는 메모리에서
profile로 투영하지만 일반 rights가 없는 경우 이 sidecar에 추가 저장하지 않는다. 필드별 허가 확정이 선행되어야 한다.
알 수 없는 값은 null/빈 목록으로 남긴다. 이미지 없다고 다운로드하거나 모델번호를 제목에서 생성하지 않는다.
기존 식품 hold/원문 권한을 유지한다. 음식의 일반 추천 데이터와 알레르기 근거·안전 판정은 분리한다.
매칭 메타데이터만 변하면 sidecar를 갱신하고 같은 v2 body를 중복 전송하지 않는다.
local sidecar는 팀 DB 저장 완료가 아니며, 별도 API 계약 승인 전 backend_contract_ready=false다.

## 동일 후보와 유사 후보

`matching.compare`는 후보 분류 도우미이며 판매처 offer를 병합하거나 최종 추천을 결정하지 않는다.

1. 유효 native GTIN 교집합 또는 브랜드+명시 MPN/모델번호 일치를 동일 상품 후보 근거로 사용한다.
2. GTIN·브랜드·명시 모델번호·MPN이 충돌하거나 동일 옵션명이 다른 경우 identity_conflict로 남긴다.
3. 색상/사이즈/용량이 미확인인 쪽은 동일 옵션이라고 간주하지 않고 partially_specified로 표시한다.
4. 모델명의 시리즈 일치, 이미지 유사, 같은 판매자 SKU만으로 동일 상품을 확정하지 않는다.
5. exact_match_confirmed=false와 requires_review=true를 유지한다. 이미지가 같고 ID가 없으면 similar_candidate다.
6. 신품·중고는 같은 모델 후보가 될 수 있으나 offer 상태/가격/판매처는 독립적으로 유지한다.
7. 리퍼/개봉/부품용/예약은 기존 v2 미지원 상태로 보류하며 new/used로 억지 매핑하지 않는다.
8. 다중 Product/hasVariant/다중 Offer는 기존 전용 어댑터 검토 경계를 유지한다. 미선택 옵션을 확정하지 않는다.

## 팀 담당자 검토용 새 API/이벤트 — 아직 서버 미구현

제공: 수집 API 담당자, 소비: 카탈로그/검색/추천 worker. 확장 입력은 회원 API 경계에서 별도 관리한다.
기존 Observation v2에 필드를 추가하지 말고 버전이 있는 listing-extension 수집 endpoint 또는 함께 ACK되는
원자적 envelope를 확정한다. 인증은 소스별 쓰기 범위, 허용 host/currency/가격/저장 권한을 검사한다.
현재 서버 COLLECTOR_TOKEN은 전역 토큰이며, 소스 scope가 이미 구현된 것으로 가정하지 않는다.

```json
{
  "schema_version":"listing-matching-extension-v1",
  "source":"html_synthetic_example",
  "source_listing_id":"SYNTHETIC-1",
  "variant_key":"SYNTHETIC-RED-L",
  "observation_key":"SYNTHETIC-event-key",
  "product_url":"https://store.example.test/items/1",
  "is_synthetic":true,
  "matching_profile":{
    "brand":"SYNTHETIC Brand",
    "model_number":"SYNTHETIC-KB-01",
    "mpn":"SYNTHETIC-KB-01-RED",
    "identifiers":[],
    "image_urls":["https://store.example.test/images/1.jpg"],
    "color":"red","size":"L",
    "options":{"color":"red","size":"L"},
    "exact_match_confirmed":false
  }
}
```

성공 ACK는 accepted extension key/hash/content_version과 created/updated/unchanged를 명시한다.
동일 event key/body는 같은 결과, 다른 body/key 재사용은409. v2 ACK와 확장 실패의 부분 수용 정책,
receipt 조회/재처리/권한 취소/원문 및 이미지 URL 만료·보존기간을 합의한다. URL은 다운로드 권한이 아니다.
이미지 fetch worker는 별도로 redirect/DNS 재검증·private IP 차단·용량/MIME·라이선스 검사 후 처리해야 한다.

확장 입력 제안(product-context-v1): page_url, session/revision/request_key, DOM에서 읽은 name/brand/
model/GTIN/옵션/선택 이미지와 각 필드의 출처. 페이지 원문/쿠키/로그인정보/추적token은 보내지 않는다.
현재 /analyses에 그대로 추가할 수 없으므로 팀이 새 버전 경로 또는 명시적인 optional context를 확정해야 한다.
DOM/JSON-LD/선택 옵션을 먼저 사용하고, 누락 시에만 비전으로 보완한다. 비전 추정에는 confidence와
evidence_origin=vision_inferred를 별도 부여한다. LLM은 필수 의존성이 아니다.

검색 조건 제안: condition=[new,used], include_used=true, availability=available 기본,
reserved/ended 포함은 명시 선택, 통화/가격·지역·배송 조건, exact 후보와 similar 후보를 별도 섹션으로 반환한다.
응답에는 offer_id/source/listing/variant, 매칭 근거·충돌·옵션 완전성, 원가격/통화/상태/URL·확인 시각을 준다.
이미지 distance를 exact 확률로 표현하지 않는다. 사용자의 시각 장애·알레르기 정보는 공개 상품 임베딩에 넣지 않는다.
이미지 임베딩 도입은 encoder/revision/dimension/modality와 query/document 전처리 계약을 새로 합의하고,
현재 텍스트 모델 공간에 다른 차원의 비전 벡터를 섞지 않는다. 생성·저장·추천 코드는 이번 변경 범위가 아니다.

## 검증과 운영 경계

새 fixture는 모두 synthetic이며 실제 API/팀 DB 쓰기는0. 이미지·모델·GTIN·색상·사이즈·누락·used/
v2 호환·권한·재시작·메타데이터만 변경·60/7200초·알레르기는 기존+새 테스트로 검사한다.
후속 팀 통합 검증: DOM payload→strict API→matching 후보→조건 필터→offer 반환,
관측 시각/원통화/권한/중복/반대 색상/동명이인 브랜드/같은 이미지 다른 제품 사례를 포함한다.

공식 필드 근거: [Schema Product](https://schema.org/Product),
[eBay Browse getItem](https://developer.ebay.com/api-docs/buy/browse/resources/item/methods/getItem).
비공개 API·차단 우회·새 유료 호출·NAS 변경은 추가하지 않았다.
