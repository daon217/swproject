# [GPT-6 (Codex)] 개발일지 · 2026-11-24 화면과 실제 백엔드·DB 연결 (#39)

- 날짜: 2026-11-24 (회고 기록일, Asia/Seoul)
- 작업 시기: 2026-11-18 (PR #5)
- 상태: 부분 해결 — 아래에 명시한 당시 범위 기준
- 브랜치 / 커밋: 기록은 `devlog`; 코드 근거 [`1339fee`](https://github.com/daon217/swproject/commit/1339fee7a3d2f30dc5a306de48b9f00061438593) / [`77e8091`](https://github.com/daon217/swproject/commit/77e8091ac698b3fddf0fdb014c2c364905aaa0d6) / [`41c1d1c`](https://github.com/daon217/swproject/commit/41c1d1c5973d31914b75841139f787a780414e2e)
- 관련 파일: [infra/ui/compose.yaml:1](https://github.com/daon217/swproject/blob/41c1d1c5973d31914b75841139f787a780414e2e/infra/ui/compose.yaml#L1); [tests/ui/integration.spec.js:1](https://github.com/daon217/swproject/blob/41c1d1c5973d31914b75841139f787a780414e2e/tests/ui/integration.spec.js#L1)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 과거 세션의 상세 모델 버전은 미확인.

> 과거 작업을 커밋·PR·대화 기록으로 복원한 일지다. 선택지 표는 회고 시점의 설계 비교이며, 모든 대안을 당시 구현·실험했다는 뜻이 아니다. 검증 수치는 해당 커밋의 기록이며 최신 코드 전체의 재검증 결과가 아니다. [기록 범위와 근거](2026-11-24-gpt-retrospective-scope-gpt-6.md)를 함께 읽는다.

## 문제점
팀원이 만든 화면을 실제 API/DB와 연결해 가입·로그인·문의·구독 상태와 분석 요청 동작을 확인할 통합 실행 환경이 필요했다.

## 원인
독립 화면 개발 환경의 고정 데이터와 실제 서버의 응답·인증·상태 전이가 연결되지 않았다. 분석 접수 성공도 실제 결과 완성과 혼동할 수 있었다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 화면마다 별도 수동 서버 설정 | 빠르게 시작 가능 | 팀원마다 재현 조건이 달라짐 | 미채택 |
| UI Compose와 API 프록시·브라우저 검사 | 동일 환경에서 실제 상태 확인 | 초기 빌드 비용 | 채택 |

## 해결 (적용 내용)
- 기존 팀 프런트엔드를 바탕으로 `--scope ui` 구동과 API 연결을 구성했다. 확장 UI 5174, 모바일 웹 8081에서 실제 API/DB 경로를 사용했다.
- 모의 결제는 명시적으로 활성화하는 방식으로 분리했다. 회원 탈퇴·구독 해지·상담 시작·이미지 접수의 API 계약을 맞추고, 대기 중 테스트 결제를 다시 요청해도 중복 결제가 생기지 않도록 했다.
- Playwright 통합 테스트 및 체크박스 라벨/접근성 상태·Windows UTF-8 실행 문제를 보완했다.
- 이 단계의 분석 검증은 접수·대기·취소까지였으며, 처리 작업자 없이 결과가 나오는 것처럼 표시하지 않도록 했다.

## 왜 그렇게 해결했는지
팀 화면을 새로 작성했다고 주장하지 않고, 실제 API에 연결되는 경계와 사용자 동작의 검증을 담당했다. 분석 파이프라인 미완성은 화면 성공 표시로 감추지 않고 대기 상태로 드러내야 했다.

## 검증
- [PR #5](https://github.com/daon217/swproject/pull/5), [Actions 실행 44230941340](https://github.com/daon217/swproject/actions/runs/44230941340): 화면 검사 2개와 별도 pending 결제 환경 검사 1개가 통과했다. 여기서 pending은 분석 결과 대기 검사가 아니라 결제 대기 상태에서 중복 요청을 막는 시나리오다.
- 당시 PR에 9개 프로젝트 빌드, API 91개 통과·1개 건너뜀 기록이 있다.
- 실행 경로: `python tools/workspace.py init`, `python tools/workspace.py up --scope ui`, `cd tests/ui` 후 `npm ci`, `npm test`.

이번 일지 작성에서는 코드 테스트를 재실행하지 않았다. 커밋별 파일·행 존재와 기록 근거를 대조했다.

## 남은 과제 / 주의
- 실제 OCR/추천 처리 완료는 #42에서 별도로 연결했다.
- 당시의 브라우저 검증은 이후 UI 변경 전체에 대한 보장이 아니다. 기존 Claude 일지 #01에는 후속 UI 회귀 테스트 수정이 기록돼 있다.
