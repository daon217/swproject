# [GPT-6 (Codex)] 개발일지 · 2026-11-24 선택 공유 접속·독립 PC 전환·문서 정리 보완 (#45)

- 날짜: 2026-11-24 (누락 보완 기록일, Asia/Seoul)
- 실제 작업 시기: 2026-11-04~11-17
- 상태: 부분 해결 — 당시 작업 범위 기준, 최신 운영 완료 판정 아님
- 브랜치 / 커밋: 문서는 `devlog`; 코드 근거 [`4551d6d`](https://github.com/daon217/swproject/commit/4551d6da71a3c6d5330a2e5617066befd2892d84), [`7cdfcdd`](https://github.com/daon217/swproject/commit/7cdfcdd91a6fdbbace41bfcf8ad300705dc9a897), [`56e0be9`](https://github.com/daon217/swproject/commit/56e0be93d9f0785535e67d31b084135e6f1525ab), [`762780e`](https://github.com/daon217/swproject/commit/762780ee2ebc4bb86ed4c8f704752744b00666ba), [`e167a8a`](https://github.com/daon217/swproject/commit/e167a8a160fa0fc6ccb99644a016823405cd0b99), [`74d0e3c`](https://github.com/daon217/swproject/commit/74d0e3c4a50879b7029a7e4f88a3a30a5d4ef480), [`ba68281`](https://github.com/daon217/swproject/commit/ba68281e7701c2c79b4735cccdbc145652e3564b)
- 관련 파일: [infra/team/gateway/sshd_config:11](https://github.com/daon217/swproject/blob/56e0be93d9f0785535e67d31b084135e6f1525ab/infra/team/gateway/sshd_config#L11); [tools/team_dev.py:38](https://github.com/daon217/swproject/blob/762780ee2ebc4bb86ed4c8f704752744b00666ba/tools/team_dev.py#L38); [tools/team_dev.py:116](https://github.com/daon217/swproject/blob/762780ee2ebc4bb86ed4c8f704752744b00666ba/tools/team_dev.py#L116); [docs/LOCAL_DEVELOPMENT.md:1](https://github.com/daon217/swproject/blob/74d0e3c4a50879b7029a7e4f88a3a30a5d4ef480/docs/LOCAL_DEVELOPMENT.md#L1); [docs/reviews/BACKEND_EFFICIENCY_2026-11-17.md:1](https://github.com/daon217/swproject/blob/ba68281e7701c2c79b4735cccdbc145652e3564b/docs/reviews/BACKEND_EFFICIENCY_2026-11-17.md#L1)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 당시 상세 모델 버전은 미확인.

> 사용자 정정에 따라 실제 코드 개발이 시작된 2026-11-04 이후만 기록한다. 그 이전 설계·ERD·발표자료 제작은 포함하지 않는다. 선택지 표는 회고 비교이며 당시 모두 실험했다는 뜻이 아니다. 기존 일지를 덮어쓰지 않고 누락을 보완한다.

## 문제점
기존 #34에는 최종 로컬 개발환경 위주로 적혀 있어 초기 저장소 협업 규칙, 선택적 공용 API 연결 도구, 독립 PC 방식으로 바뀐 과정과 GitHub 문서 정리가 충분히 기록되지 않았다.

## 원인
GitHub에서 코드를 내려받는 것과 호스트 PC의 DB 데이터를 공유하는 것은 별개다. 공유 개발에는 네트워크 경로·키 등록·API 포워딩이 필요했고, 독립 개발로 전환한 뒤에도 안내가 섞이면 VPN이 필수인 것으로 오해할 수 있었다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 공용 API만 사용 | 같은 데이터를 조회 | 호스트 전원·네트워크에 종속 | 선택 기능으로 유지 |
| 각 PC 독립 core 기본 + 공유 경로 별도 | 독립 개발 가능, 운영 방식 구분 | PC 간 DB 자동 동기화 없음 | 기본 방식으로 채택 |

## 해결 (적용 내용)
- 초기 저장소·담당 폴더·파트 브랜치·PR 협업 안내와 CI를 구성했다. 브랜치 보호를 문서에 적은 사실을 GitHub 설정 적용 완료로 간주하지 않는다.
- 선택적 사설망/SSH API 접속 도구를 추가했다. `PermitOpen api:8000`과 로컬 포워딩만 허용하며, 셸·임의 명령·DB 포워딩을 제한했다. 공개키 등록/회수·서버 지문·연결 점검을 제공했다.
- `team_dev.py`의 doctor/connect/check/backup과 DB별 dump·SHA-256 manifest·임시 복원 검증 경로를 마련했다. 11월 18일 자동 백업/monitor/restore-check 확장은 별도 #38이다.
- `e167a8a`에서 VPN 없이 각 PC가 독립 DB/API로 개발하는 절차를 추가했고 `74d0e3c`에서 문서 목록·온보딩·core/full 경계를 정리했다.
- `ba68281`에서 백엔드 안내를 `docs/backend`, 선택 공용 서버 안내를 `docs/optional`, 점검 근거를 `docs/reviews`로 분류하고 오래된 미구현 설명·링크·불필요한 import를 정리했다.
- 실행 소스·잠금 파일·기존 명령·적용된 마이그레이션·팀원 시작 코드는 보존했다. 브랜치나 커밋 이력을 삭제한 정리로 기록하지 않는다.

## 왜 그렇게 해결했는지
팀원의 네트워크와 호스트 전원에 덜 의존하는 독립 개발을 기본으로 삼되, 같은 가상 데이터를 보며 연동할 때 쓸 공유 기능을 남겼다. 문서 분류는 기능 삭제 없이 기본 경로와 선택 경로를 명확하게 하기 위한 작업이다.

## 검증
- [PR #3](https://github.com/daon217/swproject/pull/3)과 고정 점검 문서: 당시 원격 파일 177개의 blob 해시와 로컬 내용을 대조했고 상대 링크 93개를 검사한 기록이 있다. 현재 저장소 파일 수가 177개라는 뜻은 아니다.
- [접속 CI](https://github.com/daon217/swproject/actions/runs/42165837283)의 성공 상태를 재확인했다. 해당 시기의 검사 범위는 API 터널, 미등록 SSH 키 차단, DB 포워딩 차단, dump의 임시 복원이다.
- 실행 도구 진입점은 `python tools/team_dev.py doctor --role client`, `python tools/team_dev.py check`; 독립 개발은 `python tools/workspace.py up --scope core`다. 사용 모드에 맞는 사전 설정이 필요하다.
- 실제 다른 집의 팀원 접속 성공·Tailscale 계정 초대·GitHub 보호 설정을 도구 파일 존재만으로 완료 처리하지 않았다.

이번 보완에서는 과거 서비스 테스트를 재실행하지 않았다. 고정 커밋의 코드·기록·참조를 대조했으며 아래 한계를 포함한다.

## 남은 과제 / 주의
- 공용 상시 서버, 종료 시 자동 업로드, PC 간 DB 동기화는 구현하지 않았다.
- 과거 문서에 적힌 서비스 플랜/인원 제한은 현재 정보로 재검증하지 않았으므로 이 기록에 재사용하지 않는다.
- GitHub는 코드·마이그레이션 공유이며 DB 내용 공유가 아니다. 실제 원본 데이터와 비밀 설정은 저장소에 복사하지 않는다.
