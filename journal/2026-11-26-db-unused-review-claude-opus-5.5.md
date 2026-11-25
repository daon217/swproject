# [Claude Opus 5.5] 개발일지 · 2026-11-26 미사용 DB·테이블·컬럼 점검(다른 AI 결과 검증 포함)

- 작성 AI: Claude Opus 5.5 · 기준 maintest 9b4d366 · 코드·DB 수정 없음
- 방법: 격리 DB에 maintest 마이그레이션 적용 → 스키마 덤프(`_exports/2026-11-26-schema`) → 모든 테이블·컬럼 이름을 런타임 코드(services, apps, tools, kkulpick_vision; tests·migrations 제외)와 SQL 함수에서 전수 검색 → 후보를 파일:줄로 개별 확인. 인덱스는 정의와 실제 쿼리 모양 대조.

## 다른 AI 주장 검증
| 주장 | 판정 | 근거 |
| --- | --- | --- |
| DB 3개 모두 사용 | 맞음 | |
| `ingredients`, `ingredient_embeddings` 미사용 | **맞음** | 쓰는 코드 없음. `vectors.py:7` TARGETS에만 이름, 임베딩 계약은 product/food만 |
| `price_history`, `offer_url_history`, `offer_changes` 쓰기·정리만, 조회 없음 | **맞음(보충)** | ingest 쓰기, maintenance·catalog_deletion 삭제뿐. 단 `price_history`·`offer_changes`는 crawl_observations를 FK로 참조해 관측 원본 보존 기간도 결정(maintenance.py:76-77) |
| `catalog_admin_audit`, `admin_audit` 조회 없음 | 맞음 | 감사 기록 용도라 유지가 맞음 |
| `admin_accounts`(구) vs `admin_identities`(신) 이중 구조 | 맞음(주의) | 구 방식 관리자 로그인 폴백·CLI·access.py가 아직 사용 → 지우려면 기존 관리자 이전 마이그레이션 필요 |
| `catalog_items.identity_status` 미사용 | 맞음 | 읽기·쓰기 0(기본값 고정). 수집기 같은 이름 필드는 DB에 저장 안 됨 |
| `analyses.image_expires_at` 쓰기만 | 맞음 | 이미지 만료는 파일 mtime 기준(images.py) |
| `offers.url_version` 쓰기만 | 맞음 | ingest.py:153 증가만 |
| `products.identifiers` 사실상 미사용 | 맞음 | 변경 비교에만 읽고 API·매칭에 안 씀 |
| `products.variant_signature` 매칭에 안 씀 | 부분적으로 맞음 | 계산·저장 후 `/v2/offers`·matches 응답에 내려가지만 매칭 로직·클라이언트가 쓰지 않음 |
| `embedding_models.query_prefix/document_prefix/normalize` 안 읽음 | **틀림** | `embedding_config.validate()`가 행 전체(to_jsonb)를 계약과 필드별 비교. 계약 식별(model_id 해시)에도 포함 |
| `listing_extensions.is_synthetic/product_url` 미사용 컬럼 | **해당 없음** | 컬럼이 아니라 요청 필드(normalized_payload에 보관) |
| 인덱스 `offers_page` 중복 | **틀림** | 접두가 다름. 추천 `all_ids()`(kind=… ORDER BY offer_id)와 `/v2/offers` 기본 condition=all(9b4d366)에서 이 인덱스가 맞는 모양 |
| `observations_retention` vs `observations_payload_cleanup` 중복 | **틀림** | 후자는 `normalized_payload<>'{}'` 부분 인덱스로 maintenance.py:44·71 원문 비우기 쿼리와 정확히 일치, 전자는 보존 삭제용 |
| `urls_by_offer` 중복 | **틀림** | `one_active_url`은 활성 행만 담는 부분 인덱스라 offer 삭제 시 전체 이력 조회(catalog_deletion)·FK 확인을 대신 못 함 |

## 추가로 찾은 것
- `members.consent_at`: 기본값으로만 기록, 코드에서 안 읽음 — 동의 시각 법적 기록이라 **유지**.
- `analyses.image_hash`, `listing_extensions.schema_version`: 저장만 하고 안 읽음(기록용, 영향 작음).
- 자동 스캔의 오탐: `product_embeddings`·`food_embeddings`(vectors.py에서 동적 이름으로 접근), `subscription_plans.interval`(members.py:289 조회).

## 정리 후보
- 지워도 기능 영향 없음: `ingredients`, `ingredient_embeddings`, `catalog_items.identity_status`, `analyses.image_expires_at`, `offers.url_version`, `products.identifiers`(수집기가 식별자를 보내면 쓸 계획이면 유지).
- 기획 결정 필요: 이력 3종(가격 변동·URL·변경 이력 화면 계획), `admin_accounts`(구 관리자 이전 후), `variant_signature`.
- 유지: 감사 2종, `consent_at`, 언급된 인덱스 전부.
