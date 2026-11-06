# 팀원 개발환경 사용 안내

현재 기본 방식은 **팀원마다 자기 PC의 Docker에서 독립 서버와 DB를 실행**하는 것입니다.
소병선 PC, Oracle, VPN, SSH 공개키 등록, Claude API 키가 필요하지 않습니다.
GitHub는 코드·마이그레이션·가상 샘플을 공유합니다. DB 내용과 비밀번호는 자동 공유되지 않습니다.
인터넷은 최초 이미지/패키지 다운로드·Git 작업에 필요하며, 실제 수집/외부 AI 연동에도 필요합니다.

## 1. 모두 준비할 것

- Git, Python 3.11 이상(권장 3.12), Docker Desktop의 Linux 컨테이너 모드.
- Windows는 Docker Desktop에서 요구하는 WSL 2 환경을 준비하고 Docker Desktop을 켭니다.
- 웹·관리자·모바일 소스를 직접 개발할 사람은 저장소 `.nvmrc`의 Node 22(22.13 이상)도 설치합니다.
- Docker에서 DB·API만 실행할 때는 호스트에 PostgreSQL, Redis, pip 패키지나 Node를 따로 설치하지 않습니다.
- OCR/임베딩 모델·GPU는 해당 담당자만 준비합니다. 최초 공통 점검에는 필요하지 않습니다.
- 용량이 부족한 PC는 아래 core 모드부터 시작합니다. 전체 환경 및 AI 이미지의 실제 자원 소모는 별도 확인합니다.

## 2. 코드 받기 — 본인 브랜치 유지

