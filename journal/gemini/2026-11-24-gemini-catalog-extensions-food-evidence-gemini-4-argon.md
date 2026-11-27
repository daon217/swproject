# [Gemini 4 Argon] 개발일지 · 2026-11-24 카탈로그 DB 식품 원재료·추천 연동 및 상품 매칭 확장 API 구현 (#49 #50)

- 날짜: 2026-11-24 (기록일, Asia/Seoul)
- 실제 작업 시기: 2026-11-23 11:31~12:21
- 상태: 부분 해결 — 백엔드 DB 스키마(`0009_catalog_details`), 확장 적재·매칭 API, `PgCatalog` 식품 원재료 추천 연동 완료 (운영 수집기의 주기적 확장 전송 연결은 [OPEN_ISSUES.md](../../OPEN_ISSUES.md) #27·#32 참조)
- 브랜치 / 커밋: `maintest` / [`4b1f5fc`](https://github.com/daon217/swproject/commit/4b1f5fc9b0ef80124b87676e829a2e1f6c4063c6), [`89948df`](https://github.com/daon217/swproject/commit/89948dfcd6131d88af7b62d74026e40562e7a23c)
- 관련 파일: `services/api/migrations/versions/0009_catalog_details.py:1`, `services/api/migrations/versions/catalog_details.sql:1`, `services/api/kkulpick/extensions.py:1`, `services/api/kkulpick/api.py:55`, `services/api/kkulpick/analyses.py:130`, `services/recommendation/adapters/postgres.py:103`, `services/recommendation/adapters/offers_api.py:15`, `services/recommendation/http_service.py:71`
- 작성 AI: Gemini 4 Argon

## 문제점
1. **#49 카탈로그 DB 내 식품 원재료·알레르기 데이터 부재 및 알레르기 사용자 추천 차단**:
   - `app.foods` 테이블에는 `item_id`만 존재하고 원재료(`ingredients_raw`, `ingredients`)나 알레르기 유발물질(`allergens_declared`) 저장 컬럼이 없었다.
   - 그 결과 `PgCatalog`(`services/recommendation/adapters/postgres.py`)가 반환하는 후보 식품은 항상 성분이 비어 있었고, 추천 엔진의 보수적 안전 필터(`exclude_unknown=True`)가 알레르기/기피성분이 있는 사용자에게 모든 DB 후보 식품을 제외해 추천 결과가 0건이 되었다.
   - 또한 이미지 없이 `page_url`만으로 분석을 요청할 때 카탈로그 DB에서 해당 식품의 원재료를 가져와 알레르기 경고를 생성할 수 없었다.
2. **#50 상품 동일성·유사 매칭 및 상세 메타데이터(브랜드·모델번호·GTIN·옵션·이미지) 적재/조회 경로 부재**:
   - 수집기 파트(`services/collector/unified_live/VISION_MATCHING_CONTRACT.md`, `CONTRACT_GAPS.md`)에서 추출한 `matching_profile`(브랜드, 제조사, 모델명, 모델번호, MPN, GTIN, 색상, 사이즈, 옵션, 판매자, 대표/추가 이미지 URL)과 `food_evidence`를 백엔드에 저장할 테이블·컬럼·API가 없었다.
   - `GET /v2/offers` 및 분석 결과 카드(`offer_cards`)에 이미지 URL, 브랜드, 모델번호, 옵션, 식품 성분 정보가 노출되지 않았고, 동일/유사 상품 후보를 조회하는 매칭 API도 없었다.

## 원인
- `Observation v2`(`POST /internal/v2/crawl-runs/{run_id}/observations`, `services/api/kkulpick/models.py`)는 `ConfigDict(extra="forbid")`로 기본 관측 필드(`name`, `description`, `price`, `currency`, `url`, `availability`, `condition`)만 허용하며, 수집기 측 테스트(`domeggook_live/tests/test_delivery.py`)도 v2 관측 본문에 `image_url` 등 추가 필드가 들어가지 않음을 검증하고 있었다.
- `app.offer_changes.observation_id`는 `NOT NULL UNIQUE REFERENCES app.crawl_observations` 제약(`0002_arrival_updates.py`)을 가지고 있어, 별도 확장 요청의 변경 이력을 `app.offer_changes`에 직접 넣을 수 없는 구조였다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| A. 기존 `Observation v2`는 그대로 두고 버전 관리되는 별도 확장 수집 계약(`ListingExtension v1`)과 `app.listing_extensions` 원장 추가 + `0009_catalog_details` 마이그레이션으로 카탈로그/상품/식품/오퍼 컬럼 확장 | 기존 도매꾹 수집기 테스트 및 v2 계약 100% 호환, 확장 데이터만의 독립 타임스탬프(`detail_observed_at`, `food_observed_at`)·멱등성·변경 이력 관리 가능 | 관측과 확장을 두 엔드포인트로 전송해야 함 | ✅ |
| B. `Observation v2` 스키마에 모든 상세·식품 필드를 직접 추가 | 요청 1번으로 처리 가능 | 수집기 측 계약 문서(`VISION_MATCHING_CONTRACT.md`) 및 기존 배달 테스트(`test_delivery.py`) 깨짐 | |

## 해결 (적용 내용)
1. **Alembic 마이그레이션 `0009_catalog_details` 추가 (`down_revision = '0008_embedding_jobs'`)**:
   - `app.catalog_items`: `brand`, `manufacturer`, `category`, `image_url`, `image_urls (jsonb)` 추가 및 `catalog_items_brand_idx`(`lower(brand)`) 부분 인덱스 생성.
   - `app.products`: `model_name`, `model_number`, `mpn`, `gtin`, `identifiers (jsonb)`, `color`, `size`, `options (jsonb)`, `variant_signature` 추가 및 `products_gtin_idx`, `products_model_number_idx`, `products_mpn_idx` 부분 인덱스 생성.
   - `app.foods`: `ingredients_raw`, `ingredients (jsonb)`, `allergen_notice_raw`, `cross_contact_raw`, `allergens_declared (jsonb)`, `evidence_status`(`CHECK` 제약: `not_reported`, `reported`, `negative_claim_unverified`, `conflicting`, `image_only`, `ocr_unverified`), `food_observed_at` 추가.
   - `app.offers`: `seller_id`, `seller_name`, `detail_observed_at` 추가.
   - `app.listing_extensions`: 확장 수집 원장(`extension_id`, `run_id`, `source`, `observation_key`, `offer_id`, `schema_version`, `payload_hash`, `observed_at`, `normalized_payload`, `state`, `error_code`, `change_kind`, `changed_fields`, `before_data`, `after_data`, `UNIQUE(source, observation_key)`) 생성.
2. **멱등 확장 수집 및 후보 매칭 API 구현 (`services/api/kkulpick/extensions.py`)**:
   - `canonical_gtin()`: GS1 GTIN-8/12/13/14 숫자 검증 및 체크디지트 계산 후 14자리 표준 문자열로 정규화.
   - `check_image_url()`: `https` 필수, 자격증명 포함 URL 및 사설/루프백 호스트 차단, `CATALOG_IMAGE_HOSTS` 허용 목록 검증.
   - `POST /internal/v2/crawl-runs/{run_id}/extensions` 및 `POST /internal/v2/listing-extensions`:
     - `(source, observation_key)` 기준 멱등 처리(동일 해시는 `200`, 다른 페이로드는 `409 EXTENSION_PAYLOAD_CONFLICT`).
     - `(source, source_listing_id, variant_key)` 단위 `pg_advisory_xact_lock` 직렬화, 30일 초과 관측 `OBSERVATION_TOO_OLD` 격리, 삭제 매물 tombstone 검사.
     - `product` 매물에 `food_evidence` 전송 시 `DOMAIN_CONFLICT` 격리.
     - `detail_observed_at` 및 `food_observed_at` 타임스탬프 비교로 과거 확장 데이터의 최신 데이터 덮어쓰기(`stale`) 방지.
   - `GET /v2/offers/{offer_id}/matches`:
     - GTIN 일치, 브랜드+모델번호 일치, 브랜드+MPN 일치를 `exact_candidates`로, 브랜드+모델명 또는 브랜드+카테고리 일치를 `similar_candidates`로 분리하고 색상/사이즈/옵션 충돌(`_compare_options`) 후보를 제외하여 반환.
3. **상품 조회 및 분석 결과 카드 확장 (`api.py`, `analyses.py`)**:
   - `GET /v2/offers`와 분석 완료 조회(`offer_cards`)에 브랜드, 제조사, 카테고리, 대표/추가 이미지, 판매자, 모델명/모델번호/MPN/GTIN, 색상/사이즈/옵션, 식품 원재료/알레르기 표시/증거 상태를 포함했다.
4. **추천 엔진 `PgCatalog` 및 `/internal/catalog-context` 식품 원재료 연결 (`postgres.py`, `offers_api.py`, `http_service.py`)**:
   - `PgCatalog.get_many()`가 `LEFT JOIN app.foods f USING(item_id)`로 `ingredients_raw`, `ingredients`, `allergen_notice_raw`, `cross_contact_raw`, `allergens_declared`를 읽어 `CollectedProduct`를 생성하도록 연결했다.
   - `/internal/catalog-context`가 URL 매칭 시 상품명·종류뿐 아니라 DB에 저장된 `ingredients`도 함께 반환하도록 확장했다.

## 왜 그렇게 해결했는지
- `Observation v2`는 가격·재고·판매상태의 빠른 주기적 갱신을 담당하고, 상세 스펙·식별자·식품 성분표는 수집 주기와 추출 소스가 다를 수 있으므로 별도 확장 원장(`app.listing_extensions`)과 전용 타임스탬프(`detail_observed_at`, `food_observed_at`)로 분리하는 것이 기존 계약을 깨지 않으면서 데이터 정합성을 지키는 방법이었다.
- 알레르기 안전 판정에서 성분이 없는 식품을 무조건 안전하다고 가정하면 위험하므로, 기존 보수적 필터는 유지하되 DB `app.foods`에 실제 원재료 데이터를 적재·조회하는 통로를 열어 안전성이 확인된 대체 식품만 추천되도록 했다.

## 검증
- 첫 통합 실행(`45103700755`)에서 `test_embedding_pipeline.py`의 SQL 문자열 내 `'98%, 천일염 2%'` 리터럴이 `psycopg`의 `%s` 플레이스홀더 파서와 충돌(`ProgrammingError: only '%s', '%b', '%t' are allowed as placeholders, got '%,'`)한 것을 발견하여 커밋 `89948df`에서 `%s` 파라미터 바인딩으로 즉시 수정했다.
- [GitHub Actions `Persistent embedding pipeline` (Run #45104086541)](https://github.com/daon217/swproject/actions/runs/45104086541) 및 [#45105156543](https://github.com/daon217/swproject/actions/runs/45105156543): 실제 PostgreSQL 17 + pgvector 컨테이너에서 `0009_catalog_details` 마이그레이션, `test_listing_extension_matching_and_food_evidence`(확장 적재·멱등 재전송·충돌·구버전 무시·GTIN/모델번호 매칭·옵션 충돌 제외·도메인 충돌 격리·식품 원재료 조회), `test_domains_availability_and_missing_food_ingredients`(우유 알레르기 사용자에게 무성분 쿠키와 우유 쿠키는 제외하고 DB에 `["현미","천일염"]` 성분이 저장된 현미 쌀 쿠키만 추천) 모두 통과.

## 남은 과제 / 주의
- 당시 커밋(`4b1f5fc`)에서는 확장 정보가 첫 관측(`Observation v2`)보다 먼저 도착하면 `404 OFFER_NOT_FOUND`를 반환하고, 옵션은 `dict.update`로 병합만 했다. 이후 Claude 세션 2(#13, `b5c8caa`)에서 선도착 `pending` 보관 및 `null` 옵션 삭제가 보완되었다.
- 또한 당시에는 브랜드·카테고리 변경이 임베딩 트리거(`embedding_content_version`)에 포함되지 않았으나 이후 Claude 세션 2(#12, `0e3da73`)에서 `catalog-v2` 스냅샷으로 확장되었다.
- 백엔드 확장 API와 어댑터 도구는 준비되었으나 실제 운영 수집기 데몬이 주기적으로 `/extensions`를 호출하도록 연결하는 과제는 [OPEN_ISSUES.md](../../OPEN_ISSUES.md) #27·#32에 남아 있다.
