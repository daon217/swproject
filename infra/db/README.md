# 꿀픽 DB 개발환경 — 소병선 담당

회원·상품·고객센터를 독립 PostgreSQL 데이터베이스로 유지합니다. 개발비를 줄이기 위해 PostgreSQL 컨테이너 하나에 배치합니다. DB를 세 개의 schema로 바꾼 구조가 아닙니다.

현재 완료 범위는 **DB 생성·권한 분리·pgvector·데이터 보존·실행 검증**입니다. 업무 테이블 61개, ORM, Alembic 마이그레이션, FastAPI 및 공용 서버 배포는 아직 포함하지 않습니다. 최종 테이블은 기술 명세 v2.4를 검토하여 후속 마이그레이션으로 추가합니다.

## 1. 처음 실행

Docker가 이미 설치되어 있다면 실행만 해 두세요. Docker Compose v2(2.20 이상)와 Python 3.10 이상이 필요합니다. Windows는 Docker Desktop의 Linux 컨테이너 모드를 사용합니다. 아래 명령은 저장소 루트에서 실행합니다. Windows에서 `python`이 안 되면 `py`를 사용하세요.

```sh
python infra/db/db.py init
python infra/db/db.py up
python infra/db/db.py status
```

`init`은 임의 비밀번호 7개를 로컬 `.env`에 만들며, 기존 파일을 덮어쓰지 않습니다. `up`은 이미지 다운로드, DB 초기화, 정상 기동 대기, DB별 접속·권한·벡터 연산 검증을 실행합니다. 첫 실행은 이미지 다운로드 시간이 필요합니다.

각 DB의 `PASS`와 마지막 `PASS: catalog pgvector distance query`가 나오면 환경 확인 완료입니다. 업무 테이블이 비어 있는 것은 현재 단계에서 정상입니다.

## 2. 접속 정보

DBeaver 등 SQL 도구에서 PostgreSQL 연결 3개를 만드세요. 호스트 `127.0.0.1`, 포트 `5433`입니다. 비밀번호는 본인 `infra/db/.env`에서 확인합니다.

| 용도 | Database | 개발/마이그레이션 사용자 | 비밀번호 항목 |
| --- | --- | --- | --- |
| 회원·구독·결제·관리자 | kkulpick_member | kkulpick_member_owner | MEMBER_OWNER_PASSWORD |
| 상품·식품·중고·제휴·수집·벡터 | kkulpick_catalog | kkulpick_catalog_owner | CATALOG_OWNER_PASSWORD |
| 고객센터·대화 | kkulpick_support | kkulpick_support_owner | SUPPORT_OWNER_PASSWORD |

앱 실행 계정은 각각 `kkulpick_member_app`, `kkulpick_catalog_app`, `kkulpick_support_app`이며 `*_APP_PASSWORD`를 사용합니다. 앱에는 테이블 생성·삭제 권한과 다른 업무 DB 접속 권한이 없습니다. 개발/마이그레이션은 owner 계정, API의 일반 CRUD는 app 계정을 사용하세요. `postgres`는 초기화·유지보수 전용이며 API에 넣지 않습니다.

업무 테이블은 각 DB의 `app` schema에 생성합니다. `public`은 catalog의 vector 확장 등 공통 확장용입니다. owner가 `app`에 만든 새 테이블/시퀀스에 app의 CRUD/시퀀스 사용 권한을 자동 부여합니다. 반드시 해당 owner로 마이그레이션하세요. postgres로 테이블을 생성하면 이 기본 권한이 적용되지 않습니다.

SQL 콘솔을 별도 설치하지 않아도 사용할 수 있습니다.

```sh
python infra/db/db.py psql member
python infra/db/db.py psql catalog
python infra/db/db.py psql support
```

catalog에서 예시 연산: `SELECT '[1,2,3]'::vector <-> '[1,2,3]'::vector;` 결과는 0입니다. 이 3차원 예제는 실제 임베딩 차원을 정한 것이 아닙니다. 임베딩 모델/차원 확정 후 실제 vector 컬럼을 만듭니다.

향후 SQLAlchemy asyncpg 연결 형식(아직 드라이버/백엔드는 설치하지 않음):

```text
postgresql+asyncpg://kkulpick_member_app:<MEMBER_APP_PASSWORD>@127.0.0.1:5433/kkulpick_member
postgresql+asyncpg://kkulpick_catalog_app:<CATALOG_APP_PASSWORD>@127.0.0.1:5433/kkulpick_catalog
postgresql+asyncpg://kkulpick_support_app:<SUPPORT_APP_PASSWORD>@127.0.0.1:5433/kkulpick_support
```

각 DB별로 연결 풀과 Alembic 이력을 분리할 예정입니다. DB 간 일반 외래키나 직접 JOIN은 사용하지 않습니다. 같은 Docker 네트워크의 서비스에서는 호스트/포트를 `postgres:5432`로 바꿉니다. 컨테이너 안의 localhost는 그 컨테이너 자신을 가리킵니다.

## 3. 일상 사용과 데이터 보존

```sh
python infra/db/db.py check
python infra/db/db.py logs
python infra/db/db.py stop
python infra/db/db.py up
python infra/db/db.py down
```

