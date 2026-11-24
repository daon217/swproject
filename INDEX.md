# 꿀픽 개발 이슈 색인

기존 Claude 검토 기준: `part/소병선-backend-test` (기준: `origin/maintest` 2c65ccd).

GPT 회고 범위는 실제 코드 개발을 시작한 **2026-11-04 이후**다. 개발 이전 설계·ERD·발표자료는 제외한다. [개발 기록 대응표·누락 보완](GPT_COVERAGE.md)을 함께 확인한다.

GPT 회고는 각 일지에 고정한 과거 커밋 기준이다. 과거 완료 기록은 현재 미해결 이슈의 종료 판정이 아니다.

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

## GPT 작업 회고 — 당시 완료 범위

작성 AI는 현재 회고 작성자 **GPT-6 (Codex)**이며, 원 작업의 상세 GPT 모델 버전은 미확인이다. 아래 번호는 기존 #33 이후로 부여했다. “부분 해결”은 기능 연결 등 일부 완료와 운영/후속 한계를 함께 뜻한다. 기존 미해결 이슈의 상태는 유지한다.

| # | 제목 | 당시 상태 | 근거 커밋 | 작성 AI | 개발일지 |
| --- | --- | --- | --- | --- | --- |
| 34 | 초기 저장소·3개 DB·로컬 개발환경 | 부분 해결 | `0c2bff5` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-foundation-db-ci-gpt-6.md) |
| 35 | 수집 API·상품 갱신·필드별 검증 | 부분 해결 | `0e6690b` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-catalog-ingestion-gpt-6.md) |
| 36 | 회원·모의 구독·문의·관리·탈퇴·분석 API | 부분 해결 | `2c177dd` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-backend-business-apis-gpt-6.md) |
| 37 | 성능 측정·조회 쿼리와 인덱스 개선 | 부분 해결 | `248d4c5` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-performance-efficiency-gpt-6.md) |
| 38 | 설정 점검·자동 백업·복원 검증 | 부분 해결 | `39b081f` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-backup-operations-gpt-6.md) |
| 39 | 화면과 실제 백엔드·DB 연결 | 부분 해결 | `41c1d1c` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-ui-backend-integration-gpt-6.md) |
| 40 | 계정별 페이지 기억·입력 검증·전환 처리 | 부분 해결 | `f075797` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-account-isolation-validation-gpt-6.md) |
| 41 | 모바일 날짜 입력 컴포넌트 순환 참조 제거 | 해결 | `d3ccb8a` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-mobile-import-cycle-gpt-6.md) |
| 42 | 팀 코드 통합·OCR 분석 작업자·관리 화면 연결 | 부분 해결 | `a19c431` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-team-runtime-integration-gpt-6.md) |
| 43 | 백엔드 임베딩 작업자와 pgvector 추천 연결 | 부분 해결 | `2d444b0` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-persistent-embedding-pipeline-gpt-6.md) |
| 44 | API 의존성·본문 제한·실행환경 감사 보완 | 부분 해결 | `0c2bff5` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-runtime-hardening-supplement-gpt-6.md) |
| 45 | 선택 공유 접속·독립 PC 전환·문서 정리 보완 | 부분 해결 | `ba68281` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-onboarding-docs-supplement-gpt-6.md) |
| 46 | 실제 수집 파일 가져오기·정리 정책·재생성 방지 보완 | 부분 해결 | `8fcacfa` | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-import-retention-supplement-gpt-6.md) |
| 47 | main 점검 이력과 개발일지 누락 재검토 | 해결(기록 보완) | `e7f7007`(점검 대상) | GPT-6 (Codex) | [기록](journal/2026-11-24-gpt-readonly-review-supplement-gpt-6.md) |

## 개발일지 목록

| 날짜 | 작성 AI | 내용 |
| --- | --- | --- |
| 2026-11-24 | Claude Opus 5.5 | [현황 조사](journal/2026-11-24-initial-survey-claude-opus-5.5.md) — 브랜치·Actions·구조 |
| 2026-11-24 | Claude Opus 5.5 | [세션 1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md) — #01~#10 |
| 2026-11-24 | Claude Opus 5.5 | [세션 2](journal/2026-11-24-backend-test-round2-claude-opus-5.5.md) — #11~#15 |
| 2026-11-24 | Claude Opus 5.5 | [실제 구동 시뮬레이션](journal/2026-11-24-runtime-simulation-claude-opus-5.5.md) — #24~#27 발견 |
| 2026-11-24 | Claude Opus 5.5 | [수집기(최준서) 검토](journal/2026-11-24-collector-review-claude-opus-5.5.md) — 주기 적재 전제, #29~#33 발견 |
| 2026-11-24 | Claude Opus 5.5 | [#31 판매 확인 API·신선도](journal/2026-11-24-freshness-checkins-claude-opus-5.5.md) — 백엔드 부분 해결 |
| 2026-11-24 | GPT-6 (Codex) | [GPT 회고 범위·귀속 근거](journal/2026-11-24-gpt-retrospective-scope-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#34 초기 저장소·3개 DB·로컬 개발환경](journal/2026-11-24-gpt-foundation-db-ci-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#35 수집 API·상품 갱신·필드별 검증](journal/2026-11-24-gpt-catalog-ingestion-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#36 회원·모의 구독·문의·관리·탈퇴·분석 API](journal/2026-11-24-gpt-backend-business-apis-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#37 성능 측정·조회 쿼리와 인덱스 개선](journal/2026-11-24-gpt-performance-efficiency-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#38 설정 점검·자동 백업·복원 검증](journal/2026-11-24-gpt-backup-operations-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#39 화면과 실제 백엔드·DB 연결](journal/2026-11-24-gpt-ui-backend-integration-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#40 계정별 페이지 기억·입력 검증·전환 처리](journal/2026-11-24-gpt-account-isolation-validation-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#41 모바일 날짜 입력 컴포넌트 순환 참조 제거](journal/2026-11-24-gpt-mobile-import-cycle-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#42 팀 코드 통합·OCR 분석 작업자·관리 화면 연결](journal/2026-11-24-gpt-team-runtime-integration-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#43 백엔드 임베딩 작업자와 pgvector 추천 연결](journal/2026-11-24-gpt-persistent-embedding-pipeline-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#44 API 의존성·본문 제한·실행환경 감사 보완](journal/2026-11-24-gpt-runtime-hardening-supplement-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#45 선택 공유 접속·독립 PC 전환·문서 정리 보완](journal/2026-11-24-gpt-onboarding-docs-supplement-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#46 실제 수집 파일 가져오기·정리 정책·재생성 방지 보완](journal/2026-11-24-gpt-import-retention-supplement-gpt-6.md) |
| 2026-11-24 | GPT-6 (Codex) | [#47 main 점검 이력과 개발일지 누락 재검토](journal/2026-11-24-gpt-readonly-review-supplement-gpt-6.md) |
