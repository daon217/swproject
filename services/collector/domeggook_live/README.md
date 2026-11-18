# 도매꾹 LIVE 크롤러와 백엔드 API 어댑터

기존에 검증한 도매꾹 Open API 수집 코드와 backend-release를 팀 저장소에서 독립 실행할 수 있도록 통합했다. 개인 PC 경로, 별도 연구 저장소, 실제 상품 파일을 의존하지 않는다. 다른 수집기나 팀 백엔드를 변경하지 않는다.

**기본 상태: 실제 상품 영구 저장·백엔드 전송 비활성.** 상세 HTML/이미지는 `desc.license.usable=false/unknown`이면 제외하며 true도 전체 메타데이터 저장/재이용 허가를 대신하지 않는다. API 키·실제 응답·개인 체크포인트·DB 데이터는 이 폴더에 포함하지 않는다.

## 검증 범위

2026-11-18 로컬 개발에서 실제 도매꾹 신규 ID **40개**, 신규 상세 정규화 **6개**를 확인했다. 발견 큐의 당시 실제 호출은 목록2회·상세8회(신규6+재조회2)였다. 이 README의 수치는 그 실제 검증 기록이며, 테스트용 합성 상품 수나 GitHub 업로드 과정의 새로운 수집 성공을 의미하지 않는다. 실제 상품 데이터는 업로드하지 않았다.

별도 승인된 격리 PostgreSQL17.12와 127.0.0.1 테스트 API에서 합성 매물1개·고유 관측6개·가격 이력5개를 검증했다. 동일 관측 재전송3회는 HTTP200, 동시 동일 요청은200/201로 처리되고 상품·관측·이력이 중복 증가하지 않았다. API 중단/재개, 실제 서버 저장 뒤 응답 누락을 모의한 재전송, API와 PostgreSQL 재시작을 확인했다. 3주기 전송은 실제 HTTP/DB를 사용했고 주기 사이 대기시간은 모의였다. 실제 도매꾹 DB 행은0개였다.

팀 저장소로 반입한 코드의 단위/계약 테스트 **46개가 통과**했다. 같은 코드의 명시적 승인 하네스에서도 새 격리 PostgreSQL/API 검증을 다시 실행해 합성 매물1개·관측6개·가격 이력5개와 중복/장애/재시작 검증이 통과했다. import, Python CLI와 PowerShell 상태 확인도 검증했다. 단위/계약 테스트는 네트워크·DB·실제 키 없이 동작하며, 선택적 실제 PG 테스트는 명시적 승인과 별도 개발 환경을 요구한다. 기존 실행 중인 로컬 watch를 이 업로드에서 중단하거나 교체하지 않는다.

## 설치와 실행

저장소 루트, Python3.12 기준:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r services/collector/domeggook_live/requirements.txt
.\.venv\Scripts\python.exe -m services.collector.domeggook_live --status
.\.venv\Scripts\python.exe -m services.collector.domeggook_live --discover-once --dry-run
.\.venv\Scripts\python.exe -m services.collector.domeggook_live --verify
```

실제 수집 시 `DOMEGGOOK_API_KEY`를 실행 계정 환경변수로 제공하거나 이 패키지 폴더의 Git 제외 `.env`에 설정한다. `.env.example`은 빈 설정 예시일 뿐 실제 키가 아니다. 키를 CLI 인수·로그·Git에 넣지 않는다.

```powershell
# 키를 안전하게 공급한 실행 환경에서만 사용한다.
.\.venv\Scripts\python.exe -m services.collector.domeggook_live --discover-once
.\.venv\Scripts\python.exe -m services.collector.domeggook_live --discover-watch
.\.venv\Scripts\python.exe -m services.collector.domeggook_live --refresh-once
.\.venv\Scripts\python.exe -m services.collector.domeggook_live --watch

