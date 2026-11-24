# [GPT-6 (Codex)] 개발일지 · 2026-11-24 설정 점검·자동 백업·복원 검증 (#38)

- 날짜: 2026-11-24 (회고 기록일, Asia/Seoul)
- 작업 시기: 2026-11-18
- 상태: 부분 해결 — 아래에 명시한 당시 범위 기준
- 브랜치 / 커밋: 기록은 `devlog`; 코드 근거 [`7805d8e`](https://github.com/daon217/swproject/commit/7805d8eb38a75c07fd70dd350622c8b250c9ed68) / [`39b081f`](https://github.com/daon217/swproject/commit/39b081fbdada7c72c8c3882af699f5fe73c428a7)
- 관련 파일: [tools/operations.py:88](https://github.com/daon217/swproject/blob/39b081fbdada7c72c8c3882af699f5fe73c428a7/tools/operations.py#L88); [tools/operations.py:102](https://github.com/daon217/swproject/blob/39b081fbdada7c72c8c3882af699f5fe73c428a7/tools/operations.py#L102); [tools/operations.py:137](https://github.com/daon217/swproject/blob/39b081fbdada7c72c8c3882af699f5fe73c428a7/tools/operations.py#L137); [tools/operations.py:199](https://github.com/daon217/swproject/blob/39b081fbdada7c72c8c3882af699f5fe73c428a7/tools/operations.py#L199)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 과거 세션의 상세 모델 버전은 미확인.

> 과거 작업을 커밋·PR·대화 기록으로 복원한 일지다. 선택지 표는 회고 시점의 설계 비교이며, 모든 대안을 당시 구현·실험했다는 뜻이 아니다. 검증 수치는 해당 커밋의 기록이며 최신 코드 전체의 재검증 결과가 아니다. [기록 범위와 근거](2026-11-24-gpt-retrospective-scope-gpt-6.md)를 함께 읽는다.

## 문제점
팀원이 로컬 DB를 사용하면서 설정 오류·백업 누락·손상된 백업을 알아채기 어려웠다.

## 원인
파일이 존재한다는 사실만으로 백업 완료·무결성·복원 가능성을 판단할 수 없었다. 동시에 실행되는 백업과 중간 실패도 구분해야 했다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 덤프 파일 생성만 확인 | 구현 간단 | 부분 백업·손상·복원 실패를 놓침 | 미채택 |
| 잠금 + manifest 검증 + 격리 복원 | 완료·무결성·복원 경로 확인 | 추가 시간·디스크 사용 | 채택 |

## 해결 (적용 내용)
- `validate`, `monitor`, `backup-auto`, `verify-backup`, `restore-check` 명령을 추가했다.
- 기본 24시간 주기의 백업 판단, 프로세스 잠금, DB 3개 덤프 완료 후 manifest 게시, 파일명·크기·SHA-256 확인을 구성했다.
- `restore-check`는 임시 DB 3개에 복원하고 정리한다. 기존 DB를 덮어쓰는 복구 명령으로 만들지 않았다.
- 잘못된 manifest를 안전하게 실패 처리하도록 `39b081f`에서 보완했다.

## 왜 그렇게 해결했는지
운영자가 필요한 것은 “백업 명령이 돌았다”보다 “완성된 파일이고 실제로 읽어 복원할 수 있다”는 근거다. 원래 DB를 건드리지 않는 복원 검증으로 반복 점검 부담을 낮췄다.

## 검증
- [PR #3](https://github.com/daon217/swproject/pull/3): Windows/Linux 각각 도구 단위 테스트 17개 통과, 실제 Docker 백업·임시 복원 확인 기록. [Actions 실행 44221228764](https://github.com/daon217/swproject/actions/runs/44221228764) 성공 상태를 다시 확인했다.
- 도구 단위 검증 명령: `python -m unittest discover -s tools -p 'test_*.py' -q`.
- 운영 점검 진입점: `python tools/operations.py validate`, `python tools/operations.py monitor`. 복원 검증은 `python tools/operations.py restore-check --directory <백업 폴더>`로 지정한다.

이번 일지 작성에서는 코드 테스트를 재실행하지 않았다. 커밋별 파일·행 존재와 기록 근거를 대조했다.

## 남은 과제 / 주의
- 반복 실행은 PC·Docker·프로세스가 살아 있을 때만 동작한다. OS 시작 시 자동 실행, 외부 저장소 복제, 암호화, 보존기간별 자동 삭제까지 구현한 것은 아니다.
- DB 3개의 덤프가 하나의 전역 트랜잭션 스냅샷은 아니다. 이미지·환경설정·인증서 백업은 별도다.
- 실제 재해 상황에서의 전체 시스템 복구 시간은 미측정이다.
