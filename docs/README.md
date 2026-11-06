# 팀 문서 안내

처음 참여하는 팀원은 **[개발환경 사용 안내](LOCAL_DEVELOPMENT.md)**부터 읽으세요. 현재 기본은 각자의 PC에서 독립 실행하는 방식입니다.

## 목적별 문서

| 목적 | 문서 | 읽는 대상 |
| --- | --- | --- |
| 설치·브랜치 반영·매일 실행·종료·문제 해결 | [LOCAL_DEVELOPMENT](LOCAL_DEVELOPMENT.md) | 모든 팀원 |
| 담당 브랜치·PR·기존 코드 반입 | [CONTRIBUTING](../CONTRIBUTING.md) | 모든 팀원 |
| 전체 Docker 환경·작업 큐·선택 AI 이미지 | [WORKSPACE](WORKSPACE.md) | 연동·분석 담당 |
| API·이벤트 계약과 가상 샘플 | [contracts](../contracts/README.md) | API 연동 담당 |
| 자동 검사·빌드 설정 | [CI](../.ci/README.md) | 모든 팀원 |
| DB 단독 초기화·검증 | [DB](../infra/db/README.md) | DB 담당 |
| 카탈로그 API·적재·벡터 모듈 | [API](../services/api/README.md) | 백엔드·수집·추천 담당 |
| 선택적인 공용 서버·VPN·SSH 접속 | [TEAM_DEVELOPMENT](TEAM_DEVELOPMENT.md) | 공용 서버를 사용할 때만 |
| 공용 서버 접근 도구 상세 | [infra/team](../infra/team/README.md) | 공용 서버 호스트 |
| main 브랜치 보호 | [관리자 설정](../.github/ADMIN_SETUP.md) | 저장소 소유자 |

## 담당 코드의 실행 안내

[웹](../apps/web/README.md) · [확장](../apps/extension/README.md) · [모바일](../apps/mobile/README.md) · [관리자](../apps/admin/README.md) · [OCR](../services/vision/README.md) · [추천](../services/recommendation/README.md) · [수집](../services/collector/README.md)

## 문서를 수정할 때

- 공통 설치·실행 명령은 LOCAL_DEVELOPMENT, full 구성은 WORKSPACE, 협업 규칙은 CONTRIBUTING을 기준으로 수정합니다.
- 담당 기능 실행 방법은 해당 폴더 README에 작성하고 여기에서 연결합니다. 같은 설명을 여러 문서에 복제하지 않습니다.
- 기능을 추가하면 현재 상태·환경변수 예시·API 계약·CI 명령도 함께 갱신합니다.
- 스크린샷 대신 복사할 수 있는 명령어를 적고, 가상 데이터와 실제 기능의 검증 범위를 구분합니다.
- 공통 코드가 main에 반영됐는지는 [PR #3](https://github.com/daon217/swproject/pull/3)에서 확인합니다.
