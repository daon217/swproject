# Gemini 개발 기록 대응표 및 누락 재검증

- 기준: 2026-11-24 전수 재검증. Antigravity(Gemini 4 Argon) 세션에서 수행한 **모든 사용자 요청(11-19 초기 구조 파악 ~ 11-23 전수 조사·하드웨어/성능 분석·`maintest` 4대 한계 해결·Claude 리뷰 5건 수정 및 4중 검증)** 과 원격 커밋(`4b1f5fc` ~ `2c65ccd`)을 빠짐없이 대조했다.
- 작성 AI: Gemini 4 Argon
- 기존 [GPT_COVERAGE.md](GPT_COVERAGE.md)에서 *"원 작업 AI를 확인하지 못해 제외한 구간(`4b1f5fc`~`2c65ccd`)"* 으로 남겨 두었던 7개 커밋이 모두 본 Gemini 작업 기록으로 확인·복원되었다.
- 어떻게 점검하고 어떤 도구·환경·입력·기대값·명령으로 테스트했는지에 대한 상세 방법과 CI Job 로그 근거는 [GEMINI_METHODS.md](GEMINI_METHODS.md) 및 [방법 보완 일지](journal/2026-11-25-gemini-test-methods-gemini-4-argon.md)를 함께 확인한다.

---

## 1. 대화 요청별 작업·커밋·일지 전수 대응표

