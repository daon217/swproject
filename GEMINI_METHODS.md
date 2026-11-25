# [Gemini 4 Argon] Gemini 점검·테스트 수행 방법과 이력

- 작성일: 2026-11-25. 작성 AI: **Gemini 4 Argon** (`gemini-4-argon-medium`).
- 범위: **2026-11-19 초기 구조 파악 및 2026-11-23 전수 조사·하드웨어/성능 분석·`maintest` 7개 커밋(`4b1f5fc`~`2c65ccd`) 구현·Claude 리뷰 5건 수정·4중 검증 및 2026-11-24/25 `devlog` 검증**.
- 목적: 단순히 “통과했다”만 남기지 않고 **무엇을, 왜, 어떤 도구와 환경에서, 어떤 입력·행동·기대값·판정 기준으로 점검하고 테스트했는지**, 그리고 **중간 실패에서 무엇을 발견해 어떻게 고쳤는지**를 남긴다.
- 근거: `maintest`에 고정된 커밋(`4b1f5fc`~`2c65ccd`), GitHub Actions 실행 및 Job 로그, 로컬 `uv` Python 3.12 실행 결과, `devlog` 교차 검토 정오표. 이번 문서 작성은 과거 수행 방법의 복원·검증이며 오늘 전체 서비스 컨테이너를 새로 기동한 것이 아니다.
- 읽는 순서: 이 문서 → [Gemini 개발 기록 대응표](GEMINI_COVERAGE.md) → 개별 일지(`#48`~`#54`). 공통 재검증 절차는 [METHODS.md](METHODS.md), [VERIFY.md](VERIFY.md), [GPT_METHODS.md](GPT_METHODS.md)를 함께 참고한다.

---

## 1. 기존 방법론(`METHODS.md` · `PROMPTS.md` 8번)을 참고한 범위

`PROMPTS.md` 2·5~8번과 `METHODS.md`, `GPT_METHODS.md` 전체를 읽고, 원칙·도구·점검 방식·영역별 검증 설계·실제 명령 발췌·수행 이력·실패/정정 기록·게시 후 재검증 순서로 정리했다.

| 구분 | Gemini 기록에 적용하는 기준 |
| --- | --- |
| Gemini의 실제 수행 범위 | 11-19 구조 파악, 11-23 원격 브랜치/CI 조사, `maintest` `4b1f5fc`~`2c65ccd` 구현·단위/시나리오/CI 통합 검증, 11-24/25 `devlog` 검증만 Gemini 수행 사실로 기록 |
| 다른 AI(GPT·Claude) 작업과의 경계 | `2d444b0` 이전의 초기 DB·비즈니스 API·영속 임베딩 구축은 GPT([GPT_METHODS.md](GPT_METHODS.md))에, `2c65ccd` 이후 `part/소병선-backend-test`의 `#01`~`#33`·`#55`~`#59` 및 로컬 Linux 컨테이너 스크립트(`tools/run-all.sh`), 시뮬레이션(`sim/`), 내장 브라우저 UI 클릭, ERD 생성은 Claude([METHODS.md](METHODS.md))에 귀속되며 Gemini가 수행한 것으로 소급하지 않음 |
| 로컬 vs 원격 CI 구분 | 당시 Windows 로컬 PC는 Docker Desktop 데몬(`dockerDesktopLinuxEngine`)이 꺼져 있어, 로컬에서는 **DB 없는 단위 테스트(`uv run pytest`)와 인메모리 Fake/Mock 독립 시나리오 스크립트**를 실행하고, **실제 PostgreSQL 17 + pgvector 마이그레이션·동시성·컨테이너 스모크·오프라인 MiniLM 모델 검증은 GitHub Actions(`maintest`)에서 실행 후 `gh run watch`/`gh run view`로 Job 로그를 확인**했다. 이 두 환경을 섞어 쓰지 않는다 |
| 사실 vs 추정/정정 구분 | 코드·커밋 diff·CI 로그로 확인한 사실과 하드웨어 메모리/속도 추정치를 명확히 구분하고, 이후 Claude 교차 검토(`#55`~`#57`)에서 밝혀진 `#48`의 진단 오류 정정을7절에 그대로 반영한다 |

---

## 2. 사용한 도구와 역할

