# 검증 방법

## 1. DB 없이 도는 단위 테스트 (Windows에서도 가능)

```powershell
py -3.14 -m venv .venv-test
.venv-test\Scripts\python -m pip install -r services/api/requirements-dev.txt -r services/dev_runtime/requirements.lock toon-format
cd services/api; ..\..\.venv-test\Scripts\python -m pytest -q tests; cd ../..
.venv-test\Scripts\python -m pytest -q services/dev_runtime services/recommendation/tests
```
DB가 필요한 테스트는 `CATALOG_INTEGRATION`/`EMBEDDING_INTEGRATION` 환경변수가 없으면 skip된다.

## 2. 실제 PostgreSQL 통합 테스트 (격리 DB)

**검증 DB란?** 테스트만을 위해 잠깐 띄우는 별도의 PostgreSQL 컨테이너다. 평소 개발 DB와 같은 이미지·같은 초기화 스크립트·같은 마이그레이션을 쓰지만
compose 프로젝트 이름(`kkulpick-verify`), 데이터 볼륨, 포트(55433), 비밀번호가 모두 따로라서 개발 DB의 데이터에 전혀 영향을 주지 않는다.
테스트가 끝나면 `down -v`로 볼륨까지 지운다. CI(GitHub Actions)가 매번 새 DB를 만들어 테스트하는 것과 같은 방식이다.


기존 개발 DB 볼륨(`kkulpick-db-dev_postgres_data`)을 건드리지 않도록 **별도 compose 프로젝트 이름과 포트**를 쓴다.

1. 임시 env 파일을 만든다(비밀번호는 무작위, 저장소 밖에 둔다):
   `POSTGRES_PASSWORD, MEMBER_OWNER_PASSWORD, MEMBER_APP_PASSWORD, CATALOG_OWNER_PASSWORD, CATALOG_APP_PASSWORD, SUPPORT_OWNER_PASSWORD, SUPPORT_APP_PASSWORD, COLLECTOR_TOKEN, ANALYSIS_WORKER_TOKEN, WORKSPACE_TOKEN, BILLING_TEST_TOKEN`, 그리고 `DB_PORT=55433`.
2. DB와 마이그레이션:
   ```bash
   C="docker compose -p kkulpick-verify --env-file verify.env -f infra/db/compose.yaml -f infra/db/api.compose.yaml"
   $C up -d --wait postgres && $C run --rm --build migrate
   ```
3. **Windows 주의:** psycopg async는 Windows 기본 이벤트 루프(Proactor)에서 동작하지 않아 `InterfaceError`가 난다. 테스트는 Linux 컨테이너에서 실행한다.
   ```bash
   docker run --rm --network container:kkulpick-verify-postgres-1 --env-file verify-in.env \
     -v "<repo>:/src:ro" python:3.12-slim bash -c '
       mkdir /work && cd /src && cp -r services tools .github infra /work && cd /work
       pip install -q -r services/api/requirements-dev.txt -r services/dev_runtime/requirements.lock toon-format
       export DB_HOST=127.0.0.1 CATALOG_INTEGRATION=1 EMBEDDING_INTEGRATION=1 ANALYSIS_IMAGE_DIR=/tmp/a CATALOG_PASSWORD=$CATALOG_APP_PASSWORD
       python -m pytest -q services/recommendation/tests services/dev_runtime
       cd services/api && python -m pytest -q tests'
   ```
   `verify-in.env`는 `DB_PORT=5432`로 바꾼 사본(컨테이너가 DB 네트워크를 공유하므로).
   저장소 전체(`node_modules` 포함)를 복사하면 매우 느리니 필요한 폴더만 복사한다.
4. 정리: `$C down -v`

## 3. 2026-11-24 기준 결과 (part/소병선-backend-test, b5c8caa)

| 묶음 | 결과 |
| --- | --- |
| API 단위(DB 없음) | 35 passed |
| 추천 + 분석 워커 (통합) | 79 passed, 1 skipped |
| API (통합) | 87 passed, 1 skipped |
| 샘플 변조 | 32 passed |
| 실행 순서 반대 / 같은 DB 재실행 | 모두 통과 |
| Playwright UI (`tests/ui`) | **미실행** — CI에서 확인 필요 |
| tools 단위 | 1 실패 (로컬 `apps/mobile/.env.example` 변경 때문, 코드 무관) |
