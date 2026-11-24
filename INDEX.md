# [Claude Opus 5.5] 이슈 색인

작업 브랜치: `part/소병선-backend-test` (기준: `origin/maintest` 2c65ccd).

- **미해결 문제 → [OPEN_ISSUES.md](OPEN_ISSUES.md)** (현재 상태·주기 적재 시 영향·다음 행동)
- **무엇을 언제 왜 했는지 → `journal/` 개발일지**

## 해결됨

| # | 제목 | 영역 | 커밋 | 작성 AI | 개발일지 |
| --- | --- | --- | --- | --- | --- |
| 01 | PR #15 CI UI 테스트 2개 실패 | tests/ui | 2e2a806 | Claude Opus 5.5 | [세션1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md#01) |
| 02 | catalog-context 보조 검색 50건 절단 | recommendation | 2e2a806 | Claude Opus 5.5 | [세션1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md#02) |
| 03 | 유사 상품 200건 상한 | api/extensions | 2e2a806 | Claude Opus 5.5 | [세션1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md#03) |
| 05 | 분석 워커 예외 처리 | dev_runtime | 2e2a806 | Claude Opus 5.5 | [세션1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md#05) |
| 06 | 임베딩 끝없는 재시도 | recommendation | 793dc1d | Claude Opus 5.5 | [세션1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md#06) |
| 07 | 임베딩 1건씩 처리 | recommendation | 793dc1d | Claude Opus 5.5 | [세션1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md#07) |
| 08 | 관리자 백엔드 병합 | api | e18c36c | Claude Opus 5.5 | [세션1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md#08) |
| 09 | 애드픽 URL 변환 API (요청 형식은 가정) | api | e4b4678 | Claude Opus 5.5 | [세션1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md#09) |
| 10 | SQL 코드 오류가 503으로 숨겨짐 | api/errors | e4b4678 | Claude Opus 5.5 | [세션1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md#10) |
| 11 | 회원·관리자 아이디 중복 | api/auth | aec0143 | Claude Opus 5.5 | [세션2](journal/2026-11-24-backend-test-round2-claude-opus-5.5.md#11) |
| 12 | 브랜드·카테고리 임베딩 반영 (→ #24 유발) | recommendation/db | 0e3da73 | Claude Opus 5.5 | [세션2](journal/2026-11-24-backend-test-round2-claude-opus-5.5.md#12) |
| 13 | 확장 정보 선도착 유실, 옵션 삭제 불가 | api/extensions | b5c8caa | Claude Opus 5.5 | [세션2](journal/2026-11-24-backend-test-round2-claude-opus-5.5.md#13) |
| 14 | 정리 작업 crawl_runs FK 오류 | api/maintenance | b5c8caa | Claude Opus 5.5 | [세션2](journal/2026-11-24-backend-test-round2-claude-opus-5.5.md#14) |
| 15 | 테스트 DB 상태 섞임 | tests | 0e3da73 | Claude Opus 5.5 | [세션2](journal/2026-11-24-backend-test-round2-claude-opus-5.5.md#15) |
| 31 | (부분) 판매 확인 check-in API·카드 신선도 — 수집기 호출 남음 | api/recommendation | 4f26501 | Claude Opus 5.5 | [신선도](journal/2026-11-24-freshness-checkins-claude-opus-5.5.md) |

## 미해결 (상세는 OPEN_ISSUES.md)

04(부분 해결), 16~30, 31(부분 해결: 수집기 쪽 남음), 32, 33

## 개발일지 목록

| 날짜 | 작성 AI | 내용 |
| --- | --- | --- |
| 2026-11-24 | Claude Opus 5.5 | [현황 조사](journal/2026-11-24-initial-survey-claude-opus-5.5.md) — 브랜치·Actions·구조 |
| 2026-11-24 | Claude Opus 5.5 | [세션 1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md) — #01~#10 |
| 2026-11-24 | Claude Opus 5.5 | [세션 2](journal/2026-11-24-backend-test-round2-claude-opus-5.5.md) — #11~#15 |
| 2026-11-24 | Claude Opus 5.5 | [실제 구동 시뮬레이션](journal/2026-11-24-runtime-simulation-claude-opus-5.5.md) — #24~#27 발견 |
| 2026-11-24 | Claude Opus 5.5 | [수집기(최준서) 검토](journal/2026-11-24-collector-review-claude-opus-5.5.md) — 주기 적재 전제, #29~#33 발견 |
| 2026-11-24 | Claude Opus 5.5 | [#31 판매 확인 API·신선도](journal/2026-11-24-freshness-checkins-claude-opus-5.5.md) — 백엔드 부분 해결 |
