# [Gemini 4 Argon] 개발일지 · 2026-11-27 추천 후보 매칭·수식어+품목 우선순위·실시간 AI 검색 폴백·알레르기 오탐 제거 및 크롤러 연속 탐색 (#80 #92 #96 #97 #98)

- 날짜: 2026-11-27 (기록일, Asia/Seoul)
- 상태: 해결 (#80 수식어 분리·품목 우선순위 본 코드 정식 반영, #92 한·영 브랜드/품목 별칭 및 복합어 분리 매칭, #96 크롤러 회차별 미방문 URL 연속 탐색, #97 알레르기 무조건 경고·제조시설 오탐 제거 및 상품명 즉시 감지, #98 DB 추천 0건 시 실시간 쇼핑몰 검색·적재 폴백 + UI 온오프 스위치 + 추천 링크 이동 시 재분석 방지)
- 브랜치 / 커밋: `maintest` (`part/소병선-backend-test` 동기화) / [`3be1719`](https://github.com/daon217/swproject/commit/3be171910272c1d1314b2801cca87c83aa2841fe) (기준 `0bb173b` / `2a2e521`)
- 관련 파일: `services/recommendation/pipeline.py:17`, `services/recommendation/adapters/postgres.py:127`, `services/recommendation/http_service.py:170`, `services/recommendation/live_fallback.py:1`, `services/recommendation/rankers.py:16`, `services/collector/homepage_crawler/crawler.py:127`, `services/dev_runtime/analysis_worker.py:25`, `services/api/kkulpick/analyses.py:23`, `apps/extension/src/sidepanel/screens/tabs.tsx:25`, `apps/extension/src/background/index.ts:140`, `apps/extension/src/shared/ui/ResultView.tsx:141`
- 작성 AI: Gemini 4 Argon

---

## 문제점

로컬 Docker 통합 스택(`kkulpick-db-dev-*`, `--scope integrated`, `RECO_RANKER=claude`)을 구동해 Chrome 확장 프로그램으로 실제 쿠팡 상품 페이지(노트북, 양평 해장국, 무가당 땅콩버터, 제로 카카오 초콜릿, 볶은 메밀 등)와 관리자 웹을 테스트한 결과 다음 5가지 문제가 확인되었다.

1. **#96 홈페이지 크롤러(`homepage-crawler`) 반복 실행 시 관리자 페이지 등록 상품 수(`app.offers`) 미증가**:
   - `kkulpick-db-dev-homepage-crawler-1`이 10분 주기로 `"백엔드에 102개 전송"`을 출력하는데도 관리자 페이지(`GET /v2/admin/overview`)의 전체 등록 상품 수(`app.offers`)가 77개에서 전혀 늘어나지 않았다.
2. **#80·#92 한·영 상품명 불일치(`에이수스 비보북` ↔ `ASUS ... 노트북`, `나이키` ↔ `Nike`) 및 수식어(`무가당`, `제로`) 단독 매칭 편향**:
   - 쿠팡 상품명 `"에이수스 2026 비보북 고 15 라이젠5 라이젠 40 시리즈"`는 `"노트북"`이라는 단어가 없고 한글 `"에이수스"`로 표기되어, 카탈로그 DB에 있는 `"ASUS TUF A14 경량 게이밍 노트북"`과의 MiniLM 코사인 유사도가 `0.1994`(90개 중 79위)에 그쳐 상위 30개 후보(`candidate_limit=30`)에서 탈락했다.
   - 또한 `"무가당 땅콩 버터"`나 `"제로 카카오 초콜릿"` 검색 시 앞쪽 수식어(`무가당`, `제로`)가 일반 품목 단어와 동일하게 `ILIKE '%무가당%'`으로 매칭되어 `"무가당 자일리톨 잼"`처럼 핵심 품목이 다른 상품이 추천 후보로 섞였다.
3. **#97 알레르기 설정 사용자의 식품 페이지 진입 시 무조건 `알레르기 주의` 경고가 뜨거나, 반대로 상품명에 알레르기 원료가 명시된 상단 화면에서 경고가 누락되는 문제**:
   - **무조건 경고**: 사용자가 알레르기(`milk`, `peanut` 등)를 설정해 두면, 식품 페이지 상단 화면에서 아직 성분표가 읽히지 않았을 때(`not body.ingredients and not body.allergens_declared`) 백엔드가 사용자의 모든 알레르기 항목에 `evidence: "unknown"` 경고를 내려보내고, 프론트엔드 `ResultView.tsx`가 이를 빨간 `꿀픽 · 알레르기 주의` 경고창으로 렌더링했다.
   - **교차오염 문구 오탐**: 하단 성분표를 스크롤해 읽었을 때는 한국 식품 공통 문구인 `"본 제품은 돼지고기, 우유, 땅콩 등을 사용한 제품과 같은 제조시설에서 제조하고 있습니다"`가 쉼표 단위로 쪼개져 실제 함유(`evidence: "contains"`)로 오탐되었다(예: 우유가 없는 `양평 해장국`에서 `우유 알레르기 주의` 발생).
   - **상단 화면 상품명 알레르기 미감지**: 반대로 `"넛츠그린 100% 무가당 땅콩버터 크런치"`처럼 상단 화면(`ingredients: []`)의 상품명(`query`) 자체에 `"땅콩"`이 명시된 경우에는 `body.query`를 검사하지 않아 `땅콩 알레르기 주의`가 뜨지 않았다.
4. **#98 카탈로그 DB에 관련 상품이 전혀 없을 때(`0건`)의 실시간 탐색 부재 및 추천 상품 URL 클릭 시 자동 재분석 문제**:
   - 카탈로그 DB에 아직 수집되지 않은 품목(예: `"기계식 무소음 블루투스 키보드"`, `"한방선생 볶은 메밀, 500g, 1개"`)을 열람하면 추천 결과가 `0건`으로만 끝났다.
   - 사이드 패널에서 추천된 상품 카드를 클릭해 새 탭으로 판매처 URL을 열면, 확장 백그라운드(`tabs.onUpdated`)가 그 탭을 다시 캡처해 새로운 추천 분석을 또 실행해 버렸다.

---

## 원인

- **#96 크롤러 원인 (`services/collector/homepage_crawler/crawler.py:181-183`)**:
  - `crawl_site()`가 매 회차 각 쇼핑몰 메인 화면과 첫 사이트맵에서 항상 동일한 순서로 `cands` 리스트를 만든 뒤 맨 앞 `cands[:max_pages]`(12개)만 방문하고 종료했다. 방문한 URL 기록이 없어 매 회차 동일한 77개 URL만 재전송(`ON CONFLICT DO UPDATE`)되었다.
- **#80·#92 추천 후보 매칭 원인 (`services/recommendation/pipeline.py:62-78`, `services/recommendation/adapters/postgres.py:127-137`, `services/recommendation/compress.py:86-105`)**:
  - `pipeline.py`에서 `name_matches` 호출이 `if min_score > 0 or score_margin > 0:` 블록 안쪽에 들여쓰기되어 있어, `min_score=0`일 때 `name_matches`가 아예 실행되지 않았다.
  - `name_matches`로 추가된 후보의 점수가 `cutoff`(`0.0` 또는 최하위 점수)로 부여되고 vector 검색 13~30위에 걸친 항목은 점수가 보정되지 않아, `compact_candidates(..., max_items=12)`가 점수 상위 12개만 자를 때 LLM에 전달되기 전에 탈락했다.
  - 한·영 브랜드/품목 별칭(`에이수스 ↔ asus`, `비보북 ↔ 노트북`, `나이키 ↔ nike`)과 붙여쓴 복합어 분리 로직이 없었고, 수식어(`무가당`, `제로`)와 핵심 품목 명사(`땅콩버터`, `초콜릿`)의 필수/우선순위 구분이 없었다.
- **#97 알레르기 경고 원인 (`services/recommendation/http_service.py:173-190`, `apps/extension/src/shared/ui/ResultView.tsx:141-144`)**:
  - `http_service.py:188`이 `not body.ingredients and not body.allergens_declared`일 때 모든 사용자 알레르기에 `evidence: 'unknown'` 경고를 생성했고, `ResultView.tsx`의 `visibleWarnings()`가 `evidence === 'unknown'`을 필터링하지 않고 `AllergyNoticeBox`에 그대로 넘겼다.
  - `http_service.py:173`의 `detect(list(body.ingredients))`는 `'본 제품은 ... 사용한 제품과 같은 제조시설에서 제조'` 문구 토큰을 걸러내지 않았고, `body.query`(상품명)는 검사 대상에 포함하지 않았다.
- **#98 추천 링크 재분석 원인 (`apps/extension/src/sidepanel/screens/tabs.tsx:15-20`, `apps/extension/src/background/index.ts:147`)**:
  - 추천 카드 클릭 시 일반 `openUrl`(`chrome.tabs.create`)을 호출해 백그라운드 서비스 워커가 추천 카드 클릭으로 열린 탭인지 구분하지 못했다.

---

## 해결 방안 (검토한 선택지)

| 과제 | 선택지 A (채택 ✅) | 선택지 B |
| --- | --- | --- |
| **DB 미등록 상품 추천 폴백** | DB 추천 결과가 **완전히 0건(`not result.picks`)이고 사용자가 UI 설정의 `추천 상품 없을 시 AI 추천`(`ai_fallback`)을 켰을 때만**, 핵심 품목 키워드(`1순위: 수식어+품목`, `2순위: 품목`)로 허용 도메인 쇼핑몰(홈앤쇼핑·29CM·중고나라)을 실시간 검색해 단일 트랜잭션으로 DB·벡터 인덱스에 적재한 뒤 폴백 전용 경량 모델(`claude-sonnet-4-6`)로 선별 | Claude 내장 `web_search` 툴을 LLM이 직접 호출해 웹 페이지 전체를 읽게 함 (1회당 6,000~15,000 토큰 및 검색 과금 발생으로 \$60 예산 소모가 커서 제외) |
| **수식어(`무가당`·`제로`) + 핵심 품목 우선순위** | `WHERE` 절에서는 반드시 **핵심 품목 키워드(`core_keywords`) 일치**를 요구해 수식어만 같은 무관 상품을 차단하고, `ORDER BY`에서 **`핵심 품목 점수 + 선호 수식어(modifiers) 일치 가중치`** 순으로 정렬해 `무가당/제로 + 원하는 상품`을 1순위, 일반 `원하는 상품`을 2순위로 추천 | `무가당`, `제로`를 일반 검색어와 동등한 `OR` 조건으로 검색 (무관한 `무가당 잼` 등이 섞이므로 제외) |
| **LLM 모델 이원화 및 호환** | 평상시 DB 추천은 기존 `DEFAULT_MODEL`(`claude-opus-5-5`)을 유지하고, DB 0건 실시간 폴백 시에만 `FALLBACK_MODEL`(`claude-sonnet-4-6`)로 전환. `output_config={"effort": "low"}` 미지원 모델(`Haiku 4.5` 등)은 자동 폴백 호출 | 모든 호출을 단일 모델로 고정 |

---

## 해결 (적용 내용 · `3be1719`)

1. **#96 홈페이지 크롤러 회차별 미방문 URL 연속 탐색 (`services/collector/homepage_crawler/crawler.py:127-234`)**:
   - 사이트별 방문 완료 집합(`_VISITED_URLS`)과 방문한 페이지 내부에서 새로 발견한 상품 링크 풀(`_DISCOVERED_URLS`)을 유지하고 `sitemap_urls` 탐색 한도를 `200` → `1000`으로 확대하여 매 회차 새로운 상품 URL을 수집하도록 개선.
2. **#80·#92 한·영 브랜드/품목 별칭·복합어 분리 및 `수식어 + 핵심 품목` 1순위/2순위 정렬 (`services/recommendation/pipeline.py:17-235`, `services/recommendation/adapters/postgres.py:127-150`, `services/dev_runtime/analysis_worker.py:25,133-141`)**:
   - `_PREF_MODIFIERS`(`무가당`, `저당`, `무설탕`, `제로`, `유기농`, `볶은`, `구운`, `무소음`, `초경량`, `게이밍` 등)를 일반 `name_keywords`에서 분리해 수식어 단독 매칭을 차단하고, `modifier_keywords(query)`로 별도 추출.
   - `expand_keywords(query)`를 추가해 주요 한·영 브랜드/품목 별칭(`에이수스/아수스 ↔ asus/비보북/젠북/tuf`, `나이키 ↔ nike`, `애플 ↔ apple/맥북`, `삼성 ↔ samsung/갤럭시북`, `엘지 ↔ lg/그램`, `레노버 ↔ lenovo`, `해장국/설렁탕 ↔ 갈비탕/찌개` 등)과 띄어쓰기 없는 복합어(`에이수스노트북`, `양평해장국` 등)를 확장.
   - `PgCatalog.name_matches(keywords, limit, modifiers)`가 핵심 키워드(`keywords`) 일치를 필수로 요구하면서 `핵심 키워드 일치 수 * 2 + 선호 수식어 일치 수 * 3` 순으로 정렬해 반환하고, `pipeline.py`에서 `min_score=0`일 때도 항상 `name_matches` 결과를 후보 최상단(`boost`)에 배치하도록 수정.
   - `analysis_worker.py`에서 쇼핑몰 URL 쿼리 파라미터(`q`, `query`, `keyword`, `searchKeyword`)가 상품명(`title`)에 없으면 추천 검색어에 함께 보강하고, `FOOD_TITLE` 및 확장·모바일 `FOOD_WORDS`에 `메밀|보리|귀리|오트|대두|잼|스프레드|땅콩버터|피넛버터`를 추가.
3. **#97 알레르기 무조건 경고·제조시설 교차오염 오탐 제거 및 상품명 즉시 감지 (`services/recommendation/http_service.py:170-210`, `apps/extension/src/shared/ui/ResultView.tsx:141-144`)**:
   - `http_service.py`: 성분표 미인식 시 모든 사용자 알레르기에 `evidence: 'unknown'` 경고를 생성하던 코드를 제거하고, OCR 성분 토큰에서 `'본 제품은 ... 사용한 제품과 같은 제조시설/공장/혼입가능'` 구간을 필터링. 대신 `body.query`(상품명)를 `detect([body.query] + ocr_ings + unknown_declared)`에 포함해 상단 화면에서도 상품명에 명시된 알레르기 원료(`땅콩버터`, `볶은 메밀` 등)를 즉시 경고하도록 개선.
   - `ResultView.tsx`: `visibleWarnings()`에서 `w.evidence !== 'unknown'`만 반환하도록 수정.
4. **#98 DB 추천 0건 시 실시간 AI 쇼핑몰 검색 폴백(`live_fallback.py`), 폴백 모델 이원화(`rankers.py`), UI 온오프 스위치 및 추천 링크 재분석 방지 (`apps/extension/src/...`, `services/api/kkulpick/analyses.py`)**:
   - `services/recommendation/live_fallback.py`: DB 추천 결과가 `0건`(`not result.picks`)이고 `body.ai_fallback=True`일 때만 `1순위: 수식어 + 핵심 품목`, `2순위: 핵심 품목` 키워드로 홈앤쇼핑(`_search_hnsmall`, 식품·생필품 풀) 및 29CM(`_search_29cm`), 중고나라(`_search_joongna`, 중고 포함 시)를 실시간 검색해 단일 트랜잭션(`with conn.transaction():`)으로 `app.catalog_items`·`app.products`/`app.foods`·`app.offers` 및 pgvector 인덱스에 즉시 적재.
   - `services/recommendation/rankers.py`, `http_service.py`: 기본 DB 추천은 `DEFAULT_MODEL`(`claude-opus-5-5`)을 유지하고, 실시간 폴백 재추천 시에만 `FALLBACK_MODEL`(`claude-sonnet-4-6`)을 사용하도록 분기. 또한 `ClaudeRanker.rank_rendered`에서 `output_config={"effort": "low"}` 미지원 모델 호출 시 `BadRequestError`를 잡아 옵션 없이 자동 재호출하도록 호환성 확보.
   - `apps/extension/src/sidepanel/screens/tabs.tsx`, `recommendSetting.ts`, `storage.ts`: 설정 탭에 **`추천 상품 없을 시 AI 추천`** 토글 스위치(`kp.aiFallbackEnabled`, 기본 켜짐)를 추가하고 `POST /analyses` → `analyses.py` → `analysis_worker.py` → `/internal/process`까지 `ai_fallback` 플래그를 연결.
   - `apps/extension/src/sidepanel/screens/tabs.tsx`, `background/index.ts`, `messages.ts`: 추천 카드 클릭 시 `openRecommendedUrl` 메시지로 새 탭을 열고 `recommendedTabs`에 등록해, 추천 상품을 클릭해 이동한 탭에서는 자동 재분석을 건너뛰고 기존 추천 결과를 유지하도록 수정.

---

## 검증

1. **크롤러 연속 탐색 검증**:
   - `kkulpick-db-dev-homepage-crawler-1`에 반영 후 2회차 실행 시 `app.offers` 등록 상품 수가 **77개 → 109개(+32개 신규 적재)**로 즉시 증가함을 확인 (`homepage_daisomall_co_kr` 42→52, `homepage_web_joongna_com` 18→24, `homepage_29cm_co_kr` 9→19, `homepage_kurly_com` 5→11).
2. **한·영 브랜드/복합어 매칭 및 알레르기 감지·오탐 제거 검증**:
   - `"에이수스 2026 비보북 고 15 라이젠5 라이젠 40 시리즈"` → `ASUS TUF A14 경량 게이밍 노트북` 1순위 추천 (무관 의류 0건).
   - `"나이키 에어포스 화이트 운동화"` → `(W) Nike Air Force 1 '07 Low White` 1순위 추천.
   - `"마켓로드 양평 해장국 (냉동), 700g, 6개"` (내 알레르기 `우유, 땅콩`): 상단 화면(`ingredients=[]`) 및 하단 제조시설 교차오염 문구(`"본 제품은 돼지고기, 우유를 사용한 제품과 같은 제조시설..."`) 모두 `warnings: []`로 오탐 없이 `[소반옥] 왕갈비탕 1KG`, `[숭의가든] 전통 갈비탕 1KG` 추천.
   - `"넛츠그린 100% 무가당 땅콩버터 크런치, 200g, 1개"` (내 알레르기 `땅콩`): 상단 화면에서도 상품명 기반 `peanut` 알레르기 경고 즉시 발생 확인, 추출 검색어 `1순위: '무가당 넛츠그린 땅콩버터' / '무가당 땅콩버터' → 2순위: '넛츠그린 땅콩버터'` 확인.
3. **DB 미등록 상품 실시간 검색 폴백(`ai_fallback`) 및 `"한방선생 볶은 메밀, 500g, 1개"` 검증**:
   - `"기계식 무소음 블루투스 키보드"`: `ai_fallback=False`일 때 `0건`, `ai_fallback=True`일 때 `산리오 기계식 무소음 키보드`(`129,000원`, 29CM) 실시간 적재 및 추천 확인.
   - `"한방선생 볶은 메밀, 500g, 1개"`: 홈앤쇼핑 실시간 검색으로 `볶은 메밀 1kg 메밀차`(`10,500원`), `볶은 메밀 2kg(1kgx2개) 메밀차`, `[푸른들판] 국내산 볶은 메밀 가루 100% 500g`, `[더봉평] 메밀 쌀과자` 등 7건 즉시 적재 및 추천 확인.
4. **Claude 모델별 처리 속도·토큰 수 실측 (동일 질의 `"에이수스 게이밍 노트북"`)**:
   - `claude-opus-5-5` (기본): `1,731 ms` | `1,598 in / 50 out` (합계 `1,648 토큰`)
   - `claude-sonnet-5-5`: `1,580 ms` | `1,598 in / 59 out` (합계 `1,657 토큰`)
   - `claude-sonnet-4-6` (실시간 폴백 전용): `2,384 ms` | `1,488 in / 54 out` (합계 `1,542 토큰`, Opus 대비 단가 1/5)
   - `claude-haiku-5-5`: `1,711 ms` | `1,598 in / 124 out`
   - `claude-haiku-4-5-20251001`: `2,855 ms` | `1,487 in / 104 out`
   - 규칙 기반 검색어 추출 우선화로 폴백 시 검색어 추출 LLM 호출(`148 토큰`)을 생략하여 폴백 1회당 총 토큰을 `3,419` → `3,165 토큰`으로 줄이고 과금 비용을 약 46% 절감.
5. **보안 및 빌드 검증**:
   - `apps/extension` 프로덕션 빌드(`tsc --noEmit && vite build`) 통과.
   - 커밋 `3be1719` 내 `sk-ant-` 등 API 키·시크릿 문자열 0건 확인 후 `origin/maintest` 및 `origin/part/소병선-backend-test` 반영 완료.
