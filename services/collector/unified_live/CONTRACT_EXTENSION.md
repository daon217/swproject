# 팀 담당자 검토용 확장 계약 — 적용하지 않음

기존 Observation v2 body/팀 FastAPI/SQL 스키마는 변경하지 않는다. source 등록·token scope·허용 URL 호스트와
가격 기준은 기존 담당자 승인대로 검증한다. 아래는 별도 버전 계약의 제안이며 현재 저장 성공을 뜻하지 않는다.

1. 키: (source, source_listing_id, variant_key) 고유. observation_key는 이벤트 멱등 키로 유지하고
   event payload를 바꾸며 같은 키를 재사용하지 않는다. 신규/변경/미변경은 서버 ACK의 change_kind로 확인한다.
2. 판매처/표현: seller{name,native_id?}, image_urls, description, category_native{name,id?},
   region(domestic/overseas/unknown), source_reference, real_or_synthetic, first_seen_at, last_checked_at.
   URL 수집의 확장은 listing-extension-v1로 로컬에 보존하며 Observation에는 허용 필드만 넣는다.
3. 상태: new/used/refurbished/open_box/for_parts/unknown; native_condition와 매핑 근거 별도 보존.
   refurb/open_box를 new/used로 억지 변환하지 않는다. 기존 v2 미표현 상태는 보류한다.
4. 판매 상태: available/reserved/sold/out_of_stock/inactive/deleted/unknown. 구매 가능 여부는 bool|null,
   실제 수량은 int|null, 추정 수량/범위는 별도 필드. 알 수 없는 수량에0/1을 넣지 않는다.
   검색 누락·404·410은 verification_required로 표시하고 authoritative 상태 근거 없이 tombstone을 만들지 않는다.
5. 식품: 별도 food-evidence-v1 엔터티에 ingredients_raw/ingredients_normalized(name,percentage?),
   allergens_declared/allergens_possible_cross_contact/cross_contact_raw/allergen_status,
   evidence_source/evidence_url/verified_at/raw_sha256/requires_review/confidence 및 제품·제조사 식별 근거.
   원문 별도 접근권한·보존기간을 설정한다. source claim/미확인/부정 주장과 안전 판정을 구분한다.
   제조사·품목보고번호를 확인하지 않고 공공데이터의 유사 이름으로 상품을 자동 결합하지 않는다.
6. API: 기존 crawl-runs observations에 임의 필드를 추가하지 않는다. 팀이 새 확장 endpoint/schema와
   수용 가능한 상태를 확정해야 한다. 실패/불확실한 요청은 같은 key/body로 조회·조정할 수 있는 receipt
   계약이 권장된다. 클라이언트 큐 ACK는 실제 팀 API/DB 통합 승인 시험으로 따로 검증한다.
7. 내용 변화만 보내는 정책은 상품 갱신 이벤트와 freshness를 분리한다. 별도 low-cost heartbeat/last_checked
   batch 계약이 필요하다. 변경 없음으로 전송을 생략하면 팀 DB의 observed_at이 매분 갱신되지는 않는다.
8. category는 현재 자유 문자열/product·food일 뿐 공식 3단계 코드가 확정된 것이 아니다.
   SYN-CAT-*는 합성 샘플용 임시 namespace이며 실제 상품의 공식 DB ID로 사용하지 않는다.

운영 PostgreSQL 직접 INSERT/DDL/마이그레이션은 이 모듈에 없다. 코드와 Mock 전송 성공은 계약 승인이나 DB 보존 증명이 아니다.
