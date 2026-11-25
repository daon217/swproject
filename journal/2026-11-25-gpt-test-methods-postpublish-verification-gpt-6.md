# [GPT-6 (Codex)] 개발일지 · 2026-11-25 점검·테스트 방법 기록의 게시 후 재검증

- 날짜: 2026-11-25
- 상태: 해결 — 게시된 문서의 재검증 완료. 서비스 전체 테스트를 새로 수행했다는 뜻은 아님
- 브랜치 / 커밋: `devlog` / 검사 대상 `4fc894670ab29e946ebb78f06c916cbf1db6b7a5`; 비교 기준 `122b2d0a4d41d734f77609ac81effd8b326986f0`
- 관련 파일: `GPT_METHODS.md:1`, `PROMPTS.md` 8번, `INDEX.md:1`, `GPT_COVERAGE.md:1`
- 작성 AI: GPT-6 (Codex)

## 문제점
사용자는 과거 점검·테스트 방법을 올린 뒤에도 다시 검증하도록 요청했다. 업로드 전 로컬 검사만으로는 원격의 실제 내용·동시 변경 보존·수치 정확성을 확인했다고 할 수 없다.

## 원인
생성한 문서와 GitHub에 게시된 파일이 다르거나, 잘못된 커밋의 명령/수치를 옮길 수 있다. workflow 성공 표시만 보면 테스트 수와 skip, 실제 모델 검사 여부를 구분하기 어렵다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| push 성공 응답만 확인 | 빠름 | 본문·명령·결과 근거는 확인하지 못함 | 미채택 |
| 원격 본문 재독 + 게시 커밋 checkout + 원본 CI 재조회 | 게시된 내용과 근거를 함께 확인 | 추가 조회 필요 | 채택 |

## 해결 (적용 내용)
1. 게시 커밋을 고정해 수정/추가한 7개 파일의 GitHub 본문을 각각 다시 읽고 준비한 내용과 일치하는지 비교했다.
2. 원격 devlog를 fetch한 뒤 **게시된 커밋 자체**를 별도 detached worktree로 열었다. 원래 작성 폴더만 재검사한 것이 아니다.
3. Python 검사로 문서 구조·상대 링크·코드 파일/행·발췌 명령 출처를 다시 확인했다. 코드 파일은 `git show <고정 SHA>:<경로>`로 읽었다.
4. GitHub의 실제 job 로그 4개를 업로드 후 다시 받아 API/성능·UI·임베딩·실제 모델 결과를 대조했다.
5. 기준 커밋과 게시 커밋의 diff 목록, 기존 방법론·프롬프트·정오표 보존, main/maintest HEAD를 확인했다.
6. 검사 결과를 이 새 일지에 기록하고 GPT_METHODS와 INDEX에 연결한다. 기존 개발일지를 덮어쓰지 않는다.

## 왜 그렇게 해결했는지
원격 결과를 독립적으로 읽어야 생성/전송 오류를 잡을 수 있다. 코드가 가리키는 검사와 job 로그가 실제 실행한 결과를 따로 확인하면 “재현 명령”과 “실행 사실”의 혼동을 줄인다. 새 코드 변경이 없는 문서 요청이므로 DB·컨테이너·결제를 실행할 필요는 없다.

## 검증

| 검사 | 실제 결과 |
| --- | --- |
| GitHub 본문과 준비한 내용 비교 | 7개 모두 일치 |
| 마크다운 참조 조사 | 검사한 7개 문서에서 링크 211개 식별; 상대 링크 대상 존재 확인 |
| 고정 코드 참조 | 21개 파일/행 참조 확인 |
| 실제 명령 출처 | 19개 발췌 명령을 해당 커밋 workflow/package 원문과 대조, 모두 일치 |
| 신규 일지 구조 | LOG_TEMPLATE 필수 7개 항목 확인 |
| 기존 방법론/프롬프트/정정 | 기존 줄 보존; Claude/Gemini 일지와 OPEN_ISSUES 변경 없음 |
| Git diff | 새 파일 2개 + 기존 파일 5개, 예상 7개만 변경 |
| 원격 브랜치 | devlog는 게시 SHA; main `32f08ba`, maintest `82a81db`로 검사 시작 때와 동일 |
| 전체 검사 실패 | 0건 |

게시 후 재조회한 원본 결과:

| job / run | 대조한 값 |
| --- | --- |
| [catalog 133926902792](https://github.com/daon217/swproject/actions/runs/44050527427/job/133926902792) | 59 passed·1 skipped, 변형 32 passed; 조회 p95 62.46ms |
| [browser 134592359952](https://github.com/daon217/swproject/actions/runs/44242147154/job/134592359952) | 기본 환경 6 passed·1 skipped, 별도 pending 결제 환경 1 passed |
| [postgres 137433536545](https://github.com/daon217/swproject/actions/runs/45095253284/job/137433536545) | 66 passed·1 skipped, 도구 17개, API 62 passed·1 skipped |
| [semantic-model 137433536714](https://github.com/daon217/swproject/actions/runs/45095253284/job/137433536714) | 384차원, offline=True, 0.6387366271572296 > 0.008583089011040707 |

원격 job 로그의 핵심 문자열/값 13개를 재확인했다. 테스트 수치를 서로 다른 실행 사이에 더하지 않았으며, 145 통과는 해당 임베딩 run의 66+17+62다.

Git 대조 명령:

```bash
git fetch origin devlog
git diff --name-status 122b2d0 4fc8946
git show <고정 코드 SHA>:<워크플로 또는 테스트 파일 경로>
```

변경 파일: `GPT_METHODS.md`, `journal/2026-11-25-gpt-test-methods-gpt-6.md`, `README.md`, `METHODS.md`, `INDEX.md`, `GPT_COVERAGE.md`, `PROMPTS.md`.

## 남은 과제 / 주의
- 링크 211개는 식별 수이며 외부 URL 211개를 모두 HTTP 접속 검증했다는 뜻은 아니다. 상대 링크 존재와 21개 고정 코드 참조, 사용한 CI 근거를 확인했다.
- 문서 게시 후 재검증이다. 최신 앱의 전체 pytest/Playwright/성능/보안 스캔을 새로 실행하지 않았으며 실제 DB·사용자 볼륨에 접근하지 않았다.
- 원래의 테스트 한계와 기존 미해결 문제는 그대로다. 본문에서 설명한 과거 GPT 관리자 덮어쓰기 문제와 Claude 정정을 유지한다.
- 이 후속 일지의 게시 결과도 원격 본문/변경 파일을 확인한 뒤 사용자에게 완료를 보고한다.
