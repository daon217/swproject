# [GPT-6 (Codex)] GPT 점검·테스트 수행 방법과 이력

- 작성일: 2026-11-25. 회고 작성 AI: GPT-6 (Codex); 과거 각 GPT 세션의 상세 모델 버전은 미확인.
- 범위: **실제 코드 개발이 시작된 2026-11-04 이후 GPT가 수행한 작업**. 코드 검토·로컬 검사·CI·문서 검증을 포함한다. 개발 이전 설계/발표자료는 제외한다.
- 목적: “통과했다”에 더해 **무엇을, 왜, 어떤 도구와 환경에서, 어떤 입력·판정 기준으로 검사했는지** 남긴다.
- 근거: 커밋에 고정된 코드/워크플로, 실행 로그, PR, 당시 보고. 이번 작성은 과거 검증의 복원이며 최신 서비스 전체 테스트를 다시 실행한 것이 아니다.
- 읽는 순서: 이 문서 → [개발 기록 대응표](GPT_COVERAGE.md) → 연결된 일지와 고정 코드. 현재 공통 재검증 절차는 [METHODS.md](METHODS.md), [VERIFY.md](VERIFY.md), [tools/](tools/)를 따른다.

## 1. 기존 방법론을 참고한 범위

`PROMPTS.md` 2·5~7번과 METHODS.md 전체를 읽고, 원칙·코드 검토·재현·단위/통합/화면 검사·이력·한계 순서로 정리했다. 사용자는 과거에 **했던 방법을 기록**하도록 요청했으므로 5번의 전체 서비스 재점검이나 7번의 ERD 재생성을 새로 수행한 것으로 쓰지 않는다.

| 구분 | GPT 기록에 적용하는 기준 |
| --- | --- |
| GPT의 과거 실행 | 당시 커밋·CI·보고로 확인되는 도구/환경/명령만 수행 사실로 기록 |
| 최신 공통 절차 | 11-25의 Windows Python 3.14, 두 테스트 실행 순서, `tools/run-all.sh`, 내장 브라우저, ERD 도구는 Claude 방법론에 기록돼 있다. GPT의 과거 실행으로 소급하지 않음 |
| 이번 문서 검사 | GitHub 조회, Git 파일 대조, Python 문서 검사, 원격 업로드 후 재확인. DB/서비스 테스트와 구분 |
| 가정/미확인 | 정확한 당시 명령·로그·환경을 복원하지 못하면 명시. 재현 가능한 예시를 실제 실행 이력으로 바꾸지 않음 |

## 2. 사용한 도구와 역할

| 도구 | 어떻게 사용했는가 | 확인한 범위 |
| --- | --- | --- |
| Git·GitHub PR/Actions | 커밋/파일 diff, 트리·blob 해시, PR 설명, run의 head SHA와 job 로그 대조 | 어떤 코드에서 어떤 검사가 성공/실패했는지 |
| Python·pytest | 입력을 만든 뒤 API 호출/작업 실행/DB 조회 결과를 assert; fixture·parametrize·monkeypatch 사용 | 계약·업무 상태·실패 분기·DB 불변식 |
| unittest·unittest.mock | 파일/환경/실패 명령 등 운영 도구의 경계값을 재현 | 설정·manifest·잠금·실패 후 정리. 실제 Docker 검사와 별개 |
| FastAPI TestClient | 프로세스 안에서 HTTP 요청·응답을 검사 | HTTP 계약. TestClient 사용 자체가 DB를 가짜로 바꾼다는 뜻은 아님 |
| PostgreSQL·pgvector·Alembic | 실제 테스트 DB에 초기화와 마이그레이션 적용 후 SQL/벡터 조회 | 실제 제약·권한·트랜잭션·버전·잠금 |
| SQLAlchemy 이벤트·EXPLAIN | 실행 SQL 수 집계, 동일 데이터에서 인덱스 전후 계획 비교 | N+1·반환값 일치·인덱스 사용·측정 한계 |
| Docker Compose·GitHub Actions | 새 CI runner에서 DB/API/작업자/웹 실행, 단계별 검사·로그·종료 | 실제 컨테이너 연결. 사용자 PC에서 성공했다는 뜻은 아님 |
| Playwright·Chrome/Chromium | 실제 UI 클릭·입력·새로고침·계정 전환 후 화면과 API 결과 검사 | 브라우저 경로. 모바일 실기기·실제 확장 캡처 전체 검증과 구분 |
| Node·TypeScript·Expo | npm 잠금 설치, 타입 검사·lint·웹/Android export | 의존/번들/타입 검증. 기능 E2E와 구분 |
| pg_dump·pg_restore·SHA-256·SSH | DB dump 복원, 파일 손상/불완전 백업, 허용/차단 키와 포워딩 검사 | 복구 경로·접근 경계. 실제 재해 복구 시간은 미측정 |
| Pillow·PaddleOCR CPU | 합성 한국어 성분 이미지로 실제 Vision 호출 | OCR→작업자→API 결과 저장 연결 |
| HashEmbedder / 실제 SentenceTransformer | 해시는 연결·경쟁 테스트, 고정 실제 모델은 별도 오프라인 의미 사례 | 두 검사를 나눔. 해시 통과를 의미 검색 품질로 쓰지 않음 |

