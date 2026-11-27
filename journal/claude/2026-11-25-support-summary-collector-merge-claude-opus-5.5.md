# [Claude Opus 5.5] 개발일지 · 2026-11-25 #72 상담 고객 정보 · 최준서 수집기 병합·실연결 검증

- 작성 AI: Claude Opus 5.5
- 브랜치 / 커밋: maintest = `part/소병선-backend-test` **23f13f9**
  - `fbb578f` #72, `94b8756` 수집기 병합(`origin/feat/collector-homepage-html-20261125` 88c50ec ⊃ `part/최준서-collector` 719cb8e), `23f13f9` #70 변수명 정렬
- 상태: #72 해결. 수집기 병합·실제 백엔드 연결 검증 완료. #31·#32 수집기 쪽 연결 확인, #29·#30은 수집기 수정 반영(단위 테스트 기준)

## #72 상담 화면 고객 정보 — 해결 (fbb578f)
- 원인: 상담 목록 API는 고객 UUID만 반환 → 웹이 관리자 전용·최근 100명 회원 목록으로 보충 → 상담 담당자(support)는 UUID만, 관리자도 101번째 이전 고객 정보 없음.
- 해결: `accounts.py`에 회원 요약 쿼리 `MEMBER_SUMMARY`·`member_summaries()` 하나로 정의(회원 목록과 공유 → "구독 중" 판정 동일). `/v2/admin/support/conversations`가 `owner_login_id`와 `owner{login_id, gender, age_decade, subscribed, subscription_started_at}`를 함께 반환(탈퇴 회원은 null). 웹 상담 화면은 이 값을 먼저 쓰고 회원 목록 조회는 예전 서버 대비 보충용으로만.
- 개인정보 범위: 상담 담당자에게 성별·연령대·구독 여부가 보임(웹이 원래 의도한 고객정보 카드). 생년월일·전화번호 등은 포함하지 않음.
- 검증: API 테스트(support·admin 둘 다, 커서로 전체 목록 확인) 추가. 격리 DB API **92**·추천 85·변조 33 통과. **브라우저**: support 계정 로그인 → 메뉴는 고객상담만, 목록에 고객 로그인 아이디 표시, 상담 상세 고객정보 카드 "30대·여성·미구독"(시드 데이터와 일치), 관리자 전용 회원 목록 호출 없음.

## 수집기(최준서) 병합 (94b8756)
- 범위: `services/collector`만 238개 파일·약 2만 줄(collector_ops, unified_live 홈페이지 수집, marketplace_live, used_market_live, food_evidence, synthetic_catalog 등). 백엔드·웹 코드는 건드리지 않음.
- 점검: 비밀값·공인 IP 없음(사설 192.168.x 예시만), 실제 수집 원본 데이터 없음, 설정 JSON에 키 없음.
- 충돌 1건 `domeggook_live/domeggook_backend.py`: 수집기 쪽 최신 버전 채택(확장 202 `pending` 상태와 `listing-checks` 경로 추가가 기존 줄의 확장).
- 수집기 테스트: **600 통과**(+ 하위 215), `domeggook_live/devtest`는 명시적 승인 환경변수가 필요한 수동 하네스라 제외. CI는 수집기 테스트를 돌리지 않음(빌드만).

## 수집기 → 실제 백엔드 연결 검증 (격리 API, 합성 HTML만 사용)
수집기의 **실제 전송 경로**(URLWorker → ChangeDelivery → ApprovedOutbox → RoutedBackend `internal_http`)로 실제 FastAPI에 보냄. 외부 사이트 요청 없음(수집기의 합성 상품 페이지 픽스처).
| 확인 | 결과 |
| --- | --- |
| 상태 미표시 상품 | 관측 `condition=unknown` → DB `unknown` (#68 계약 그대로) |
| 중고 상품 | `used` |
| 전송 결과 | 3/3 `applied`, 보류·격리·소진 0 |
| 확장(판매처) | `listing_extensions` 2건 `applied`, `offers.seller_name` 저장 |
| 변경 없는 재수집 | 관측 재전송 없음, `listing-checks`로 `last_seen_at` 갱신 (**#31 수집기 쪽 연결**) |
| 가격 변경 9.50→9.90 | `change_kind=updated` |
- 수집기 메모: `HOMEPAGE_VALIDATION_RESULTS.json`상 이전에는 실제 백엔드 전송이 0건이었음 → 이번이 첫 실연결 확인.

## 기존 미해결 문제에 미치는 영향
- #31: 백엔드(4f26501) + 수집기(unified_live) 모두 연결 → **해결**(NAS 실데이터 확인 필요).
- #32: 수집기가 확장 API로 판매처·매칭 정보 전송 → **해결(수집기)**. 식품 성분 전송(#27)은 수집기 food_evidence 경로가 있으나 실 상품으로는 미확인.
- #29·#30: 수집기 커밋(719cb8e "recover delivery failures", 409 항목 단위 보류 테스트)에 반영. 단위 테스트 통과, 실 장애 상황은 미검증 → **부분 해결**.

## 결정 필요 (사용자)
- 수집기 팀 제안서(`collector_ops/CONTRACT_GAPS.md`)는 `unknown` 상태 상품을 확인 전까지 일반 결과에서 **제외**하자고 함. 현재 백엔드(#68)는 기본 추천·유사 상품에 `used`가 아닌 것(new+unknown)을 보여 주고 `/v2/offers` 기본 필터만 `new`. 일반 쇼핑몰 상품 대부분이 unknown이 될 수 있어 제외하면 추천 대상이 크게 줄어듦 → 정책 결정 필요.
- 제안서의 refurbished/open_box 등 세부 상태, 재고 수량, lifecycle 필드는 백엔드 미지원(수집기는 보내지 않고 보류) — 범위 결정 필요.

## 다음
- NAS에서 수집기 실데이터 적재 확인(`COLLECTOR_BACKEND_TRANSPORT=internal_http`, `COLLECTOR_BACKEND_BASE_URL`, `KKULPICK_BACKEND_TOKEN`, `COLLECTOR_DELIVERY_APPROVED=yes`).

## 추가: condition 기준 통일 (사용자 결정, 9b4d366 — maintest 푸시 완료)
- 결정: 전체 = new+used+unknown, 새 상품만 = new, 중고만 = used, 기본 추천·유사 상품 = new+used+unknown. unknown은 new로 취급하지 않고 '미확인'으로 표시.
- 변경: `GET /v2/offers` 기본 `condition=all`(이전 new) / 기본 추천이 used를 빼던 조건 제거 / 유사 상품은 이미 `include_used` 기본 true / 모든 상품 카드에 `condition` 포함(`CARD_FRESHNESS`) / 확장·모바일 카드 보조 문구에 "중고"·"상태 미확인" / 관리자 수집 목록에 '상품 상태' 열(새 상품·중고·미확인) / 계약 문서.
- 유지: 개인 맞춤 AI 추천은 회원의 '중고 포함' 설정을 따름(사용자가 직접 끈 경우는 제외가 맞음).
- 검증: 확장·모바일 TypeScript 검사 통과, 웹 JS 문법, 격리 DB API 92·추천 85·변조 33(두 순서). 기본 목록·new 필터·기본 추천 used 포함·카드 condition 테스트 갱신.