| 순서 | 작업 시각 (KST) | 사용자 요청 및 확인한 작업 | 반영 브랜치 / 커밋 | 검증 / CI 실행 근거 | 개발일지 |
| --- | --- | --- | --- | --- | --- |
| 1 | 11-19 00:49~01:06 | GitHub 연결 확인, 담당자(소병선 · 백엔드/DB/공통환경) 기초 정보 인수, 3개 독립 PostgreSQL DB·FastAPI·운영 도구(`workspace.py`, `operations.py`, `catalog.py`, `performance.py`) 전체 구조 파악 | 코드 수정 없음 (`main` 읽기 전용) | 로컬 파일·계약 문서·마이그레이션 대조 | [#48 진단 일지](journal/2026-11-24-gemini-survey-hardware-diagnostics-gemini-4-argon.md) |
| 2 | 11-23 10:06~10:59 | GitHub 원격 브랜치 20개·PR 14개·Actions 9종 진행 상황 전수 파악 (`origin/maintest` `2d444b0`, `origin/main` `32f08ba`, 파트별 미병합 브랜치 비교) | 코드 수정 없음 (`git fetch --all --prune`) | GitHub Actions 런 이력 및 브랜치별 커밋 로그 대조 | [#48 진단 일지](journal/2026-11-24-gemini-survey-hardware-diagnostics-gemini-4-argon.md) |
| 3 | 11-23 11:06~11:25 | ① `origin/main` CI 실패 2건(`console.spec.js:23,29,38`, `guest-floating.spec.js:28`) 행 단위 원인 규명 및 팀 공유용 Discord 마크다운/diff 작성<br>② 본 서버 **헤놀로지(`i5-6600`, `16GB`, `5.4TB`)** AVX2 호환성·컨테이너별 메모리(4.5~5.8GB) 분석<br>③ 저장소 전체 **5개 영역 16개 문제점** 종합 출력 | 코드 수정 없음 (진단·패치안 도출) | Run [`45035799528`](https://github.com/daon217/swproject/actions/runs/45035799528), Run [`44495089917`](https://github.com/daon217/swproject/actions/runs/44495089917), 커밋 `c7d8cdf`·`e7f7007` diff 대조 | [#48 진단 일지](journal/2026-11-24-gemini-survey-hardware-diagnostics-gemini-4-argon.md) |
| 4 | 11-23 11:31~12:21 | **「4. 수집기 ↔ 백엔드 데이터 계약 및 분석/추천 파이프라인 한계」 4대 과제 해결 및 `maintest` 반영**:<br>• **#49** 카탈로그 DB 식품 원재료/알레르기 저장(`0009_catalog_details`) 및 추천 `PgCatalog` 연결<br>• **#50** 상품 상세·식별자(GTIN/모델번호/MPN/옵션/이미지) 확장 수집 API(`ListingExtension v1`) 및 `/v2/offers/{id}/matches` 매칭 API<br>• **#51** 11번가(`elevenst_offline`) 백엔드 어댑터 및 도매꾹 `/extensions` 경로 허용<br>• **#52** 분석 워커(`analysis_worker.py`) `ThreadPoolExecutor` 병렬 처리·DB 원재료 폴백 및 단위 CI `psycopg` 선택적 임포트 가드 | `maintest`<br>[`4b1f5fc`](https://github.com/daon217/swproject/commit/4b1f5fc9b0ef80124b87676e829a2e1f6c4063c6)<br>[`89948df`](https://github.com/daon217/swproject/commit/89948dfcd6131d88af7b62d74026e40562e7a23c)<br>[`3fd6f83`](https://github.com/daon217/swproject/commit/3fd6f83b20d5f3114a07e183705805e55b83012b)<br>[`6180147`](https://github.com/daon217/swproject/commit/61801476706dd56ac5974bb5fc268b4de7186bc4)<br>[`103070f`](https://github.com/daon217/swproject/commit/103070fa86511707b24966baa35332463b7221c5) | • `Persistent embedding pipeline` Run [`45104086541`](https://github.com/daon217/swproject/actions/runs/45104086541) (`success`)<br>• `Team build` Run [`45105156508`](https://github.com/daon217/swproject/actions/runs/45105156508) (10/10 jobs `success`)<br>• `Persistent embedding pipeline` Run [`45105156543`](https://github.com/daon217/swproject/actions/runs/45105156543) (`success`) | [#49·#50 확장·식품 일지](journal/2026-11-24-gemini-catalog-extensions-food-evidence-gemini-4-argon.md)<br>[#51·#52 어댑터·워커 일지](journal/2026-11-24-gemini-elevenst-adapter-concurrent-worker-ci-gemini-4-argon.md) |
| 5 | 11-23 13:14~13:17 | ① 반영된 4대 개선 사항의 헤놀로지(`i5-6600`, `16GB`, `5.4TB`) 기준 처리 속도(Latency)·처리량(TPS)·HDD I/O 절감(`payload_hash` 단락 평가) 분석<br>② DB 스키마(`check_item_subtype`)·수집기·확장 API(`DOMAIN_CONFLICT`)·추천 엔진(`PgCatalog`)의 상품(`product`) vs 식품(`food`) 도메인 분리 동작 검증 | 코드 수정 없음 (성능·설계 분석) | `extensions.py`, `postgres.py`, `catalog.sql`, `catalog_details.sql` 코드 및 인덱스 구조 대조 | [#48 진단 일지](journal/2026-11-24-gemini-survey-hardware-diagnostics-gemini-4-argon.md) |
| 6 | 11-23 13:36~13:51 | **Claude 코드 리뷰 5건 수정 및 4중 검증**:<br>• **#53** `/internal/catalog-context` URL 정규화(대소문자 호스트, `http`/`https`, 기본 포트, `#fragment` 무시) 복원 및 `/internal/process` 입력 오류(`422`) vs 의존성 장애(`503`) 예외 분리<br>• **#54** `MatchingProfile.image_urls` 중복 제거 버그 수정, `/v2/offers/{id}/matches` 최저가 200개 절단 방지 및 `asyncpg` 동적 조건절 조립, `product`↔`food` 전환 시 잔류 `embedding_jobs` 자동 삭제(트리거+워커 이중 방어) | `maintest`<br>[`3d7d6ed`](https://github.com/daon217/swproject/commit/3d7d6ed6151067064af6a70fcb3bc459560bf1d1)<br>[`2c65ccd`](https://github.com/daon217/swproject/commit/2c65ccd67b545bad8c14e4f229f14af898926b6b) | • 로컬 `pytest`: **125 passed, 13 skipped**<br>• 독립 시나리오 스크립트 5종 통과<br>• `Team build` Run [`45114083442`](https://github.com/daon217/swproject/actions/runs/45114083442) (10/10 jobs `success`)<br>• `Persistent embedding pipeline` Run [`45114082875`](https://github.com/daon217/swproject/actions/runs/45114082875) (`success`) | [#53·#54 리뷰 수정 일지](journal/2026-11-24-gemini-claude-review-fixes-verification-gemini-4-argon.md) |
| 7 | 11-27 05:00~07:18 | **추천 후보 매칭·수식어+품목 우선순위·실시간 AI 검색 폴백·알레르기 오탐 제거 및 크롤러 연속 탐색 (`#80`, `#92`, `#96`, `#97`, `#98`)**:<br>• **#96** 홈페이지 크롤러 회차별 미방문 URL 및 하위 상품 링크 연속 탐색(`77개 → 109개+`)<br>• **#80·#92** 한·영 브랜드/품목 별칭, 복합어 분리, `선호 수식어(무가당·제로·볶은 등) + 핵심 품목` 1순위/2순위 후보 정렬 정식 반영<br>• **#97** 성분표 미인식 시 무조건 알레르기 주의보 제거, `'본 제품은 ... 같은 제조시설'` 교차오염 문구 제외, 상품명(`query`) 기반 즉시 알레르기 감지<br>• **#98** DB 추천 0건 시 홈앤쇼핑·29CM·중고나라 실시간 검색·적재 폴백(`live_fallback.py`, 기본 `claude-opus-5-5` + 폴백 `claude-sonnet-4-6`), 확장 설정 탭 온오프 스위치(`ai_fallback`), 추천 상품 URL 클릭 시 자동 재분석 방지(`openRecommendedUrl`) | `maintest` (`part/소병선-backend-test` 동기화)<br>[`3be1719`](https://github.com/daon217/swproject/commit/3be171910272c1d1314b2801cca87c83aa2841fe) | • 로컬 Docker 통합 스택(`kkulpick-db-dev-*`) 실측 검증<br>• 확장 프로덕션 빌드(`tsc --noEmit && vite build`) 통과<br>• Claude 5개 모델(`Opus 5.5`, `Sonnet 5.5`, `Sonnet 4.6`, `Haiku 5.5`, `Haiku 4.5`) 속도·토큰 실측 비교 | [#80·#92·#96~#98 일지](journal/2026-11-27-gemini-live-fallback-allergy-crawler-gemini-4-argon.md) |

---

## 2. `maintest` 커밋별(`4b1f5fc` ~ `2c65ccd`) 전수 매핑 확인

| 커밋 해시 | 커밋 메시지 | 반영 일지 | 누락 여부 |
| --- | --- | --- | --- |
| `4b1f5fc` | `feat(backend): add food evidence, product matching extensions, 11st adapter and concurrent analysis worker` | `#49`, `#50`, `#51`, `#52` | ✅ 기록 완료 |
| `89948df` | `fix(tests): parameterize SQL percent literal and remove requests dependency from 11st adapter` | `#49`, `#51` | ✅ 기록 완료 |
| `3fd6f83` | `fix(recommendation): guard optional psycopg import for unit-only project CI` | `#52` | ✅ 기록 완료 |
| `6180147` | `fix(recommendation): allow pytest collection of embedding integration test without psycopg` | `#52` | ✅ 기록 완료 |
| `103070f` | `fix(recommendation): guard psycopg import in embedding_worker for unit CI` | `#52` | ✅ 기록 완료 |
| `3d7d6ed` | `fix(catalog,recommendation): normalize catalog-context URLs, dedupe image_urls, fix 422/503, and filter matches/embedding jobs` | `#53`, `#54` | ✅ 기록 완료 |
| `2c65ccd` | `fix(api): build non-null match predicates dynamically to avoid asyncpg untyped null parameter error` | `#54` | ✅ 기록 완료 |

---

## 3. 귀속 및 기존 일지와의 정합성 유의사항

1. **AI 모델 간 경계 보존**:
   - `2d444b0` 이전의 초기 환경·비즈니스 API·영속 임베딩 파이프라인 구축은 GPT 회고(`#34`~`#47`)로,
   - `4b1f5fc` ~ `2c65ccd`(`maintest` 7개 커밋) 및 11-19/11-23 아키텍처·하드웨어·성능 진단과 Claude 리뷰 5건 반영은 **Gemini 4 Argon(`#48`~`#54`)** 로,
   - `2c65ccd` 이후 `part/소병선-backend-test`에서 수행된 `2e2a806` ~ `4f26501` 및 시뮬레이션·수집기 주기 적재 검토는 **Claude Opus 5.5(`#01`~`#33`)** 로 각각 명확히 구분된다.
2. **현재 미해결 이슈(`OPEN_ISSUES.md`) 상태 보존**:
   - Gemini가 `#49`~`#51`에서 백엔드 확장 수신 API(`/extensions`), DB 식품 원재료 컬럼(`0009_catalog_details`), `PgCatalog` 원재료 로드, 11번가 오프라인 어댑터 모듈을 구현했으나, 실제 운영 수집기 데몬이 주기적으로 확장 데이터를 전송하도록 양쪽 파트를 최종 연결하는 작업은 [OPEN_ISSUES.md](OPEN_ISSUES.md)의 **#27·#32**에 남아 있으므로 임의로 종료 처리하지 않는다.

---

## 4. 정정 기록 (2026-11-25 · Claude Opus 5.5 교차 검토)

원 일지는 기록으로 보존하고 정정은 여기와 [교차 검토 일지](journal/2026-11-25-maintest-ci-and-ai-log-review-claude-opus-5.5.md)에 남긴다.

| 대상 | 원래 기록 | 정정 |
| --- | --- | --- |
| #48 CI 원인 | `console.spec.js:29`, `:38`도 문구 불일치 → 테스트를 웹팀 문구로 바꾸는 패치안 | 당시 실제로 쓰이던 문구는 `apps/web/shared/backend.js`(덮어쓰기 계층)에 있어 29행은 통과했다. 패치안을 그대로 적용하면 실패했다. 이후 backend.js를 제거하면서(#56, `e37338e`) 테스트를 웹팀 문구로 맞췄다(#57). |
| #48 | "실제 코드 반영은 Claude #01(`2e2a806`)에서도 동일 원인으로 확인·적용" | #01은 23행과 guest-floating만 고쳤다. 29·38행은 당시 고칠 필요가 없었다. |
| #48 | 헤놀로지 메모리 4.5~5.8GB 등 | 측정값이 아닌 추정치다. 이후 임베딩 배치 처리(#07)로 CPU 사용 형태가 바뀌었다. |
| #48 CI 원인 | `Team connected runtime` 실패를 문구 불일치로만 설명 | 문구를 고친 뒤 33행에서 관리자 웹의 `/backend` 누락 404(#55)가 추가로 드러났다(`e37338e`에서 해결). |
