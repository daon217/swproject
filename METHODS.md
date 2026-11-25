# [Claude Opus 5.5] 점검·테스트 방법론

> 이 저장소(꿀픽, daon217/swproject)에서 **어떻게 점검하고, 무엇으로, 어떤 순서로 테스트했는지**를 2026-11-24부터 지금까지 한 일 포함해 정리한 문서.
> 다른 AI나 사람이 같은 방식으로 이어서 하라고 만들었다. 그대로 붙여 넣을 프롬프트는 [PROMPTS.md](PROMPTS.md) 5번에 있다.
> 실행 명령의 세부(격리 DB 띄우기)는 [VERIFY.md](VERIFY.md), 쓰는 스크립트는 [`tools/`](tools/)에 있다.
> 마지막 갱신: 2026-11-25 · 기준 커밋 `part/소병선-backend-test` b51ffdc

---

## 1. 원칙

| 원칙 | 내용 | 이유 |
| --- | --- | --- |
| 조사만 할 때는 수정하지 않는다 | "파악만", "확인해줘" 요청은 읽기·실행만. 수정은 요청이 있을 때 | 사용자가 범위를 정한다 |
| 확인한 사실과 추측을 구분 | 확인 못한 것은 `가정:`/`미확인:`으로 쓴다. 문제는 **재현하거나 코드 줄로** 보여 준다 | 다른 AI 로그(Gemini #48)에서 잘못된 진단이 실제로 있었다 |
| 격리 환경에서만 실행 | 검증용 compose 프로젝트(`kkulpick-verify`, `kkulpick-ui` 등), 다른 포트·무작위 비밀번호, 끝나면 `down -v` | 사용자의 개발 DB(`kkulpick-db-dev_postgres_data` 볼륨, `kkulpick-db-dev-*` 컨테이너)를 절대 건드리지 않기 위해 |
| 비밀값은 어디에도 남기지 않는다 | 애드픽 키는 `services/api/.env`에만. 로그·커밋·일지에는 환경변수 이름만 | |
| 푸시·병합은 요청이 있을 때만 | 테스트 브랜치 푸시, maintest 반영, PR 병합은 각각 사용자 지시가 있어야 한다 | 팀 공용 브랜치 보호 |
| 로컬 미커밋 파일은 커밋하지 않는다 | `apps/mobile/.env.example`(사설 IP), `apps/mobile/package-lock.json` | 사용자 개인 설정 |
| 운영 전제를 깔고 판단 | 크롤링 데이터는 수집기(최준서)가 **주기적으로** DB에 넣는다(2시간 주기, 바뀐 상품만 관측 전송) | "실시간 수집"이나 "미리 넣기" 전제로 판단하면 영향 평가가 틀어진다(실제로 한 번 정정함) |
| 답변은 한국어 | | 사용자 요청 |

## 2. 브랜치 흐름

```
origin/maintest (팀 통합 테스트, PR #15)
   └─ part/소병선-backend-test (개인 테스트 브랜치 — 여기서 작업·검증, 유지)
devlog (orphan, 문서 전용 — 이 브랜치)
```

1. **최신화**: `git fetch --all --prune` → `git log <현재>..origin/maintest`로 새 커밋 확인 → 새 커밋 **내용을 먼저 검토** → `git merge --ff-only origin/maintest` (조상 관계일 때). 앞으로 당길 수 없으면 병합 전에 사용자에게 알린다.
2. **작업**: 테스트 브랜치에서 수정·테스트 → 의미 단위 커밋(끝에 `Co-Authored-By` 줄) → 테스트 브랜치 푸시.
3. **팀 반영**: 사용자가 요청하면 maintest에 반영(테스트 브랜치와 같은 커밋으로 맞춤).
4. **팀원 브랜치 병합**(예: 김호진 웹): 테스트 브랜치에 병합 → 충돌은 "상대 구조를 살리고 우리 수정만 유지" → 상대 브랜치가 새로 넣은 같은 종류 버그까지 확인 → 브라우저로 화면 검증 → 사용자 승인 후 maintest.
5. **devlog**: 작업마다 `journal/`에 일지, 미해결은 `OPEN_ISSUES.md`, 해결은 `INDEX.md`.
   devlog는 별도 worktree(`_devlog/`, `.git/info/exclude`에 등록)로 체크아웃해서 코드 브랜치와 섞지 않는다.

## 3. 점검 방법 (무엇을 어떻게 보는가)

### 3.1 GitHub 현황 파악
- `gh pr list`, `gh pr view 15 --json ...`, `gh pr checks 15 --repo daon217/swproject`, `gh run list`
- `git branch -r`, `git log --oneline --graph`, 브랜치별 `git log A..B`로 누가 무엇을 바꿨는지
- CI 실패는 `gh run view <id> --log-failed`로 실제 로그를 본다(추측 금지).

### 3.2 코드 전체 훑기 — grep으로 지도부터 만든다
| 보는 것 | 명령 예 |
| --- | --- |
| API 라우트 전체 | `grep -nE "@(router\|app)\.(get\|post\|put\|patch\|delete)\(" services/api/kkulpick/*.py` |
| 인증 의존성(누가 부를 수 있나) | `grep -n "Depends(member\|admin_member\|collector\|worker" ...`, `access(req,uid,{'admin'})` 역할 집합 |
| 오류 코드 전체(상태별) | `grep -ohE "fail\([0-9]{3}, *'[A-Z_]+'"` + `HTTPException(` |
| 전역 예외 매핑 | `services/api/kkulpick/errors.py` (SQLAlchemy 계열·네트워크 오류·미처리 예외) |
| 재시도·상태 머신 | analyses(lease·attempt<3), embedding_jobs(attempts·parking), 수집기 outbox(`status` 값들) |
| 설정값 | `grep -n "getenv("` — 기본값이 운영에서 안전한지 |

### 3.3 리뷰 체크리스트 (발견한 문제들이 여기서 나왔다)
1. **예외 분류**: 일시 장애(503, retryable) / 코드 결함(500, 재시도 금지) / 입력 오류(4xx)가 섞이지 않는가. 예: `ProgrammingError`를 503으로 돌려 재시도 폭주(#05 계열).
2. **무한 재시도·영구 정지**: 실패 상한, 대기(backoff), 상한 도달 후 처리(보류·재처리 명령). 예: 임베딩 무한 재시도 → 8회 보류 + `--requeue-failed`; 분석 즉시 재대기(#25); 수집기 영구 동결(#29).
3. **멱등성·동시성**: 재전송 키, 유니크 제약, `FOR UPDATE SKIP LOCKED`, 낙관적 잠금(version), 트랜잭션 안의 savepoint.
4. **도착 순서**: 확장 정보가 관측보다 먼저 오면? (#12 → 202 보류 후 적용)
5. **권한**: 역할별 접근, 권한 회수 즉시 반영(auth_version), 관리자 토큰 위임 같은 우회(#20).
6. **보안**: 무인증 외부 호출(#16), 프록시 뒤 IP 제한(#17), SSRF(사설 호스트 차단), 오류·로그에 비밀값 노출.
7. **팀 파트 사이 계약**: 같은 값을 양쪽이 같은 철자로 쓰는가. 자주 깨지는 곳 = 코드 집합.
   - 앱이 부르는 경로가 백엔드에 있는가: `grep -rhoE "'/v2/[^']*'" apps/...` vs 라우트 목록
   - 상태·enum 값(분석 state, evidence)
   - 알레르기 코드: 클라이언트 `soybean` vs 추천 내부 `soy`(82a81db), 신고 코드 `shellfish`·`pine_nut` 누락(#59)
8. **기능 미연결**: 만들어졌지만 호출하는 쪽이 없는 것(#31 check-in API, #32 확장 API를 수집기가 안 씀).
9. **운영 전제 대입**: "2시간마다 바뀐 상품만 들어온다"를 넣고 각 실패 정책이 어떻게 되는지(신선도, 동결, 출처 전체 정지).

### 3.4 재현으로 확정하기
의심되면 짧은 스크립트로 바로 확인한다. 예(#59):
```bash
python -c "from services.recommendation.allergens import ALLERGENS,detect,split_ingredients; \
print([c for c in ALLERGENS if not detect(split_ingredients(c))])"   # → ['shellfish', 'pine_nut']
```
재현된 것만 '문제'로 올리고, 재현 못한 것은 `미확인:`으로 둔다.

### 3.5 다른 AI 작업 검증
- GPT·Gemini가 남긴 일지를 커밋과 대조(`git show <hash>`), 주장마다 코드 줄로 확인.
- 틀린 진단은 지우지 않고 정오표로 남긴다(`GPT_COVERAGE.md`, `GEMINI_COVERAGE.md` 하단). 예: Gemini #48의 console.spec 29/38줄 진단은 오류.

### 3.6 팀원 코드 검토 (예: 수집기)
- 그 파트의 상태 머신을 표로 그린다(outbox: pending → retry_wait → delivered / quarantine / held / exhausted / rejected).
- 백엔드 응답(201/200/409/422/5xx)마다 수집기가 어떤 상태로 가는지 대응표를 만든다 → #29(영구 동결), #30(409로 출처 전체 정지) 발견.

## 4. 테스트 방법 (무엇으로 어떻게 돌리는가)

| 단계 | 무엇 | 어디서 | 도구 |
| --- | --- | --- | --- |
| ① 단위 | DB 없는 테스트(API 36, 추천·워커 단위) | Windows venv | `py -3.14 -m venv`, pytest |
| ② 통합 | 실제 PostgreSQL+pgvector에 마이그레이션 적용 후 전체 | 격리 compose + **Linux 컨테이너** | docker compose, `python:3.12-slim`, [`tools/run-all.sh`](tools/run-all.sh) |
| ③ 순서 바꿔 재실행 | 추천→API, API→추천 두 순서 + 같은 DB 재실행 | 위와 같음 | 테스트 간 잔여 데이터(서빙 중 임베딩 계약 등) 탐지 |
| ④ 샘플 변조 | 계약 샘플을 일부러 망가뜨려 검증이 잡는지 | 위와 같음 | `tests/test_sample_mutations.py` |
| ⑤ 실제 구동 시뮬레이션 | 실제 수집 원본 300건 적재 → 임베딩 대기 → 추천·분석·관리자 흐름, Vision 끊긴 상태 포함 | 격리 compose 네트워크 | [`sim/`](sim/), [`tools/sim-worker.compose.yaml`](tools/sim-worker.compose.yaml) |
| ⑥ 화면 검증 | 관리자 웹을 실제 API에 붙여 클릭으로 확인 | 격리 compose(API 58000, 웹 53000) | [`tools/ui.compose.yaml`](tools/ui.compose.yaml), Claude 데스크톱 앱 내장 브라우저 |
| ⑦ CI | GitHub Actions 24개(Playwright 포함) | PR #15 | `gh pr checks 15` |
| ⑧ 문서 출력 | DB에서 직접 스키마 추출 → ERD·PDF | 격리 DB + docgen 컨테이너 | [`tools/extract_schema.sh`](tools/extract_schema.sh), [`tools/erd/`](tools/erd/) |

### 4.1 격리 통합 테스트 (매번 하는 기본)
```bash
python tools/gen_env.py <임시폴더>          # 무작위 비밀번호로 verify.env / verify-in.env 생성 (저장소 밖)
C="docker compose -p kkulpick-verify --env-file <임시폴더>/verify.env -f infra/db/compose.yaml -f infra/db/api.compose.yaml"
$C up -d --wait postgres && $C run --rm --build migrate
docker run --rm --network container:kkulpick-verify-postgres-1 --env-file <임시폴더>/verify-in.env \
  -v "<저장소>:/src:ro" -v "<devlog>/tools:/s:ro" python:3.12-slim bash /s/run-all.sh
$C down -v
```
- 왜 Linux 컨테이너: psycopg async가 Windows 기본 이벤트 루프(Proactor)에서 `InterfaceError`.
- 왜 `services tools .github infra`만 복사: `node_modules`까지 복사하면 매우 느리다.
- 결과 읽는 법: 두 순서 모두 같은 통과 수여야 한다. 한쪽만 실패하면 테스트 간 잔여 상태 문제.

### 4.2 화면 검증 (UI)
1. `kkulpick-ui` 프로젝트로 API+웹을 띄우고(`ui.compose.yaml` 덮어쓰기) 샘플·실제 상품을 적재.
2. 내장 브라우저로 `http://127.0.0.1:53000` 접속 → 흐름별 확인:
   - 관리자 가입 신청 → 승인 전 로그인 차단(토큰 저장 없음) → 관리자 승인 → 목록에서 사라짐
   - 수집 상품 목록 건수 = API 건수, 선택 삭제 → API에서도 사라짐(브라우저 숨김 아님)
   - `tests/ui/console.spec.js` 흐름(상담 답변·설정, 제휴 등록)
   - 화면 7개 이동 중 콘솔 오류 수(`read_console_messages`) 0건
3. 글자 확인은 스크린샷보다 `read_page`/`get_page_text`(정확하고 가볍다).

### 4.3 시뮬레이션에서 발견한 것
실제 데이터로 돌려야만 보이는 문제가 있다: #24(임베딩 v2 전환 직후 추천 0건), #25(재시도 대기 없음), #26(이미지 없는 미매칭이 OCR_FAILED), #27(알레르기 사용자 식품 추천 0건).
주의: 크롤 실행 1개 = 출처 1개(`RUN_SOURCE_CONFLICT`), `field_presence`는 실제 보낸 필드와 일치해야 한다.

### 4.4 ERD·문서 출력
1. 격리 DB에 마이그레이션 적용(4.1의 첫 두 줄, 프로젝트 이름만 `kkulpick-erd`).
2. `bash tools/extract_schema.sh kkulpick-erd-postgres-1 <폴더>` → member/catalog/support TSV.
3. `docker build -t kkulpick-docgen tools/erd` (graphviz + 나눔 글꼴 + reportlab).
4. `docker run --rm -v <폴더>:/d kkulpick-docgen python /d/make_erd.py /d` → `erd_*.png/svg/pdf`.
5. PDF: `make_pdf.py /d /o` — **내용은 d0a46f8 시점 스냅샷**이다. 다시 쓸 때는 라우트·오류 코드·테스트 수를 3.2의 grep으로 새로 뽑아 고친다.
6. 결과물은 저장소 루트 `_exports/<날짜>/`(git 제외)에 둔다.

## 5. 함정과 해결 (실제로 겪은 것)

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| DB 테스트 `InterfaceError` | Windows Proactor 루프 | Linux 컨테이너에서 실행 |
| 임베딩 테스트가 API 테스트 뒤에만 실패 | 앞 테스트의 임베딩 계약이 서빙 상태로 남음 | 픽스처 finalizer로 retire, bootstrap이 이전 계약 정리 |
| Windows에서 Python으로 파일을 고쳤더니 diff가 파일 전체 | `open(...,'w')`가 LF를 CRLF로 바꿈 | `open(p,'w',encoding='utf-8',newline='')`, 이미 바뀌면 `sed -i 's/\r$//'` |
| bash heredoc 안 복잡한 따옴표가 깨짐 | Git Bash 파싱 | 스크립트를 파일로 쓰고 실행 |
| `git add`에 이미 지운 파일을 넣어 커밋이 엉킴 | 삭제 파일은 `git add -A <경로>` 또는 `git rm` | `git reset --soft HEAD~1` 후 다시 커밋 |
| Docker API 연결 실패 | Docker Desktop 꺼짐(날짜 변경 후) | `%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe` 실행 후 `docker info` 대기 |
| Graphviz `<B></B>` 문법 오류 | 빈 태그 | 내용 없으면 태그 생략 |
| 분석 워커 실패 코드 422 | 백엔드 허용 목록에 없는 코드(`WORKER_ERROR`) | `RECOMMENDATION_FAILED` 사용 |
| `AllergyWarning.allergen=None` → 422 | 모델이 문자열 필수 | 알레르기 코드마다 경고 1개 |

## 6. 지금까지 한 점검·테스트 이력

| 날짜 | 작업 | 방법 | 결과 | 일지 |
| --- | --- | --- | --- | --- |
| 11-24 | 현황 조사(브랜치·Actions·구조·성능) | gh·git log·grep, 수정 없음 | 구조·병목 파악 | [현황 조사](journal/2026-11-24-initial-survey-claude-opus-5.5.md) |
| 11-24 | 관리자 백엔드 병합, 무한 재시도·예외 처리 개선, 애드픽 | 코드 리뷰 + 격리 통합 테스트 | #01~#10 | [세션 1](journal/2026-11-24-backend-test-branch-claude-opus-5.5.md) |
| 11-24 | 4·5·6·8 개선, devlog 개설 | 같음 | #11~#15 | [세션 2](journal/2026-11-24-backend-test-round2-claude-opus-5.5.md) |
| 11-24 | 실제 구동 시뮬레이션 | 실제 300건 + Vision 끊김 시나리오 | #24~#27 발견 | [시뮬레이션](journal/2026-11-24-runtime-simulation-claude-opus-5.5.md) |
| 11-24 | 수집기 로직 검토 | 상태 머신·응답 대응표 | #29~#33 발견 | [수집기 검토](journal/2026-11-24-collector-review-claude-opus-5.5.md) |
| 11-24 | #31 판매 확인 API | 구현 + 통합 테스트 | 백엔드 부분 해결 | [신선도](journal/2026-11-24-freshness-checkins-claude-opus-5.5.md) |
| 11-25 | maintest CI·다른 AI 로그 검토 | gh run 로그, 커밋 대조 | #55~#57, 정오표 | [CI·AI 로그](journal/2026-11-25-maintest-ci-and-ai-log-review-claude-opus-5.5.md) |
| 11-25 | 웹 404·덮어쓰기 계층 정리 | 코드 리뷰 + 화면 검증 | #55~#57 해결 | [웹 정리](journal/2026-11-25-web-fix-cleanup-claude-opus-5.5.md) |
| 11-25 | 김호진 웹 병합 | 충돌 해결 + 화면 검증 + 통합 테스트 | #20·#58 해결 | [웹 병합](journal/2026-11-25-web-branch-merge-claude-opus-5.5.md) |
| 11-25 | ERD·프로젝트 정리 PDF | 격리 DB 스키마 추출 → graphviz·reportlab | ERD 4장, PDF 15쪽 | (일지 없음, 4.4 참고) |
| 11-25 | maintest 최신화 후 재점검 | ff 최신화, 계약 대조, 재현, 통합 테스트, CI | #59~#61 발견 | [재점검](journal/2026-11-25-maintest-sync-recheck-claude-opus-5.5.md) |
| 11-25 | #59 알레르기 신고 코드 수정 | 재현 → 수정 → 단위·통합 테스트 추가 | #59 해결 | [#59](journal/2026-11-25-allergen-declared-codes-claude-opus-5.5.md) |