`stop`은 정지, `down`은 컨테이너 제거입니다. 둘 다 named volume의 DB 데이터는 남깁니다. `down -v` 또는 Docker의 volume 삭제는 데이터를 지우므로 평소 사용하지 마세요. 일반 CLI에 데이터 초기화 명령을 넣지 않았습니다.

초기화 스크립트는 **데이터 볼륨이 비어 있는 첫 실행에서만** 실행됩니다. 기존 DB에서 `.env` 수정은 비밀번호 변경이 아닙니다. 비밀번호를 바꾸려면 DB의 `ALTER ROLE`과 로컬 설정을 함께 변경해야 합니다. `.env`를 분실한 상태에서 재생성해도 기존 DB 비밀번호는 복구되지 않습니다.

첫 초기화가 중간에 실패하면 부분 초기화된 볼륨이 남을 수 있습니다. 로그로 원인을 먼저 해결하세요. 사용할 데이터가 전혀 없는 첫 설정임을 확인한 경우에만 해당 개발 볼륨을 삭제하고 다시 시작할 수 있습니다. 기존 데이터가 있으면 삭제하지 말고 개별 복구합니다.

5433 포트 충돌 시 시작 전에 `.env`의 `DB_PORT`를 비어 있는 포트로 변경합니다. 접속 도구와 API 설정도 같은 포트를 사용해야 합니다.

## 4. 공동 개발 방식

- GitHub에는 Compose·초기화 코드·마이그레이션·가상 샘플을 공유합니다. DB의 실제 행 데이터가 GitHub로 동기화되지는 않습니다.
- 현재는 각자 PC에 독립된 동일 구조를 실행합니다. 팀원이 볼 데이터를 맞추는 작업은 다음 단계의 마이그레이션과 seed로 수행합니다.
- 모두가 동일한 실시간 데이터를 사용하려면 별도 공용 DB 호스트와 접속 설정이 필요합니다. 현재 이 환경은 localhost에만 열려 있어 외부 팀원이 직접 접속할 수 없습니다.
- 공용 개발 환경은 별도 호스트/자격증명/백업을 정한 뒤 구성합니다. 개인 PC의 DB 포트를 인터넷에 공개하지 않습니다.
- 웹·확장 앱은 FastAPI를 통해 접근합니다. 수집기도 합의된 내부 적재 API를 사용하며 DB 비밀번호를 배포하지 않습니다.
- `.env`, 원본 크롤링 덤프, 실제 회원 데이터, API 키를 커밋하지 않습니다. Claude API는 이 DB 기동 과정에서 호출하지 않습니다.

## 5. 구성 선택과 제한

- 이미지 `pgvector/pgvector:0.8.7-pg17-trixie`: PostgreSQL 17 계열 + pgvector 0.8.7을 팀 공통 기준으로 사용합니다. 최신 태그를 자동 추적하지 않습니다. 태그는 재빌드될 수 있으므로 배포 단계에서 이미지 digest까지 고정합니다.
- PostgreSQL 한 프로세스: 개발 메모리 부담을 줄입니다. DB/계정은 분리되지만 서버 장애·자원 한도는 공유합니다. 운영의 고가용성 구성은 아닙니다.
- pgvector는 catalog DB에만 설치합니다. 별도 벡터 DB 비용은 없습니다. 임베딩 생성은 별도 모델 실행 단계입니다.
- 저장 시각은 UTC, 접속은 호스트 인증 SCRAM, 외부 바인딩은 `127.0.0.1`입니다. 로컬 개발 전용으로 TLS는 아직 설정하지 않았습니다.
- DB 최대 연결 60, shared_buffers 128MB, 앱 쿼리 시간 제한 15초는 개발 시작값입니다. 후속 FastAPI/worker 풀의 합을 예산 안에서 설정하고 실제 부하로 조정합니다.
- named volume은 백업이 아닙니다. 공용 DB 도입 전에 3개 DB별 백업·복구 검증을 추가합니다.
- 기존 PC에서 사용하므로 별도 클라우드 요금은 발생하지 않습니다. 전기·디스크 등의 비용까지 0이라는 뜻은 아닙니다.

## 6. 검증과 다음 작업

`.github/workflows/database.yml`은 임시 DB를 실제 기동하여 3개 DB 인증, owner DDL, app DDL 차단, app 교차 DB 접속 차단, pgvector 계산을 확인합니다. 컨테이너를 재생성하고 재확인하여 볼륨 초기화 상태도 검증합니다. 임시 CI 자격증명만 사용하며 실제 개발 DB에 접근하지 않습니다.

다음 순서: ① DB별 Alembic 기반과 정규화 테이블 ② 가상 샘플 데이터 ③ FastAPI 연결 풀/세션 ④ 회원 인증 및 수집 적재 API ⑤ 공용 통합 환경. 이번 PR은 ① 이전의 실행 기반입니다.

공식 근거:
- https://github.com/pgvector/pgvector — 확장 설치와 PostgreSQL 버전별 Docker 이미지
- https://hub.docker.com/_/postgres — 첫 실행 초기화 및 볼륨/비밀번호 동작
- https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html — 신규 객체 기본 권한
- https://www.postgresql.org/docs/17/ddl-schemas.html — DB와 schema 구분
