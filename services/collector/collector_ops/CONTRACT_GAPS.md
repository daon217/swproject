# 팀 FastAPI/DB 담당자에게 전달할 계약 변경안

검토용 문서다. 이번 작업에서 services/api, 실제 PostgreSQL, 팀원 파일은 수정하지 않았다.
이전 marketplace_live 및 used_market_live의 판매처/상태 제안을 통합하며, 담당자에게 메시지를 발송하지 않았다.

## 현재 운영 경계

상품은 /internal/v2/crawl-runs/{UUID}/observations에 토큰 인증으로 전송한다.
기존 Observation v2는 new/used와 구매 가능 상태를 표현하지만 판매처·카테고리·식품 전용 근거·
확정/추정 수량·세부 상태를 손실 없이 저장할 수 없다. 새 메타데이터는 기존 body에 몰래 추가하지 않는다.
신규 상품의 availability 필수 문제도 숫자 재고 수량과 구분해야 한다.

## 제안 필드와 정책

1. seller: provider_seller_id/display_name을 분리하고 출처를 보존한다. 개인 전화/주소/채팅을 대체값으로 수집하지 않는다.
2. category: provider category ID/label/path와 정규 taxonomy ID를 분리한다. 매핑되지 않은 ID를 임의로 만들지 않는다.
3. condition: new,used,refurbished,open_box,new_with_defects,for_parts,damaged 및 구체적인 condition_detail.
   eBay의 1500/1750/2000/2010/2020/2030/2500/7000을 별도로 표현하고 Graded/Ungraded를 마모 등급과 혼동하지 않는다.
   상태 자체가 없는 Serper 결과 등은 condition=unknown + pending_verification으로 구분하는 확장도 필요하다.
   상태 미상을 new로 기본 처리하지 않고 확인 전 일반 신품/중고 검색 결과에서 제외한다.
4. availability: available/out_of_stock/ended/unknown. unknown 신규 상품은 pending_verification으로 받고 구매 가능 검색에서 제외한다.
5. quantity: exact_stock_quantity nullable, estimated_quantity 및 threshold/comparison 별도. eBay Browse 추정치를 exact로 저장하지 않는다.
6. lifecycle: active/sold/inactive/deleted/unknown과 authoritative evidence/observed_at/expiry.
   과거 active가 최신 tombstone을 덮어쓰지 못하도록 필드 시계를 적용한다.
   검색 누락·404·권한 오류는 deleted 증거가 아니며 stale/verification_required와 구분한다.
7. food_evidence: source, URL, field, observed_at, raw_sha256, 원문 근거, 파싱 버전,
   ingredients_raw/normalized, allergens_raw/declared, may_contain, unmapped_terms, evidence_status.
   원문은 공급자의 저장·재사용 허가와 보유기간에 따라 선택적으로 보존한다. 원문 제거 의무를 메타데이터 해시로 대체하지 않는다.
   not_reported/negative_claim_unverified/conflicting/image_only/OCR_unverified를 표현하고 missing을 안전으로 바꾸지 않는다.
   safe_to_consume이나 allergy_free=true 같은 추론 필드는 이 수집기에서 생성하지 않는다.

## API 버전 및 저장

서버가 새 필드를 지원하는 capability 또는 새 버전 endpoint를 먼저 제공한 뒤 수집기가 전송한다.
서버가 지원하지 않으면 식품 전용 메타데이터, 리퍼/개봉/부품용 상품은 현재처럼 보류한다.
기존 v2 body/key/outbox를 재작성하지 않는다. source_listing_id/variant_key는 유지하고 새 이벤트만 새 계약으로 만든다.
한 이벤트 재전송은 동일 body/key를 유지해 멱등성을 보장한다.
국내 source/호스트/통화/권한은 계약 승인 후 명시적으로 허용한다. synthetic_catalog는 운영 v2에 추가하지 않는다.

별도 withdraw/delete 이벤트는 최소 source/listing/variant ID, 시각, stable event key와 허가된 근거만으로 처리할 수 있어야 한다.
공개 노출 중단, 원문·개인정보 삭제, 최소 감사 기록 보존을 별도 정책으로 정의한다.
수집기는 SQL INSERT/UPDATE/DELETE를 직접 실행하지 않는다.

## 수락 기준

- 판매처·세부 상태·카테고리와 식품 원문/정규화 근거가 왕복 보존된다.
- 누락 원재료/알레르기, "없음" 주장, 미확인 이미지/OCR이 안전으로 노출되지 않는다.
- unknown 재고/수량은 null/unknown으로 유지하며 0/1을 기본값으로 쓰지 않는다.
- stale active/unknown 및 verification_required는 최신 구매 가능 정보처럼 표시하지 않는다.
- 중복 key 재전송, 429/5xx/네트워크 ACK 손실, 오래된 관측, 삭제 이벤트 재전송을 계약 테스트한다.
- 저장/재사용/가격·소유자 승인 및 공급자별 토큰 권한을 유지한다.

근거 문서: 기존 팀 models.py/ingest.py와 실제 ACK change_kind 정의를 읽기 전용으로 확인했다.
상품 검색 API를 확보했다는 사실은 식품 표시 정보의 완전성이나 데이터 재배포 허가의 증거가 아니다.
