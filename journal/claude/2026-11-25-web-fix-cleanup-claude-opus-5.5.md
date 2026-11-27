# [Claude Opus 5.5] 개발일지 · 2026-11-25 관리자 웹 404·덮어쓰기 계층 정리, 코드 점검·정리 (#55~#57 해결)

- 작성 AI: Claude Opus 5.5
- 브랜치 / 커밋: `part/소병선-backend-test` / `e37338e`(웹), `36f5f28`(정리) → `maintest` 반영
- 상태: #55·#56·#57 **해결**
- 계기: [maintest 점검·AI 일지 검토](2026-11-25-maintest-ci-and-ai-log-review-claude-opus-5.5.md)에서 찾은 문제 수정 요청

## #55 상품 목록 404 — 해결 (e37338e)
- 문제·원인: `new URL('/v2/offers', getApiBase())`가 `/backend`를 버려 Next 프록시를 거치지 않고 404. 제휴 등록 화면 판매정보가 비고 `Team connected runtime` CI가 실패.
- 해결: `new URL(this.getApiBase() + '/v2/offers')` (`shared/layout.js`, `pages/crawling/index.js`).
- 왜: 기준 경로를 문자열로 이어 붙이면 `/backend` 프록시 경로가 항상 유지된다. 같은 문제가 김호진 브랜치에도 있어 병합 시 같은 줄이 충돌할 수 있다 → 웹 담당에게 공유 필요.

## #56 `shared/backend.js` 덮어쓰기 계층 — 해결 (e37338e)
- 검토한 선택지
| 선택지 | 판단 |
| --- | --- |
| A. backend.js 제거, 웹팀 페이지 구현 사용 | ✅ 페이지가 이미 라우트별로 실제 API를 부름(`liveAffiliates`·`liveCounseling`·`liveCatalog`·`liveCustomers`·`liveOverview`, `refreshAdminData`). 김호진 브랜치 병합 시 새 화면이 그대로 보임 |
| B. backend.js 유지 | 웹팀 신규 기능이 계속 가려짐 |
- 해결: `shared/backend.js` 삭제, `index.html` 스크립트·`app.js` 병합 대상 제거. 로그인 쪽에서 backend.js에만 있던 `loadConsoleData`/`clearConsoleData` 호출을 `clearLiveConsoleData()`(페이지 캐시 초기화)로 교체 — 계정을 바꿔 로그인해도 이전 계정 목록이 남지 않게.
- 효과: 로그인 직후 같은 관리자 API를 두 번씩 부르던 중복 요청도 사라짐(네트워크 기록에서 확인).

## #57 테스트 기대 문구 — 해결 (e37338e)
- `console.spec.js`: '서비스 현황' → 'MAIN · 대시보드', '상담 설정을 DB에 저장했습니다.' → '상담 설정을 팀 서버 DB에 저장했습니다.', '제휴상품을 저장했습니다.' → '새 제휴 상품을 서버에 등록했습니다.'

## 코드 점검·정리 (36f5f28)
- pyflakes(백엔드·추천·워커·tools)와 `node --check`(웹 전체) 실행.
- 정리: 테스트에서만 쓰던 `analysis_worker.context_url`과 그 테스트 삭제, `tools/performance.py`·`tools/test_operations.py`의 사용하지 않는 import 삭제, `devapp.py`에 재수출 의도 표시(`__all__`).
- 테스트 파일의 pyflakes 경고(pytest fixture를 import하는 패턴)는 의도된 것이라 그대로 둠.
- 문서: `docs/embedding-pipeline.md`를 현재 동작에 맞춤(catalog-v2 템플릿, 배치 32개, 8회 실패 시 보류, `--requeue-failed`, bootstrap의 이전 계약 정리와 #24 주의).

## 검증
- **브라우저(격리 환경 `kkulpick-ui`: postgres+api+web, 상품 63건, CLI 승인 관리자)**: UI 테스트(`console.spec.js`)의 모든 단계를 직접 수행 — 로그인 후 'MAIN · 대시보드', 상담 메시지 표시·답변 전송·새로고침 후 유지, 상담 설정 10:00 저장·새로고침 후 유지, 제휴 등록 판매정보 63건 조회·등록·새로고침 후 제휴사 표시. 6개 화면(대시보드·통계·수집·고객·제휴·상담) 이동 중 스크립트 오류 0건. `backend.js` 요청 없음, `/backend/v2/offers` 200.
- **자동 테스트**: 격리 DB에서 CI 순서·반대 순서 모두 추천+워커 79(삭제한 테스트 1개 감소), API 89, 샘플 변조 32 통과. Windows 단위 API 35, 워커·추천 62, CI 스크립트 9 통과.
- tools 1건 실패는 커밋하지 않은 로컬 `apps/mobile/.env.example` 변경 때문(기존과 동일, CI 무관).
- 검증 못한 것: 실제 Playwright 실행은 CI에서 확인 예정.

## 남은 과제
- 김호진 브랜치에 같은 404 코드(#55)가 있음 → 웹 담당 공유. 김호진 브랜치를 maintest에 병합할 때 `login/index.js`, `layout.js` 충돌 예상.