공통 환경 변경의 병합 상태는 아래 PR #3에서 확인합니다. 병합 전에는 `part/소병선-backend`, 병합 후에는 `origin/main`에서 가져옵니다.
[PR #3](https://github.com/daon217/swproject/pull/3)을 팀원 1명 이상 검토 후 main에 병합하는 규칙을 유지합니다.

처음 받는 사람만 실행:
```powershell
git clone https://github.com/daon217/swproject.git
cd swproject
```
이미 폴더가 있으면 그 프로젝트 폴더로 이동합니다. 다시 clone하거나 기존 폴더를 삭제하지 않습니다.
```powershell
git status
git fetch origin
```
미커밋 변경이 있으면 본인의 작업을 먼저 커밋/보관합니다. 강제 초기화하지 않습니다.
아래에서 **본인의 브랜치 한 개만** 선택합니다.

| 담당자 | 브랜치 | 담당 폴더 |
| --- | --- | --- |
| 소병선 | part/소병선-backend | services/api, infra, tools |
| 이다온 | part/이다온-vision | services/vision |
| 박정우 | part/박정우-recommendation | services/recommendation |
| 최준서 | part/최준서-collector | services/collector |
| 김호진 | part/김호진-web | apps/web |
| 서지웅 | part/서지웅-extension | apps/extension |

예시 — 웹 담당자:
```powershell
git switch "part/김호진-web"
git merge "origin/part/소병선-backend"
```
공통 환경 PR 병합 전 필요한 변경을 본인 브랜치에 반영하는 명령입니다. 충돌이 나면 해당 파일을 검토해 해결합니다.
병합된 뒤부터는 본인 브랜치에서 `git fetch origin`, `git merge origin/main`으로 동기화합니다.
소병선 브랜치를 사용하는 본인은 `git pull --ff-only`로 갱신합니다. 모든 팀원이 소병선 브랜치에 작업하지 않습니다.

## 3. 처음 실행 — DB 3개 + API

저장소 루트(README.md와 tools 폴더가 보이는 위치)의 PowerShell에서 한 줄씩 실행합니다.
```powershell
py tools/workspace.py doctor
py tools/workspace.py init
py tools/workspace.py up --scope core
py tools/workspace.py seed
py tools/workspace.py check --scope core
```
- `doctor`: Python·Git·Docker·Linux 컨테이너 확인. FAIL이 있으면 해당 프로그램부터 준비합니다.
- `init`: PC마다 새 비밀번호/토큰 생성. 기존 파일은 덮어쓰지 않습니다. 웹·관리자·모바일 `.env.local`도 없을 때만 생성합니다.
- `up --scope core`: PostgreSQL 한 컨테이너 안의 독립 DB 3개, 마이그레이션, FastAPI 실행.
- `seed`: 실제 수집 대신 가상 상품 1개의 가격·URL 변경 관측 2건을 적재합니다. 재실행하면 관측 이력이 추가됩니다.
- `check --scope core`: 실제 API·상품/식품 조회·OpenAPI·DB 3개 권한/연결/pgvector 검증.
- Mac/Linux에서는 `py`를 `python3`로 바꿉니다. ARM 기기는 이미지 지원 여부를 확인해야 하며 현재 Docker 통합 CI는 Linux x86-64입니다.

| 주소 | 용도 |
| --- | --- |
| http://127.0.0.1:8000/docs | API 명세·요청 테스트 |
| http://127.0.0.1:8000/health | API·카탈로그 DB 상태 |
| http://127.0.0.1:8000/v2/offers?selected_domain=product | 상품 목록 |
| http://127.0.0.1:8000/v2/offers?selected_domain=food | 식품 목록(초기 샘플 없음) |
| 127.0.0.1:5433 | 자기 PC의 PostgreSQL 접속 |

샘플 상품은 24시간 후 신선도 조건으로 목록에서 빠질 수 있습니다. 다시 `seed`하면 새 관측이 들어옵니다.
DB 3개를 생성하지만 회원·고객센터 업무 테이블/기능까지 구현된 것은 아닙니다.

## 4. 담당 작업 실행

### 웹·관리자

core 환경을 켠 뒤 새 PowerShell에서:
```powershell
cd apps/web
npm ci
npm run dev
```
웹은 http://localhost:3000, 관리자는 `apps/admin`에서 같은 명령을 실행하고 http://localhost:3001을 사용합니다.
`init`이 만든 `.env.local`의 `INTERNAL_API_URL=http://127.0.0.1:8000`을 확인합니다.
예전에 공용 서버를 쓰던 사람은 기존 값 `18000`을 `8000`으로 직접 바꾸고 개발 서버를 다시 시작합니다.
`npm.ps1` 실행 정책 오류가 나면 같은 명령을 `npm.cmd ci`, `npm.cmd run dev`로 실행합니다.

### 확장

Chrome의 `chrome://extensions` → 개발자 모드 → 압축해제된 확장 프로그램 로드 → `apps/extension`.
확장 버튼에서 API 포트 **8000** → API 확인. 자기 PC의 API에 연결하며 SSH 터널은 필요 없습니다.
소스 변경 후 확장 관리 화면에서 새로고침합니다. 현재 기능은 연결 점검이며 캡처·사이드바는 별도 개발입니다.

### 백엔드·수집·OCR·추천

- 소병선: `services/api/kkulpick` 소스를 수정하면 로컬 API가 자동 재시작합니다. 의존성·마이그레이션 수정 후에는 `up --scope core`를 다시 실행합니다.
- 최준서: 자기 API의 `/internal/v2/crawl-runs/{run_id}/observations`에 관측을 전송합니다. 자기 `services/api/.env`의 `COLLECTOR_TOKEN`을 서버 코드에서 읽습니다. 실제 수집 도메인은 같은 파일의 `CATALOG_URL_HOSTS`에 쉼표 구분으로 등록하고 재실행합니다.
- 이다온·박정우: 전체 연결 환경이 필요하면 아래 full 모드를 사용합니다. OCR/임베딩 CPU 의존성 이미지는 [전체 환경 안내](WORKSPACE.md)의 선택 설치를 따릅니다. 기본 어댑터는 연결용이고 업무 처리에는 501을 반환합니다.
- 브라우저/확장/모바일에는 DB 비밀번호·내부 수집 토큰·Claude 키를 넣지 않습니다.

### 모바일

`apps/mobile`에서 `npm ci`, `npm start`. Android 에뮬레이터용 기본 API는 `http://10.0.2.2:8000`입니다.
실제 휴대폰 접속은 별도 설정이 필요합니다. 현재 API는 PC 내부 주소에만 열리며 다른 기기에서 바로 접속되지 않습니다.

## 5. 전체 연결 환경이 필요할 때

```powershell
py tools/workspace.py up --scope full
py tools/workspace.py check --scope full
```
core에 웹·관리자, Redis 2개, Celery 작업자, OCR/추천/수집 개발 어댑터, 비공개 임시 저장소를 추가합니다.
실제 크롤링·모델 가중치 다운로드·Claude 유료 호출은 하지 않습니다.
Docker의 웹/관리자는 빌드 결과이므로 수정 후 `up`으로 재빌드합니다. 소스 자동 반영은 4장의 `npm run dev`를 사용합니다.
같은 포트의 Docker 웹과 `npm run dev`를 동시에 켜지 않습니다.
full에서 core로 가볍게 전환할 때는 먼저 `py tools/workspace.py stop`, 그 다음 `up --scope core`를 실행합니다.
`up --scope core`만 실행하면 이미 켜져 있던 다른 컨테이너를 자동으로 끄지는 않습니다.

## 6. 매일 시작·종료·갱신

모든 명령은 저장소 루트에서 실행합니다. Docker Desktop을 먼저 켜세요.

| 목적 | PowerShell 명령 |
| --- | --- |
| 개발 시작 | `py tools/workspace.py up --scope core` |
| 기본 환경 확인 | `py tools/workspace.py check --scope core` |
| 컨테이너 상태 | `py tools/workspace.py status` |
| 최근 오류 로그 | `py tools/workspace.py logs` |
| 가상 상품 다시 적재 | `py tools/workspace.py seed` |
| DB 백업 | `py tools/workspace.py backup` |
| 개발 종료 | `py tools/workspace.py stop` |
| 전체 연결 환경 시작 | `py tools/workspace.py up --scope full` |
| 전체 연결 환경 확인 | `py tools/workspace.py check --scope full` |

`--scope`를 생략하면 full이 기본값이므로 시작·점검 시 core/full을 명시합니다. `init`은 최초 준비에 사용하며 매일 실행할 필요가 없습니다.


```powershell
py tools/workspace.py up --scope core
py tools/workspace.py status
py tools/workspace.py backup
py tools/workspace.py stop
```
`npm run dev`나 `npm start`를 별도 창에서 실행했다면 그 창에서 `Ctrl+C`로 종료합니다. 이후 Docker Desktop을 종료해도 됩니다.
종료해도 Docker 볼륨의 데이터는 남습니다. `down -v`, Docker 볼륨 삭제는 하지 않습니다.
백업은 `infra/team/local/backups`에 DB별 dump로 저장되며 VPN 설정이 필요하지 않습니다. 다른 개인 저장장치에도 보관합니다.

코드를 갱신할 때는 미커밋 작업 확인 → 백업 → 본인 브랜치에 최신 공통 변경 반영 → `up` → `check` 순서로 진행합니다.
한 PC에 여러 복제 폴더를 만들어도 같은 Compose 프로젝트 이름을 쓰므로 DB가 자동 분리되지 않습니다. **PC당 실행용 checkout 한 개**를 사용하고 그 안에서 브랜치를 전환합니다.

### 개발한 코드 올리기

자신의 담당 브랜치에서 아래 순서로 확인합니다. `<변경한-파일-경로>`는 실제 수정한 파일로 바꾸며, 비밀값이 포함되지 않았는지 확인합니다.

```powershell
git branch --show-current
git status
git diff --check
git add <변경한-파일-경로>
git diff --cached
git commit -m "feat(web): 상품 목록 화면 구현"
git push
```

커밋 메시지의 영역과 설명은 본인 작업에 맞춥니다. 원격 추적이 없는 새 브랜치만 `git push -u origin "본인-브랜치명"`을 사용합니다.
GitHub에서 본인 브랜치를 head, `main`을 base로 PR을 만듭니다. 실행한 명령·결과·아직 연결하지 않은 기능을 적고 팀원 1명 이상 검토 후 병합합니다. [상세 협업 규칙](../CONTRIBUTING.md)을 따릅니다.

## 7. 자주 막히는 부분

| 상황 | 조치 |
| --- | --- |
| `py` 명령 없음 | Python 설치 시 launcher 포함, PowerShell 다시 열기 |
| Docker 연결 실패 | Docker Desktop 실행, Linux 컨테이너 모드 확인 |
| 폴더가 이미 있어 clone 실패 | 기존 프로젝트 폴더로 이동해서 fetch/pull |
| `tools/workspace.py` 없음 | 2장의 공통 환경 브랜치 반영 여부 확인 |
| API 포트 8000 충돌 | 기존 서버를 종료하거나 `services/api/.env`의 API_PORT 변경. 웹/확장/모바일의 주소도 함께 변경 |
| DB 포트 5433 충돌 | `infra/db/.env`의 DB_PORT를 변경한 뒤 up |
| 웹 포트 3000/3001 충돌 | Docker full을 stop한 뒤 core + npm dev 실행 |
| DB 비밀번호 불일치 | 기존 볼륨에 대응하는 기존 .env 복구. 비밀번호 파일만 새로 만들거나 DB를 삭제하지 않기 |
| 수정한 파이썬 코드가 실행되지 않음 | API 패키지 밖 파일·의존성·작업자는 up으로 재빌드, 로그 확인 |
| API는 되는데 웹/확장은 안 됨 | 기존 .env.local의 18000 주소, 확장 포트 확인 |

기존 VPN 공유를 이미 실행했다면 `py infra/team/team.py stop`으로 공유 게이트웨이도 종료합니다.
로컬 `up`은 저장된 VPN 주소가 있어도 공유 게이트웨이를 새로 실행하지 않습니다.
다시 공유할 때만 `workspace.py share`를 사용합니다. 공유 게이트웨이까지 상태/로그/종료를 처리하려면 `--shared`를 지정합니다.

## 8. 팀 간 공유 범위와 완료 기준

- 공유: 코드, DB 마이그레이션, 의존성 잠금 파일, 가상 샘플, API 계약.
- 미공유: 각 PC의 DB 데이터·비밀번호·API 키·백업. 실제 크롤링 결과는 나중에 정해진 적재 계약으로 전달합니다.
- `.env`, `.env.local`, DB 백업, 실제 개인 데이터는 커밋하지 않습니다.
- 팀원별 완료: `check --scope core` 성공, 자기 담당 화면/서비스가 자기 API에 연결, stop/up 후 데이터 유지.
- 각자 로컬 성공은 여러 팀원의 기능이 한 서버에서 통합 완료되었다는 뜻이 아닙니다. 공용 서버 통합은 다음 단계입니다.
