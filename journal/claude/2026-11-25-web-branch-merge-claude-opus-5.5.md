# [Claude Opus 5.5] 개발일지 · 2026-11-25 김호진 웹 브랜치 maintest 병합 (#20·#58 해결)

- 작성 AI: Claude Opus 5.5
- 브랜치 / 커밋: `part/소병선-backend-test` 병합 커밋 `d0a46f8` (← `origin/part/김호진-web` `3619d22`) → `maintest`
- 상태: 병합 완료, #20 해결(maintest 기준), #58 해결

## 가져온 것 (김호진 9073f9b, 3619d22)
수집 화면 카탈로그 목록·선택 삭제·점진 로딩, 대시보드 일별 구독자 카드, 구독자 지표 수정, 상담·고객·통계 화면 개선.

## 병합하며 처리한 것

### 1. 충돌 3개 (`layout.js`, `crawling/index.js`, `login/index.js`)
- 웹팀의 새 구조(`Promise.allSettled` 병렬 조회, `onBatch` 점진 표시, 페이지 상한)를 기준으로 하고 #55 주소 수정만 유지.
- **`login/index.js`의 `requestAdminAuth`**: 브랜치가 `fetch(new URL(endpoint, getAdminAuthOrigin()))`로 바꿨는데 #55와 같은 버그(경로가 `/`로 시작해 `/backend`가 빠짐) → 그대로 받았으면 **관리자 로그인·가입·승인 요청이 전부 404**. 문자열 연결을 유지하고 시간 제한만 브랜치 값(15초)을 반영.

### 2. #20 관리자 토큰 위임 우회 제거 (보안) — 해결
- 원인: 관리자 API가 404일 때를 대비한 "NAS 관리자 승인 폴백"(`3619d22`). 관리자 로그인 시 본인 토큰을 localStorage와 `local-demo.cjs`(`/__admin-approval/delegate`)에 저장하고, 인증 없는 `/status?login_id=`로 승인된 사용자에게 그 토큰을 넘김. 승인 실패도 `.catch(() => ({status:'approved'}))`로 성공 처리. 관리자 가입 404 시 일반 회원으로 가입. 상품 삭제 404 시 브라우저에서만 숨김.
- 선택지: (A) 데모 모드에서만 허용 / (B) 완전 제거 ✅ — 백엔드가 이제 `/v2/admin/auth/*`, `/v2/admin/catalog/offers/delete`를 제공(#08)하므로 폴백이 필요 없고, 토큰 위임은 데모에서도 위험.
- 적용:
  - 로그인·가입 신청 목록·승인·카탈로그 삭제를 서버 응답만 사용. 404면 오류 메시지.
  - `requestLocalApproval`, `getLocalApprovalCache`, `recordPendingAdminRequest`, 위임 토큰 처리, 로컬 삭제 목록 필터 삭제.
  - `local-demo.cjs`는 maintest 버전 유지(브랜치가 추가한 `/__admin-approval` 전부 제외).
  - 예전 버전이 남긴 localStorage(`kkulpick-admin-approvals` — 관리자 토큰이 들어 있을 수 있음, `kkulpick-deleted-catalog-offers` — 실제 상품을 계속 숨길 수 있음)를 로그인·로그아웃·수집 화면 진입 시 삭제.

### 3. #58 매출 표시 — 해결 (병합 중 발견)
- 문제: 대시보드 "당월 누적 매출금액"이 실제로는 **최근 30일 모의 결제 합계**, "금일 누적 매출금액"은 (모의 매출 ÷ 구독자 수 × 오늘 구독자 수)로 **추정한 값**. 통계 차트는 30일 합계를 오늘 막대 하나에 그림. 각주는 "실제 매출 데이터"라고 표시.
- 해결: `/v2/admin/overview`에 `today_mock_revenue_krw`(KST 오늘의 모의 결제 합계) 추가. 카드 제목을 "최근 30일 모의 결제 합계", "오늘 모의 결제 합계"로, 설명을 "개발용 모의 결제 · 실매출 아님"으로. 차트는 오늘 값만, 각주 정정.
- 왜: 추정값·기간이 다른 값을 매출로 보여주면 운영 판단을 잘못하게 된다. 서버가 아는 값만, 이름 그대로 보여준다.
- 테스트: `test_console_aggregates_settings_and_public_basic`에 오늘 결제 2건 합계와 `today_mock_revenue_krw` 증가분이 같은지 추가.

## 검증
- **브라우저(격리 환경, 상품 68건)**: 웹에서 관리자 가입 신청 → 승인 전 로그인 시 "관리자 가입 승인 대기 중"(세션·저장 토큰 없음) → 관리자로 로그인해 승인 화면에서 support 승인 → 목록에서 사라짐. 대시보드에 일별 구독자 카드·모의 결제 카드. 수집 화면 68건 표시, 1건 선택 삭제 → API에서도 사라짐(로컬 숨김 없음). UI 테스트 흐름(상담 메시지·답변·설정, 제휴 판매정보 68건·등록) 통과. 7개 화면 이동 중 스크립트 오류 0건.
- **자동 테스트**: 격리 DB에서 CI 순서·반대 순서 추천+워커 79, API 89(매출 검증 포함), 샘플 변조 32 통과. Windows API 단위 35 통과. JS 문법 검사 전체 통과.

## 남은 과제 / 주의
- `origin/part/김호진-web` 브랜치 자체에는 #55(404)·#20(토큰 위임) 코드가 그대로 있다. 웹 담당이 그 브랜치에서 계속 작업해 다시 병합하면 되살아날 수 있으므로, **maintest를 먼저 받아서(merge/rebase) 작업**하도록 공유 필요.
- 실제 Playwright 실행은 CI 결과로 확인.
