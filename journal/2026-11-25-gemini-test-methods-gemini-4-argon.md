# [Gemini 4 Argon] 개발일지 · 2026-11-25 Gemini 점검·테스트 방법과 수행 이력 보완

- 날짜: 2026-11-25 (Asia/Seoul)
- 실제 작업 시기: 2026-11-19 및 2026-11-23 (점검·구현·테스트 수행); 2026-11-25 (방법론·실행 근거 복원 및 검증)
- 상태: 해결 — Gemini 점검·테스트 방법 및 실행 근거 문서화 완료 (기존 `OPEN_ISSUES.md`의 미해결 코드 이슈 종료를 뜻하지 않음)
- 브랜치 / 커밋: 문서는 `devlog` (기준 `582176d`); 코드 근거는 `maintest` [`4b1f5fc`](https://github.com/daon217/swproject/commit/4b1f5fc9b0ef80124b87676e829a2e1f6c4063c6) ~ [`2c65ccd`](https://github.com/daon217/swproject/commit/2c65ccd67b545bad8c14e4f229f14af898926b6b)
- 관련 파일: `GEMINI_METHODS.md:1`, `GEMINI_COVERAGE.md:1`, `PROMPTS.md:154`, `METHODS.md:1`, `GPT_METHODS.md:1`, `INDEX.md:1`, `README.md:1`
- 작성 AI: Gemini 4 Argon

## 문제점
기존 Gemini 개발일지(`#48`~`#54`)와 `GEMINI_COVERAGE.md`에는 무엇을 구현했고 어떤 CI가 통과했는지는 적혀 있었으나, `PROMPTS.md` 8번 및 `METHODS.md`·`GPT_METHODS.md` 체계처럼 **어떤 도구를 왜 선택했는지, 로컬 Windows 환경(Docker 미기동)과 GitHub Actions Ubuntu 컨테이너 환경을 어떻게 분리해 검증했는지, 각 테스트의 입력·행동·기대값과 실제 CI Job 로그의 통과/스킵 수치가 얼마였는지, 중간 실패에서 무엇을 발견해 고쳤는지**가 하나의 방법론 문서로 정리되어 있지 않았다.

## 원인
- 11-23 당시 Windows 로컬 PC에서는 Docker Desktop 데몬(`dockerDesktopLinuxEngine`)이 실행되지 않고 기본 Python도 3.14/3.15만 설치되어 있어, 로컬에서는 `uv run --python 3.12` 기반의 단위 테스트와 인메모리 Fake/Mock 독립 시나리오 스크립트로 빠르게 검증하고 실제 PostgreSQL 17 + pgvector 마이그레이션·동시성·드라이버 타입 검증은 GitHub Actions(`maintest`)에서 수행했다.
- 이 환경 분리 이유와 중간 실패(예: `psycopg`의 `%,` 플레이스홀더 파싱 오류, `requests` 간접 의존성, 단위 CI의 `psycopg` 미설치, `asyncpg`의 untyped NULL 파라미터 오류)를 겪으며 테스트를 보강한 과정이 개별 일지에 흩어져 있으면 다음 작업자가 재현 조건과 한계를 한눈에 파악하기 어렵다.

## 해결 방안 (검토한 선택지)
| 선택지 | 장점 | 단점 | 채택 |
| --- | --- | --- | --- |
| A. 별도 `GEMINI_METHODS.md`에 도구·환경·4중 검증 구조·항목별 입력/기대값·실제 명령·Job 로그 수치·실패/정정 이력을 정리하고 게시 후 원격 본문과 로그를 재검증 | Claude(`METHODS.md`)·GPT(`GPT_METHODS.md`)와 대칭을 이루며, 로컬/CI 경계와 후속 정정까지 투명하게 재현 가능 | 원격 CI Job 로그 재조회 및 문서 간 링크 검증 필요 | ✅ |
| B. 기존 `#48`~`#54` 일지 파일들을 직접 덮어써서 수정 | 파일 수가 늘지 않음 | `devlog` 규칙("쓴 뒤에는 고치지 않음, 정정·보완은 새 문서/일지에") 위반 | |
| C. `METHODS.md`의 로컬 Linux 컨테이너(`tools/run-all.sh`)나 시뮬레이션(`sim/`)을 Gemini도 실행한 것처럼 합쳐서 기술 | 문서가 단순해짐 | 실행 주체와 시점 오귀속(당시 로컬 Docker 데몬은 꺼져 있었음) | |

## 해결 (적용 내용)
1. **[GEMINI_METHODS.md](../GEMINI_METHODS.md) 신규 작성**:
   - **원칙 및 범위(1절)**: Gemini가 실제 수행한 범위(`11-19` 파악, `11-23` 조사·구현·4중 검증, `11-24/25` devlog 검증)만 기록하고, GPT(`2d444b0` 이전)와 Claude(`2c65ccd` 이후 `part/소병선-backend-test`, `tools/run-all.sh`, `sim/`, 브라우저 UI 클릭, ERD 생성)의 작업을 소급 합산하지 않도록 경계를 명시했다.
   - **도구와 역할(2절)**: 격리 클론/worktree, `gh` CLI, `uv` Python 3.12, `pytest`·`TestClient`, `httpx.MockTransport`·`ThreadPoolExecutor`, 인메모리 시나리오 스크립트, Ubuntu Actions PostgreSQL 17 + pgvector + Alembic `0009`, 오프라인 MiniLM 컨테이너의 역할과 한계를 표로 정리했다.
   - **점검·검증 방식 및 항목별 판정 기준(3~4절)**: `#48`~`#54` 각각에 대해 목적, 환경, 고정 코드 SHA·줄 링크, 입력·행동·기대값을 구체적으로 기록했다.
   - **실제 실행 명령 발췌 및 수행 이력(5~6절)**: 로컬 `uv run` 명령과 CI 워크플로 명령을 문맥과 함께 발췌하고, Run `45103700755`, `45104086541`, `45105156508`, `45105156543`(149 통과·2 skip), `45113756566`, `45113756891`, `45114082875`(151 통과·2 skip, 오프라인 384차원 `0.6387 > 0.0086`), `45114083442`의 Job ID와 실제 수치를 분리 기록했다.
   - **실패에서 확인한 것과 교차 검토 정정 수용(7절)**: 구현·검증 중 겪은 6건의 실패→수정 과정과 함께, 2026-11-25 Claude 교차 검토에서 확인된 `#48`의 `console.spec.js:29, 38` 진단 오류(`apps/web/shared/backend.js` 덮어쓰기 계층 미고려 및 33행 `/backend` 누락 404 `#55`~`#57`) 정정과 헤놀로지 메모리·성능 수치의 추정치 성격을 명시적으로 반영했다.
2. **색인 및 안내 문서 연결 (`README.md`, `METHODS.md`, `INDEX.md`, `GEMINI_COVERAGE.md`)**:
   - 기존 Claude/GPT 문서를 훼손하지 않고 `GEMINI_METHODS.md`와 본 일지 링크를 추가했다.

## 왜 그렇게 해결했는지
로컬 단위/인메모리 테스트가 통과해도 실제 PostgreSQL/asyncpg 드라이버(`45113756566`의 NULL 파라미터 타입 추론 오류)나 `psycopg` 플레이스홀더 파서(`45103700755`의 `%,` 오류), 혹은 `psycopg`가 없는 단위 CI(`45104927874`)에서 다른 오류가 발생할 수 있음을 실제로 겪었기 때문이다. 어떤 테스트가 무엇을 잡았고 무엇을 잡지 못했는지를 그대로 남겨야 이후 다른 AI나 개발자가 검증 단계를 생략하지 않는다.

## 검증
- `PROMPTS.md` 8번, `METHODS.md`, `GPT_METHODS.md`, `GEMINI_COVERAGE.md`(정오표 포함), `INDEX.md`, `OPEN_ISSUES.md`를 모두 읽고 규칙을 대조했다.
- `gh run view`로 Gemini가 실행한 8개 GitHub Actions run(`45103700755`, `45104086541`, `45105156508`, `45105156543`, `45113756566`, `45113756891`, `45114082875`, `45114083442`)의 head SHA, conclusion, 전체 Job ID를 조회했다.
- `gh run view --job <id> --log`로 `137464692324`(`103070f` postgres: `68 passed, 1 skipped` + `Ran 17 tests` + `64 passed, 1 skipped`), `137492787339`(`2c65ccd` postgres: `70 passed, 1 skipped` + `Ran 17 tests` + `64 passed, 1 skipped`), `137492787444`(`2c65ccd` semantic-model: `384`, `offline: True`, `0.6387365338826615 > 0.008583121512580857`)의 실제 로그 출력 줄을 직접 대조했다.
- 문서 내 상대 링크, 고정 코드 경로·줄 번호, `LOG_TEMPLATE.md` 필수 섹션, `git diff --check`를 검사했다.
- 1차 게시 후에는 `PROMPTS.md` 8번의 7~8단계에 따라 원격 커밋 본문·고정 코드 참조·발췌 명령·CI 수치를 다시 대조하고 게시 후 재검증 일지를 추가로 남긴다.

## 남은 과제 / 주의
- 이번 작업은 과거 Gemini 수행 방법의 문서화 및 근거 재검증이며, 오늘 새로운 DB/컨테이너 통합 테스트를 다시 실행한 것이 아니다.
- `2c65ccd` 이후 `maintest`에 병합된 Claude 작업(`82a81db`, `b51ffdc` 등)과 현재 미해결 이슈는 [OPEN_ISSUES.md](../OPEN_ISSUES.md) 및 최신 Claude 일지를 따른다.
