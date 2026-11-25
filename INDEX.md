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
| 55 | 관리자 웹 상품 목록 404(`/backend` 누락) | apps/web | e37338e | Claude Opus 5.5 | [웹 정리](journal/2026-11-25-web-fix-cleanup-claude-opus-5.5.md#55-상품-목록-404--해결-e37338e) |
| 56 | `shared/backend.js` 덮어쓰기 계층 제거 | apps/web | e37338e | Claude Opus 5.5 | [웹 정리](journal/2026-11-25-web-fix-cleanup-claude-opus-5.5.md) |
| 57 | UI 테스트 기대 문구를 웹팀 화면에 맞춤 | tests/ui | e37338e | Claude Opus 5.5 | [웹 정리](journal/2026-11-25-web-fix-cleanup-claude-opus-5.5.md) |
| 20 | 김호진 웹의 관리자 토큰 위임 우회 제거(보안) | apps/web | d0a46f8 | Claude Opus 5.5 | [웹 병합](journal/2026-11-25-web-branch-merge-claude-opus-5.5.md) |
| 58 | 대시보드·통계 매출 표시(추정값·기간 불일치) 정정, 오늘 모의 결제 합계 API | apps/web·api | d0a46f8 | Claude Opus 5.5 | [웹 병합](journal/2026-11-25-web-branch-merge-claude-opus-5.5.md) |
| 59 | 식품 알레르기 신고 코드(`shellfish`·`pine_nut`) 누락·원문 있으면 무시 → 코드 직접 판정, 저장 코드 통일 | recommendation·api·dev_runtime | b51ffdc | Claude Opus 5.5 | [#59](journal/2026-11-25-allergen-declared-codes-claude-opus-5.5.md) |
| 66 | Vision 워커 메모리 계단식 증가·OOM → OCR 입력 크기 고정(캔버스·폭 2가지), 메모리 기준 교체, mem_limit | kkulpick_vision·infra | 9247330 | Claude Opus 5.5 | [수정](journal/2026-11-25-vision-memory-embedding-fix-claude-opus-5.5.md) |
| 67 | 임베딩 느림 → torch 스레드 제한(34→268/s), 배치 커밋(4.08→2.61ms/건) | recommendation | 426a5da | Claude Opus 5.5 | [수정](journal/2026-11-25-vision-memory-embedding-fix-claude-opus-5.5.md) |
| 68 | `condition=unknown` 지원(판매처가 신품·중고 미표시), unknown은 기존 상태를 덮어쓰지 않음, 추천 계약 422 방지 | api·recommendation·db | e6c7a3e | Claude Opus 5.5 | [#68](journal/2026-11-25-condition-unknown-web-sync-claude-opus-5.5.md) |
| 69 | 관리자 웹 제휴 링크 우회 저장(store.example.test/redirect) 제거, 저장된 주소 그대로 표시 | apps/web | 04375f2 | Claude Opus 5.5 | [수정](journal/2026-11-25-fix-69-70-71-claude-opus-5.5.md) |
| 70 | (코드) 수집기 테스트의 NAS IP → KKULPICK_API_BASE (이력은 미해결 목록) | collector | 5a72193 | Claude Opus 5.5 | [수정](journal/2026-11-25-fix-69-70-71-claude-opus-5.5.md) |
| 71 | 강제 종료로 시도 상한에 닿은 임베딩 작업을 exhausted:WorkerLost로 보류 | recommendation | a83cdb6 | Claude Opus 5.5 | [수정](journal/2026-11-25-fix-69-70-71-claude-opus-5.5.md) |
| 72 | 상담 목록이 고객 아이디·요약을 함께 반환(상담 담당자도 고객정보 표시, 100명 제한 무관) | api·apps/web | fbb578f | Claude Opus 5.5 | [일지](journal/2026-11-25-support-summary-collector-merge-claude-opus-5.5.md) |
| 31 | (완료) 수집기 unified_live가 listing-checks 호출 — 실제 백엔드 연결 검증 | collector | 94b8756 | 최준서 / 검증 Claude Opus 5.5 | [일지](journal/2026-11-25-support-summary-collector-merge-claude-opus-5.5.md) |
| 32 | 수집기가 확장 API로 판매처·매칭 정보 전송 — 실제 백엔드 연결 검증 | collector | 94b8756 | 최준서 / 검증 Claude Opus 5.5 | [일지](journal/2026-11-25-support-summary-collector-merge-claude-opus-5.5.md) |

## 미해결 (상세는 OPEN_ISSUES.md)

04(부분 해결), 16~30(29·30 부분), 33, 60~65, 70(이력), 73~77

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

## Gemini 작업 기록 — maintest 구현·검증 및 아키텍처/하드웨어 진단 (`4b1f5fc`~`2c65ccd`)

작성 AI는 **Gemini 4 Argon**다. 기존 GPT 회고에서 원 작업 AI 미확인으로 제외해 두었던 `maintest`의 `4b1f5fc`~`2c65ccd` 구간(7개 커밋)과 11-19/11-23 전체 구조·CI 실패 규명·헤놀로지(`i5-6600`) 하드웨어/성능 분석을 기록한다. 전체 요청·커밋·CI 실행 대응표는 [GEMINI_COVERAGE.md](GEMINI_COVERAGE.md)를 함께 확인한다. 기존 `OPEN_ISSUES.md`의 미해결 상태는 그대로 유지한다.

| # | 제목 | 상태 | 근거 커밋 | 작성 AI | 개발일지 |
| --- | --- | --- | --- | --- | --- |
| 48 | 전체 브랜치·CI 실패 2건 원인 규명·헤놀로지(i5-6600) 하드웨어/성능 분석 및 16개 문제점 진단 | 해결(진단) | `32f08ba`, `2d444b0`(점검 대상) | Gemini 4 Argon | [기록](journal/2026-11-24-gemini-survey-hardware-diagnostics-gemini-4-argon.md) |
| 49 | 카탈로그 DB(`0009_catalog_details`) 식품 원재료·알레르기 저장 및 추천 엔진(`PgCatalog`) 직결 | 부분 해결(수집기 주기 전송은 #27·#32) | `4b1f5fc`, `89948df` | Gemini 4 Argon | [기록](journal/2026-11-24-gemini-catalog-extensions-food-evidence-gemini-4-argon.md) |
| 50 | 상품 상세·식별자(GTIN·모델번호·MPN·옵션·이미지) 확장 수집 API(`ListingExtension v1`) 및 후보 매칭 API | 부분 해결(후속 #13 보완·수집기 전송 #32) | `4b1f5fc` | Gemini 4 Argon | [기록](journal/2026-11-24-gemini-catalog-extensions-food-evidence-gemini-4-argon.md) |
| 51 | 11번가 오프라인 수집기(`elevenst_offline`) 백엔드 전달 어댑터 및 도매꾹 `/extensions` 경로 허용 | 부분 해결(운영 수집기 연결은 #32) | `4b1f5fc`, `89948df` | Gemini 4 Argon | [기록](journal/2026-11-24-gemini-elevenst-adapter-concurrent-worker-ci-gemini-4-argon.md) |
| 52 | 분석 워커(`analysis_worker.py`) `ThreadPoolExecutor` 병렬 처리·DB 원재료 폴백 및 단위 CI `psycopg` 가드 | 해결(예외 세분화는 후속 #05) | `4b1f5fc`, `3fd6f83`, `6180147`, `103070f` | Gemini 4 Argon | [기록](journal/2026-11-24-gemini-elevenst-adapter-concurrent-worker-ci-gemini-4-argon.md) |
| 53 | `catalog-context` URL 정규화 매칭 복원 및 `/internal/process` 입력 오류(`422`) vs 의존성 장애(`503`) 분리 | 해결(호스트 식 인덱스는 후속 #02) | `3d7d6ed` | Gemini 4 Argon | [기록](journal/2026-11-24-gemini-claude-review-fixes-verification-gemini-4-argon.md) |
| 54 | `image_urls` 중복 제거·`/v2/offers/{id}/matches` 200건 절단 및 `asyncpg` 동적 조건 수정·도메인 전환 시 잔류 임베딩 작업 자동 정리 | 해결(유사 후보 세부 정렬은 후속 #03) | `3d7d6ed`, `2c65ccd` | Gemini 4 Argon | [기록](journal/2026-11-24-gemini-claude-review-fixes-verification-gemini-4-argon.md) |

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
| 2026-11-24 | Gemini 4 Argon | [Gemini 개발 기록 대응표·누락 재검증](GEMINI_COVERAGE.md) — `4b1f5fc`~`2c65ccd` 및 전체 세션 대조 |
| 2026-11-24 | Gemini 4 Argon | [#48 전체 구조·CI 실패 2건 규명·헤놀로지(i5-6600) 하드웨어/성능 분석 및 16개 문제점 진단](journal/2026-11-24-gemini-survey-hardware-diagnostics-gemini-4-argon.md) |
| 2026-11-24 | Gemini 4 Argon | [#49·#50 카탈로그 DB 식품 원재료·추천 연동 및 상품 매칭 확장 API 구현](journal/2026-11-24-gemini-catalog-extensions-food-evidence-gemini-4-argon.md) |
| 2026-11-24 | Gemini 4 Argon | [#51·#52 11번가 확장 어댑터·분석 워커 병렬화 및 단위 CI psycopg 가드](journal/2026-11-24-gemini-elevenst-adapter-concurrent-worker-ci-gemini-4-argon.md) |
| 2026-11-24 | Gemini 4 Argon | [#53·#54 Claude 코드 리뷰 5건 해결 및 4중 검증](journal/2026-11-24-gemini-claude-review-fixes-verification-gemini-4-argon.md) |
| 2026-11-25 | Claude Opus 5.5 | [maintest 점검·GPT/Gemini 일지 교차 검토](journal/2026-11-25-maintest-ci-and-ai-log-review-claude-opus-5.5.md) — #55~#57 발견, Gemini #48 진단 일부 정정 |
| 2026-11-25 | Claude Opus 5.5 | [관리자 웹 404·덮어쓰기 계층 정리, 코드 점검](journal/2026-11-25-web-fix-cleanup-claude-opus-5.5.md) — #55~#57 해결 |
| 2026-11-25 | Claude Opus 5.5 | [김호진 웹 브랜치 maintest 병합](journal/2026-11-25-web-branch-merge-claude-opus-5.5.md) — #20·#58 해결 |
| 2026-11-25 | Claude Opus 5.5 | [maintest 최신화(82a81db) 후 재점검](journal/2026-11-25-maintest-sync-recheck-claude-opus-5.5.md) — #59~#61 발견 |
| 2026-11-25 | Claude Opus 5.5 | [#59 알레르기 신고 코드 판정](journal/2026-11-25-allergen-declared-codes-claude-opus-5.5.md) — #59 해결 |
| 2026-11-25 | GPT-6 (Codex) | [GPT 점검·테스트 방법과 수행 이력](journal/2026-11-25-gpt-test-methods-gpt-6.md) — [방법 상세](GPT_METHODS.md), 도구·환경·판정 기준·고정 실행 근거 |
| 2026-11-25 | GPT-6 (Codex) | [점검·테스트 방법 기록 게시 후 재검증](journal/2026-11-25-gpt-test-methods-postpublish-verification-gpt-6.md) — 원격 본문·코드 참조·명령·CI 수치 재확인 |
| 2026-11-25 | Gemini 4 Argon | [Gemini 점검·테스트 방법과 수행 이력](journal/2026-11-25-gemini-test-methods-gemini-4-argon.md) — [방법 상세](GEMINI_METHODS.md), 도구·4중 검증·실패 수정·정정 수용 및 고정 CI 근거 |
| 2026-11-25 | Gemini 4 Argon | [Gemini 점검·테스트 방법 기록 게시 후 재검증](journal/2026-11-25-gemini-test-methods-postpublish-verification-gemini-4-argon.md) — 원격 blob 본문·고정 코드 참조 15개·링크 179개·CI Job 로그 수치 재확인 |
| 2026-11-25 | Claude Opus 5.5 | [Vision OCR 정제·파이프라인 검토](journal/2026-11-25-vision-pipeline-review-claude-opus-5.5.md) — #62~#65 발견, #21 상향 |
| 2026-11-25 | Claude Opus 5.5 | [Vision 메모리·임베딩 속도 측정](journal/2026-11-25-vision-memory-embedding-speed-claude-opus-5.5.md) — #66·#67 원인 확정 |
| 2026-11-25 | Claude Opus 5.5 | [#66 Vision 메모리·#67 임베딩 속도 수정](journal/2026-11-25-vision-memory-embedding-fix-claude-opus-5.5.md) — maintest 반영 |
| 2026-11-25 | Claude Opus 5.5 | [condition=unknown·웹 브랜치 반영](journal/2026-11-25-condition-unknown-web-sync-claude-opus-5.5.md) — #68 해결, #69~#71 발견 |
| 2026-11-25 | Claude Opus 5.5 | [#69·#70·#71 수정·재확인](journal/2026-11-25-fix-69-70-71-claude-opus-5.5.md) — 브라우저 검증 포함 |
| 2026-11-25 | Claude Opus 5.5 | [#72 상담 고객정보·수집기 병합 실연결 검증](journal/2026-11-25-support-summary-collector-merge-claude-opus-5.5.md) — maintest 23f13f9 |
