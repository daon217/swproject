# 공동개발 시작 안내

전체 서비스 실행은 [WORKSPACE.md](WORKSPACE.md)를 먼저 확인하세요. 이 문서는 VPN·SSH와 기존 DB/API 접속의 상세 안내입니다.

## 사용하는 구조

GitHub는 코드를 공유하고, 소병선 PC의 Docker는 공통 개발 API와 DB를 실행합니다.
각 팀원은 자기 PC에서 담당 코드를 개발하고, Tailscale 사설망 + SSH 터널을 통해 공통 API에 접속합니다.
회원·상품·고객센터 DB 3개는 유지합니다. DB 비밀번호를 프론트엔드에 배포하지 않습니다.
호스트를 끄거나 절전하면 공통 API가 중단됩니다. 본인 PC에 독립 DB를 실행하는 방식도 지원합니다.

## 담당자와 작업 위치

| 담당자 | 브랜치 | 코드 위치 | 공통 환경 사용 |
| --- | --- | --- | --- |
| 소병선 | part/소병선-backend | services/api, infra | 공통 서버 실행, 마이그레이션, 백업, 접근 등록 |
| 최준서 | part/최준서-collector | services/collector | 수집 관측을 내부 적재 API로 전송 |
| 이다온 | part/이다온-vision | services/vision | OCR 코드 개발; 분석 계약은 별도 구현 필요 |
| 박정우 | part/박정우-recommendation | services/recommendation | 임베딩·추천 코드 개발; 현재 벡터 모듈은 API 서비스 내부 Python 함수 |
| 김호진 | part/김호진-web | apps/web | 터널 주소로 상품·식품 목록 조회 |
| 서지웅 | part/서지웅-extension | apps/extension | 확장 프로그램에서 로컬 터널 접근 권한을 개발 설정에 지정 |

## 1. 모두 준비할 것

