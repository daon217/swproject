# 팀 문서 안내

처음 참여하는 팀원은 **[실행 방법](../실행방법.md)**으로 전체 기능을 띄운 뒤, 필요한 내용을 아래에서 찾으세요. 기본은 각자 PC의 독립 실행입니다.

## 공통 개발환경

| 목적 | 기준 문서 |
| --- | --- |
| 전체 기능 실행(분석·추천·수집·관리자)·Claude 키 | [TEAM_INTEGRATION](TEAM_INTEGRATION.md) |
| 설치·브랜치 반영·매일 실행·종료·문제 해결 | [LOCAL_DEVELOPMENT](LOCAL_DEVELOPMENT.md) |
| 담당 브랜치·PR·기존 코드 반입 | [CONTRIBUTING](../CONTRIBUTING.md) |
| 전체 Docker·개발 큐·선택 AI 이미지 | [WORKSPACE](WORKSPACE.md) |
| 자동 검사·빌드 설정 | [CI](../.ci/README.md) |
| main 브랜치 보호 | [저장소 소유자 설정](../.github/ADMIN_SETUP.md) |

## 백엔드 업무

| 목적 | 사용·운영 안내 | API 계약 |
| --- | --- | --- |
| 상품 수신·중복 제거·최신화 | [상품 데이터](backend/CATALOG_INGESTION.md) | [카탈로그 v2](../contracts/catalog-v2.md) |
| 회원·모의 구독·정리 정책·성능 명령 | [DB 운영](backend/DB_OPERATIONS.md) | [회원·구독 v2](../contracts/member-billing-v2.md) |
| 고객센터·제휴·관리자·탈퇴·분석 작업 | [백엔드 업무](backend/INDEPENDENT_BACKEND.md) | [업무 API v2](../contracts/independent-backend-v2.md) |
| DB 단독 초기화·권한·벡터 | [DB 도구](../infra/db/README.md) | [API 모듈](../services/api/README.md) |
| 파일 정리·효율성 점검 근거 | [2026-11-17 점검](reviews/BACKEND_EFFICIENCY_2026-11-17.md) | — |
| 자동 백업·복원 검사·설정·장애 진단 | [운영 도구](backend/OPERATIONS.md) | — |

## 선택적인 공용 서버

자기 PC에서 개발할 때 아래 설정은 필요하지 않습니다.

- [공용 호스트·VPN·SSH 사용](optional/TEAM_DEVELOPMENT.md)
- [호스트 도구 상세](../infra/team/README.md)

## 담당 코드

[웹](../apps/web/README.md) · [확장](../apps/extension/README.md) · [모바일](../apps/mobile/README.md) · [관리자](../apps/admin/README.md) · [OCR](../services/vision/README.md) · [추천](../services/recommendation/README.md) · [수집](../services/collector/README.md)

## 문서 관리 기준

- 공통 실행은 LOCAL_DEVELOPMENT, full 구성은 WORKSPACE, 협업은 CONTRIBUTING을 기준으로 합니다.
- 업무 사용법은 docs/backend, 요청·응답은 contracts, 시점별 검증 결과는 docs/reviews에 기록합니다.
- 같은 설명을 복사하지 않고 기준 문서로 연결합니다. 코드 변경 시 현재 구현·임시 정책·미연결 부분을 함께 갱신합니다.
- 실행 명령은 저장소 루트 기준입니다. 실제 비밀번호·원본 수집 데이터·DB 백업은 Git에 올리지 않습니다.
- 통합 기준 브랜치는 `maintest`입니다. 진행 일지·미해결 문제는 `devlog` 브랜치에 있습니다.
