# [GPT-6 (Codex)] 개발일지 · 2026-11-24 계정별 페이지 기억·입력 검증·전환 처리 (#40)

- 날짜: 2026-11-24 (회고 기록일, Asia/Seoul)
- 작업 시기: 2026-11-18 (PR #6)
- 상태: 부분 해결 — 아래에 명시한 당시 범위 기준
- 브랜치 / 커밋: 기록은 `devlog`; 코드 근거 [`2158683`](https://github.com/daon217/swproject/commit/21586831f1554e6327b6e03fb0288a4a6ae9efc2) / [`194794a`](https://github.com/daon217/swproject/commit/194794a6aee69e05372a0ef60605d02aee3aa75d) / [`86f2aeb`](https://github.com/daon217/swproject/commit/86f2aeb60df041401a3d83b347438f9f00df8ea8) / [`f075797`](https://github.com/daon217/swproject/commit/f0757973cccb908d4654da5defda7a054495e2be)
- 관련 파일: [apps/extension/src/shared/accountData.ts:2](https://github.com/daon217/swproject/blob/f0757973cccb908d4654da5defda7a054495e2be/apps/extension/src/shared/accountData.ts#L2); [apps/extension/src/shared/validation.ts:2](https://github.com/daon217/swproject/blob/f0757973cccb908d4654da5defda7a054495e2be/apps/extension/src/shared/validation.ts#L2); [apps/extension/src/background/index.ts:1](https://github.com/daon217/swproject/blob/f0757973cccb908d4654da5defda7a054495e2be/apps/extension/src/background/index.ts#L1); [tests/ui/account-isolation.spec.js:1](https://github.com/daon217/swproject/blob/f0757973cccb908d4654da5defda7a054495e2be/tests/ui/account-isolation.spec.js#L1)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 과거 세션의 상세 모델 버전은 미확인.

> 과거 작업을 커밋·PR·대화 기록으로 복원한 일지다. 선택지 표는 회고 시점의 설계 비교이며, 모든 대안을 당시 구현·실험했다는 뜻이 아니다. 검증 수치는 해당 커밋의 기록이며 최신 코드 전체의 재검증 결과가 아니다. [기록 범위와 근거](2026-11-24-gpt-retrospective-scope-gpt-6.md)를 함께 읽는다.

## 문제점
아이디 공백 제한과 짧은 비밀번호의 피드백이 부족했고, 기본 페이지와 마지막 페이지가 혼동됐다. 계정 전환 때 이전 사용자의 기록·비동기 결과가 섞일 위험도 있었다.

## 원인
전역 저장 키와 계정별 상태의 구분, 저장 URL 정책, 인증 전환 중 늦은 응답 처리 기준이 필요했다. 로그인 입력 오류를 제출 후에만 보여 주면 사용자가 원인을 알기 어려웠다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 브라우저 전체 기록·전역 저장 키 사용 | 구현 간단 | 계정 간 데이터 혼재와 과도한 수집 | 미채택 |
| 서버 user_id별 로컬 저장 + 명시적 복원 | 계정 경계와 사용자의 선택 유지 | 동기화·기기 변경 복원은 별도 | 채택 |

## 해결 (적용 내용)
- 아이디는 영문·숫자 4~16자, 공백 불가를 안내하고 비밀번호 8~128자·확인 입력의 실시간 피드백을 추가했다. 공백 입력을 허용한 변경으로 기록하지 않는다.
- 서버의 user_id를 기준으로 저장 키를 분리하고 기본 페이지와 마지막 방문 페이지를 나눴다. 마지막 페이지는 명시적인 다시 열기 동작으로 복원한다.
- 방문 정보는 최대 50개·30일 기준으로 제한하고 쿼리/fragment 제거, 로그인·결제 URL 제외 정책을 적용했다. Chrome 전체 방문 기록을 수집하지 않는다.
- 로그아웃 시 해당 데이터는 숨기고 탈퇴 시 해당 사용자 데이터를 지우도록 구분했다. 쿠키/세션과 페이지 기억을 같은 저장 대상으로 보지 않았다.
- 탭 간 인증 전환, 늦게 도착하는 응답과 분석 캐시를 보완하고 중복 마지막 URL 저장을 줄였다. 인증 응답 캐시 억제도 반영했다.

## 왜 그렇게 해결했는지
페이지 기억은 계정별 편의 기능이며 쇼핑몰 로그인 쿠키를 DB에 복제하는 기능이 아니다. 수집 범위를 줄이고 명시적인 복원을 제공하면 다른 계정의 화면이 나타나는 혼란과 민감 URL 저장을 줄일 수 있다.

## 검증
- [PR #6](https://github.com/daon217/swproject/pull/6), [Actions 실행 44242147154](https://github.com/daon217/swproject/actions/runs/44242147154): 가입 안내 2개, 계정 전환/다른 탭 로그아웃 2개, 기존 연동 2개, 별도 pending 결제 1개로 총 7개 통과했다. 첫 환경의 pending 결제 검사는 조건부 skip이지만 별도 pending 환경에서는 통과한 것으로 PR에 기록돼 있다. 분석 완료 검증과는 별개다.
- 재현 진입점: UI 테스트 환경을 띄운 뒤 `tests/ui`에서 `npm test`. `account-isolation.spec.js`에서 계정 분리 시나리오를 확인할 수 있다.
- 로컬 Codex 체크포인트 `b1c7dcc`와 원격 `86f2aeb`, `5210428`와 `f075797`의 Git tree 동일성을 회고 작성 시 확인했다.

이번 일지 작성에서는 코드 테스트를 재실행하지 않았다. 커밋별 파일·행 존재와 기록 근거를 대조했다.

## 남은 과제 / 주의
- OS 암호화 저장소, 기기 간 동기화, 운영 HTTPS 및 HttpOnly/CSRF 정책 전체를 완료한 기록은 아니다.
- Chrome의 유출 비밀번호 경고를 끄거나 우회하지 않았다. 테스트 비밀번호에 대한 브라우저 자체 경고는 앱 입력 검증과 별개다.
- 전환·저장 정책은 당시 커밋 기준이며 현재 브라우저/모바일 실기기 전체 재검증은 하지 않았다.