## 3. 점검에서 검증까지 진행한 방식

1. **대상 고정:** 브랜치 이름뿐 아니라 커밋 SHA를 기록했다. 기존 사용자 변경과 다른 담당자의 코드를 구분했다. devlog 작업은 별도 worktree에서 했다.
2. **구조 확인:** 파일 검색과 코드 읽기로 라우트, 호출자, 저장 경로, 환경값, DB 제약, 작업 상태를 연결했다. 최신 공통 방법론의 모든 체크리스트를 당시 매번 수행했다고 주장하지 않는다.
3. **관찰 가능한 문제로 바꾸기:** 예를 들어 “느리다”를 “이력 100건 조회 시 catalog SQL 101회”로, “데이터가 섞인다”를 “A 로그아웃→B 로그인 후 A의 기록/늦은 응답 노출”로 구체화했다.
4. **입력·행동·기대값 분리:** 새 데이터를 준비하고 한 조건만 바꾸거나 경쟁 요청을 보낸 뒤, HTTP 상태뿐 아니라 DB 행·이력·버전·소유권까지 확인했다.
5. **실제 서비스 경계 확인:** 단위 검사를 거친 뒤 DB가 필요한 검사는 실제 PostgreSQL에서, 화면은 실제 DB/API를 붙인 브라우저에서 확인했다. 실패 로그와 코드 원인을 대조해 수정 후 같은 경로를 재검증했다.
6. **성공의 범위 기록:** build/health 성공, DB 계약 성공, 브라우저 흐름 성공, 의미 모델 출력은 서로 다른 근거다. 실패·skip·미실행은 통과에 넣지 않았다.

## 4. 항목별로 무엇을 어떻게 검사했는가

### 4.1 초기 저장소·CI·DB·개발환경

- Python CI 도구는 “코드 없는 프로젝트 비활성”, “코드가 있는데 검증 설정 없음”, 실패 명령 전파 등 계획/실행 규칙을 검사했다. 초기 단위 7개 통과는 앱 자체 테스트가 아니다.
- DB는 member/catalog/support 각각의 권한, CRUD·sequence, 다른 DB 접속 차단, catalog 벡터 연산, 컨테이너 재생성 후 데이터 보존을 검사했다.
- core/full 환경은 seed 후 조회값을 보관하고 stop→up 뒤 같은 값인지 비교했다. 실제 API UID로 이미지 볼륨에 임시 파일을 썼다 지우는 검사도 CI에 넣었다.
- CPU 라이브러리 이미지는 네트워크 없는 컨테이너에서 import했다. 이 단계의 import 성공을 실제 OCR/추천 추론 성공으로 기록하지 않는다.
- 11-06의 본문 제한 검사는 Content-Length 유무를 나눠 64 KiB 초과가 앱에 도달하기 전에 413인지, 정상 JSON은 보존되는지 확인했다. CORS preflight도 허용/비허용 origin으로 나눴다.