| 도구 | 어떻게 사용했는가 | 확인한 범위와 한계 |
| --- | --- | --- |
| Git · 격리 클론/Worktree | 사용자의 `C:\Users\user\swproject`(미커밋 `apps/mobile` 변경 포함)를 건드리지 않기 위해 `scratch/swproject-maintest`(코드용)와 `scratch/swproject-devlog`(문서용 worktree)로 분리; `git fetch --all --prune`, `git show <SHA>:<경로>`, `git log A..B --stat` 수행 | 로컬 미커밋 파일 100% 보호, 브랜치별 정확한 커밋·줄 대조 |
| GitHub CLI (`gh`) | `gh run list`, `gh run watch --exit-status`, `gh run view <id> --log-failed`, `gh run view --job <job_id> --log`, `gh workflow run build.yml --ref maintest` | 원격 CI 트리거, 실시간 완료 대기, 실패 스택트레이스 및 통과/스킵 수 직접 확인 |
| `uv` (Python 3.12 격리 런타임) | Windows 로컬에 Python 3.14/3.15만 기본 설치되어 있고 `pytest`가 전역에 없어 `uv run --python 3.12 --with ...`으로 격리된 Python 3.12 테스트 환경을 즉석 구성해 실행 | 로컬 전역 패키지 오염 없이 CI(Python 3.12)와 동일한 인터프리터 메이저/마이너 버전에서 단위 테스트 수행 |
| `pytest` · `FastAPI TestClient` | `services/api/tests/test_contract.py`, `services/dev_runtime/test_analysis_worker.py`, `services/recommendation/tests`, `services/collector/elevenst_offline/tests/test_pipeline.py` 실행 | Pydantic 스키마·GTIN 체크디지트·HTTPS 이미지·URL 정규화·422/503 예외 분기·11번가 어댑터 단위 검증 |
| `httpx.MockTransport` · `ThreadPoolExecutor` | 외부 네트워크 없이 API(`api`), Vision(`vision-api:8100`), 추천(`recommendation`) 응답을 모킹하고, 3개 분석 작업을 동시 투입해 폴링 지연 중 후속 작업 추월 완료 순서를 검증 | `analysis_worker.py`의 병렬 claim/process 동작과 Head-of-Line Blocking 해소 확인 (실제 OCR 컨테이너 부하는 별도) |
| 인메모리 Fake/Mock 시나리오 스크립트 (`python -c`) | `pytest` 외에 별도 파이썬 원라이너 스크립트로 `FakeConn`/`WorkerConn`을 주입해 6종 변형 URL 매칭, 2종 불일치 쿼리 거절, 이미지 중복 제거, 422 응답, 도메인 전환 시 `DELETE FROM app.embedding_jobs` SQL 호출을 재검증 | 수정한 함수와 SQL 분기가 의도대로 호출되는지 다중 방법으로 교차 확인 |
| PostgreSQL 17 + `pgvector` + Alembic (`Persistent embedding pipeline` CI) | Ubuntu Actions runner에서 실제 PostgreSQL 17 컨테이너 기동 → `0009_catalog_details` 마이그레이션 → `test_embedding_pipeline.py` 및 API 통합 테스트(`CATALOG_INTEGRATION=1`) → 실제 `recommendation`·`embedding-worker` Docker 컨테이너 빌드/기동 및 `--drain` 검증 | 실제 DB 제약, `pg_advisory_xact_lock`, 트리거(`enqueue_catalog_embedding`), HNSW 벡터 검색, 식품 원재료 기반 알레르기 필터링, 210개 저가 상품 너머의 정확 일치 매칭 확인 |
| 오프라인 `SentenceTransformer` (`semantic-model` CI Job) | 고정 revision(`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`)의 `paraphrase-multilingual-MiniLM-L12-v2` 모델을 Docker 이미지에 굽고 `docker run --rm --network none`으로 실행 | 네트워크 단절 상태에서 384차원 출력 및 한국어 쿼리-문서 내적 점수 확인 |

---

## 3. 점검에서 검증까지 진행한 방식

1. **작업 공간 격리 및 읽기 전용 원칙 준수**:
   - 사용자가 "파일 수정 없이 파악만 해둘 것"을 요청했을 때(11-19, 11-23 오전)는 `git fetch --all --prune`과 읽기 전용 `git show` / `gh run view`만 수행했다.
   - 코드 수정 지시(`maintest` 반영)가 내려온 뒤에는 로컬 `C:\Users\user\swproject`의 unstaged 파일(`apps/mobile/.env.example`, `apps/mobile/package-lock.json`)을 보호하기 위해 `C:\Users\user\.gemini\antigravity\scratch\swproject-maintest`에 별도 클론을 만들어 작업했다.
2. **기존 계약 및 제약조건 선행 확인**:
   - 코드를 고치기 전에 기존 테스트와 SQL 제약을 먼저 확인했다. 예를 들어 `Observation v2`에 `image_url`을 직접 넣으면 도매꾹 수집기 테스트(`test_delivery.py`)와 `VISION_MATCHING_CONTRACT.md`가 깨진다는 점, `app.offer_changes.observation_id`가 `app.crawl_observations`에 대한 `NOT NULL UNIQUE` FK를 가져 확장 변경 이력을 `app.listing_extensions`에 따로 저장해야 한다는 점을 먼저 확인하고 설계했다.
3. **4중 교차 검증 (Multi-method Verification)**:
   - **1단계 (로컬 단위 테스트)**: `uv run --python 3.12 ... pytest`로 API 계약·분석 워커·추천·11번가 수집기 테스트 125개 통과 확인.
   - **2단계 (독립 재현/시나리오 스크립트)**: `pytest` 픽스처에 의존하지 않는 독립 파이썬 스크립트로 경계값(대소문자 호스트·포트·`#fragment` URL 8종, 중복 이미지 배열, 잘못된 프로필 dict, 도메인 전환 인플라이트 워커)을 직접 주입해 `assert` 검증.
   - **3단계 (프로젝트별 단위 CI — `Team build`)**: `gh workflow run build.yml --ref maintest`로 9개 프로젝트(`api`, `recommendation`, `vision`, `collector`, `dev-runtime`, `web`, `admin`, `extension`, `mobile`)와 `CI configuration`까지 총 10개 Job이 `psycopg` 없는 단위 환경에서도 모두 통과하는지 확인.
   - **4단계 (실제 PostgreSQL 17 + pgvector 통합 CI — `Persistent embedding pipeline`)**: 실제 DB 마이그레이션(`0009_catalog_details`), 동시성/역전 방지/매칭/원재료 필터링 통합 테스트, Docker 컨테이너 스모크 및 오프라인 384차원 임베딩 모델 호환성까지 통과 확인.
