# [GPT-6 (Codex)] 개발일지 · 2026-11-24 초기 저장소·3개 DB·로컬 개발환경 (#34)

- 날짜: 2026-11-24 (회고 기록일, Asia/Seoul)
- 작업 시기: 2026-11-04~11-06; DB 선택 설명은 후속 대화에서 보완
- 상태: 부분 해결 — 아래에 명시한 당시 범위 기준
- 브랜치 / 커밋: 기록은 `devlog`; 코드 근거 [`3eaffed`](https://github.com/daon217/swproject/commit/3eaffeda86ad2d23191c3c72b03f175985734a52) / [`3102a78`](https://github.com/daon217/swproject/commit/3102a781dd4a0fa3e06e2c1e0c1587a90605d77d) / [`0c2bff5`](https://github.com/daon217/swproject/commit/0c2bff56d04a085e8e92e1889afcfd4f5fc63105)
- 관련 파일: [infra/db/init/10-databases.sh:1](https://github.com/daon217/swproject/blob/0c2bff56d04a085e8e92e1889afcfd4f5fc63105/infra/db/init/10-databases.sh#L1); [.github/scripts/ci.py:13](https://github.com/daon217/swproject/blob/0c2bff56d04a085e8e92e1889afcfd4f5fc63105/.github/scripts/ci.py#L13); [tools/workspace.py:18](https://github.com/daon217/swproject/blob/0c2bff56d04a085e8e92e1889afcfd4f5fc63105/tools/workspace.py#L18)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 과거 세션의 상세 모델 버전은 미확인.

> 과거 작업을 커밋·PR·대화 기록으로 복원한 일지다. 선택지 표는 회고 시점의 설계 비교이며, 모든 대안을 당시 구현·실험했다는 뜻이 아니다. 검증 수치는 해당 커밋의 기록이며 최신 코드 전체의 재검증 결과가 아니다. [기록 범위와 근거](2026-11-24-gpt-retrospective-scope-gpt-6.md)를 함께 읽는다.

## 문제점
팀원별 코드 위치·실행 방법이 다르고 회원/상품/고객지원 데이터를 구분할 DB와 반복 가능한 빌드 검증이 필요했다.

## 원인
초기 저장소에는 서비스별 실행·검증 계약과 DB 초기화가 없었다. 위 CI 파일은 프로젝트 목록으로 실행 대상을 결정하고, DB 초기화 파일은 독립 DB·역할을 만든다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| PostgreSQL 한 서버 안에 독립 DB 3개 + Compose | 기존 관계형 요구와 pgvector, 로컬 재현에 맞음 | DB 간 FK·단일 트랜잭션 불가, 운영 책임 필요 | 채택 |
| 하나의 DB에 스키마 분리 | DB 안에서 조인·참조 무결성 관리 용이 | 사용자가 정한 독립 DB 경계 변경 | 미채택 |
| Firebase 계열 관리형 DB로 전환 | 인프라 관리 부담 감소 가능 | 현행 SQL·권한·마이그레이션·벡터 경로를 다시 설계해야 함 | 후속 논의만 |

## 해결 (적용 내용)
- 팀 디렉터리와 빌드 매트릭스, 프로젝트별 CI 검사 도구를 추가했다. 초기 비어 있는 8개 영역은 명시적으로 비활성화했고, 코드가 생긴 프로젝트의 검증 누락은 탐지하도록 했다.
- PostgreSQL 17 + pgvector 0.8.7 컨테이너 안에 member/catalog/support DB를 분리하고 owner/app 역할과 접근 범위를 나눴다. 벡터 확장은 catalog에만 적용했다.
- 로컬 설정 생성, 루프백 기본 바인딩, 볼륨 보존, 팀원 온보딩·독립 PC 실행 도구를 구성했다. 이후 전체 개발환경의 서비스 및 Node LTS 의존성을 정리했다.
- Firebase 비교 대화에서는 현재 관계형 구조·기존 구현·로컬 운영 조건이 PostgreSQL 선택에 맞는다고 설명했다. 이 논의로 DB를 교체하거나 Firebase 실험 코드를 추가하지는 않았다.

## 왜 그렇게 해결했는지
회원·상품·문의의 데이터 경계와 사용자의 3개 DB 유지 요구를 반영했다. 독립 DB 간 관계는 애플리케이션에서 다뤄야 한다. Firebase를 쓰지 않은 이유를 “벡터 검색 자체가 불가능해서”라고 단정하지 않는다. 관리형 서비스와 현재 로컬 구조는 운영 책임과 비용 산정 방식이 달라 별도 평가가 필요하다. 또한 문서에 언급된 Spring 스택과 이 기록의 실제 Python 서비스 구현을 동일시하지 않는다.

## 검증
- [PR #1](https://github.com/daon217/swproject/pull/1): CI 도구 단위 테스트 7개 통과 기록, 빈 프로젝트 계획 및 YAML 확인. 당시 비어 있던 앱을 실제 빌드했다고 기록하지 않는다.
- [PR #2](https://github.com/daon217/swproject/pull/2): DB 생성·확장·역할별 접근 검증. [Actions 실행 41867281673](https://github.com/daon217/swproject/actions/runs/41867281673)의 성공 상태를 회고 작성 시 다시 확인했다.
- 당시 실행 진입점: `python infra/db/db.py init`, `python infra/db/db.py up`, `python tools/workspace.py init`. 설정 생성만으로 모든 서비스 기능이 완성되는 것은 아니다.

이번 일지 작성에서는 코드 테스트를 재실행하지 않았다. 커밋별 파일·행 존재와 기록 근거를 대조했다.

## 남은 과제 / 주의
- DB 3개 간 외래키·원자적 갱신은 제공하지 않는다. 백업도 DB별 시점 차이가 있다.
- 로컬 PC 종료 시 서비스가 중단된다. 상시 운영·외부 공개·장애 복구·실사용 비용 검증은 별도다.
- Firebase/Firestore 전환의 성능·비용 비교 실험은 미실시. “fire db”의 정확한 제품 지칭도 확정하지 않았으므로 Firestore로 단정한 구현 기록을 만들지 않는다.