근거: [.github/workflows/workspace.yml:1](https://github.com/daon217/swproject/blob/0c2bff56d04a085e8e92e1889afcfd4f5fc63105/.github/workflows/workspace.yml#L1) / [services/api/tests/test_contract.py:25](https://github.com/daon217/swproject/blob/0c2bff56d04a085e8e92e1889afcfd4f5fc63105/services/api/tests/test_contract.py#L25) / [.github/workflows/database.yml:1](https://github.com/daon217/swproject/blob/3102a781dd4a0fa3e06e2c1e0c1587a90605d77d/.github/workflows/database.yml#L1). 상세는 #34·#44·#45 일지.

### 4.2 수집 계약·실제 300건·32개 변형 검사

- 동일 관측 키/동일 내용은 재전송, 동일 키/다른 내용은 409로 구분했다. 늦은 시각, 같은 시각 충돌, 누락과 명시적 null, 상품/식품 유형, 품절/종료/timeout/not_found 등을 나눴다.
- 입력마다 HTTP 코드, 적용 상태, 현재 상품값, 가격/URL/변경 이력 개수를 함께 검사했다. 201을 “상품값 적용 성공”과 동일시하지 않았다.
- 실제 300건 파일은 **로컬 격리 PostgreSQL에서** 신규 적재→동일 파일 재전송→중복 없음, 실제 HTTP importer, 0001→0002 마이그레이션 후 값 보존을 확인한 당시 기록이 있다. 원본을 이번 문서에 복사하지 않는다.
- 공개 CI는 원본 파일이 없어 그 검사를 skip했다. 대신 비식별 가상 표본에 32개 단일 조건 변형을 적용했다. 이 32개 검사는 실제 쇼핑몰 가격/재고의 진위를 확인하는 검사가 아니다.
- 정리 작업은 dry-run과 실제 삭제, 삭제 전 관측 재전송, 최신 재입고 보존, payload를 비운 뒤 키/해시 판정, 30일 초과 관측을 검사했다.

근거: [docs/CATALOG_INGESTION.md:1](https://github.com/daon217/swproject/blob/6058d22f34c30f98c771fab4381192b79d5578f0/docs/CATALOG_INGESTION.md#L1) / [services/api/tests/test_sample_mutations.py:26](https://github.com/daon217/swproject/blob/0e6690bec28d440688519f8f39f3c4d0fa24af64/services/api/tests/test_sample_mutations.py#L26) / [services/api/tests/test_retention.py:25](https://github.com/daon217/swproject/blob/8fcacfa345fe4f9d02c6cc776f424370cd69226d/services/api/tests/test_retention.py#L25). 실행 문맥은 로컬 보고와 CI를 구분한다.

### 4.3 회원·모의 결제·문의·권한·분석 상태

- 가입/로그인/세션/프로필과 본인·다른 사용자·관리자 역할을 나눠 검사했다.
- 결제는 mock의 성공/실패/pending을 분리했다. 같은 멱등 키를 순차·동시 요청했을 때 중복 청구/권한 부여가 없는지, 실패 후 DB 롤백과 소유권이 유지되는지 확인했다.
- 분석은 접수→임대→완료/실패/취소의 상태와 소유권을 검사했다. 초기 API 상태 테스트와 후속 실제 OCR 연결은 별도다.
- 모의 결제 테스트 통과는 실결제 PG 승인·웹훅·정기청구 검증이 아니다.

근거: [services/api/tests/test_members_billing.py:45](https://github.com/daon217/swproject/blob/085e7f618608d7370f82fd0da62d8ca88afe24e3/services/api/tests/test_members_billing.py#L45) 및 #36 일지.

### 4.4 성능·쿼리·인덱스

- `tools/performance.py`는 HTTP로 신규 관측·갱신·재전송·조회 요청을 보내고 지연 분포/오류를 집계했다. 1천 행/동시 8과 1만 행/동시 16을 나눴다.
- HTTP 성공뿐 아니라 applied 상태, 최종 가격·URL, 전체 페이지 고유행 수를 검증했다. 테스트마다 별도 가상 source를 쓰고 `--cleanup`으로 해당 데이터를 정리했다.
- SQLAlchemy `before_cursor_execute` 이벤트로 **catalog SQL**을 세어 이력 100건에서 2회인지 검사했다. 인증 DB 쿼리는 이 수치에 포함하지 않는다.
- 인덱스 검사는 같은 데이터·트랜잭션에서 SAVEPOINT로 해당 인덱스를 제거한 계획과 존재하는 계획을 비교했다. `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`, 반환행 일치, 인덱스명, 공간 비용을 보고 데이터/DDL을 롤백했다.
- 최초 인덱스 크기 측정의 search_path 의존 오류는 `085e7f6`에서 수정 후 다시 확인했다.

근거: [tools/performance.py:45](https://github.com/daon217/swproject/blob/085e7f618608d7370f82fd0da62d8ca88afe24e3/tools/performance.py#L45) / [services/api/tests/test_efficiency.py:15](https://github.com/daon217/swproject/blob/085e7f618608d7370f82fd0da62d8ca88afe24e3/services/api/tests/test_efficiency.py#L15) / [.github/workflows/catalog-api.yml:1](https://github.com/daon217/swproject/blob/085e7f618608d7370f82fd0da62d8ca88afe24e3/.github/workflows/catalog-api.yml#L1).

### 4.5 백업·복원·접속 경계

- 단위 검사: 같은 크기의 손상 파일도 SHA-256으로 잡는지, 미완성/중복/경로 이탈/symlink/잘못된 manifest를 거절하는지, 재시작 시 주기 판단과 잠금 경쟁, dump 실패 시 완료 manifest가 생기지 않는지 확인했다.
- 실제 Docker 검사: DB 3개 백업→해시/목록 확인→임시 DB 복원→주요 테이블/마이그레이션 확인→임시 DB 제거. 같은 주기 재실행은 `not_due`인지 확인했다.
- 중단 감지 후 재시작 정상화와 데이터 유지도 검사했다. 운영 DB를 덮어쓰는 복구 연습과는 다르다.
- SSH는 등록 키로 API 포워딩/같은 샘플 조회 성공, 미등록 키 거절, DB 포워딩 거절, 키 회수 뒤 터널 접근 실패를 확인했다.

근거: [tools/test_operations.py:46](https://github.com/daon217/swproject/blob/39b081fbdada7c72c8c3882af699f5fe73c428a7/tools/test_operations.py#L46) / [.github/workflows/workspace.yml:1](https://github.com/daon217/swproject/blob/39b081fbdada7c72c8c3882af699f5fe73c428a7/.github/workflows/workspace.yml#L1) / [.github/workflows/team-access.yml:1](https://github.com/daon217/swproject/blob/39b081fbdada7c72c8c3882af699f5fe73c428a7/.github/workflows/team-access.yml#L1).

### 4.6 실제 화면·계정 분리·모바일 빌드

- Ubuntu Actions에서 Docker DB/API와 확장 UI·모바일 웹 preview를 실행했다. `npm ci` 후 설치된 Chrome을 쓰거나 Playwright Chromium을 설치했다. API stub 없이 UI를 조작했다.
- 가입/회원정보 저장/새로고침/문의/분석 접수·취소/구독·탈퇴를 확인했다. 계정 A→로그아웃→B→A 복원, 다른 탭 로그아웃, 입력 중 오류 표시, 늦은 응답과 저장 키 경계를 별도로 확인했다.
- 기본 결제 환경의 pending 검사는 조건부 skip이었다. 별도 pending 서버 환경에서 재실행해 중복 결제나 프리미엄 권한 부여가 없는지 확인했다. **분석 완료 대기 테스트가 아니다.**
- Playwright trace/스크린샷/report를 당시 Actions artifact로 저장했다(7일 보존 설정). 지금도 다운로드 가능하다고 보장하지 않는다.
- 모바일 순환 참조는 공통 스타일을 분리한 뒤 typecheck/lint와 Android Hermes·web export를 확인했다. 실제 휴대폰 reload 경고 소멸은 미검증이었다.

근거: [.github/workflows/ui-integration.yml:1](https://github.com/daon217/swproject/blob/f0757973cccb908d4654da5defda7a054495e2be/.github/workflows/ui-integration.yml#L1) / [tests/ui/account-isolation.spec.js:1](https://github.com/daon217/swproject/blob/f0757973cccb908d4654da5defda7a054495e2be/tests/ui/account-isolation.spec.js#L1) / [apps/mobile/package.json:1](https://github.com/daon217/swproject/blob/d3ccb8a43961a7a6b13fc9bf8b7fff13caeec88b/apps/mobile/package.json#L1) / [.ci/projects.json:1](https://github.com/daon217/swproject/blob/d3ccb8a43961a7a6b13fc9bf8b7fff13caeec88b/.ci/projects.json#L1).

### 4.7 팀 통합·실제 OCR·수집 어댑터

- 합성 한국어 이미지(“원재료명 및 함량”, “우유, 밀가루, 설탕, 소금”)를 Pillow/Noto CJK로 만들고 실제 PaddleOCR CPU Vision 8100에 보냈다.
- `integration_smoke.py`는 실제 API 분석 상태가 completed인지, 저장된 추천 항목과 사유가 있는지, Vision의 성분 결과에 “우유”가 포함되는지 확인했다.
- 수집 어댑터는 생성→가격/URL 변경→중복 재전송→과거 관측→품절 숨김을 실제 DB/API와 대조했다. 외부 쇼핑몰 실수집 성공 검사와 구분한다.
- 관리자 CRUD는 `TEAM_CONSOLE_TEST=1`로 별도 Playwright 시나리오를 실행했다.
- 이때 추천은 HashEmbedder/RuleRanker·메모리 방식이었다. 실제 OCR 성공과 실제 의미 검색 완성을 같은 것으로 쓰지 않는다.

근거: [.github/workflows/team-integration.yml:1](https://github.com/daon217/swproject/blob/a19c4312b0e18b78c6b9260cbac299d223558eba/.github/workflows/team-integration.yml#L1) / [tools/integration_smoke.py:14](https://github.com/daon217/swproject/blob/a19c4312b0e18b78c6b9260cbac299d223558eba/tools/integration_smoke.py#L14). 이후 밝혀진 관리자 화면 덮어쓰기의 한계는 7절에 기록한다.

### 4.8 영속 임베딩·동시성·실제 모델

- 실제 PostgreSQL/pgvector와 테스트용 해시 인코더를 조합해 outbox·계약·작업자·추천 HTTP를 검사했다. DB를 가짜 객체로 바꾼 테스트가 아니다.
- bootstrap 재실행과 HNSW 중복 방지, 기존 1,001개 backfill/정확한 URL 검색, 영역/판매 상태 필터를 확인했다.
- 원문 변경 뒤 과거 벡터 제외→최신 버전 저장, 계산 중 원문 갱신 뒤 낡은 완료 응답 거절, 가격만 변경·트랜잭션 롤백 때 작업 미등록을 검사했다.
- `ThreadPoolExecutor(2)`로 서로 다른 연결이 작업을 나눠 갖는지 확인하고, 임대 만료·새 토큰 발급·옛 토큰의 완료 거절을 검사했다. 모델 추론 오류는 실패하는 인코더 객체로 주입해 작업 보존/재시도를 확인했다.
- HTTP 2회 요청에서 encoder 호출 2회, 상품 벡터 생성 시각 유지, offers 배열 입력 거절, 인증 누락 401, 계약 미준비 503을 검사해 요청마다 상품을 재색인하지 않는지 확인했다.
- 별도 job은 고정 revision의 실제 MiniLM 384차원 모델을 이미지에 넣고 `--network none`에서 실행했다. 한국어 “무선 헤드셋”이 헤드폰 문서에 채소 문서보다 높은 내적 점수를 주는지 확인했다.
- 계약 테스트와 실제 모델의 단일 의미 사례를 분리했다. 검색 품질 전체, 대량 처리 시간, 실제 운영 배포는 검증하지 않았다.

근거: [services/recommendation/tests/test_embedding_pipeline.py:78](https://github.com/daon217/swproject/blob/2d444b0ee4e1c181701c8491c77800b9c30f2e88/services/recommendation/tests/test_embedding_pipeline.py#L78) / [.github/workflows/embedding-pipeline.yml:1](https://github.com/daon217/swproject/blob/2d444b0ee4e1c181701c8491c77800b9c30f2e88/.github/workflows/embedding-pipeline.yml#L1).

## 5. 당시 실행 명령 — 문맥과 함께 읽기

아래는 고정 커밋 CI/스크립트의 **실제 명령 발췌**다. 완전한 설치/격리 스크립트가 아니며 현재 사용자 개발 폴더에 그대로 실행하는 지침도 아니다. 당시 CI는 새 runner의 임시 체크아웃·생성된 설정을 사용했다. 수동 재실행은 VERIFY.md의 별도 프로젝트/볼륨/포트부터 준비하고, 필요한 모든 환경값은 해당 버전의 워크플로를 따른다.

### API/변형 검사 (`085e7f6`, 작업 폴더 `services/api`)

전제: 해당 버전 requirements-dev 설치, 테스트 DB 초기화·마이그레이션, 테스트용 설정 로드. `CATALOG_PASSWORD`는 역할이 맞는 app 비밀번호여야 한다. 아래는 Bash 문법이다.

```bash
EFFICIENCY_REPORT=../../data/benchmarks/query-plans.json CATALOG_INTEGRATION=1 CATALOG_PASSWORD="$CATALOG_APP_PASSWORD" python -m pytest -q --ignore=tests/test_sample_mutations.py
CATALOG_INTEGRATION=1 CATALOG_PASSWORD="$CATALOG_APP_PASSWORD" python -m pytest -vv -s tests/test_sample_mutations.py
```

### HTTP 성능 (`085e7f6`, 저장소 루트, 전용 테스트 API 실행 상태)

```bash
python tools/performance.py --allow-write --rows 1000 --requests 500 --workers 8 --cleanup
python tools/performance.py --allow-write --rows 10000 --requests 1000 --workers 16 --output data/benchmarks/10000-rows.json --cleanup
```

### 운영 도구 (`39b081f`, 저장소 루트, 테스트용 Compose 설정)

```bash
python -m unittest discover -s tools -p 'test_*.py' -v
python tools/operations.py validate
python tools/operations.py backup-auto
python tools/operations.py verify-backup
python tools/operations.py restore-check
python tools/operations.py monitor
```

### 브라우저 (`f075797`, `tests/ui`, 테스트 DB/API·UI 실행 상태)

```bash
npm ci
npm test
UI_PAYMENT_OUTCOME=pending UI_TEST_OUTPUT=test-results-pending npm test -- billing.spec.js --reporter=list
```

마지막 줄 전에 저장소 루트에서 `MOCK_PAYMENT_OUTCOME=pending python tools/workspace.py up --scope ui`로 서버의 모의 결제 상태도 바꿨다. 클라이언트 환경변수만 바꾸면 같은 검증이 아니다. Chrome 경로/Chromium 설치는 고정 workflow를 따른다.

### 통합 OCR (`a19c431`, 저장소 루트)

```bash
python tools/integration_smoke.py --image /tmp/ingredients.png --collector
```

이미지는 workflow에서 생성하고 integrated 서비스를 미리 실행했다. 관리자 UI 명령은 `tests/ui`의 `TEAM_CONSOLE_TEST=1 npm test -- console.spec.js`였다.

### 임베딩 (`2d444b0`, 저장소 루트)

전제: workflow의 설치·테스트 DB·환경 로드. postgres job의 `RECO_EMBEDDER=hash` 설정과 app 연결 자격을 유지한다.

```bash
EMBEDDING_INTEGRATION=1 python -m pytest -q services/recommendation/tests services/dev_runtime/test_analysis_worker.py
python -m unittest discover -s tools -p 'test_*.py' -q
```

실제 모델 검사는 같은 workflow의 별도 `semantic-model` job에서 Docker build와 `docker run --rm --network none`으로 실행했다. 명령 전체와 pinned 모델 구성은 위 소스 링크에 남긴다.

### 타입·모바일 (`d3ccb8a`, `apps/mobile`)

```bash
npm ci
npm run typecheck
npm run lint
npm run build
```

해당 버전 `build`는 `expo export --platform android --platform web`다. 스토어 배포·실기기 설치 명령이 아니다.

## 6. 수행 이력과 결과 근거

수치는 서로 다른 실행 사이에 누적 합산하지 않는다. `warnings`는 실패와 다르지만 생략한 경고가 없었다고 주장하지 않는다. 워크플로 success와 테스트 passed 개수도 다른 값이다.

| 당시 시기·대상 | 환경·방법 | 당시 결과/한계 | 근거 |
| --- | --- | --- | --- |
| 11-04 CI 기반 | 로컬 unittest·계획/YAML 확인 | 7개 통과; 앱 코드가 없어 앱 빌드는 미실시 | PR #1·#34 일지 |
| 11-05 DB `3102a78` | Ubuntu Actions·실제 DB·권한/벡터/재기동 | workflow 성공; 업무 전체 완성 아님 | [실행 41867281673](https://github.com/daon217/swproject/actions/runs/41867281673) |
| 11-06 `0c2bff5` | 로컬 계약/도구 + 컨테이너 CI | 당시 보고 로컬 29개; 5개 workflow 성공. API/공통 runtime 권고 0건은 당시 스캔 | #44 일지·[실행 42165837309](https://github.com/daon217/swproject/actions/runs/42165837309) |
| 11-16 `6058d22` | 로컬 PG 17.11/pgvector 0.8.0·HTTP importer | 26개 통과, 실제 300건 신규/재전송·마이그레이션 확인. Docker pgvector 설정과 로컬 버전은 다름 | #46 일지·고정 CATALOG_INGESTION 문서 |
| 11-17 `085e7f6` | 실제 DB/API·32개 변형·부하 | 일반 59 + 변형 32 = 91 passed, 원본 의존 1 skipped | [실행 44050527427](https://github.com/daon217/swproject/actions/runs/44050527427) |
| 같은 실행의 성능 | 1천/동시 8 및 1만/동시 16 | 조회 p95 29.68ms / 62.46ms, 각각 오류 0. 운영 SLA 아님 | 위 실행 `catalog` job |
| 11-18 `39b081f` | Ubuntu/Windows unittest + 실제 Docker 복원 | 도구 각 17개·환경 성공. 실제 재해 복구 시간 미측정 | [실행 44221228764](https://github.com/daon217/swproject/actions/runs/44221228764) |
| 11-18 `41c1d1c` | Playwright 실제 UI/API/DB | 일반 화면 2개 + 별도 pending 결제 1개 통과 | [실행 44230941340](https://github.com/daon217/swproject/actions/runs/44230941340) |
| 11-18 `f075797` | 계정 분리/입력/기존 UI + pending 환경 | 첫 환경 6 passed, 1 skipped; 별도 pending 환경 1 passed → 확인된 7개 | [실행 44242147154](https://github.com/daon217/swproject/actions/runs/44242147154) |
| 11-18 모바일 `d3ccb8a` | 타입/lint·Hermes/web export | 성공 기록, 휴대폰 reload는 미확인 | PR #8·#41 일지 |
| 11-19 `a19c431` | 실제 OCR·DB·수집/관리 브라우저 | PR #13의 6개 workflow 성공; collector 108개는 별도 팀 빌드 기록. 실제 사이트 수집 보장 아님 | PR #13·#42 일지 |
| 11-22 `e7f7007` 검토 | 코드·Actions 읽기 전용 점검 | 임시 추천/관리 UI 회귀 확인, 코드 수정·병합 안 함 | #47 일지 |
| 11-23 `2d444b0` | 실제 DB + 해시 연결검사·운영도구·API | 66 passed/1 skipped + 17 통과 + 62 passed/1 skipped = **145 통과·2 skip** | [실행 45095253284](https://github.com/daon217/swproject/actions/runs/45095253284) |
| 같은 실행의 실제 모델 | 고정 CPU 모델·네트워크 없는 컨테이너 | 384차원, 헤드폰 약 0.6387 > 채소 약 0.0086. 한 사례 검사 | 위 실행 `semantic-model` job |
| 11-24 개발일지 | 커밋/PR/과거 보고 대조·파일 hash | 개발 범위와 모델 귀속 구분, 원격 반영 파일 확인 | GPT_COVERAGE·#47 |
| 11-25 이번 방법 기록 | 고정 workflow·job 로그 재독·문서 검사 | 과거 검사 방법/수치를 재확인. 서비스 테스트 재실행 아님 | 오늘 작성 일지 |

PR 근거: [#1](https://github.com/daon217/swproject/pull/1), [#3](https://github.com/daon217/swproject/pull/3), [#8](https://github.com/daon217/swproject/pull/8), [#13](https://github.com/daon217/swproject/pull/13).

## 7. 놓쳤던 것·실패에서 확인한 것

| 항목 | 관찰/원인 | 처리·남는 한계 |
| --- | --- | --- |
| 초기 로컬 테스트 수집 오류 | PYTHONPATH/실행 위치 불일치 | 올바른 경로로 재실행한 결과를 기록. 첫 오류를 기능 실패/통과로 잘못 집계하지 않음 |
| 최초 catalog 쓰기 | 바인딩/상품 하위 유형 문제 | `22fa5bf` 수정과 실제 DB 검사. 입력 모델만으로 DB 동작을 보장하지 않음 |
| SQL 크기 측정 | search_path 의존 | `085e7f6` 수정·재검증; 기능 검사를 생략해 성공 처리하지 않음 |
| Windows 설정 읽기·UI 선택자 | UTF-8 및 custom checkbox 접근성 | `77e8091`·`c5fcca9`·`41c1d1c`에서 보완하고 실제 UI 동작 확인 |
| collector import | 루트 실행과 프로젝트별 CI의 import 경로 차이 | `4969fa3`·`a19c431` 등에서 경로 보완 후 CI 확인 |
| **관리 웹 덮어쓰기 계층 누락** | GPT 통합 `a9da43b`의 `apps/web/shared/backend.js`가 웹팀 함수를 덮음. 당시 통과한 CRUD만으로 향후 병합 호환성까지 확인하지 못함 | 최신 GPT_COVERAGE 정오표·Claude #55~#57 반영. Claude의 제거/수정을 GPT 성과로 쓰지 않음 |
| 통합 이후 UI 회귀 | PR #13 당시 통과 뒤 웹팀 병합에서 다른 경로/문구 문제가 드러남 | 당시 성공을 현재 성공으로 확대하지 않음. 한 테스트가 중간에서 멈췄으면 뒤 단계는 미실행 |
| 해시/실제 모델 혼동 위험 | 연결 테스트와 의미 품질 검사는 목적이 다름 | 별도 job·별도 계약으로 기록, 실제 대표 검색어 품질/성능 미검증 |
| 임베딩 잔여 한계 | GPT `2d444b0`는 1건 처리·재시도 횟수 상한 없음 | 후속 Claude #06/#07을 분리. 현재 미해결 이슈도 임의 종료하지 않음 |

## 8. 재현·이어받기 및 게시 후 재검증

- 과거 결과를 재현할 때는 **같은 코드 커밋의 requirements/lock/workflow**부터 읽는다. 현재 main 파일과 과거 명령을 섞지 않는다. 새 worktree는 코드만 분리하며 DB 격리를 보장하지 않으므로 Compose 프로젝트·포트·볼륨도 별도로 둔다.
- 테스트 전 migration 성공, 실제 DB 연결, integration 플래그를 확인한다. DB 없이 skip된 suite를 “전체 통합 통과”라고 쓰지 않는다. 새 실행의 결과는 새 날짜/커밋으로 기록한다.
- 현재 사용자의 개발 볼륨을 지우지 않는다. `down -v`는 **검증용으로 직접 만든 프로젝트만** 대상으로 한다. 이번 기록에서는 DB/컨테이너를 실행하거나 정리하지 않았다.
- 비밀번호·토큰·실제 수집 원문·개인 이미지·전체 CI 원문을 문서에 복사하지 않는다. 환경변수 이름과 테스트용 예제만 둔다.
- 이번 작성에서 7개 과거 Actions run의 head SHA/success를 확인했고, 핵심 4개 job 로그(API/성능, UI, 임베딩 DB, 실제 모델)의 결과 줄을 직접 대조했다.
- 게시 후에는 devlog HEAD, 변경 파일의 원격 blob/본문, 고정 코드 참조·명령 출처·결과 수치를 다시 확인한다. 기존 Claude/Gemini 일지와 정오표 보존도 검사한다. 재검증 결과는 같은 날짜의 후속 일지에 남긴다.
- 원 작업 AI가 불명확한 관리자 가입 원형은 GPT에 귀속하지 않는다. `4b1f5fc`~`2c65ccd`는 이후 Gemini 일지에서 귀속이 확인되어 GPT 범위 밖이다.