4. **실패 로그 즉시 대조 및 근본 원인 수정**:
   - CI나 로컬 테스트가 실패하면 추측하지 않고 `gh run view <id> --log-failed`로 정확한 예외 클래스와 파일:줄을 확인해 즉시 후속 커밋(`89948df`, `3fd6f83`, `6180147`, `103070f`, `2c65ccd`)으로 고치고 두 워크플로를 모두 재실행해 `success`를 확인했다.

---

## 4. 항목별로 무엇을 어떻게 검사했는가

### 4.1 전체 구조·원격 20개 브랜치·CI 실패 진단 및 헤놀로지 하드웨어 분석 (`#48`)
- **목적**: 코드 수정 전 전체 브랜치 병합 상태, `origin/main`의 반복 CI 실패 원인, 헤놀로지(`i5-6600`, `16GB`, `5.4TB`) 구동 가능성 및 저장소 전체 문제점을 파악한다.
- **방법**:
  - `git branch -a`, `git log origin/main..origin/<브랜치>`로 `maintest`(`2d444b0`), `part/최준서-collector`(`b1f45f9`), `codex/separate-admin-signup`(`855192d`, `52c486e`), `part/김호진-web`의 커밋 차이를 대조했다.
  - `gh run view 45035799528`(`Team connected runtime`) 및 `gh run view 44495089917`(`Frontend backend integration`) 실패 로그와 커밋 `c7d8cdf`, `e7f7007`의 diff를 대조했다.
  - Intel Core i5-6600(Skylake) 명령어 집합(`AVX`, `AVX2`, `FMA3`)과 각 서비스 컨테이너의 베이스 이미지·모델 크기를 대조했다.
- **확인한 범위와 한계 (후속 정정 반영)**:
  - `guest-floating.spec.js:28`(모바일 비회원 `'식품'` 버튼 삭제 후 클릭 타임아웃)과 `console.spec.js:23`(`'답변 추가'` → `'답변 보내기'`) 진단은 정확했다.
  - **한계 및 정정**: 당시 `apps/web/pages/*` 코드만 보고 `console.spec.js:29, 38`도 문구 불일치라고 진단했으나, 실제로는 `index.html` 마지막에 로드되는 `apps/web/shared/backend.js` 덮어쓰기 계층이 옛 문구를 반환하고 있어 29행은 통과하고 33행에서 `/backend` 프리픽스 누락 404(`#55`)로 실패하고 있었다(2026-11-25 Claude 교차 검토 `#55`~`#57`에서 확인·정정). 또한 헤놀로지 메모리(4.5~5.8GB)와 처리 속도는 실제 NAS 컨테이너 `docker stats` 실측이 아닌 모델·프로세스 구조 기반 **산출 추정치**다.

