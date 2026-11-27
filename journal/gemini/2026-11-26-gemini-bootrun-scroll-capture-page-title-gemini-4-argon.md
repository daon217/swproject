# [Gemini 4 Argon] 개발일지 · 2026-11-26 로컬 통합 부트런 점검·확장 스크롤 재캡처 및 페이지 상품명 연동 (#63 #80)

- 날짜: 2026-11-26 (기록일, Asia/Seoul)
- 상태: 해결 (#63 부분 해결 — 스크롤 멈춤 시 재캡처·`page_title` 보존 연동 완료 / #80 로컬 부트런 환경·추천 품질 개선)
- 브랜치 / 커밋: `maintest` / [`2a2e521`](https://github.com/daon217/swproject/commit/2a2e521) (기준 `origin/maintest` `a77b950`)
- 관련 파일: `apps/extension/src/content/index.tsx:55`, `apps/extension/src/background/index.ts:338`, `apps/extension/src/shared/api/http.ts:50`, `apps/extension/src/shared/messages.ts:27`, `services/api/kkulpick/analyses.py:26`, `services/api/kkulpick/analyses.py:134`, `services/api/kkulpick/analyses.py:173`, `services/api/kkulpick/analyses.py:319`, `services/dev_runtime/analysis_worker.py:83`
- 작성 AI: Gemini 4 Argon

## 문제점

`origin/maintest`(`a77b950`)를 내려받아 로컬 통합 환경(PostgreSQL `5433`, Backend API `8000`, Vision AI `8100`, Recommendation `8200`, Analysis/Embedding Worker, Homepage Crawler, Admin Web `3000`, Extension `5174`, Mobile `8081`)을 전체 부트런하고 실제 Chrome 브라우저에서 쿠팡 등 쇼핑몰 상품 상세페이지를 테스트한 결과 다음 문제들이 발생했다.

1. **#63 상세페이지 최초 1장 캡처 후 스크롤 시 성분표 미탐색 및 상품명 유실**:
   - 쇼핑몰 상품 상세페이지 진입 직후(0.8초 디바운스) 최상단 화면 1장만 캡처해 `POST /analyses`를 호출하고(`apps/extension/src/background/index.ts:147-202`), 이후 사용자가 원재료명/성분표가 있는 하단으로 스크롤해도 이미 `prev.status === 'done'` 상태라 재캡처가 일어나지 않았다.
   - 또한 프론트엔드의 콘텐츠 스크립트(`apps/extension/src/shared/pageProduct.ts:111-157`)가 JSON-LD·`og:title`·`<h1>`에서 정확한 상품명(`page_product.name`)을 추출하고도 `createAnalysis`(`apps/extension/src/shared/api/http.ts:50-59`)에서 서버로 전송하지 않아, Vision AI의 Phase 1 OCR 최대 면적 텍스트 추출에만 의존하고 있었다.
   - 그 결과 쇼핑몰 상단 화면에서 바운딩 박스 면적이 가장 큰 리뷰·배너 문구(예: `"***** 44,633 개상품평 한달간 9,000명이상 구매했어요"`)가 상품명으로 오인식되거나, 스크롤을 내린 뒤 재시도하면 상단 상품명이 화면에서 사라져 엉뚱한 텍스트로 추천이 요청되는 문제가 발생했다.
2. **#80 로컬 부트런 환경의 LLM 추천 0건(`empty`)·수식어 편향 및 Admin 일자별 크롤링 집계 500 오류**:
   - **LLM 빈 목록 반환**: OCR이 리뷰 문구를 상품명으로 추출해 추천 서비스(`LocalLLMRanker`, `RECO_RANKER=local`)에 넘기자, 시스템 프롬프트(`services/recommendation/compress.py:118`, `"요청과 맞지 않는 후보는 고르지 않는다. 없으면 빈 목록"`)에 따라 LLM이 `{"picks": []}`를 반환하여 사용자 화면에 추천 상품이 0건으로 표시되었다.
   - **수식어(`무가당` 등) 편향 및 카탈로그 품목 부족**: `[아르헨티나산 하이올레익] 피트넛 무첨가 무가당 땅콩버터 100% 스무스, 1개, 500g` 페이지 분석 시 로컬 카탈로그 DB에 땅콩버터/스프레드 품목이 없고 `'무가당'` 수식어가 핵심 품목명과 동일 가중치로 매칭되어 `'그릭요거트 무가당'`, `'검은콩 두유 무가당'` 등이 후보로 추천되었다.
   - **Windows 내장 PostgreSQL(`pgserver`) 타임존 누락**: `GET /v2/admin/overview`(`services/api/kkulpick/console.py:60`)가 `AT TIME ZONE 'Asia/Seoul'`을 실행할 때 Windows용 `pgserver` 배포본의 `share/postgresql/timezone` 폴더가 비어 있어 `InvalidParameterValue: time zone "Asia/Seoul" not recognized` 500 오류가 발생하고 Admin 웹(`#/crawling`)의 일자별 수집 현황이 갱신되지 않았다.

## 원인

- **클라이언트 ↔ 백엔드 분석 입력 단절**:
  - `apps/extension/src/shared/api/http.ts:50-59`에서 `req.page_product.name`과 `req.page_url`을 `FormData`에 담지 않고 캡처 이미지만 전송했다.
  - `services/api/kkulpick/analyses.py:23-30`(`AnalysisInput`)에 페이지에서 추출한 상품명 힌트를 받을 필드(`page_title`)가 없었고, `services/dev_runtime/analysis_worker.py:83`은 카탈로그 URL 매칭(`match['name']`)이 실패하면 무조건 Vision OCR 추출 제목만 사용했다.
- **단발성 캡처 구조**:
  - `apps/extension/src/content/index.tsx`에 스크롤 이벤트 기반 재캡처 트리거가 없었고, `apps/extension/src/background/index.ts:152`는 동일 URL에서 `status === 'done'`이면 `force=true` 없이는 재분석을 건너뛰었다.
  - `services/dev_runtime/analysis_worker.py:93-98`은 단일 캡처 이미지를 `/api/v1/vision/init`과 `/api/v1/vision/frame`(`is_last_frame=True`)에 동시에 보내 즉시 세션을 마감하므로, 첫 화면에 성분표가 없으면 `ingredient_status: "not_found"`로 종료되었다.

## 해결 방안 (검토한 선택지)

| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| A. 확장 콘텐츠 스크립트에서 성분 미검출(`ingredient_status === 'not_found'`) 시 스크롤 정지(900ms 디바운스, 최대 15회)마다 재캡처(`scrollCapture`)를 요청하고, DOM에서 읽은 `page_title`·`page_url`을 `POST /analyses` → `analyses.result_metadata` → `analysis_worker`로 전달해 스크롤 위치와 무관하게 상품명을 보존 | 백엔드 `/analyses`의 단일 이미지 큐 계약과 호환되면서도 성분표를 찾을 때까지(Early Exit) 스크롤 캡처가 동작하고, 하단 스크롤 시에도 정확한 상품명으로 추천 수행 | 스크롤 재캡처마다 새 분석 요청으로 갱신됨 | ✅ |
| B. 백엔드 `/analyses`를 다중 프레임 스트리밍 WebSocket/청크 업로드 세션으로 전면 재설계 | 단일 `analysis_id` 안에서 15프레임을 모두 처리 가능 | 백엔드 API·DB 스키마·확장·모바일 폴링 계약을 모두 바꿔야 해 기존 통합 테스트와 충돌 위험이 큼 | |

## 해결 (적용 내용)

1. **확장 프로그램 스크롤 성분표 재탐색(`scrollCapture`) 추가 (`2a2e521`)**:
   - `apps/extension/src/shared/messages.ts:26-28`: `Message` 유니온 타입에 `{ type: 'scrollCapture' }` 추가.
   - `apps/extension/src/content/index.tsx:55-84`: 현재 탭 분석이 완료(`state.status === 'done'`)되었으나 아직 성분표를 찾지 못한 상태(`state.analysis.ingredient_status === 'not_found'`)일 때, 사용자가 250px 이상 스크롤한 뒤 900ms 동안 멈추면 `sendMessage({ type: 'scrollCapture' })`를 호출하도록 구현. 성분이 검출되면(`partial`) 즉시 추가 캡처를 중단(Early Exit)하며 페이지당 최대 15회(Hard Timeout)로 제한.
   - `apps/extension/src/background/index.ts:338-347`: `scrollCapture` 메시지 수신 시 현재 탭이 `done`이고 `ingredient_status === 'not_found'`이면 `analyze(tab.id, tab.url, true)`로 현재 뷰포트를 재캡처·재분석.
2. **페이지 추출 상품명(`page_title`) 및 `page_url` 전달·보존 (`2a2e521`)**:
   - `apps/extension/src/shared/api/http.ts:50-60`: `createAnalysis`의 `FormData`에 `req.page_url`과 `req.page_product?.name`(`page_title` 필드)을 포함하도록 수정(multipart 필드 수 증가에 맞춰 `services/api/kkulpick/analyses.py:134`의 `max_fields`를 `5` → `7`로 확장).
   - `services/api/kkulpick/analyses.py:26, 173-179, 319-342`: `AnalysisInput`에 `page_title: str | None = Field(default=None, max_length=500)`을 추가하고, 접수 시 초기 `result_metadata`에 `{"page_title": ...}`를 저장한 뒤 워커가 `/internal/v2/analyses/claim`을 호출할 때 `page_title`을 함께 반환하도록 연결.
   - `services/dev_runtime/analysis_worker.py:83`: `title = (match['name'] if match else None) or job.get('page_title')`로 우선 설정하여, 카탈로그에 아직 없는 URL이거나 사용자가 성분표를 보려고 화면 하단으로 스크롤한 상태에서도 정확한 상품명이 Vision AI 및 추천 서비스로 전달되게 수정.
3. **로컬 런타임(Git 추적 외 로컬 환경) 보완**:
   - **Windows `pgserver` 타임존 보완**: Python `tzdata` 패키지의 `zoneinfo` 데이터를 `pgserver`의 `share/postgresql/timezone` 경로에 복사하여 `SELECT now() AT TIME ZONE 'Asia/Seoul'` 및 `GET /v2/admin/overview`가 코드 수정 없이 `200 OK`로 동작함을 확인.
   - **수식어 필터링·품목 명사 가중치 및 LLM 랭커 보완**:ローカル 부트런 런처에서 중량/수량(`500g`, `1개`, `100%`) 및 일반 수식어(`무가당`, `무첨가`, `유기농`, `스무스` 등)를 검색 토큰에서 분리하고 핵심 품목 명사(`땅콩버터`, `피넛버터` 등) 일치에 높은 가중치를 부여하도록 보정했으며, 로컬 카탈로그 DB에 땅콩버터·잼/스프레드 및 주요 인기 식품 데이터를 추가 시드하고 pgvector 임베딩 색인을 갱신했다.

## 왜 그렇게 해결했는지

- Vision AI 워커는 상단 화면에서 상품명을 읽고 하단 스크롤 화면에서 원재료명/성분표를 읽도록 설계되어 있으나, 단일 캡처만 보내고 DOM 상품명을 버리면① 첫 화면에서는 성분표가 없어 알레르기 판정이 누락되고 ② 하단 화면에서는 상품명이 안 보여 추천 검색어가 깨지는 모순이 생긴다.
- 따라서 페이지 DOM에서 읽은 `page_title`을 서버 분석 작업에 전달해 상품명을 고정하고, 성분표가 아직 인식되지 않은 경우에만 스크롤 정지 시 뷰포트를 재캡처하도록 하면 불필요한 캡처 요청을 줄이면서도 성분표 인식과 정확한 상품 추천을 동시에 달성할 수 있다.
- API 키(`SUNMOON_API_KEY`, `LOCAL_LLM_API_KEY`, `ANTHROPIC_API_KEY`)와 로컬 런타임 패치는 보안 규칙에 따라 Git 추적 대상에서 제외하고 환경변수로만 주입했다.

## 검증

- **확장 프로그램 TypeScript 타입 검사 및 프로덕션 빌드**:
  - 명령: `cd apps/extension && npm run build` (`tsc --noEmit && vite build && vite build --config vite.content.config.ts`)
  - 결과: 오류 0건, `dist/sidepanel.html`, `dist/background.js`, `dist/content.js` 정상 빌드 완료.
- **실제 LLM 랭커(`RECO_RANKER=local`) 및 추천 서비스 엔드투엔드 호출 검증**:
  - `POST http://127.0.0.1:8200/internal/process`에 쿠팡 상품명 `"[아르헨티나산 하이올레익]피트넛 무첨가 무가당 땅콩버터 100% 스무스, 1개, 500g"`(`selected_domain="food"`) 요청 시:
    - `100% 피넛버터 스무스 무가당 땅콩버터 500g` (`"요청하신 무가당 스무스 타입이며 가격이 저렴합니다."`)
    - `100% 땅콩버터 크런치 무첨가 무가당 500g` (`"무첨가 무가당 제품이나 크런치 제형입니다."`)
    - `유기농 무가당 땅콩버터 스무스 350g` (`"유기농 땅콩을 사용한 무가당 스무스 제품입니다."`)
    - `스키피 수퍼청크 땅콩버터 462g` (`"가장 저렴한 땅콩버터이나 식물성유지가 포함됩니다."`)
    등 실제 동일 카테고리 상품과 한국어 추천 사유가 정상 반환됨을 확인.
- **관리자 웹 수집 집계 검증**:
  - `GET http://127.0.0.1:8000/v2/admin/overview` → `200 OK` 및 `homepage_crawler --backend --watch --max-pages 40` 실행으로 수집 상품 수(441건 → 475건+α) 실시간 반영 확인.

## 남은 과제 / 주의

- 현재 `scrollCapture`는 스크롤 정지 시마다 새 분석 요청(`page_revision` 증가)으로 결과를 갱신하므로, 상단 스크롤에서 이미 성분을 찾은 뒤(`ingredient_status === 'partial'`)에는 재캡처를 보내지 않지만, 성분을 찾기 전 여러 번 스크롤하면 분석 이력이 여러 건 생성될 수 있다.
- 로컬 `RECO_EMBEDDER=hash` 환경에서는 글자 n-gram 해시만으로는 한국어 복합명사 의미 유사도가 낮으므로, 운영 및 통합 컨테이너에서는 `RECO_EMBEDDER=st`(`paraphrase-multilingual-MiniLM-L12-v2`)를 기본으로 사용하거나 카탈로그 상품명/카테고리 키워드 후보 결합을 추천 파이프라인 본 코드(`services/recommendation/pipeline.py`)에 정식 옵션으로 편입하는 것을 검토할 필요가 있다.
