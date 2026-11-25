# [Claude Opus 5.5] 개발일지 · 2026-11-25 maintest(4f26501) 점검과 GPT·Gemini 개발일지 교차 검토 (#55~#57)

- 작성 AI: Claude Opus 5.5
- 대상: `origin/maintest` 4f26501 (11-24 push 이후 변경 없음), devlog의 GPT-6(#34~#47)·Gemini 4 Argon(#48~#54) 일지
- 코드 변경 없음 (점검·재현만)

## 1. maintest CI 결과 (PR #15, 4f26501)
| 워크플로 | 결과 |
| --- | --- |
| Team build, Team development access, Catalog API integration, Full development workspace, Persistent embedding pipeline(push·PR), **Frontend backend integration** | 성공 (#01에서 고친 guest-floating 테스트 통과) |
| **Team connected runtime** | 실패 — `tests/ui/console.spec.js:33` |

`console.spec.js:23`('답변 보내기', #01 수정)과 29~30행(상담 설정)은 통과했고, 그 다음 단계에서 처음으로 실패. 이전에는 23행에서 멈춰 이 단계까지 온 적이 없다.

---

## <a id="55"></a>#55 관리자 웹이 상품 목록을 `/backend` 없이 요청해 404 — 미해결 (CI 실패 원인)

**문제점** 제휴 상품 등록 화면의 "판매정보" 선택 목록이 항상 비어 있다("선택할 수 있는 카탈로그 판매정보가 없습니다"). 제휴 상품을 새로 등록할 수 없다. `Team connected runtime` CI 실패의 직접 원인.

**재현** 격리 환경(`kkulpick-ui`: postgres+api+web 컨테이너, 상품 130건, CLI로 승인한 관리자)에서 내장 브라우저로 `#/affiliate/create` 진입 → 목록 비어 있음. 네트워크: `GET http://127.0.0.1:53000/v2/offers?selected_domain=product...` → **404** (product·food 각각 2회).

**원인** `apps/web/shared/layout.js:127` (`fetchAllCatalogOffers`)
```js
const url = new URL('/v2/offers', this.getApiBase());   // getApiBase() = "http://host/backend"
```
경로가 `/`로 시작하면 `new URL`이 기준 주소의 경로(`/backend`)를 버린다 → `/v2/offers`로 요청 → Next 프록시(`app/backend/[...path]`)를 거치지 않아 404. 같은 코드가 `apps/web/pages/crawling/index.js:101`에도 있다.
- 처음 들어온 커밋: 김호진 `51046ab`, `d126928`. `origin/part/김호진-web`(`layout.js:129`, `crawling/index.js:191`)에도 그대로.
- 김호진 로컬 데모(`local-demo.cjs`)는 루트 경로에서 API를 응답해서 개발 중에는 드러나지 않은 것으로 보인다(추정).

**해결 방안** `new URL(this.getApiBase() + '/v2/offers')`처럼 기준 경로를 유지. 두 파일 각 1줄. 웹 담당(김호진)과 공유 필요 — maintest에서 고치면 김호진 브랜치 병합 시 같은 줄이 충돌할 수 있다.

---

## <a id="56"></a>#56 `apps/web/shared/backend.js`가 웹팀 화면 구현을 덮어쓴다 — 미해결 (웹 병합 전 결정 필요)

**문제점** maintest의 관리자 웹에는 화면 구현이 두 벌 있다.
1. 웹팀(김호진) 페이지: `pages/*/index.js`, `shared/layout.js`
2. 통합용 덮어쓰기 계층 `shared/backend.js` (`a9da43b`, GPT 통합 #42) — `index.html`에서 **마지막에 로드**되어 같은 이름의 함수를 덮어쓴다.

덮어쓰는 함수: `renderContent`, `getMainDashboardHtml`, `getStatsHtml`(= 대시보드와 동일), `getCrawlingHtml`(관측 집계 표), `submitAffiliateForm`, `confirmDeleteAffiliate`, `saveCounselingSettings`, `sendCounselingReply`, `completeCounseling`, `loadMessages`, 차트 초기화(빈 함수) 등.

**영향**
- 지금 maintest에서 보이는 통계·수집 현황·대시보드는 웹팀 화면이 아니라 `backend.js`의 단순 화면이다.
- `origin/part/김호진-web`을 maintest에 병합해도(`git merge-tree`로 확인) `backend.js`는 그대로 남고 `index.html`에서도 마지막에 로드된다 → 김호진의 새 기능(수집 화면 상품 선택 삭제, 일별 구독자 카드, 카탈로그 점진 로딩, 통계 화면)이 **화면에 나타나지 않는다.**
- 같은 동작이 두 곳에 있어 문구도 다르다(아래 #57).

**해결 방안 (결정 필요)**
| 선택지 | 비고 |
| --- | --- |
| A. 웹팀 구현을 기준으로 `backend.js` 제거(또는 웹팀 구현에 없는 부분만 남김) | 김호진 브랜치가 이미 실제 API를 연결함(`d126928` "complete live admin API integration"). 권장 |
| B. `backend.js`를 기준으로 유지 | 웹팀 신규 화면 기능을 포기하거나 backend.js로 다시 옮겨야 함 |
- 어느 쪽이든 UI 테스트(`console.spec.js`)의 기대 문구를 함께 맞춰야 한다.

---

## <a id="57"></a>#57 UI 테스트 기대 문구가 덮어쓰기 계층에만 있다 — 확인 필요

- `console.spec.js:29` `'상담 설정을 DB에 저장했습니다.'`, `:38` `'제휴상품을 저장했습니다.'` → 이 문구는 `shared/backend.js:105`, `:92`에 있고, 웹팀 화면(`counseling/index.js:566` '상담 설정을 팀 서버 DB에 저장했습니다.', `affiliate/index.js:842` '새 제휴 상품을 서버에 등록했습니다.')과 다르다.
- 현재는 backend.js가 이기므로 29행은 통과(CI 확인). #56에서 A안을 택하면 테스트 문구를 웹팀 문구로 바꿔야 한다.

---

## 2. GPT·Gemini 개발일지 교차 검토

### 정확한 부분 (코드·CI와 일치)
- **Gemini #53·#54**: `3d7d6ed`/`2c65ccd`의 URL 후보 매칭, 422/503 분리, `image_urls` 중복 제거, 도메인 전환 시 임베딩 작업 삭제 — 코드와 일치. 남은 한계(보조 검색 LIMIT 50, 유사 후보 가격순)를 스스로 적고 #02·#03으로 연결한 것도 정확.
- **Gemini #49·#50**: 0009 스키마·확장 API·PgCatalog 성분 연결 — 코드와 일치. 운영 수집기 미연결(#27·#32)을 종료하지 않고 남긴 것도 적절.
- **GPT 대응표**: 귀속을 모르는 구간을 제외하고, 과거 완료 보고를 현재 이슈 종료로 쓰지 않는다는 원칙이 명시되어 있음.
- **Gemini #48 CI 원인 중 23행·guest-floating**: 정확(#01과 같은 결론).

### 틀리거나 보완이 필요한 부분
| 일지 | 내용 | 판정 |
| --- | --- | --- |
| Gemini #48 | `console.spec.js:29`, `:38`도 문구 불일치라 테스트를 웹팀 문구로 바꿔야 한다고 진단·패치안 제시 | **부정확.** 실제로 쓰이는 문구는 `shared/backend.js`에 있어 29행은 CI에서 통과. 그 패치안을 적용하면 오히려 실패한다(#57). |
| Gemini #48 | "실제 코드 반영은 이후 Claude #01(2e2a806)에서도 동일 원인으로 확인·적용" | **일부만 맞음.** #01은 23행과 guest-floating만 고쳤고 29·38행은 고치지 않음(고칠 필요가 없었음). |
| Gemini #48 | 헤놀로지 메모리 4.5~5.8GB, 처리량 등 | **추정치.** 측정값이 아니므로 "확인한 사실" 항목과 분리해 읽어야 함. 이후 임베딩 배치 처리(#07, 32건 묶음)로 CPU 사용 형태가 바뀜. |
| GPT #42 | 관리자 화면 실제 CRUD 연결 | `shared/backend.js` 덮어쓰기 계층을 추가했다는 사실과 그 영향(웹팀 화면 가림)이 기록에 없음 → #56으로 보완. |
| GPT #42 | PR #13에서 브라우저 관리 CRUD 확인 | 당시는 통과했으나 11-19 김호진 병합(`c7d8cdf`) 이후 main에서 계속 실패. 과거 수치를 현재 상태로 읽으면 안 됨(대응표의 유의사항과 같은 취지). |

## 3. 정리
- maintest 백엔드 쪽은 CI 전부 통과. 남은 CI 실패 1건은 **웹 코드 버그(#55)**.
- 김호진 웹 병합 전에 **#56(덮어쓰기 계층 정리 방향)**을 먼저 정해야 병합 효과가 화면에 나타난다.
- 검증 환경(`kkulpick-ui`)은 점검 후 삭제.
