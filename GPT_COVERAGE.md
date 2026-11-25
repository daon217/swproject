# GPT 개발 기록 대응표

- 기준: 2026-11-24 누락 재검토. 사용자의 정정에 따라 **실제 코드 개발이 시작된 2026-11-04 이후**만 포함한다.
- 작성: GPT-6 (Codex). 과거 GPT 상세 모델 버전은 미확인.
- 최초 커밋: [4551d6d](https://github.com/daon217/swproject/commit/4551d6d). 날짜는 한국 시간 기준이며 실행 보고와 소스 커밋의 시각을 혼동하지 않는다.
- 범위: 구현·수정·통합·검증 및 그 작업의 사용/운영 문서. 개발 시작 이전 설계·ERD·발표자료는 제외한다.
- 이 표는 핵심 커밋/작업의 대응표이며 저장소 모든 커밋이 GPT 작업이라는 뜻이 아니다. 개별 일지의 검증 한계와 귀속 근거를 함께 읽는다.

## 작업과 기록 대응

| 작업 시기 | 확인한 개발 작업 | 대표 커밋 | 개발일지 |
| --- | --- | --- | --- |
| 11-04 | 저장소·팀 폴더·브랜치 협업 규칙·CI | [`4551d6d`](https://github.com/daon217/swproject/commit/4551d6da71a3c6d5330a2e5617066befd2892d84), [`7cdfcdd`](https://github.com/daon217/swproject/commit/7cdfcdd91a6fdbbace41bfcf8ad300705dc9a897), [`9bcff21`](https://github.com/daon217/swproject/commit/9bcff218c2be0daf43a3d9843e7bac61bb37b69b), [`02135c6`](https://github.com/daon217/swproject/commit/02135c6e80e96b7ebb2fe0d5c64843bd91ec4866), [`3eaffed`](https://github.com/daon217/swproject/commit/3eaffeda86ad2d23191c3c72b03f175985734a52) | [기록](journal/2026-11-24-gpt-foundation-db-ci-gpt-6.md) |
| 11-05 | 독립 DB 3개·pgvector·역할 권한 | [`3102a78`](https://github.com/daon217/swproject/commit/3102a781dd4a0fa3e06e2c1e0c1587a90605d77d) | [기록](journal/2026-11-24-gpt-foundation-db-ci-gpt-6.md) |
| 11-05 | 수집·벡터 저장 도우미와 최초 쓰기/하위 유형 수정 | [`cd72f41`](https://github.com/daon217/swproject/commit/cd72f4113d7a3064b1de243d6d94ce0f997e5e8c), [`22fa5bf`](https://github.com/daon217/swproject/commit/22fa5bfc84b255315c7be08c87b5342b2a8a9f0e) | [기록](journal/2026-11-24-gpt-catalog-ingestion-gpt-6.md) |
| 11-05~06 | 선택 VPN/SSH·온보딩·수동 백업·독립 PC 전환 | [`56e0be9`](https://github.com/daon217/swproject/commit/56e0be93d9f0785535e67d31b084135e6f1525ab), [`762780e`](https://github.com/daon217/swproject/commit/762780ee2ebc4bb86ed4c8f704752744b00666ba), [`e167a8a`](https://github.com/daon217/swproject/commit/e167a8a160fa0fc6ccb99644a016823405cd0b99), [`74d0e3c`](https://github.com/daon217/swproject/commit/74d0e3c4a50879b7029a7e4f88a3a30a5d4ef480) | [기록](journal/2026-11-24-gpt-onboarding-docs-supplement-gpt-6.md) |
| 11-05 | 전체 개발 서비스·CPU 환경·전체 프로젝트 CI/Node LTS | [`29da828`](https://github.com/daon217/swproject/commit/29da82863f9c8b6e7f2397bb1426cd60927a46f8), [`73e756e`](https://github.com/daon217/swproject/commit/73e756eaaac83ea752dc7cd32e53a442e5c46021) | [기록](journal/2026-11-24-gpt-foundation-db-ci-gpt-6.md) |
| 11-06 | 의존성 잠금·본문 크기·CORS·UID/볼륨·기본 core·감사 | [`0c2bff5`](https://github.com/daon217/swproject/commit/0c2bff56d04a085e8e92e1889afcfd4f5fc63105) | [기록](journal/2026-11-24-gpt-runtime-hardening-supplement-gpt-6.md) |
| 11-16 | 도착 시 갱신·실제 300건 import·마이그레이션 유지 | [`6058d22`](https://github.com/daon217/swproject/commit/6058d22f34c30f98c771fab4381192b79d5578f0) | [기록](journal/2026-11-24-gpt-import-retention-supplement-gpt-6.md) |
| 11-16 | 단일 필드 변형 32개 검사 | [`0e6690b`](https://github.com/daon217/swproject/commit/0e6690bec28d440688519f8f39f3c4d0fa24af64) | [기록](journal/2026-11-24-gpt-catalog-ingestion-gpt-6.md) |
| 11-17 | 회원/모의 결제·문의·제휴·관리자 권한·탈퇴·분석 원장 | [`8fcacfa`](https://github.com/daon217/swproject/commit/8fcacfa345fe4f9d02c6cc776f424370cd69226d), [`6096b35`](https://github.com/daon217/swproject/commit/6096b3593680021dd6eee00121a94e4c7d92802c), [`2c177dd`](https://github.com/daon217/swproject/commit/2c177dd173adfac72fd46147aebb170d40916666) | [기록](journal/2026-11-24-gpt-backend-business-apis-gpt-6.md) |
| 11-17 | 보존기간·정리·삭제 식별 기록·과거 재생성 방지 | [`8fcacfa`](https://github.com/daon217/swproject/commit/8fcacfa345fe4f9d02c6cc776f424370cd69226d) | [기록](journal/2026-11-24-gpt-import-retention-supplement-gpt-6.md) |
| 11-17 | 백엔드 문서 분류·기존 파일 대조·링크 정리 | [`ba68281`](https://github.com/daon217/swproject/commit/ba68281e7701c2c79b4735cccdbc145652e3564b) | [기록](journal/2026-11-24-gpt-onboarding-docs-supplement-gpt-6.md) |
| 11-17 | N+1·인덱스·측정 오류 수정·1천/1만 건 부하 검사 | [`ba68281`](https://github.com/daon217/swproject/commit/ba68281e7701c2c79b4735cccdbc145652e3564b), [`085e7f6`](https://github.com/daon217/swproject/commit/085e7f618608d7370f82fd0da62d8ca88afe24e3), [`248d4c5`](https://github.com/daon217/swproject/commit/248d4c51fcc0fd6302a9ea423accf62855c85141) | [기록](journal/2026-11-24-gpt-performance-efficiency-gpt-6.md) |
| 11-18 | 자동 백업·설정 점검·격리 복원·manifest 오류 처리 | [`7805d8e`](https://github.com/daon217/swproject/commit/7805d8eb38a75c07fd70dd350622c8b250c9ed68), [`39b081f`](https://github.com/daon217/swproject/commit/39b081fbdada7c72c8c3882af699f5fe73c428a7) | [기록](journal/2026-11-24-gpt-backup-operations-gpt-6.md) |
| 11-18 | 실제 UI/API/DB·pending 결제·접근성·Windows UTF-8 | [`1339fee`](https://github.com/daon217/swproject/commit/1339fee7a3d2f30dc5a306de48b9f00061438593), [`77e8091`](https://github.com/daon217/swproject/commit/77e8091ac698b3fddf0fdb014c2c364905aaa0d6), [`c5fcca9`](https://github.com/daon217/swproject/commit/c5fcca9e123acfcacb6e76e0419cb8a434a39395), [`41c1d1c`](https://github.com/daon217/swproject/commit/41c1d1c5973d31914b75841139f787a780414e2e) | [기록](journal/2026-11-24-gpt-ui-backend-integration-gpt-6.md) |
| 11-18 | 가입 안내·계정별 페이지/탭·캐시·중복 저장 억제 | [`2158683`](https://github.com/daon217/swproject/commit/21586831f1554e6327b6e03fb0288a4a6ae9efc2), [`194794a`](https://github.com/daon217/swproject/commit/194794a6aee69e05372a0ef60605d02aee3aa75d), [`7e25f48`](https://github.com/daon217/swproject/commit/7e25f4843805430364f6b4ec493a01f8c5ec8014), [`86f2aeb`](https://github.com/daon217/swproject/commit/86f2aeb60df041401a3d83b347438f9f00df8ea8), [`f075797`](https://github.com/daon217/swproject/commit/f0757973cccb908d4654da5defda7a054495e2be) | [기록](journal/2026-11-24-gpt-account-isolation-validation-gpt-6.md) |
| 11-18 | 날짜 입력 순환 참조 제거 | [`d3ccb8a`](https://github.com/daon217/swproject/commit/d3ccb8a43961a7a6b13fc9bf8b7fff13caeec88b) | [기록](journal/2026-11-24-gpt-mobile-import-cycle-gpt-6.md) |
| 11-19 | 팀 엔진 통합·관리 CRUD·수집 연결·CI import 보완 | [`a9da43b`](https://github.com/daon217/swproject/commit/a9da43b7727c515344c94e552eacd27969396b5d), [`4969fa3`](https://github.com/daon217/swproject/commit/4969fa38ee17ff306c92f8eaa4e9a61f652d009a), [`46b781a`](https://github.com/daon217/swproject/commit/46b781aaf789e12ef544e9b00dee339768189e21), [`a19c431`](https://github.com/daon217/swproject/commit/a19c4312b0e18b78c6b9260cbac299d223558eba) | [기록](journal/2026-11-24-gpt-team-runtime-integration-gpt-6.md) |
| 11-22 | main 읽기 전용 상태·추천 임시 경로·UI 회귀 점검 | [`e7f7007`](https://github.com/daon217/swproject/commit/e7f7007da36f03914df2ae2496b853d77d3633f0) | [기록](journal/2026-11-24-gpt-readonly-review-supplement-gpt-6.md) |
| 11-23 | maintest outbox/임베딩 작업자·모델 계약·DB 검색 | [`2d444b0`](https://github.com/daon217/swproject/commit/2d444b0ee4e1c181701c8491c77800b9c30f2e88) | [기록](journal/2026-11-24-gpt-persistent-embedding-pipeline-gpt-6.md) |
| 11-24 | GPT 회고 기록과 누락 재검토 | [`514ac7b`](https://github.com/daon217/swproject/commit/514ac7b3c4e01324b9a686b49819976353b59325) | [기록](journal/2026-11-24-gpt-readonly-review-supplement-gpt-6.md) |

## 누락 보완·정정 사항

1. 기존 #34의 “의존성 정리”를 #44에서 실제 요청/권한/로그/검증 항목으로 구체화했다.
2. #34의 최종 로컬 개발 구조에 가려진 초기 공유 접속·온보딩·문서 정리를 #45에 추가했다.
3. #35의 공개 CI 원본 데이터 skip과 별개로, **로컬 실제 300건 적재·재전송 검증은 수행된 기록이 있다.** 파일 importer와 정리 정책을 #46에 보완했다.
4. 구현 커밋이 없었던 11월 22일 읽기 전용 검토를 #47에 추가했다.
5. 이번 확인에서 찾은 10월 설계/정규화/발표자료는 사용자 정정에 따라 추가하지 않았다. 이전 회고도 11월 코드 작업을 중심으로 작성돼 있어 삭제할 10월 일지는 없었다.

## 귀속·검증 유의사항

- GPT 대화 보고, PR, 원격 코드와 로컬 Codex 체크포인트 일치를 함께 근거로 삼는다. 상세 모델 버전은 소급 추정하지 않는다.
- 팀원 엔진/프런트엔드는 GPT의 통합 작업과 구분한다. Claude 공동 작성 후속 커밋을 합산하지 않는다.
- `4b1f5fc`~`2c65ccd`, `855192d`, `52c486e` 등 원 작업 AI를 확인하지 못한 구간은 계속 제외한다. 코드 존재를 부정하는 뜻이 아니다.
- 과거 완료 보고와 현재 코드 상태는 다르다. 이 표로 OPEN_ISSUES를 종료하지 않으며, 테스트 수치를 서로 다른 실행 사이에 누적 합산하지 않는다.
- 모델·제품·가격·보안 상태에 대한 과거 자료는 당시 근거다. 이번 작업은 문서 감사이며 서비스 전체 테스트나 최신 취약점 진단을 새로 수행한 것은 아니다.

## 정정 기록 (2026-11-25 · Claude Opus 5.5 교차 검토)

원 일지는 보존하고 정정은 여기와 [교차 검토 일지](journal/2026-11-25-maintest-ci-and-ai-log-review-claude-opus-5.5.md)에 남긴다.

| 대상 | 정정 |
| --- | --- |
| #42 팀 통합(`a9da43b`) | 관리자 화면 연결 과정에서 `apps/web/shared/backend.js` 덮어쓰기 계층을 추가했다는 사실이 기록에 없었다. 이 파일이 마지막에 로드되어 웹팀의 대시보드·통계·수집·제휴·상담 구현을 가렸고, 김호진 웹 병합 후에도 남는 구조였다(#56). `e37338e`에서 제거했다. |
| #42 검증 | PR #13의 브라우저 관리 CRUD 통과는 당시 기록이다. 11-19 김호진 병합(`c7d8cdf`) 이후 main에서 계속 실패했고 `e37338e`에서 원인(#55·#57)을 해결했다. |
| 귀속 유의사항 | "`4b1f5fc`~`2c65ccd`는 원 작업 AI 미확인으로 제외" → 이후 [GEMINI_COVERAGE.md](GEMINI_COVERAGE.md)에서 Gemini 4 Argon 작업(#48~#54)으로 확인되었다. `855192d`, `52c486e`(관리자 가입 백엔드)는 여전히 원 작업 AI 미확인이며, maintest 반영은 Claude #08(`e18c36c`)이다. |
