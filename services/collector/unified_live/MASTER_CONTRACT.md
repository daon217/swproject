# 팀 API 담당자용 실제 계약 확인 및 확장안 — 미적용

2026-11-23 로컬 services/api/kkulpick/api.py/models.py/ingest.py를 읽었다. NAS의 배포 버전과
동일하다는 원격 검증은 불가능했다. API/SQL/모델 팀원 파일은 수정하지 않았다.

## 현재 실제 코드

- POST `/internal/v2/crawl-runs/{run_id:UUID}/observations`, Bearer. 서버 `COLLECTOR_TOKEN` 하나,
  최소32자. 현재 로컬 서버에 소스별 token scope는 없다. 클라이언트 `KKULPICK_BACKEND_TOKEN(_FILE)`.
- 응답201/200 및 실제 receipt를 확인한 뒤만 ACK. source+observation_key/payload 재사용 충돌은409,
  run-source 충돌도409. 상품 identity는 source/source_listing_id/variant_key. 상세 SQL은 기존 ingest 소유.
- Observation extra=forbid. 금액은decimal 문자열, price/currency 동시, field_presence와 실제 필드 일치.
- selected_domain=product/food, condition=new/used, availability=available/out_of_stock/ended.
  현재 v2에 실제 재고 수량 필수 필드는 없다. unknown quantity를 조작할 필요가 없다.
- URL host는 서버 `CATALOG_URL_HOSTS`, 통화는 `CATALOG_CURRENCIES`에 허용돼야 한다.
  임의 host/source를 무조건 허용하도록 검사를 해제하지 않는다.
- description은 기존 지원(max4000). seller/이미지/상품 category/국가/GTIN/알레르기/합성표시는 미지원.
  기존 v2 body에 판매처를 넣을 수 없어 DB에 보존되지 않는 것이 현재 계약상 제한이다.
  selected_domain은 상품 카테고리 3단계 코드가 아니다.

## 제안: 별도 버전 listing-extension + food-evidence

1. seller={native_id?,name,native_url?}, marketplace/country, image_urls, category_native와
   공식 category mapping version, GTIN, evidence_source, is_synthetic를 추가. 합성은 별도schema/권한으로 격리.
2. condition=new/used/refurbished/open_box/for_parts/unknown와 native_condition/id/매핑근거를 구분.
   refurbished/open_box를new/used로 변환하지 않는다. unknown을new기본값으로 덮지 않는다.
3. 판매 상태 available/reserved/sold/out_of_stock/inactive/deleted/unknown, purchase_available=bool|null,
   stock_quantity=int|null(정확값), estimated_quantity/range/threshold와 근거를 별도 보존.
   검색누락·404/410만으로sold/deleted로 바꾸지 않는다. 명시 상태/시각/출처가 필요하다.
4. first_seen_at/last_checked_at/last_changed_at, description_sha256/native_updated_at,
   semantic payload hash를 보존. 변경이 없어 전송 생략해도freshness를 갱신할 별도batch heartbeat가 필요하다.
5. ACK 계약에 change_kind(created/updated/unchanged), event key/hash, source/listing/variant,
   persisted_at를 명시. 불확실 응답용 read-only receipt 조회(source+observation_key+payload_sha256)를 추가한다.
   retry는 같은event key/body로만, conflict는409와확정reason. 이 endpoint는 아직 구현된 것이 아니다.
6. food-evidence-v1: exactGTIN/제조사/품목식별근거, ingredients_raw/normalized/percentage,
   allergens_declared/possible_cross_contact, raw labels, inferred_tags(비공식추정분리),
   evidence_url/source/at/hash, requires_review/confidence, license/retention.
   부정표시·미확인·유사명자료·community transcription을제조자보증으로해석하지 않는다.
   safe_to_consume=null. 원문저장권한과제품포장우선순위를별도정의한다.
7. 신규 소스 등록/host/currency/가격 의미/보존기한은 운영 담당자 승인. 소스별token scope와
   revocation을권장하나 현재 단일token구현을소스scope지원으로보고하지 않는다.

## 승인 후 검증 절차

팀 소유의 격리test endpoint/schema에서 host/currency/price/source/token → 신규1 → 동일event재전송 →
가격변경 → 상태변경 → 누락/오류보존 → 판매처/식품확장보존 → receipt조회를검증한다.
이번local loopback+SQLite lab는실제HTTP/멱등성3개와팀Pydantic호환성만확인했다.
운영FastAPI/PostgreSQL business transaction이나새제안필드의저장성공을증명하지않는다.