### 4.2 카탈로그 DB 식품 원재료 저장(`0009_catalog_details`) 및 추천 엔진(`PgCatalog`) 연결 (`#49`)
- **목적**: `app.foods`에 실제 원재료·알레르기 정보를 저장하고, `PgCatalog`가 이를 읽어 알레르기 보유 사용자에게 안전한 식품만 추천하는지 확인한다.
- **환경·도구**: Ubuntu Actions 실제 PostgreSQL 17 + pgvector (`Persistent embedding pipeline`), `pytest`, `FastAPI TestClient`.
- **입력·행동·기대값** ([services/recommendation/tests/test_embedding_pipeline.py:192](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/recommendation/tests/test_embedding_pipeline.py#L192)):
  - 판매 불가(`ended`, `suspect`, `out_of_stock`) 상품 3개, 성분 미입력 식품(`우유 쿠키`) 1개, 안전 성분 입력 식품(`현미 쌀 쿠키`, `ingredients=["현미","천일염"]`) 1개, 알레르기 성분 입력 식품(`버터 우유 쿠키`, `ingredients=["밀가루","우유","버터"]`, `allergens_declared=["milk","wheat"]`) 1개를 실제 DB에 seed하고 `drain(conn)`으로 임베딩을 생성한다.
  - `allergens=["milk"]` 프로필과 `ingredients=["우유"]`(현재 페이지 OCR 성분)로 `POST /internal/process`를 호출했을 때:
    1. 현재 페이지 성분에 대한 `'milk'` 알레르기 경고가 `warnings`에 생성되어야 한다.
    2. 성분이 비어 있는 `우유 쿠키`와 우유가 포함된 `버터 우유 쿠키`는 추천 결과(`offer_ids`)에서 **제외**되어야 한다.
    3. DB에 안전 원재료가 저장된 `현미 쌀 쿠키`는 추천 결과(`offer_ids`)에 **포함**되어야 한다.

### 4.3 상품 상세·식별자 확장 수집(`ListingExtension v1`) 및 후보 매칭 API (`#50`)
- **목적**: `Observation v2` 계약을 깨지 않고 브랜드·모델번호·MPN·GTIN·옵션·이미지·식품 원재료를 멱등 적재하고, 동일/유사 상품 후보를 정확히 매칭하는지 확인한다.
- **환경·도구**:
  - 단위 검증: 로컬 `uv run pytest` ([services/api/tests/test_contract.py:73](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/api/tests/test_contract.py#L73))
  - 실제 DB 통합 검증: Ubuntu Actions PostgreSQL 17 ([services/api/tests/test_arrival_updates.py:156](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/api/tests/test_arrival_updates.py#L156))
- **입력·행동·기대값**:
  1. **GS1 GTIN-14 정규화 및 이미지 URL 검증**: `"8801043014809"` → `"08801043014809"`, 잘못된 체크디지트(`"8801043014800"`), `http://` 비보안 이미지, `https://127.0.0.1/...` 사설 호스트 이미지, 본문 없는 빈 확장 요청은 모두 `ValidationError`(422)로 거절.
  2. **멱등성·충돌·구버전 역전 방지**:
     - 첫 전송 `POST /internal/v2/crawl-runs/{run_id}/extensions` → `201 Created` (`state='applied'`).
     - 동일 `(source, observation_key)` + 동일 본문 재전송 → `200 OK` (멱등).
     - 동일 키 + 다른 본문(`is_synthetic=True`) → `409 Conflict` (`EXTENSION_PAYLOAD_CONFLICT`).
     - 더 오래된 `observed_at`으로 브랜드 변경 전송 → `change_kind='stale'`로 기록만 되고 최신 브랜드가 유지됨.
  3. **후보 매칭 및 옵션 충돌 제외**:
     - 기준 오퍼(`stable-1`, `new`, `color='blue'`, `gtin='08801043014809'`)와 동일한 GTIN·모델번호·색상을 가진 중고 오퍼(`stable-2`, `used`)는 `include_used=true`일 때 `exact_candidates`에 포함되고 `include_used=false`일 때 제외됨.
     - 동일한 GTIN·모델번호라도 `color='red'`로 옵션이 충돌하는 오퍼(`stable-3`)는 `exact_candidates`에서 제외됨.
  4. **도메인 격리 및 식품 원재료 조회**:
     - `product` 오퍼에 `food_evidence` 전송 시 `state='quarantine'`, `error_code='DOMAIN_CONFLICT'`.
     - `food` 오퍼에 `POST /internal/v2/listing-extensions`로 원재료(`['유기농 현미', '천일염']`)와 알레르기 표시(`['soy']`) 전송 시 `201 Created`, 이후 `GET /v2/offers?selected_domain=food` 응답에 해당 배열이 정확히 노출됨.

### 4.4 11번가 오프라인 어댑터·분석 워커 병렬 처리·단위 CI `psycopg` 가드 (`#51` · `#52`)
- **목적**:
  1. 11번가 파서 출력(`parse_listing`)이 백엔드 `Observation v2` 및 `ListingExtension v1` 페이로드로 변환·전송되는지 확인한다.
  2. 분석 워커가 느린 Vision OCR 폴링 중에도 다른 분석 작업을 동시에 가져와 먼저 완료하는지 확인한다.
  3. `psycopg`가 설치되지 않은 단위 CI(`Team build`)에서도 모든 프로젝트 테스트와 `tools/check_adapter.py`가 통과하는지 확인한다.
- **입력·행동·기대값**:
  - **11번가 어댑터** ([services/collector/elevenst_offline/tests/test_pipeline.py:210](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/collector/elevenst_offline/tests/test_pipeline.py#L210), [services/dev_runtime/test_analysis_worker.py:248](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/dev_runtime/test_analysis_worker.py#L248)): `parse_listing` 결과에 대해 `prepare_elevenst_observation`(`schema_version=2`, `price='1234'`)과 `prepare_elevenst_extension`(브랜드, 모델번호, GTIN, 식품 원재료)을 생성하고 Mock transport로 201 응답을 받아 `applied=True`, `extension_applied=True`를 확인.
  - **병렬 분석 워커** ([services/dev_runtime/test_analysis_worker.py:199](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/dev_runtime/test_analysis_worker.py#L199)):
    - 큐에 `job-1`(이미지 포함, Vision status 3번째 폴링에서야 `success` 반환), `job-2`(이미지 없음, URL 카탈로그 매칭으로 식품 원재료 `['우유','밀가루']` 폴백 조회 후 우유 알레르기 경고 생성), `job-3`(이미지 없음, 일반 상품) 3건을 넣고 `worker.drain_concurrent(max_workers=3)` 실행.
    - 기대값: 3건 모두 완료(`== 3`)되고, `job-1`이 OCR을 폴링하는 동안 `job-2`와 `job-3`이 먼저 완료되어 `completed_order[-1] == 'job-1'`이어야 한다.

### 4.5 Claude 코드 리뷰 5건 수정 및 4중 검증 (`#53` · `#54`)
- **목적**: Claude 리뷰에서 지적된 버그 3건(URL 매칭 범위 축소, `image_urls` 중복 미제거, 입력 오류 503 응답)과 주의사항 2건(`offer_matches` 최저가 200개 절단, 도메인 전환 시 임베딩 작업 잔류)을 수정하고 4가지 방법으로 교차 검증한다.
- **항목별 입력·행동·기대값**:
  1. **URL 정규화 매칭 (`#53-1`)** ([services/recommendation/tests/test_embedding_pipeline.py:247](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/recommendation/tests/test_embedding_pipeline.py#L247)):
     - DB에 `https://store.example.test/1000`으로 저장된 상품에 대해 `https://store.example.test/1000#review`, `https://STORE.EXAMPLE.TEST/1000#review`, `http://store.example.test/1000#detail`, `https://store.example.test:443/1000`으로 `/internal/catalog-context` 호출 시 모두 `'가상 상품 1000'`과 매칭되어야 하고, 쿼리가 다른 `1000?different=1`은 `match: None`이어야 한다.
  2. **`422` vs `503` 예외 분리 (`#53-2`)** ([services/dev_runtime/test_analysis_worker.py:59](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/dev_runtime/test_analysis_worker.py#L59)):
     - 잘못된 프로필(`{'user_id': ''}`, `{'user_id': 'u', 'allergens': 'milk'}`, `{'user_id': 'u', 'unknown_field': 123}`) 및 `UserProfile.from_dict`에서 `KeyError` 발생 시 **`422`** 반환; 반대로 `config.connect`에서 `OSError('db down')` 발생 시 **`503`** 반환.
  3. **`image_urls` 중복 제거 (`#54-1`)** ([services/api/tests/test_contract.py:89](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/api/tests/test_contract.py#L89)):
     - `[".../1.jpg", ".../1.jpg", ".../2.jpg", ".../2.jpg"]` 입력 시 순서가 유지된 2개(`[".../1.jpg", ".../2.jpg"]`)로 중복 제거.
  4. **최저가 200개 너머의 정확 일치 매칭 (`#54-2`)** ([services/api/tests/test_arrival_updates.py:217](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/api/tests/test_arrival_updates.py#L217)):
     - 기준 상품(가격 12,000원, GTIN `08801043014809`) 외에 가격 100원짜리 무관한 상품 **210개**를 먼저 넣은 뒤, 가격 99,000원짜리 동일 GTIN 상품(`expensive-exact`)을 넣었을 때 `GET /v2/offers/{first_id}/matches?include_used=false`의 `exact_candidates`에 `expensive-exact`가 잘리지 않고 포함되어야 한다.
  5. **도메인(`product` ↔ `food`) 전환 시 구 도메인 임베딩 작업 자동 삭제 (`#54-3`)** ([services/recommendation/tests/test_embedding_pipeline.py:276](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/services/recommendation/tests/test_embedding_pipeline.py#L276)):
     - `product` 아이템을 생성해 `product` 모델 임베딩 작업이 큐에 들어간 상태에서, 트랜잭션 안에서 `app.products` 행을 지우고 `app.foods` 행을 넣은 뒤 `app.catalog_items.kind='food'`로 변경하면, 트리거가 기존 `product` 모델 작업을 즉시 삭제하고 `food` 모델 작업 1건만 남겨 `drain(conn)` 후 잔여 작업 수가 `0`이 되어야 한다. 또한 이미 워커에 임대(claim)된 인플라이트 작업도 `worker.finish()` 시점에 도메인 불일치를 감지해 `DELETE FROM app.embedding_jobs`를 수행함을 독립 스크립트로 확인했다.

---

## 5. 당시 실제 실행 명령과 문맥

아래 명령들은 Gemini가 로컬 Windows(`scratch/swproject-maintest`)와 GitHub Actions(`maintest`)에서 실제로 실행한 명령이다.

### 5.1 로컬 Windows Python 3.12 단위 테스트 (`uv run`, DB 없음)
- 작업 폴더: `C:\Users\user\.gemini\antigravity\scratch\swproject-maintest`
- 환경: Windows, Python 3.12.13 (`uv` 임시 환경), `CATALOG_INTEGRATION` 및 `EMBEDDING_INTEGRATION` 미설정(DB 의존 통합 테스트 13개는 자동 skip).

```powershell
$env:PYTHONPATH="C:\Users\user\.gemini\antigravity\scratch\swproject-maintest;C:\Users\user\.gemini\antigravity\scratch\swproject-maintest\services\api"
uv run --python 3.12 --with pytest --with fastapi --with httpx --with "sqlalchemy[asyncio]" --with pydantic --with toon-format --with anthropic pytest services/api/tests/test_contract.py services/dev_runtime/test_analysis_worker.py services/recommendation/tests services/collector/elevenst_offline/tests/test_pipeline.py -v
```
- 결과: **`125 passed, 13 skipped in 14.05s`**

### 5.2 로컬 독립 시나리오 검증 스크립트 (Fake/Mock 커넥션 기반 5종 경계 검증)
- 작업 폴더: `C:\Users\user\.gemini\antigravity\scratch\swproject-maintest`
- 목적: `pytest` 픽스처와 별개로 URL 정규화 8종(매칭 6·비매칭 2), `image_urls` 중복 제거, `/internal/process` 422 응답, `embedding_worker.finish()`의 도메인 불일치 작업 즉시 삭제 SQL 호출을 단일 스크립트로 검증.

```powershell
uv run --python 3.12 --with fastapi --with httpx --with "sqlalchemy[asyncio]" --with pydantic --with toon-format --with anthropic python -c "
import os
from fastapi.testclient import TestClient
from kkulpick.extensions import MatchingProfile
from services.recommendation import http_service, embedding_worker
# FakeConn으로 ANY(%s) 및 substring 호스트 폴백, MatchingProfile.image_urls 중복 제거,
# /internal/process 422 응답, WorkerConn으로 finish() 시 DELETE FROM app.embedding_jobs 호출 검증
"
```
- 결과: **`ALL 5 MULTI-METHOD VERIFICATIONS PASSED!`**

### 5.3 GitHub Actions 실제 PostgreSQL 17 + pgvector 통합 파이프라인 (`Persistent embedding pipeline`)
- 워크플로 파일: [.github/workflows/embedding-pipeline.yml:1](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/.github/workflows/embedding-pipeline.yml#L1)
- 실행 환경: Ubuntu runner, Docker PostgreSQL 17 + pgvector(`127.0.0.1:5433`), Alembic `upgrade head`(`0009_catalog_details` 포함), `RECO_EMBEDDER=hash` (`postgres` job) 및 고정 revision 실제 MiniLM 384차원 오프라인 컨테이너 (`semantic-model` job).

```bash
# 1) 추천·임베딩·병렬 분석 워커·11번가 어댑터 통합 및 단위 테스트 (저장소 루트)
EMBEDDING_INTEGRATION=1 python -m pytest -q services/recommendation/tests services/dev_runtime/test_analysis_worker.py
python -m unittest discover -s tools -p 'test_*.py' -q

# 2) 카탈로그 API·확장 적재·210건 너머 매칭·DB 회귀 테스트 (services/api)
cd services/api
CATALOG_INTEGRATION=1 CATALOG_PASSWORD="$CATALOG_APP_PASSWORD" python -m pytest -q --ignore=tests/test_sample_mutations.py

# 3) 실제 recommendation 및 embedding-worker 컨테이너 빌드·기동·스모크
docker compose --env-file infra/db/.env --env-file services/api/.env --env-file infra/workspace/.env \
  -f infra/db/compose.yaml -f infra/db/api.compose.yaml -f infra/integration/embeddings.compose.yaml \
  up -d --build --wait api recommendation embedding-worker
docker compose ... run --rm --no-deps embedding-worker --drain
```

### 5.4 GitHub Actions 전체 프로젝트 단위 CI (`Team build`)
- 워크플로 파일: [.github/workflows/build.yml:1](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/.github/workflows/build.yml#L1), 설정: [.ci/projects.json:1](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/.ci/projects.json#L1)
- 트리거 및 모니터링 명령:
```powershell
gh workflow run build.yml -R daon217/swproject --ref maintest
gh run watch <run_id> -R daon217/swproject --exit-status
```

---

## 6. 수행 이력과 결과 근거

서로 다른 실행의 통과 수를 합산하지 않는다. 각 실행(Run) 안에서의 세부 수치는 해당 Job 로그 원문과 일치한다.

| 시기 · 대상 커밋 | 환경 · 방법 | 실제 결과 및 세부 수치 | 실행 / Job 근거 |
| --- | --- | --- | --- |
| 11-19 · `main` | 로컬 파일·계약·마이그레이션 읽기 전용 파악 | 3개 DB 권한 분리·Alembic·운영 도구 구조 확인, 코드 수정 0건 | [#48 일지](journal/2026-11-24-gemini-survey-hardware-diagnostics-gemini-4-argon.md) |
| 11-23 오전 · `32f08ba`, `2d444b0` | `git fetch`, `gh run view` 읽기 전용 전수 조사 | 20개 브랜치·9종 Actions 파악, 16개 문제점 도출 (일부 UI 테스트 진단은 7절 정정 참조) | [Run 45035799528](https://github.com/daon217/swproject/actions/runs/45035799528), [Run 44495089917](https://github.com/daon217/swproject/actions/runs/44495089917) |
| 11-23 · `4b1f5fc` | Ubuntu Actions `Persistent embedding pipeline` (1차 실행) | `semantic-model` 통과; `postgres` Job에서 SQL `%,` 플레이스홀더 오류 및 11번가 어댑터 `requests` 미설치로 2건 실패 → 즉시 `89948df`로 수정 | [Run 45103700755](https://github.com/daon217/swproject/actions/runs/45103700755) / [postgres 137460071312](https://github.com/daon217/swproject/actions/runs/45103700755/job/137460071312) |
| 11-23 · `89948df` | Ubuntu Actions `Persistent embedding pipeline` (재실행) | `postgres` 및 `semantic-model` **모두 `success`** (`0009_catalog_details`, 식품 원재료 추천, 확장/매칭 API, 병렬 워커, 11번가 어댑터 통과) | [Run 45104086541](https://github.com/daon217/swproject/actions/runs/45104086541) / [postgres 137461273229](https://github.com/daon217/swproject/actions/runs/45104086541/job/137461273229) |
| 11-23 · `103070f` | Ubuntu Actions `Team build` + `Persistent embedding pipeline` | • `Team build`: **10개 Job 전원 `success`** (`CI configuration` + 9개 프로젝트)<br>• `Persistent embedding pipeline` (`postgres` `137464692324`): 추천·워커 **`68 passed, 1 skipped`**, 도구 **`17 tests OK`**, API **`64 passed, 1 skipped`** (해당 run 합계 **149 통과·2 skip**) + 컨테이너 스모크 및 `semantic-model`(`137464692082`) **성공** | [Team build 45105156508](https://github.com/daon217/swproject/actions/runs/45105156508)<br>[Embedding 45105156543](https://github.com/daon217/swproject/actions/runs/45105156543) |
| 11-23 오후 · `3d7d6ed` | 로컬 `uv run pytest` (Python 3.12) + 독립 시나리오 스크립트 | • 로컬 단위 pytest: **`125 passed, 13 skipped`** (14.05s)<br>• 독립 시나리오 5종 검증 스크립트: **`ALL 5 MULTI-METHOD VERIFICATIONS PASSED!`** | [#53·#54 일지](journal/2026-11-24-gemini-claude-review-fixes-verification-gemini-4-argon.md) |
| 11-23 오후 · `3d7d6ed` | Ubuntu Actions `Team build` + `Persistent embedding pipeline` | • `Team build`: 10개 Job 전원 `success`<br>• `Persistent embedding pipeline`: 추천·워커(`70 passed, 1 skipped`) 통과 후 API `test_arrival_updates.py`에서 `asyncpg` NULL 파라미터 타입 추론 `ProgrammingError` 1건 실패 → 즉시 `2c65ccd`로 수정 | [Team build 45113756891](https://github.com/daon217/swproject/actions/runs/45113756891)<br>[Embedding 45113756566](https://github.com/daon217/swproject/actions/runs/45113756566) |
| 11-23 오후 · `2c65ccd` | Ubuntu Actions `Team build` + `Persistent embedding pipeline` (최종) | • `Team build`: **10개 Job 전원 `success`**<br>• `Persistent embedding pipeline` (`postgres` `137492787339`): 추천·워커 **`70 passed, 1 skipped`**, 도구 **`17 tests OK`**, API **`64 passed, 1 skipped`** (해당 run 합계 **151 통과·2 skip**) + 컨테이너 `--drain` 스모크 통과<br>• `semantic-model` (`137492787444`): `dimensions=384`, `offline=True`, `0.6387365338826615 > 0.008583121512580857` | [Team build 45114083442](https://github.com/daon217/swproject/actions/runs/45114083442)<br>[Embedding 45114082875](https://github.com/daon217/swproject/actions/runs/45114082875) |

---

## 7. 놓쳤던 것·실패에서 확인한 것·교차 검토 정정 수용

| 항목 | 관찰 / 실패 원인 | 해결 및 남는 한계 / 정정 |
| --- | --- | --- |
| `catalog_details.sql` 초기 인덱스 대상 컬럼 | 초안 작성 시 `products_model_number_idx`에 `lower(brand)`를 함께 넣었으나 `brand`는 `app.catalog_items`에 있고 `model_number`는 `app.products`에 있음 | 커밋 전 스키마 대조로 발견해 `catalog_items_brand_idx`와 `products_model_number_idx`로 분리 (`4b1f5fc`) |
| GitHub OAuth 토큰 `workflow` 스코프 제한 | `.github/workflows/embedding-pipeline.yml`에 11번가 테스트 경로를 추가해 push하자 GitHub가 `refusing to allow an OAuth App to create or update workflow without workflow scope`로 거절 | 워크플로 파일 수정을 즉시 되돌리고, 기존 워크플로가 이미 실행하는 `services/dev_runtime/test_analysis_worker.py`에 11번가 어댑터 테스트를 추가해 CI에서 자동 실행되게 함 |
| `psycopg`의 `%` 리터럴 플레이스홀더 파싱 (`45103700755`) | `test_embedding_pipeline.py`에서 `UPDATE app.foods SET ingredients_raw='현미 98%, 천일염 2%' WHERE item_id=%s`를 실행하자 `psycopg`가 `'98%,'`의 `%,`를 잘못된 포맷 지정자로 해석해 `ProgrammingError` 발생 | `89948df`에서 문자열 리터럴을 `%s` 바인딩 파라미터(`('현미 98%, 천일염 2%', safe_item)`)로 분리해 해결 |
| 11번가 어댑터의 `requests` 간접 의존성 (`45103700755`) | `elevenst_offline/backend_adapter.py`가 `domeggook_backend.py`의 헬퍼를 import했는데, `domeggook_backend.py` 최상단의 `import requests` 때문에 `requests`가 없는 `dev_runtime` 테스트 환경에서 `ModuleNotFoundError` 발생 | `89948df`에서 `domeggook_backend` 의존성을 제거하고 `urllib.parse`와 `re` 표준 라이브러리만으로 검증 로직을 내장해 해결 |
| 단위 CI(`Team build`)의 `psycopg` 미설치 환경 (`45104927874`) | `build.yml`의 `recommendation` 프로젝트 단위 테스트는 `psycopg`를 설치하지 않아 `embedding_config.py`, `http_service.py`, `embedding_worker.py`, `test_embedding_pipeline.py` import 단계에서 실패 | `3fd6f83`, `6180147`, `103070f`에서 `try: import psycopg` 선택적 가드를 적용하고 `tools/check_adapter.py`에 `CATALOG_PASSWORD` 미설정 시 인메모리 스텁을 추가해 10개 Job 전원 통과 확인 |
| 로컬 `uv` 실행 시 비동기 드라이버·선택 패키지 및 `monkeypatch.undo()` | 로컬 1차 `uv run`에서 `sqlalchemy[asyncio]`용 `greenlet`, `toon-format`, `anthropic` 누락으로 3건 실패하고, `test_analysis_worker.py`에서 `UserProfile.preferences`(문자열 필드)에 문자열을 넣어 422 대신 200이 나왔으며 `monkeypatch.undo()`가 autouse 픽스처까지 해제함 | `--with "sqlalchemy[asyncio]" --with toon-format --with anthropic`을 지정하고, `unknown_field` 입력 및 `with monkeypatch.context() as m:` 블록으로 수정해 125 passed 확인 |
| `asyncpg`의 untyped NULL 파라미터 오류 (`45113756566`) | `3d7d6ed`의 `offer_matches`에서 SQL에 `(:gtin IS NOT NULL AND p.gtin = :gtin)`을 고정으로 넣었더니 `gtin=None`일 때 PostgreSQL/asyncpg가 파라미터 타입을 결정하지 못해 `ProgrammingError` 발생 | 실제 DB 통합 CI가 잡아낸 덕분에 `2c65ccd`에서 값이 존재하는 매칭 조건만 동적으로 SQL `WHERE`/`ORDER BY`에 조립하도록 고쳐 해결 (로컬 Fake 테스트만으로는 잡을 수 없었던 실제 DB 드라이버 버그) |
| **#48 `console.spec.js:29, 38` 진단 오류 정정 수용** | `#48`에서 웹팀 코드(`apps/web/pages/*`)만 대조해 `console.spec.js`의 23·29·38행 3곳 모두 문구 불일치라고 진단·패치안을 작성함 | 2026-11-25 Claude 교차 검토([정오표](GEMINI_COVERAGE.md#4-정정-기록-2026-11-25--claude-opus-55-교차-검토), [#55~#57 일지](journal/2026-11-25-maintest-ci-and-ai-log-review-claude-opus-5.5.md))에서 확인된 바와 같이, 당시에는 `apps/web/shared/backend.js` 덮어쓰기 계층이 로드되어 29행은 통과하고 33행에서 `/backend` 누락 404(#55)로 실패했다. 원 일지는 보존하고 이 정정을 명시한다 |
| **#48 헤놀로지 메모리·성능 수치의 성격 구분** | `#48` 및 대화 응답에서 헤놀로지(`i5-6600`, `16GB`, `5.4TB`) 메모리 점유(4.5~5.8GB)와 처리 속도(건당 ms, TPS)를 제시함 | 이는 실제 NAS 장비에서 컨테이너를 띄워 측정한 벤치마크가 아니라 모델 크기·스레드 수·인덱스 구조에 기반한 **이론적 산출 추정치**다. 이후 Claude `#07`(`793dc1d`, 32건 배치 임베딩)로 임베딩 워커의 CPU/트랜잭션 사용 형태도 개선되었다 |
| **`2c65ccd` 이후 후속 보완과의 경계** | Gemini의 `2c65ccd` 시점에는 ① `catalog-context` 호스트 보조 검색 `LIMIT 50`, ② `offer_matches` 유사 후보 가격순 정렬, ③ 확장 선도착 시 404 및 옵션 삭제 불가, ④ `maintenance.py`의 `listing_extensions.run_id` FK 미고려, ⑤ `allergens_declared`의 `shellfish`·`pine_nut` 코드 판정 누락이 남아 있었음 | 이들은 이후 Claude가 `part/소병선-backend-test`(`#02`, `#03`, `#13`, `#14`, `#59`)에서 발견·해결했으며 Gemini 성과로 합산하지 않는다 |

---

## 8. 재현·이어받기 및 게시 후 재검증

1. **과거 커밋 기준 재현**:
   - Gemini가 수행한 통합 검증을 그대로 재현할 때는 고정 커밋(`103070f` 또는 `2c65ccd`)과 해당 커밋의 [.github/workflows/embedding-pipeline.yml](https://github.com/daon217/swproject/blob/2c65ccd67b545bad8c14e4f229f14af898926b6b/.github/workflows/embedding-pipeline.yml)을 기준으로 삼는다.
   - Windows 로컬에서 실제 PostgreSQL 통합 테스트를 돌릴 때는 `psycopg` async의 Windows `ProactorEventLoop` 제약 때문에 [VERIFY.md](VERIFY.md) 및 [METHODS.md](METHODS.md) 4.1절의 **격리 Compose 프로젝트(`kkulpick-verify`, 포트 55433) + Linux 컨테이너(`python:3.12-slim`)** 절차를 사용한다. 사용자의 기존 개발 DB 볼륨(`kkulpick-db-dev_postgres_data`)은 절대 건드리지 않는다.
2. **민감정보 및 데이터 보호**:
   - 비밀번호·API 키·토큰 값·개인정보·실제 수집 원본 300건 본문은 문서에 적지 않으며 환경변수 이름(`WORKSPACE_TOKEN`, `ANALYSIS_WORKER_TOKEN`, `COLLECTOR_TOKEN`, `CATALOG_APP_PASSWORD`)만 기록한다.
3. **게시 후 재검증 절차 (`PROMPTS.md` 8번 7~8단계)**:
   - 문서를 `origin/devlog`에 push한 뒤에는 로컬 작업 폴더만 보지 않고, ① 원격 `origin/devlog` HEAD와 게시된 파일들의 GitHub 원격 blob/본문을 다시 읽어 로컬 원문과 바이트/줄 단위로 일치하는지 확인하고, ② 문서 내 모든 상대 링크와 고정 커밋 코드 경로/행(`git show <SHA>:<경로>`)의 실존 여부를 스크립트로 재검증하며, ③ 발췌한 명령과 CI Job 로그(`137464692324`, `137492787339`, `137492787444` 등)의 수치 일치 및 `main`/`maintest`/기존 타 AI 일지 보존 여부를 확인한 뒤 별도 게시 후 재검증 일지에 기록한다.
