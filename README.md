# 꿀픽(swproject) 개발일지

코드와 분리된 **개발일지 전용 브랜치(`devlog`)** 입니다. 코드 히스토리와 섞이지 않도록 orphan 브랜치로 만들었습니다.

목적
- 다른 AI 모델(또는 사람)이 작업을 이어받거나 **검증**할 때 맥락을 바로 파악하게 한다.
- 나중에 "왜 이렇게 했지?"를 다시 찾을 수 있게 **문제 → 원인 → 해결 방안 → 해결 → 이유 → 검증**을 남긴다.

## 구성

| 경로 | 내용 | 성격 |
| --- | --- | --- |
| [SUMMARY.md](SUMMARY.md) | **전체 작업 요약**: 맡은 범위·진행 흐름·결과 숫자·현재 기능 (발표·검토용) | 정기 갱신 |
| [OPEN_ISSUES.md](OPEN_ISSUES.md) | **아직 해결 안 된 문제만** (상태·영향·다음 행동) | 살아 있는 문서 |
| [INDEX.md](INDEX.md) | 해결된 이슈 표 + 개발일지 목록 | 색인 |
| `journal/claude/` · `journal/gpt/` · `journal/gemini/` | **개발일지** — 작성 AI별 폴더, 파일명 `YYYY-MM-DD-<주제>-<모델명>.md` | 기록 — 쓴 뒤에는 고치지 않음(정정은 새 일지에) |
| `guide/` | 일지 양식([LOG_TEMPLATE](guide/LOG_TEMPLATE.md)), 검증 명령([VERIFY](guide/VERIFY.md)), 점검 방법론([METHODS](guide/METHODS.md)·[GPT](guide/GPT_METHODS.md)·[Gemini](guide/GEMINI_METHODS.md)), 기록 대응표([GPT](guide/GPT_COVERAGE.md)·[Gemini](guide/GEMINI_COVERAGE.md)), AI 프롬프트([PROMPTS](guide/PROMPTS.md)) | 참고 |
| `tools/` | 검증 스크립트: env 생성, 통합 테스트 실행, UI·워커 compose 덮어쓰기, 스키마 추출, ERD·PDF 생성 | |
| `sim/` | 실제 구동 시뮬레이션 스크립트 | |

새 AI의 일지는 `journal/<ai 이름>/`에 넣고, INDEX의 개발일지 목록에 한 줄 추가한다.

## 흐름

1. 문제를 발견하면 → `OPEN_ISSUES.md`에 번호를 붙여 추가 (번호는 INDEX·OPEN_ISSUES 통틀어 다음 번호, 재사용 금지)
2. 작업하면 → 그날의 개발일지(`journal/`)에 과정과 이유를 쓴다
3. 해결되면 → `OPEN_ISSUES.md`에서 지우고 `INDEX.md` "해결됨" 표에 추가(커밋·일지 링크)

## 규칙

1. 개발일지 항목: 문제점 / 원인(파일:줄) / 해결 방안(검토한 선택지) / 해결(파일·커밋) / 왜 그렇게 해결했는지 / 검증 / 남은 과제.
2. **추측과 확인한 사실을 구분**한다. 확인 못한 것은 `가정:` 또는 `미확인:`.
3. 커밋 해시와 브랜치를 적는다.
4. 비밀번호·API 키·토큰·개인정보는 쓰지 않는다(환경변수 이름만).
5. **제목은 `# [AI 모델명] 개발일지 · ...`**, 파일명 끝에 모델명(예: `-claude-opus-5.5`). INDEX의 "작성 AI" 칸에도 적는다. 다른 AI의 검증 결과는 `journal/YYYY-MM-DD-review-<모델명>.md`.
6. 미해결 항목에는 **운영 전제(예: 수집기 주기 적재)에 따른 영향**을 함께 적는다.
7. 상태 값: `해결` / `부분 해결` / `미해결` / `보류` / `확인 필요`.

## 운영 전제
- 크롤링 데이터는 수집기(최준서 파트)가 주기적으로 DB에 넣는다 (2026-11-24 결정·정정).

## 브랜치 관계 (2026-11-24 기준)

```
origin/main ── origin/maintest (PR #15)
                    └── part/소병선-backend-test (작업 브랜치 · maintest와 같은 커밋으로 유지)
devlog (이 브랜치, orphan, 문서만)
```
