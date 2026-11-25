# [Claude Opus 5.5] 개발일지 · 2026-11-26 DB 정규화·비정규화 점검과 최적화 (d85eeec, 로컬)

- 기준 maintest 9b4d366 → 테스트 브랜치 d85eeec (2026-11-26 테스트 브랜치·maintest 푸시 완료)
- 결과 스키마: `_exports/2026-11-26-schema/`, 한국어 ERD: `_exports/2026-11-26-ERD-한국어/` (생성기 `tools/erd/make_erd_ko.py`)

## 측정
- 인덱스 없는 외래키 7개 → 실제로 부모 행을 지우거나 검사하는 것만 의미: `listing_extensions.run_id`(maintenance가 오래된 수집 실행 삭제 시 매 실행마다 검사), `invoices.subscription_id`. `offers(item_id,kind)`는 `offers_by_item(item_id)`로 충분, 임베딩 model_id·구독 plan_id는 부모를 지우지 않음 → 인덱스 추가는 쓰기 비용만.
- 같은 사실을 두 번 저장하는 곳(비정규화) 점검:

| 반복 저장 | 원본 | 판단 |
| --- | --- | --- |
| offers.kind | catalog_items.kind | 유지 — 복합 FK로 이미 일치 보장, 목록 필터 인덱스에 필요 |
| crawl_observations.source, listing_extensions.source | crawl_runs.source | **보장 없음(코드 검사만)** → 복합 FK 추가 |
| invoices.user_id | subscriptions.user_id | 유지(회원별 결제 조회) 하지만 **보장 없음** → 복합 FK 추가 |
| listing_extensions의 수집처·상품 ID·옵션 키 | offers | 유지 — 관측 전 도착(보류) 상태엔 offer가 없음 |
| embedding_jobs.snapshot | catalog_items 내용 | 유지 — 작업 시점 내용 고정(outbox) |
| analyses.offer_ids (UUID 배열) | offers | 유지 — 작은 순서 있는 결과, 삭제된 상품은 카드에서 빠지는 게 의도 |
| foods.ingredients·allergens_declared (jsonb 배열) | — | 유지 — 통째로 읽고 씀. SQL 사전 필터를 만들 때 알레르기 코드 인덱스 검토 |

## 변경 (마이그레이션 0014_schema_integrity_cleanup, member_0005)
1. `crawl_runs UNIQUE(run_id, source)` + 관측·확장의 `(run_id, source)` 복합 FK (NOT VALID → VALIDATE: 운영 데이터 검사 후 적용)
2. `listing_extensions(run_id)` 부분 인덱스
3. `subscriptions UNIQUE(subscription_id, user_id)` + `invoices(subscription_id, user_id)` 인덱스·복합 FK
4. 죽은 컬럼 삭제: `catalog_items.identity_status`, `offers.url_version`, `analyses.image_expires_at` (쓰는 코드도 제거)
- 보류(팀 결정): `ingredients`·`ingredient_embeddings`(설계상 계획), 이력 3종, `admin_accounts`, `products.identifiers`·`variant_signature`

## 검증
- 새 테스트 `test_run_source_and_invoice_owner_are_enforced_by_the_database`: 다른 수집처 관측·확장, 다른 회원의 청구서가 DB에서 거부됨.
- 격리 DB 전체: API 93, 추천 85, 변조 33 (두 순서).
- 되돌리기: 두 DB 모두 downgrade(0013/member_0004, 삭제 컬럼 3개 복원) → upgrade(0014/member_0005) 왕복 성공.
- 운영 적용 주의: VALIDATE 단계에서 기존 데이터가 규칙을 어기면 마이그레이션이 멈춤(코드가 막아 왔으므로 없어야 정상).