# PowerShell 호환 진입점: 같은 Python/큐/원장을 사용한다.
.\services\collector\domeggook_live\Start-Domeggook.ps1 --watch -Python "$PWD\.venv\Scripts\python.exe"
```

`--once`는 기존 상품 갱신1주기, `--watch`는 발견+갱신+권한이 확인된 전송 반복이다. `--discover-watch`는 신규 발견/상세를 반복한다. `--cycles N`, `--interval`, `--limit`(갱신 범위), `--detail`, `--source domeggook`도 유지한다. `--dry-run`은 요청·키 읽기·상태 쓰기를 하지 않는다. `--status`는 집계/커서만 읽고 `--verify`는 로컬 설정·체크포인트 형식을 검사한다.

## 발견·갱신·예산

config.json의 기본 검색어는 갤럭시·아이폰·충전기·보조배터리·이어폰·키보드·마우스·모니터·노트북·휴대폰케이스·생활용품·주방용품·청소용품이다. 확인된 중분류 이하 카테고리는 discovery.categories에 넣을 수 있다. [공식 목록 API](https://docs.channel.io/domeggook_api/ko/articles/43780628)의 kw/ca/pg/sz를 사용한다. 존재하지 않는 카테고리는 공급자가 무시할 수 있어 예시 코드를 실제 기본값으로 넣지 않았다.

Discovery Queue는 페이지·검색어를 순회하며 원본 상품번호를 중복 제거해 상세 대기열로 넘긴다. 기본 페이지20개·대기열40개이며 대기열이 차면 새 페이지 요청을 멈추고 상세를 먼저 처리한다. 완료 페이지는 현재 탐색 회차에서 건너뛴다. 빈 결과/마지막 페이지 뒤 다음 검색어로 이동한다. 검색조건을 모두 처리한 회차는 최소24시간 뒤 다시 탐색한다. 상한은 config.json에 명시하며 대규모 카탈로그의 빠른 완전 수집을 보장하지 않는다.

Refresh Queue는 마지막 성공 확인 시각이 오래된 상품부터 갱신한다. 3600초는 재조회 대상이 되는 최소 간격이며 모든 상품을 매시간 갱신한다는 보장은 아니다. 원본 상품번호와 실제 옵션 코드를 유지하고 `(source, source_listing_id, variant_key)`로 구분한다. 표시명·URL·가격·배열 순서로 ID를 만들지 않고 불명확한 옵션은 격리한다.

| 요청 예산 | 기본값 |
|---|---:|
| 요청 간격 | 최소10초 |
| 전체 주기 | 6회, 재시도 포함 |
| 발견 / 갱신 | 4회 / 2회 |
| 발견 중 목록 | 최대2회 |
| 최근1시간 / KST 날짜당 | 12회 / 120회 |
| watch 간격 | 3600초 |

공식 문서의 분당180회·일일15000회는 목표 사용량이 아니다. [공식 제한 문서](https://docs.channel.io/domeggook_api/ko/articles/표준오류메세지-7a511249). 401/403/429, 리디렉션, 비JSON, API 본문 오류, 결과 불명확 요청은 영속 hold로 중단한다. 원장을 리셋해 한도를 우회하지 않는다. once는 budget_wait를 반환하고 watch는 다음 허용 시각까지 기다린다. 같은 계정의 다른 프로그램 호출도 공급자 제한에 포함된다.

## 상태·재개·개인 데이터

기본 상태는 이 패키지의 Git 제외 `data/`에 저장한다. `KKULPICK_STATE_DIR`로 다른 절대 경로를 지정할 수 있다. 상태에는 원본 ID/옵션 코드·검색 커서·요청 상태·시각·집계를 보존하고, 이용 권한이 미확인인 상품명·가격·본문·이미지 URL은 RAM에서만 처리한다. 메모리량도 설정 상한으로 제한한다.

완료된 ID/페이지 수신 확인은 원자 저장한다. 손상/빈 체크포인트를 몰래 초기화하지 않는다. 성공 응답과 ID 수신 확인 저장 사이 중단돼 본문을 잃으면 자동 재요청/성공 처리 대신 hold 또는 다음 허용 관측으로 보류한다. 같은 상태 디렉터리의 OS 잠금으로 중복 worker를 차단한다.

기존 로컬 크롤러를 계속 사용해도 된다. 이 업로드는 기존294개 상품/53개 HTTP 기록/11번가 ID/격리 원본을 삭제하거나 반입하지 않는다. 기존 상태를 재사용할 때는 현재 watch를 정상 종료한 뒤 기존 data 경로를 KKULPICK_STATE_DIR로 지정하고 config.json의 검색 조건이 기존 체크포인트와 같은지 확인한다. 기존 상품 JSON·.env를 Git에 복사하지 않는다. 선택적 legacy native_identity_manifest.json은 로컬에서 읽기만 하며 없는 경우 새 원본 ID 근거를 검증한다.

## 백엔드

`POST /internal/v2/crawl-runs/{run_id}/observations` 단일 v2 객체를 사용한다. DB 직접 연결 코드는 수집기/전송 모듈에 없다. `--backend-config backend_delivery.example.json`으로 별도 프로필을 읽으며 공급원 예산을 이 프로필에서 덮어쓸 수 없다.

실제 전송에는 backend_enabled, backend_owner_approved, live_authorized 모드, 승인된 HTTPS 주소, 필드별 storage/reuse 허용·근거·만료, 단가/MOQ 표시 합의가 필요하다. 토큰은 `KKULPICK_BACKEND_TOKEN` 환경변수로만 주입한다. 예시는 비활성이다. 승인되지 않은 실제 상품은 대기열에도 적재하지 않는다.

현재 계약에는 정확한 재고 수량·MOQ·최소 결제금액·이미지·사양 필드가 없다. 단가를 price로, 판매 가능/품절/종료를 availability로 매핑하고 수량·MOQ는 크롤러에 유지한다. 이 계약을 몰래 확장하지 않는다. 예상 최소 결제금액은 불명확한 배송 조건을 포함해 정확한 최종 금액으로 표시하지 않는다.

허용된 전송 대기열은 같은 관측 키·본문으로 내구성 재시도한다. 전송 완료 후 본문을 제거한다. 연결 오류/일시적5xx 등은 최대5회 지수 백오프, 인증/충돌/리디렉션은 hold, quarantine은 applied와 구분한다. 서버 중단 시 수집 체크포인트를 보존하고, 전송 대기열이 가득 차면 수집을 대기시킨다.

## 테스트와 자동 재시작

```powershell
.\.venv\Scripts\python.exe -m pip install -r services/collector/domeggook_live/requirements-dev.txt
.\.venv\Scripts\python.exe -B -m pytest -q services/collector/domeggook_live/tests
```

requirements.lock.txt는 반입 검증에 사용한 전체 테스트 환경 pin이다. 실제 개발 DB 테스트는 [devtest/README.md](devtest/README.md)를 따른다. 다른 팀의 API 파일과 스키마는 읽기 전용으로 참조하며 팀 DB나 실제 상품을 사용하지 않는다.

자동 재시작은 현재 watch와 교체 시점을 정한 후 등록한다. 이번 업로드는 예약 작업을 등록하지 않는다. PowerShell 작업 스케줄러에서 이 폴더의 Start-Domeggook.ps1 --watch를 실행하고, 작업 디렉터리를 저장소 루트로 지정한다. AtLogOn(로그인 시) 또는 승인된 서비스 계정의 AtStartup, MultipleInstances=IgnoreNew, 실패 시1분 간격 최대3회 재시작을 사용한다. 토큰은 작업 인수에 넣지 않는다. 재시작에도 동일 상태/원장/outbox를 사용하고 hold를 자동 해제하지 않는다.
