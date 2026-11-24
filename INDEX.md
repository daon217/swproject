# 이슈 목록

작업 브랜치: `part/소병선-backend-test` (기준: `origin/maintest` 2c65ccd). 상세는 각 로그 파일 참고.

| # | 제목 | 영역 | 상태 | 커밋 | 작성 AI | 로그 |
| --- | --- | --- | --- | --- | --- | --- |
| 01 | PR #15 CI UI 테스트 2개 실패 | tests/ui | 해결 | 2e2a806 | Claude Opus 5.5 | [세션1](logs/2026-11-24-backend-test-branch-claude-opus-5.5.md#01) |
| 02 | catalog-context 보조 검색이 50건에서 잘려 매칭 누락 | recommendation | 해결 | 2e2a806 | Claude Opus 5.5 | [세션1](logs/2026-11-24-backend-test-branch-claude-opus-5.5.md#02) |
| 03 | 유사 상품이 200건 상한 밖으로 밀림 | api/extensions | 해결 | 2e2a806 | Claude Opus 5.5 | [세션1](logs/2026-11-24-backend-test-branch-claude-opus-5.5.md#03) |
| 04 | 식품 오판 시 알레르기 경고가 사라짐 | dev_runtime | 부분 해결 | 2e2a806 | Claude Opus 5.5 | [세션1](logs/2026-11-24-backend-test-branch-claude-opus-5.5.md#04) |
| 05 | 분석 워커 예외 처리 (재시도 불가·리스 점유·Vision 404 오인) | dev_runtime | 해결 | 2e2a806 | Claude Opus 5.5 | [세션1](logs/2026-11-24-backend-test-branch-claude-opus-5.5.md#05) |
| 06 | 임베딩 작업 끝없는 재시도 | recommendation | 해결 | 793dc1d | Claude Opus 5.5 | [세션1](logs/2026-11-24-backend-test-branch-claude-opus-5.5.md#06) |
| 07 | 임베딩 1건씩 처리 (성능) | recommendation | 해결 | 793dc1d | Claude Opus 5.5 | [세션1](logs/2026-11-24-backend-test-branch-claude-opus-5.5.md#07) |
| 08 | 관리자 백엔드가 maintest에 없음 (웹 404 우회 유발) | api | 해결 | e18c36c | Claude Opus 5.5 | [세션1](logs/2026-11-24-backend-test-branch-claude-opus-5.5.md#08) |
| 09 | 애드픽 URL 변환 API 추가 | api | 해결(가정 포함) | e4b4678 | Claude Opus 5.5 | [세션1](logs/2026-11-24-backend-test-branch-claude-opus-5.5.md#09) |
| 10 | SQL 코드 오류가 "일시 장애 503"으로 숨겨짐 | api/errors | 해결 | e4b4678 | Claude Opus 5.5 | [세션1](logs/2026-11-24-backend-test-branch-claude-opus-5.5.md#10) |
| 11 | 회원·관리자 아이디 중복 가능 | api/auth | 해결 | aec0143 | Claude Opus 5.5 | [세션2](logs/2026-11-24-backend-test-round2-claude-opus-5.5.md#11) |
| 12 | 브랜드·카테고리 변경이 임베딩에 반영 안 됨 | recommendation/db | 해결 | 0e3da73 | Claude Opus 5.5 | [세션2](logs/2026-11-24-backend-test-round2-claude-opus-5.5.md#12) |
| 13 | 확장 정보 선도착 시 404로 유실, 옵션 삭제 불가 | api/extensions | 해결 | b5c8caa | Claude Opus 5.5 | [세션2](logs/2026-11-24-backend-test-round2-claude-opus-5.5.md#13) |
| 14 | 정리 작업이 crawl_runs FK 오류로 통째로 실패 | api/maintenance | 해결 | b5c8caa | Claude Opus 5.5 | [세션2](logs/2026-11-24-backend-test-round2-claude-opus-5.5.md#14) |
| 15 | 테스트끼리 DB 상태가 섞여 순서에 따라 실패 | tests | 해결 | 0e3da73 | Claude Opus 5.5 | [세션2](logs/2026-11-24-backend-test-round2-claude-opus-5.5.md#15) |
| 16 | 애드픽 API 무인증 → 분당 60회 할당량 남용 가능 | api/adpick | 미해결 | - | Claude Opus 5.5 | [미해결](logs/2026-11-24-open-issues-claude-opus-5.5.md#16) |
| 17 | 프록시 뒤에서 IP별 제한이 전체 제한이 됨 | infra/api | 미해결 | - | Claude Opus 5.5 | [미해결](logs/2026-11-24-open-issues-claude-opus-5.5.md#17) |
| 18 | 분석 워커 동시 4 vs OCR 1, 90초 타임아웃 | infra/dev_runtime | 미해결 | - | Claude Opus 5.5 | [미해결](logs/2026-11-24-open-issues-claude-opus-5.5.md#18) |
| 19 | 식품/상품 키워드 판별 범위가 넓음 | dev_runtime | 미해결 | - | Claude Opus 5.5 | [미해결](logs/2026-11-24-open-issues-claude-opus-5.5.md#19) |
| 20 | 김호진 웹의 관리자 토큰 위임 fallback (보안) | apps/web | 미해결 | - | Claude Opus 5.5 | [미해결](logs/2026-11-24-open-issues-claude-opus-5.5.md#20) |
| 21 | Vision 캐시 키가 이미지 앞 4KB만 비교 | kkulpick_vision | 미해결 | - | Claude Opus 5.5 | [미해결](logs/2026-11-24-open-issues-claude-opus-5.5.md#21) |
| 22 | 추천 서비스 요청마다 DB 연결 새로 생성 | recommendation | 미해결 | - | Claude Opus 5.5 | [미해결](logs/2026-11-24-open-issues-claude-opus-5.5.md#22) |
| 23 | 실제 수집 원본 300건이 저장소에 커밋됨 | collector | 확인 필요 | - | Claude Opus 5.5 | [미해결](logs/2026-11-24-open-issues-claude-opus-5.5.md#23) |

현황 조사(브랜치·Actions·구조): [logs/2026-11-24-initial-survey-claude-opus-5.5.md](logs/2026-11-24-initial-survey-claude-opus-5.5.md)
