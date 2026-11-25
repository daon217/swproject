# 프론트 · 백엔드 통합 실행

서지웅의 `apps/extension`(Chrome 확장)과 `apps/mobile`(Expo 앱)을 소병선의 `services/api`에 연결했습니다. `apps/web`·`apps/admin`은 기존 개발 상태 확인용 화면이며 실제 사용자 UI는 아래 두 화면입니다.

## 처음 실행 — Windows PowerShell

Docker Desktop을 Linux 컨테이너 모드로 켜고, Python 3.11 이상과 Git을 설치합니다. 아래 명령은 저장소 루트에서 실행합니다. 작업 중인 수정 파일이 있다면 먼저 본인 브랜치에 커밋하세요. `git reset --hard`로 정리하지 마세요.

```powershell
cd C:\Users\사용자이름\swproject
git fetch origin
git switch main
git pull --ff-only origin main
py tools/workspace.py doctor
py tools/workspace.py init
py tools/workspace.py up --scope ui
py tools/workspace.py seed
py tools/workspace.py check --scope ui
```

최초 실행은 이미지·의존성 다운로드와 모바일 웹 빌드 때문에 몇 분 걸릴 수 있습니다. `init`은 기존 비밀번호와 개인 설정을 보존합니다. 각 PC의 DB는 독립이며 팀원 데이터가 자동 공유되지 않습니다.

| 대상 | 주소 / 내용 |
| --- | --- |
| 확장 UI 미리보기 | http://localhost:5174/preview.html |
| 모바일 웹 미리보기 | http://localhost:8081 |
| API 문서 | http://localhost:8000/docs |
| 실제 저장소 | Docker PostgreSQL 안의 회원·카탈로그·고객센터 DB 3개 |

5174·8081의 `/backend/`는 같은 Docker API로 전달됩니다. 화면 목업으로 자동 전환하지 않습니다. API가 꺼졌다면 오류가 표시됩니다. `seed`는 가상 주전자 상품의 가격·URL 갱신을 검증하는 예시이며 실제 쇼핑몰 데이터나 AI 추천을 생성하지 않습니다.

## 화면에서 확인할 기능

1. 확장 미리보기 오른쪽 **설정 → 로그인 → 회원가입**에서 테스트 계정을 만듭니다. 실제 개인정보 대신 가상의 정보를 사용하세요.
2. **마이페이지 → 개인정보 수정**에서 생년월일·성별·알레르기를 저장하고 새로고침해서 유지되는지 확인합니다.
3. **설정 → 고객지원**에서 메시지를 보내고 다시 들어와 저장된 내용을 확인합니다. 상담원 자동 답변은 제공하지 않습니다.
4. 미리보기 왼쪽에서 2MiB 이하 PNG/JPEG/WebP 이미지를 선택해 **분석 접수 테스트 → 분석 취소**를 확인합니다. 로그인해야 접수할 수 있습니다.
5. 같은 계정으로 모바일 웹에 로그인하면 회원 정보와 상담 내역을 같은 DB에서 읽습니다. 로그인 토큰과 바로가기 설정은 각 화면의 로컬 저장소에 별도로 보관됩니다.

OCR·추천 작업자가 미연결인 경우 분석은 `queued`로 남습니다. 접수·상태 조회·취소 기능을 검증할 수 있지만 실제 분석 결과가 나오는 상태는 아닙니다. 미리보기의 쇼핑몰 영역은 실제 쇼핑몰 브라우저가 아닙니다.

## 구독 테스트 — 실제 청구 없음

기본값은 결제 비활성입니다. 개발 테스트가 필요할 때만 `services/api/.env`에 아래를 추가하거나 기존 값을 수정합니다. 같은 키를 중복 작성하지 마세요.

```dotenv
APP_ENV=development
BILLING_MODE=mock
MOCK_PAYMENT_OUTCOME=succeeded
```

`py tools/workspace.py up --scope ui`로 설정을 적용하고 마이페이지의 프리미엄 화면에서 진행합니다. 화면에 **개발용 테스트 결제**가 표시됩니다. 카드번호·계좌정보를 입력하거나 실제 PG를 호출하지 않습니다. 자동 결제 해지 후에도 테스트 이용 기간은 유지됩니다. `pending`은 성공이나 실패로 단정하지 않고 결과 대기로 표시합니다. 대기 요청 해결은 백엔드의 내부 테스트 API에서 처리하며 내부 토큰을 프론트 환경변수에 넣으면 안 됩니다.

