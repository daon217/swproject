# [Gemini 4 Argon] 개발일지 · 2026-11-24 11번가 확장 어댑터·분석 워커 병렬화 및 단위 CI psycopg 가드 (#51 #52)

- 날짜: 2026-11-24 (기록일, Asia/Seoul)
- 실제 작업 시기: 2026-11-23 11:48~12:21
- 상태: 해결 (어댑터 모듈·병렬 분석 워커·단위 CI 호환 완료; 분석 워커 예외 세분화는 이후 Claude #05에서 추가 보완)
- 브랜치 / 커밋: `maintest` / [`4b1f5fc`](https://github.com/daon217/swproject/commit/4b1f5fc9b0ef80124b87676e829a2e1f6c4063c6), [`89948df`](https://github.com/daon217/swproject/commit/89948dfcd6131d88af7b62d74026e40562e7a23c), [`3fd6f83`](https://github.com/daon217/swproject/commit/3fd6f83b20d5f3114a07e183705805e55b83012b), [`6180147`](https://github.com/daon217/swproject/commit/61801476706dd56ac5974bb5fc268b4de7186bc4), [`103070f`](https://github.com/daon217/swproject/commit/103070fa86511707b24966baa35332463b7221c5)
- 관련 파일: `services/collector/elevenst_offline/backend_adapter.py:1`, `services/collector/elevenst_offline/tests/test_pipeline.py:210`, `services/collector/domeggook_live/domeggook_backend.py:42`, `services/dev_runtime/analysis_worker.py:62`, `services/dev_runtime/test_analysis_worker.py:159`, `services/recommendation/embedding_config.py:9`, `services/recommendation/http_service.py:5`, `services/recommendation/embedding_worker.py:6`, `tools/check_adapter.py:1`
- 작성 AI: Gemini 4 Argon

## 문제점
1. **#51 11번가 오프라인 수집기(`elevenst_offline`)의 백엔드 적재 어댑터 부재 및 전송 경로 제한**:
   - `services/collector/elevenst_offline`은 파서(`parse_listing`)와 정규화·체크포인트 파이프라인은 갖추고 있었으나, 파싱된 레코드를 백엔드 `Observation v2` 및 `ListingExtension v1` 형식으로 변환해 전송하는 어댑터가 없었다.
   - 또한 도매꾹 전송 계층(`services/collector/domeggook_live/domeggook_backend.py`의 `HTTPBackendTransport`)의 경로 정규식이 `/internal/v2/crawl-runs/{run_id}/observations`만 허용하고 `/extensions`는 차단하고 있었다.
2. **#52 분석 워커(`analysis_worker.py`)의 단일 스레드 순차 블로킹 및 단위 CI(`Team build`) `psycopg` 미설치 실패**:
   - `services/dev_runtime/analysis_worker.py`가 단일 스레드 `while True` 루프에서 작업 1건을 claim한 뒤 Vision OCR(`8100`)이 완료될 때까지 최대 90초 동안 `time.sleep(0.5)`로 동기 대기했다. 앞선 사용자의 OCR이 도는 동안 뒤 사용자의 분석 요청(특히 OCR이 필요 없는 카탈로그 URL 매칭 요청)까지 모두 `queued` 상태로 멈추는 Head-of-Line Blocking이 발생했다.
   - 또한 `Team build`(`build.yml`) 워크플로는 프로젝트별 단위 테스트를 `psycopg` 없이 실행하는데, `maintest`에서 추가된 `embedding_config.py`, `http_service.py`, `embedding_worker.py`, `test_embedding_pipeline.py`가 최상단에서 `import psycopg`를 수행하고 `tools/check_adapter.py`가 실제 DB 연결을 시도해 `recommendation` 프로젝트 빌드가 실패했다.

## 원인
- `analysis_worker.py`의 `once()`가 작업 선점(`claim`)과 실행(Vision 폴링 + 추천 호출 + 완료 보고)을 한 함수 안에서 직렬로 묶어 두었고 동시 실행 풀이 없었다.
- `elevenst_offline/backend_adapter.py`를 처음 작성할 때(`4b1f5fc`) `domeggook_backend.py`를 import했으나, `domeggook_backend.py`가 표준 라이브러리가 아닌 `requests`를 최상단에서 import하고 있어 `requests`가 설치되지 않은 `dev_runtime`/`recommendation` 테스트 환경에서 `ModuleNotFoundError: No module named 'requests'`가 발생했다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| A. 분석 워커는 `ThreadPoolExecutor`(`ANALYSIS_WORKER_CONCURRENCY`, 기본 4)로 병렬화하고, 11번가 어댑터는 외부 패키지(`requests`) 의존성 없이 표준 라이브러리만으로 독립 구현하며, 추천 모듈은 `try: import psycopg` 선택적 가드 적용 | 기존 동기 `httpx.Client` 및 테스트 구조와 100% 호환되면서 OCR 대기 중 다른 작업 즉시 추월 처리 가능, 단위 CI와 통합 CI 양쪽 모두 통과 | 프로세스 내부 스레드 풀 방식이므로 단일 컨테이너 규모에서 동작 | ✅ |
| B. 분석 워커 전체를 `asyncio` + `httpx.AsyncClient`로 전면 재작성 | 이벤트 루프 기반 동시성 | 기존 `httpx.MockTransport` 기반 동기 단위 테스트 전체와 호환성이 깨짐 | |

## 해결 (적용 내용)
1. **11번가 백엔드 어댑터 구현 및 도매꾹 전송 경로 확장 (`4b1f5fc`, `89948df`)**:
   - `services/collector/elevenst_offline/backend_adapter.py`를 신설하여 `prepare_elevenst_observation()`, `prepare_elevenst_extension()`, `ElevenstBackendAdapter`를 구현했다.
   - `backend_enabled`, `backend_owner_approved`, `price_semantics_confirmed` 3중 게이트와 `allowed_product_hosts`, `currencies`, HTTPS URL, 가격 정수 문자열 검증을 통과한 레코드만 백엔드 `/observations`와 `/extensions`로 전달한다.
   - `89948df`에서 `domeggook_backend` import를 제거하고 URL/호스트/가격 검증을 표준 라이브러리(`urllib.parse`, `re`)로 자체 내장하여 `requests` 미설치 환경에서도 동작하게 했다.
   - `services/collector/domeggook_live/domeggook_backend.py`의 `_OBSERVATION_PATH_RE`를 `/(?:observations|extensions)$`까지 허용하도록 확장했다.
2. **분석 워커 병렬 처리 및 카탈로그 DB 원재료 폴백 (`services/dev_runtime/analysis_worker.py`, `4b1f5fc`)**:
   - `Worker`를 `claim_job()`과 `process_job(job)`으로 분리하고 `drain_concurrent(max_workers)` 및 `ThreadPoolExecutor(max_workers=worker.max_concurrency)` 기반 `main()` 루프를 구현했다(`ANALYSIS_WORKER_CONCURRENCY` 기본값 `4`).
   - 이미지 OCR에서 추출된 원재료가 없을 때 `/internal/catalog-context`가 반환한 카탈로그 DB의 `ingredients`를 폴백으로 사용해 추천 엔진(`/internal/process`)에 전달하도록 연결했다.
3. **단위 CI(`Team build`) 호환을 위한 `psycopg` 선택적 임포트 가드 (`3fd6f83`, `6180147`, `103070f`)**:
   - `services/recommendation/embedding_config.py`, `http_service.py`, `embedding_worker.py`, `tests/test_embedding_pipeline.py`에서 `psycopg` import를 `try ... except ImportError`로 감싸고, `psycopg`가 없는 단위 테스트 환경에서는 `PG_ERRORS = ()`로 동작하게 했다.
   - `tools/check_adapter.py`에서 `CATALOG_PASSWORD`가 설정되지 않은 단위 CI 실행 시 `config.connect`, `config.validate`, `config.embedder`를 인메모리 해시 인덱스로 스텁하여 DB 없이도 HTTP 어댑터 계약 검사가 수행되도록 보완했다.
   - 참고: GitHub CLI OAuth 토큰에 `workflow` 스코프가 없어 `.github/workflows/*.yml` 파일은 수정하지 않고 기존 워크플로가 실행하는 테스트 파일(`services/dev_runtime/test_analysis_worker.py`)에 11번가 어댑터와 병렬 워커 테스트를 함께 배치했다.

## 왜 그렇게 해결했는지
- 헤놀로지(`i5-6600`, 4C/4T)에서 Vision OCR은 이미지당 1.5~4.5초의 CPU 추론 시간이 걸리는데, 분석 워커 자체는 HTTP 응답을 기다리는 I/O 대기 상태다. 스레드 풀(기본 4)로 분리하면 OCR을 기다리는 동안 이미지 없는 일반 분석 요청이 약 40~90ms 만에 먼저 완료되어 체감 대기 시간을 크게 줄일 수 있다.
- OAuth 토큰 권한 제약을 우회하려 하지 않고 기존 CI 워크플로 구조를 그대로 유지하면서 선택적 import 가드를 적용해 단위 CI(`Team build`)와 DB 통합 CI(`Persistent embedding pipeline`)를 모두 만족시켰다.

## 검증
- `test_worker_concurrent_pool_processes_multiple_jobs_without_blocking`: `job-1`이 Vision OCR 상태 폴링(3회)을 대기하는 동안 뒤이어 들어온 `job-2`(식품, DB 원재료 폴백)와 `job-3`(일반 상품)이 블로킹 없이 먼저 완료(`completed_order[-1] == 'job-1'`)되는 것을 검증했다.
- `test_elevenst_offline_backend_adapter_observation_and_extension`: 11번가 픽스처 파싱 → Observation v2 및 ListingExtension(브랜드, 모델번호, GTIN) 변환 → 전송 어댑터 호출까지 통과.
- [GitHub Actions `Team build` (Run #45105156508)](https://github.com/daon217/swproject/actions/runs/45105156508): `CI configuration`, `api`, `recommendation`, `vision`, `collector`, `dev-runtime`, `web`, `admin`, `extension`, `mobile` **10개 Job 전원 통과**.
- [GitHub Actions `Persistent embedding pipeline` (Run #45105156543)](https://github.com/daon217/swproject/actions/runs/45105156543): `postgres` 및 `semantic-model` **전원 통과**.

## 남은 과제 / 주의
- `ANALYSIS_WORKER_CONCURRENCY=4`일 때 캡처 이미지 분석만 대량으로 동시에 몰리면 단일 OCR 워커 대기열 뒤쪽 작업이 90초 폴링 기한을 넘길 수 있다([OPEN_ISSUES.md](../OPEN_ISSUES.md) #18).
- 당시 `analysis_worker.py`의 예외 처리는 실패를 일괄 `retryable=False`로 보고했으나, 이후 Claude 세션 1(#05, `2e2a806`)에서 일시 장애(`retryable=True`)와 코드 오류(`RECOMMENDATION_FAILED`)로 세분화되었다.
