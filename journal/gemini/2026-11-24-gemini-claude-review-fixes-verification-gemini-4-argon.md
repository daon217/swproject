# [Gemini 4 Argon] 개발일지 · 2026-11-24 Claude 코드 리뷰 5건(URL 정규화·이미지 중복·422/503·매칭 절단·임베딩 잔류) 해결 및 다중 검증 (#53 #54)

- 날짜: 2026-11-24 (기록일, Asia/Seoul)
- 실제 작업 시기: 2026-11-23 13:36~13:51
- 상태: 해결 (5개 항목 모두 수정 및 4중 검증 완료; 이후 Claude 세션 1 #02·#03에서 호스트 식 인덱스 등 추가 고도화)
- 브랜치 / 커밋: `maintest` / [`3d7d6ed`](https://github.com/daon217/swproject/commit/3d7d6ed6151067064af6a70fcb3bc459560bf1d1), [`2c65ccd`](https://github.com/daon217/swproject/commit/2c65ccd67b545bad8c14e4f229f14af898926b6b)
- 관련 파일: `services/recommendation/http_service.py:72`, `services/api/kkulpick/extensions.py:95`, `services/api/kkulpick/extensions.py:429`, `services/recommendation/embedding_worker.py:33`, `services/api/migrations/versions/catalog_details.sql:60`, `services/api/tests/test_contract.py:79`, `services/api/tests/test_arrival_updates.py:212`, `services/dev_runtime/test_analysis_worker.py:59`, `services/recommendation/tests/test_embedding_pipeline.py:253`
- 작성 AI: Gemini 4 Argon

## 문제점
사용자가 Claude로 `maintest`(`103070f`)를 교차 검토하여 확인된 버그 3건과 주의사항 2건(총 5건)의 수정을 요청했다.
1. **#53-1 분석 페이지 URL 매칭 범위 축소 (`services/recommendation/http_service.py` `/internal/catalog-context`)**:
   - `WHERE o.current_url = %s`로 문자열이 완전히 같아야만 매칭되어, `https://WWW.11st.co.kr/...`(대문자 호스트), `http://` vs `https://`, 기본 포트(`:80`, `:443`), `#review` 프래그먼트가 포함된 페이지 URL이 카탈로그 상품과 매칭되지 않고 상품명·성분을 받지 못했다.
2. **#53-2 입력 오류가 `503`으로 응답됨 (`services/recommendation/http_service.py` `/internal/process`)**:
   - `except PG_ERRORS + (KeyError, OSError)`가 `KeyError`를 먼저 잡아서, 원래 `422 INVALID_RECOMMENDATION_INPUT`으로 응답되어야 할 입력 오류(`KeyError` 등)가 `503 RECOMMENDATION_DEPENDENCY_UNAVAILABLE`로 응답되고 두 번째 `except (ValueError, KeyError, ContractError)`의 `KeyError`가 죽은 코드가 되었다.
3. **#54-1 이미지 URL 중복 미제거 (`services/api/kkulpick/extensions.py` `MatchingProfile.valid_image_list`)**:
   - `seen` 리스트에 `HttpUrl` 객체를 추가하면서 `if s not in seen:`으로 문자열(`str`)과 비교해 항상 `True`가 되어 중복된 이미지 URL이 제거되지 않았다.
4. **#54-2 `/v2/offers/{id}/matches` 최저가 200개 절단 문제 (`services/api/kkulpick/extensions.py` `offer_matches`)**:
   - 아무 필터 없이 `ORDER BY o.price ASC LIMIT 200`으로 가장 싼 오퍼 200개만 먼저 가져온 뒤 파이썬에서 비교하여, 무관한 저가 상품이 200개 이상 있으면 GTIN이나 브랜드+모델번호가 똑같은 더 비싼 상품이 정확 일치 후보(`exact_candidates`)에서 누락될 수 있었다.
5. **#54-3 상품 도메인(`product` ↔ `food`) 변경 시 구 도메인 임베딩 작업 잔류 (`catalog_details.sql`, `embedding_worker.py`)**:
   - 상품의 `kind`가 바뀌면 새 도메인 모델의 작업만 enqueue되고 이전 도메인 모델의 `app.embedding_jobs` 행이 큐에 남아 재시도되거나 `--drain`을 막을 수 있었다.

## 원인
- #53-1: `2d444b0`에서 `context_url()`(파이썬 메모리 비교)을 DB 쿼리 `o.current_url = %s`로 바꿀 때 URL 정규화 후보 생성 로직이 빠졌다.
- #53-2: 환경변수(`os.environ['CATALOG_PASSWORD']`) 누락 시 발생하는 `KeyError`를 잡으려다 입력 검증 블록과 DB 연결 블록이 하나의 `try` 안에 섞였다.
- #54-1: Pydantic v2 `HttpUrl` 타입과 `str` 타입은 `==` 비교가 `False`라는 점을 놓쳤다.
- #54-2: 첫 구현(`4b1f5fc`)에서 SQL `WHERE` 절에 매칭 식별자 조건을 넣지 않고 Python 루프 필터링에만 의존했다. 또한 1차 수정(`3d7d6ed`)에서 SQL에 `(:gtin IS NOT NULL AND p.gtin = :gtin)`을 넣었을 때 `gtin=None`이면 `asyncpg`가 타입 미지정 NULL 파라미터 오류(`ProgrammingError`)를 일으키는 것을 CI에서 확인했다.
- #54-3: `app.enqueue_catalog_embedding()` 트리거가 `WHERE m.target = NEW.kind`인 작업만 `INSERT ... ON CONFLICT DO UPDATE`하고 `m.target <> NEW.kind`인 기존 대기 작업을 지우지 않았다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| A. ① URL은 정규화 후보 배열(`ANY(%s)`)로 기존 인덱스를 먼저 타고 대소문자 호스트 폴백 지원, ② 입력 검증 `try`와 DB/임베딩 `try` 블록 분리, ③ `seen_urls: set[str]`로 중복 제거, ④ `offer_matches`는 값이 있는 식별자만 동적 SQL 조건·우선순위 정렬로 조립, ⑤ DB 트리거 + 워커 `finish()` 양쪽에서 도메인 불일치 작업 즉시 삭제 | 5가지 문제를 모두 근본 원인에서 해결하고 `asyncpg` 타입 추론 오류와 인덱스 미사용 문제를 동시에 방지 | 동적 조건 조립 코드가 약간 길어짐 | ✅ |
| B. `offer_matches`에서 단순히 `LIMIT 200`만 `LIMIT 5000`으로 상향 | 코드 변경이 1줄임 | 상품이 5,000개를 넘으면 다시 재발하며 불필요한 행을 대량 로드함 | |

## 해결 (적용 내용)
1. **`/internal/catalog-context` URL 정규화 매칭 복원 (`services/recommendation/http_service.py`, `3d7d6ed`)**:
   - `_normalized_url_candidates(raw_url)`로 공백/프래그먼트(`#...`) 제거, 소문자 호스트, `https`/`http` 양쪽 스킴, 기본 포트(`:80`, `:443`) 제거, 끝 슬래시 변형 후보 리스트를 만들어 `WHERE o.current_url = ANY(%s)`로 `offers_context_url` 인덱스를 타도록 했다.
   - 만약 DB에 대문자 호스트로 저장된 URL이 있어 1차 매칭이 안 되면 소문자 호스트 추출 조건으로 보조 조회한 뒤 `(host, path?query)`가 일치하는 오퍼를 매칭하도록 했다.
2. **`/internal/process`의 `422` vs `503` 예외 처리 분리 (`services/recommendation/http_service.py`, `3d7d6ed`)**:
   - 입력 프로필 파싱 및 `UserProfile.from_dict(raw)` 단계를 별도 `try ... except (ValueError, TypeError, KeyError, ContractError)`로 분리하여 잘못된 입력(빈 `user_id`, 리스트가 아닌 `allergens`, 알 수 없는 프로필 키, `KeyError` 등)은 항상 `422 INVALID_RECOMMENDATION_INPUT`을 반환하도록 고쳤다.
   - 이후 DB 연결 및 추천 실행 블록의 `PG_ERRORS + (KeyError, OSError)`만 `503`을 반환하도록 분리했다.
3. **`MatchingProfile.valid_image_list` 중복 제거 수정 (`services/api/kkulpick/extensions.py`, `3d7d6ed`)**:
   - `seen_urls: set[str]`에 `str(v)`를 기록하고 `deduped: list[HttpUrl]`에는 원본 `HttpUrl`을 담아 순서를 유지하며 중복을 제거했다.
4. **`/v2/offers/{offer_id}/matches` SQL 필터링·정확 일치 우선 정렬 및 `asyncpg` 동적 조건 조립 (`extensions.py`, `3d7d6ed`, `2c65ccd`)**:
   - 대상 오퍼의 `gtin`, `brand`, `model_number`, `mpn` 중 값이 존재하는 항목만 SQL `WHERE` 절(`p.gtin = :gtin`, `lower(i.brand) = :brand`, `lower(p.model_number) = :model_num`, `lower(p.mpn) = :mpn`)과 `ORDER BY CASE WHEN (...) THEN 0 ELSE 1 END ASC, o.price ASC`에 동적으로 포함시켰다.
   - 이를 통해 `asyncpg`의 untyped NULL 파라미터 `ProgrammingError`를 방지하고, 무관한 저가 상품이 수백 개 있어도 정확 일치 상품이 0순위로 조회되도록 했다.
5. **도메인(`product` ↔ `food`) 전환 시 구 도메인 임베딩 작업 정리 (`catalog_details.sql`, `embedding_worker.py`, `3d7d6ed`)**:
   - `catalog_details.sql`에서 `app.enqueue_catalog_embedding()` 트리거 함수를 갱신하여 `NEW.kind IS DISTINCT FROM OLD.kind`일 때 `m.target <> NEW.kind`인 `app.embedding_jobs` 행을 즉시 `DELETE`하도록 했다.
   - `embedding_worker.py`의 `finish()`에서도 `app.catalog_items.kind`와 `app.embedding_models.target`을 대조해 아이템이 삭제되었거나 도메인이 바뀐 경우 해당 작업을 즉시 `DELETE`하고 `False`를 반환하도록 이중 방어를 적용했다.

## 왜 그렇게 해결했는지
- 단순 상한 조정이나 단일 계층 방어 대신, URL 매칭은 인덱스 경로(`ANY(%s)`)와 대소문자 폴백을 함께 두고, 임베딩 작업 정리는 DB 트리거(발생 시점 차단)와 워커 `finish()`(이미 임대된 인플라이트 작업 정리) 양쪽에 적용해야 경합 상황에서도 찌꺼기 작업이 남지 않기 때문이다.

## 검증
4가지 독립된 방법으로 교차 검증을 수행했다.
1. **로컬 단위 및 회귀 테스트 (`uv run pytest`, Python 3.12)**:
   - `services/api/tests/test_contract.py`, `services/dev_runtime/test_analysis_worker.py`, `services/recommendation/tests`, `services/collector/elevenst_offline/tests/test_pipeline.py` 실행 → **125 passed, 13 skipped** (6.1~14.0초).
   - 중복 이미지 4개 → 2개 압축(`test_listing_extension_validation_gtin_and_images`), URL 정규화 및 `422` vs `503` 분기(`test_normalized_url_candidates_and_process_422_vs_503`) 통과.
2. **독립 시나리오 검증 스크립트 실행**:
   - 6종 변형 URL(`https://WWW.11st.co.kr/...`, `http://...:80/...#qna`, `https://...:443/...#top` 등) 매칭 및 다른 쿼리(`?trTypeCd=99`) 미매칭, `image_urls` 순서 보존 중복 제거, `/internal/process` 422 응답, 워커 인플라이트 도메인 전환 시 `DELETE FROM app.embedding_jobs` 실행을 인메모리 Fake/Mock 커넥션으로 직접 검증(`ALL 5 MULTI-METHOD VERIFICATIONS PASSED!`).
3. **실제 PostgreSQL 17 + pgvector 통합 테스트 (`test_arrival_updates.py`, `test_embedding_pipeline.py`)**:
   - `test_listing_extension_matching_and_food_evidence`: 100원짜리 무관한 상품 **210개**를 먼저 넣은 뒤 99,000원짜리 동일 GTIN 상품을 추가했을 때 `/v2/offers/{id}/matches`의 `exact_candidates`에 99,000원 상품이 누락 없이 포함됨을 실제 DB에서 확인.
   - `test_context_lookup_is_exact_and_not_first_thousand_limited`: 1,001개 상품에서 `https://STORE.EXAMPLE.TEST/1000#review`, `http://store.example.test/1000#detail`, `https://store.example.test:443/1000` 모두 정상 매칭 확인.
   - `test_domain_switch_cleans_up_stale_embedding_jobs`: 실제 DB 트랜잭션에서 `product` → `food`로 전환 시 기존 `product` 모델 임베딩 작업이 즉시 삭제되고 `food` 모델 작업만 남아 `drain()` 후 대기 작업이 `0`이 됨을 확인.
4. **GitHub Actions CI 전체 통과 (`maintest` 커밋 `2c65ccd`)**:
   - [Team build (Run #45114083442)](https://github.com/daon217/swproject/actions/runs/45114083442) — **10개 Job 전원 `success`**
   - [Persistent embedding pipeline (Run #45114082875)](https://github.com/daon217/swproject/actions/runs/45114082875) — `postgres`(실제 DB 마이그레이션·회귀·컨테이너 스모크) 및 `semantic-model` **전원 `success`**

## 남은 과제 / 주의
- `3d7d6ed`의 `/internal/catalog-context` 대소문자 호스트 보조 검색은 `LIMIT 50` 후 파이썬에서 `path?query`를 비교했고, `2c65ccd`의 `offer_matches`는 정확 일치(0) 외의 유사 후보를 가격순으로 정렬했다. 이 두 가지는 다음 날 Claude 세션 1(`part/소병선-backend-test`, `2e2a806`)의 **#02**(SQL 내 suffix 비교 + `0010_offer_url_host` 식 인덱스)와 **#03**(브랜드+모델명 1순위 정렬)에서 추가로 다듬어졌다.