테스트 종료 후 `BILLING_MODE=disabled`로 되돌리고 다시 `up --scope ui`를 실행합니다. PG 선택·실결제 검증은 별도 작업입니다.

## 종료 · 다시 실행 · 로그

```powershell
py tools/workspace.py status --scope ui
py tools/workspace.py logs --scope ui
py tools/workspace.py stop --scope ui
py tools/workspace.py up --scope ui
```

보통 종료·재실행 시 DB 볼륨은 유지됩니다. `docker compose down -v` 또는 Docker Desktop의 볼륨 삭제는 데이터를 지우므로 일반 종료에 사용하지 마세요. 기존 `--scope core`는 DB·API만, `--scope full`은 UI와 기존 전체 개발 서비스까지 실행합니다.

## 프론트 소스 수정 시

Docker 미리보기는 빌드된 화면입니다. 코드 수정 후 `up --scope ui`로 재빌드합니다. 빠른 화면 수정은 로컬 Node.js 22와 npm을 사용합니다. Docker UI와 개발 서버의 포트가 겹치지 않게 먼저 `stop --scope ui` 후 `up --scope core`로 DB·API만 실행하세요.

확장 UI:

```powershell
cd apps/extension
npm ci
npm run preview:sidepanel
```

모바일 웹(별도 터미널):

```powershell
cd apps/mobile
npm ci
npm run web
```

로컬 개발 서버를 직접 사용할 때 API CORS 허용 목록에 `http://localhost:5174,http://127.0.0.1:5174,http://localhost:8081,http://127.0.0.1:8081`을 추가합니다. `infra/workspace/.env`의 `DEV_ORIGINS` 기존 값 뒤에 쉼표로 추가하고 `up --scope core`를 다시 실행합니다. Docker UI 프록시는 이 수동 설정이 필요 없습니다.

`apps/extension/.env.local`의 `VITE_API_BASE_URL`, `apps/mobile/.env.local`의 `EXPO_PUBLIC_API_BASE_URL`은 기본 `http://127.0.0.1:8000`입니다. Android 에뮬레이터는 `http://10.0.2.2:8000`으로 수정합니다. 휴대폰 실기기에서 localhost는 휴대폰 자신이므로 PC 연결 방법을 별도로 설정해야 합니다. 현재 Docker 포트는 PC 로컬에만 노출합니다.

화면 디자인만 목업으로 확인할 때는 `VITE_USE_MOCK_API=true` 또는 `EXPO_PUBLIC_USE_MOCK_API=true`를 명시합니다. 이때의 계정·결제·상품은 실제 DB 검증 결과가 아닙니다.

## 실제 Chrome 확장 설치

`apps/extension`에서 `npm ci`, `npm run build` 후 `chrome://extensions` → 개발자 모드 → **압축해제된 확장 프로그램을 로드** → `apps/extension/dist`를 선택합니다. `apps/extension` 루트가 아닙니다. API는 실행 중이어야 합니다. 확장 자동 캡처는 로그인 후 지원 상품 페이지에서 동작합니다. 분석 요청은 작업자가 연결되기 전에는 완료되지 않으며 30초 대기 후 취소됩니다.

모바일의 웹 미리보기는 네이티브 앱 설치·WebView 캡처 검증을 대신하지 않습니다. Android 개발 빌드 및 iOS 기기 테스트는 해당 환경에서 별도로 진행합니다.

## 자동 검증

GitHub **Actions → Frontend backend integration**은 매번 독립 Docker DB와 API를 띄우고 Chromium으로 실제 화면을 조작합니다. API 응답을 목업으로 가로채지 않습니다. 테스트 결제만 mock 모드를 사용하며 외부 결제·유료 AI 호출은 없습니다. 결과 화면과 실패 trace는 7일간 `frontend-integration-evidence` 아티팩트에 보관합니다.

로컬 재현은 mock 결제를 켠 `--scope ui` 환경에서:

```powershell
cd tests/ui
npm ci
npx playwright install chromium
npm test
```

테스트는 가상의 회원을 생성하고 마지막에 탈퇴를 접수합니다. 중간에 테스트가 실패하면 해당 테스트 회원이 남을 수 있습니다. 기존 팀원 계정을 수정하거나 삭제하지 않습니다. 서비스 재시작 시 데이터 보존, DB 권한 분리, 수집 갱신·중복 처리, 성능·마이그레이션 검증은 기존 별도 CI에서 수행합니다.
