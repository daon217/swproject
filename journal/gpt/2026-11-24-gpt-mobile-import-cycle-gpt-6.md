# [GPT-6 (Codex)] 개발일지 · 2026-11-24 모바일 날짜 입력 컴포넌트 순환 참조 제거 (#41)

- 날짜: 2026-11-24 (회고 기록일, Asia/Seoul)
- 작업 시기: PR #8 작업 당시 (정확한 작업 시작 시각 미확인)
- 상태: 해결 — 아래에 명시한 당시 범위 기준
- 브랜치 / 커밋: 기록은 `devlog`; 코드 근거 [`d3ccb8a`](https://github.com/daon217/swproject/commit/d3ccb8a43961a7a6b13fc9bf8b7fff13caeec88b)
- 관련 파일: [apps/mobile/src/ui/BirthDateField.tsx:5](https://github.com/daon217/swproject/blob/d3ccb8a43961a7a6b13fc9bf8b7fff13caeec88b/apps/mobile/src/ui/BirthDateField.tsx#L5); [apps/mobile/src/ui/BirthDateField.web.tsx:1](https://github.com/daon217/swproject/blob/d3ccb8a43961a7a6b13fc9bf8b7fff13caeec88b/apps/mobile/src/ui/BirthDateField.web.tsx#L1); [apps/mobile/src/ui/componentStyles.ts:5](https://github.com/daon217/swproject/blob/d3ccb8a43961a7a6b13fc9bf8b7fff13caeec88b/apps/mobile/src/ui/componentStyles.ts#L5); [apps/mobile/src/ui/components.tsx:1](https://github.com/daon217/swproject/blob/d3ccb8a43961a7a6b13fc9bf8b7fff13caeec88b/apps/mobile/src/ui/components.tsx#L1)
- 작성 AI: GPT-6 (Codex, 회고 작성)
- 원 작업 AI: GPT/ChatGPT/Codex. 과거 세션의 상세 모델 버전은 미확인.

> 과거 작업을 커밋·PR·대화 기록으로 복원한 일지다. 선택지 표는 회고 시점의 설계 비교이며, 모든 대안을 당시 구현·실험했다는 뜻이 아니다. 검증 수치는 해당 커밋의 기록이며 최신 코드 전체의 재검증 결과가 아니다. [기록 범위와 근거](2026-11-24-gpt-retrospective-scope-gpt-6.md)를 함께 읽는다.

## 문제점
공통 UI와 생년월일 입력 컴포넌트가 서로 참조하는 순환 의존성이 있었다.

## 원인
`components.tsx`가 날짜 입력 컴포넌트를 내보내면서 날짜 입력 컴포넌트는 다시 `components.tsx`의 스타일에 의존했다. 플랫폼별 구현에서도 같은 경계를 고려해야 했다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| 순환 참조 경고만 억제 | 수정량 적음 | 초기화 순서 위험 유지 | 미채택 |
| 스타일 모듈을 독립 파일로 분리 | 의존 방향 단순화, 기존 공개 API 유지 | 파일 하나 추가 | 채택 |

## 해결 (적용 내용)
- 공통 스타일을 `componentStyles.ts`로 분리하고 네이티브/웹 생년월일 컴포넌트가 해당 모듈을 직접 참조하도록 했다.
- 기존 components 내보내기와 날짜 입력 동작을 유지하는 범위로 변경했다.

## 왜 그렇게 해결했는지
날짜 선택 UI를 다시 구현할 필요 없이 순환을 만드는 공통 의존성만 분리하는 것이 변경 범위를 줄인다.

## 검증
- [PR #8](https://github.com/daon217/swproject/pull/8): typecheck, lint, Android Hermes 및 웹 export 성공 기록. 브라우저/기기에서 실제 재시작까지 확인한 것으로 확대하지 않는다.
- 검증 명령의 정확한 당시 옵션·개별 테스트 수는 이 회고에서 확정하지 않는다. PR의 검증 기록을 근거로 한다.
- 로컬 Codex 커밋 `e5cfc20`과 원격 `d3ccb8a`의 stable patch 일치를 확인했다. 서로 다른 부모 커밋 때문에 tree 자체가 같은 경우와 구분한다.

이번 일지 작성에서는 코드 테스트를 재실행하지 않았다. 커밋별 파일·행 존재와 기록 근거를 대조했다.

## 남은 과제 / 주의
- 실제 Android 기기의 reload 동작은 미검증이다. 네트워크 접속 오류를 이 순환 참조 수정으로 해결했다고 주장하지 않는다.