- Git, Python 3.11 이상(권장 3.12), 편집기, OpenSSH 클라이언트.
- 집에서 공통 서버를 쓰려면 [Tailscale](https://tailscale.com/download/windows) 설치 후 각자 계정으로 로그인.
- Docker Desktop(Linux 컨테이너)은 호스트 또는 독립 DB를 실행할 사람에게 필요합니다.
- Node와 패키지 매니저, OCR·추천 라이브러리는 각 담당 코드의 버전·잠금 파일이 올라온 뒤 그 기준으로 설치합니다. 아직 코드가 없는 파트의 실행 성공을 보장하지 않습니다.
- 이 비상업 학생 프로젝트는 Tailscale Personal 무료 범위에서 사용합니다. 실제 계정의 플랜을 확인하고 유료 플랜/카드 등록은 하지 않습니다. 현재 공식 안내는 Personal 최대 6명이며 개별 장치 공유도 지원합니다.

처음인 경우:
```powershell
git clone https://github.com/daon217/swproject.git
cd swproject
git fetch origin
git switch "part/김호진-web"
```
브랜치 이름은 본인 것으로 바꾸세요. 이미 swproject가 있다면 다시 clone하지 말고 그 폴더로 이동합니다.

공통 변경 PR이 main에 병합된 후 각자의 브랜치에서:
```powershell
git status
git fetch origin
git merge origin/main
py tools/team_dev.py doctor --role client
```
미커밋 변경이 있으면 먼저 본인의 변경을 정리합니다. 충돌 시 강제 푸시/초기화하지 않습니다.
공통 변경이 아직 PR 상태라면 검토를 위해 `git merge "origin/part/소병선-backend"`로 가져올 수 있습니다. 팀원이 main을 받아도 공통 파일이 없으면 PR 병합 여부부터 확인하세요.

## 2. 호스트 소병선: 처음 준비

기존 DB 비밀번호와 볼륨은 그대로 사용합니다. 저장소 루트에서:
```powershell
py services/api/dev.py init
py tools/team_dev.py doctor --role host
py services/api/dev.py up
py infra/db/db.py check
py tools/team_dev.py check --port 8000
```
init은 기존 .env를 덮어쓰지 않습니다. 첫 가상 샘플이 필요한 경우에만 `py services/api/dev.py seed`를 실행합니다.
공유 서버에 붙여야 하는 .env나 DB 백업은 Git에 올리지 않습니다.

## 3. 각 팀원: 본인 접속 키 만들기

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\kkulpick_team"
```
이미 파일이 있으면 덮어쓰지 말고 기존 키를 사용합니다. **kkulpick_team.pub만** 소병선에게 전달합니다.
확장자가 없는 파일은 개인키이므로 전송하거나 저장소에 올리지 않습니다.

## 4. 호스트: 장치 공유와 공개키 등록

Tailscale 관리자 화면 Machines에서 호스트 PC 한 대를 각 팀원 계정에 공유하고 팀원은 초대를 수락합니다.
계정 비밀번호를 함께 사용하지 않습니다. 이 초대와 로그인은 본인 계정에서 직접 수행해야 합니다.
받은 .pub 파일은 아래 예시처럼 서로 다른 이름으로 Downloads에 저장합니다.

```powershell
py infra/team/team.py enroll junseo "$env:USERPROFILE\Downloads\junseo.pub"
py infra/team/team.py enroll daon "$env:USERPROFILE\Downloads\daon.pub"
py infra/team/team.py enroll jeongwoo "$env:USERPROFILE\Downloads\jeongwoo.pub"
py infra/team/team.py enroll hojin "$env:USERPROFILE\Downloads\hojin.pub"
py infra/team/team.py enroll jiwoong "$env:USERPROFILE\Downloads\jiwoong.pub"
py infra/team/team.py home
```
실제로 받은 파일만 등록합니다. 출력된 호스트 100.x 주소와 서버 SHA256 지문을 팀원에게 전달합니다.
추가 등록 후에는 home을 다시 실행하고 기존 팀원은 터널을 재접속합니다.
방화벽 때문에 실패할 때만 팀 VPN/팀원 주소에서 TCP 2222에 접근하도록 제한된 허용 규칙을 추가합니다.
DB 포트, 공유기 포트포워딩 또는 전체 방화벽 해제는 필요하지 않습니다.

## 5. 팀원: 공통 서버 연결

아래 주소를 호스트가 전달한 실제 100.x 주소로 교체합니다.
```powershell
py tools/team_dev.py connect 100.101.102.103
```
처음 표시되는 서버 지문이 호스트가 보낸 것과 일치할 때 yes를 입력합니다. 창은 열어 둡니다.
새 PowerShell에서 프로젝트 폴더로 이동한 뒤:
```powershell
py tools/team_dev.py check
```

| 항목 | 팀원 접속 주소 |
| --- | --- |
| API 기본 주소 | http://127.0.0.1:18000 |
| API 상태 | http://127.0.0.1:18000/health |
| API 사용 설명 | http://127.0.0.1:18000/docs |
| 요청·응답 명세 | http://127.0.0.1:18000/openapi.json |
| 상품 | http://127.0.0.1:18000/v2/offers?selected_domain=product |
| 식품 | http://127.0.0.1:18000/v2/offers?selected_domain=food |

18000이 사용 중이면 `connect 실제IP --port 18001`, `check --port 18001`로 맞춥니다.
가상 샘플은 24시간 뒤 조회 목록에서 빠질 수 있습니다. 빈 items는 접속 실패와 다릅니다.
휴대폰·에뮬레이터의 localhost는 개발 PC가 아니므로 위 주소를 그대로 사용할 수 없습니다. 모바일 연결은 담당과 개발 장치가 확정된 뒤 구성합니다.

## 6. 파트별 연동 규칙

- 웹: 프로젝트의 로컬 환경변수에 API 기본 주소만 지정합니다. 내부 토큰·DB 비밀번호·Claude 키는 브라우저 코드에 넣지 않습니다.
- 웹 CORS: 기본 origin은 http://localhost:3000입니다. 127.0.0.1:3000, localhost:5173 등 다른 origin이 필요하면 소병선이 services/api/.env의 DEV_ORIGINS에 쉼표로 구분해 추가한 뒤 home을 재실행합니다. 포트까지 일치해야 합니다.
- 확장: 개발용 host_permissions를 로컬 API 주소에 맞춥니다. 수집 토큰을 확장에 포함하지 않습니다.
- 수집: `POST /internal/v2/crawl-runs/{run_id}/observations`, Authorization Bearer 토큰을 사용합니다. 예시는 services/api/fixtures/offer.json, 상세는 /docs입니다. 호스트의 COLLECTOR_TOKEN은 수집 담당 서버에만 비공개 전달합니다. 실제 수집 도메인은 호스트의 CATALOG_URL_HOSTS에 등록해야 합니다.
- 추천/OCR: 기존 벡터 저장소 준비와 모델 추론 서비스 완성은 다릅니다. 아직 원격 임베딩 쓰기 API가 없으므로 현재 내부 DB 함수를 HTTP로 호출할 수 있다고 가정하지 않습니다. 담당자의 실행 코드와 모델명·차원·입출력 계약을 PR로 받아 연결합니다.
- DB 스키마: 공통 DB에 임의 수동 변경을 하지 않습니다. 마이그레이션 파일을 커밋하고 소병선이 백업 후 적용합니다. 호스트 DB를 지우는 down -v는 사용하지 않습니다.
- Claude: 지원받은 API 크레딧은 서버에서만 사용하며 환경 구성 점검은 Claude API를 호출하지 않습니다.

## 7. 호스트 백업과 종료

작업 종료 전과 마이그레이션 전:
```powershell
py tools/team_dev.py backup
```
3개 DB의 custom-format dump와 SHA256 manifest를 `infra/team/local/backups/시각-ID`에 저장합니다.
완료된 백업은 manifest.json이 있습니다. 실패한 폴더/partial 파일을 완료된 백업으로 취급하지 않습니다.
백업은 DB별로 순차 생성되므로 DB 3개 전체의 동일 시점 원자적 스냅샷은 아닙니다.
명령은 아카이브 목록을 검사합니다. CI에서는 별도 임시 DB로 복원 후 샘플 조회까지 검증합니다.
백업은 같은 PC 안에 있으므로 완료 폴더를 별도 개인 저장장치에도 복사하세요. 자동 스케줄/외부 백업은 아직 설정하지 않았습니다.
DB 역할 비밀번호, API 토큰, SSH 개인키는 이 데이터 백업에 포함하지 않습니다. 기존 .env와 역할 초기화 스크립트를 별도로 보존해야 전체 서비스 복구가 가능합니다.
실제 DB에 덮어쓰는 복구는 제공하지 않습니다. 먼저 별도 PostgreSQL 17+pgvector 환경에서 역할을 초기화하고 pg_restore로 검증한 뒤 전환합니다.

공유만 종료: `py infra/team/team.py stop`. 키 회수: `py infra/team/team.py revoke junseo` 후 나머지 사용자는 home으로 다시 시작합니다.
서버를 업데이트할 때는 팀에 사용 중단을 알리고 백업 → 코드 갱신 → home → check 순서로 진행합니다.

## 8. 완료 확인과 아직 필요한 것

- 저장소 자동 검사: API 패키지, 실제 PostgreSQL/pgvector, 마이그레이션, 권한, 공통 API 터널, 미등록 키 차단, DB 포워딩 차단, 백업 복원.
- 실제 접속 완료 조건: 집이 다른 팀원 1명 이상이 check 성공, 호스트와 같은 offer_id 조회, 수집 담당이 인증된 샘플 적재 성공.
- 저장소 소유자: .github/ADMIN_SETUP.md에 따라 main 보호와 팀원 1명 리뷰를 적용. 보호가 문서만 있고 실제 적용되지 않은 상태는 완료가 아닙니다.
- 모든 파트 코드가 실행되는 환경 완성에는 담당자의 코드·의존성 파일·실행 명령·사용 포트·필수 환경변수 이름이 필요합니다. 비밀값 자체는 PR에 올리지 않습니다.
- 회원·결제·고객센터 업무 기능, 작업 큐, 실제 모델 추론 및 배포는 현재 공통 개발 API와 별도 구현 범위입니다.

공식 참고: [장치 공유](https://tailscale.com/docs/features/sharing), [무료 플랜](https://tailscale.com/docs/account/manage-plans/free-plans-discounts), [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
