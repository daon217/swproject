# 꿀픽 전체 공동개발환경

## 범위와 기준

2026-11-02 기술 명세서 4장(시스템), 7~10장(분석·OCR·수집·추천), 15~16장(임시 저장·운영)을 기준으로 구성합니다.
DB는 기존 독립 3개를 유지합니다. 오래된 단일 DB 설계나 Java/Spring 목록을 적용하지 않습니다.
이 문서는 **개발환경** 안내입니다. 개발용 health가 성공해도 OCR·회원·결제 등 업무 기능이 구현되었다는 뜻이 아닙니다.

| 구성 | 담당 | 현재 제공하는 환경 |
| --- | --- | --- |
| FastAPI + PostgreSQL/pgvector | 소병선 | 기존 적재·조회 API와 DB 3개, 마이그레이션·가상 데이터 |
| Redis Broker | 소병선 | 별도 인스턴스, AOF, noeviction, 128MB 한도 |
| Redis Cache | 소병선 | 별도 인스턴스, allkeys-lru, 64MB 한도; 개발 큐 결과도 짧게 저장 |
| Celery | 소병선 | development/vision/recommendation/collector 큐별 작업자, 각 동시성 1 |
| OCR HTTP 서비스 | 이다온 | FastAPI 연결 틀 + 별도 PaddleOCR/PaddlePaddle/OpenCV CPU 설치 이미지 |
| 추천 HTTP 서비스 | 박정우 | FastAPI 연결 틀 + Sentence-Transformers/CPU PyTorch/Claude SDK 이미지 |
| 수집 HTTP 서비스 | 최준서 | FastAPI 연결 틀, 기존 관측 적재 API·샘플 계약 |
| 사용자 웹 | 김호진 | Next.js/React/TypeScript/Tailwind, API 연결 확인 페이지 |
| Chrome 확장 | 서지웅 | MV3 로컬 개발 확장, 터널 API 연결 확인 |
| 모바일 | 배정 필요 | React Native/Expo 연결 확인 앱, Android JS 번들 검사 |
| 관리자 웹 | 배정 필요 | 별도 Next.js 개발 시작 화면·API 확인; 업무·인증 미구현 |
| 비공개 이미지 | 소병선 | Docker 볼륨, HTTP 공개 없음, 1시간 TTL 정리기 |

OCR·추천·수집은 `business_ready=false`를 반환합니다. `/internal/process`는 501입니다. `/internal/dev/probe`는 키 인증을 검사하는 연결 전용 요청이며 실제 화면을 분석하거나 사이트를 크롤링하지 않습니다.
Celery smoke 검사는 실제 Redis·작업자·HTTP·볼륨을 사용하나 분석 원장·Outbox·개인정보 삭제를 대신 구현하지 않습니다.

## 가장 먼저 실행

Windows: Docker Desktop을 Linux 컨테이너 모드로 켜고 저장소 루트 PowerShell에서 실행합니다.
필수: Git, Python 3.11 이상(권장 3.12), Docker Compose v2. Docker 안에서 웹·서비스를 실행하면 호스트 Node 설치는 선택입니다.
```powershell
git switch "part/소병선-backend"
git pull --ff-only
py tools/workspace.py init
py tools/workspace.py up
py tools/workspace.py check
```
처음에는 이미지·패키지 다운로드로 시간이 걸립니다. `init`은 기존 DB/API 설정과 비밀번호를 유지합니다.
이미 DB를 만들어 두었어도 기존 볼륨을 재사용합니다. `down -v`나 Docker 볼륨 삭제는 실행하지 않습니다.

| 주소/명령 | 용도 |
| --- | --- |
| http://localhost:3000 | 웹 개발 시작 페이지 |
| http://localhost:3001 | 관리자 개발 시작 페이지 |
| http://localhost:8000/docs | 기존 API 명세 |
| `py tools/workspace.py status` | 전체 컨테이너 상태 |
| `py tools/workspace.py check` | 실제 작업 전달·서비스 연결·캐시·임시 저장 검사 |
| `py tools/workspace.py logs` | 최근 개발 로그 |
| `py tools/workspace.py stop` | 전체 환경 중단, 데이터 보존 |
| `py tools/team_dev.py backup` | 기존 업무 DB 3개 백업 |

브로커/캐시/OCR/추천/수집은 호스트 포트를 열지 않고 Docker 네트워크 안에서 통신합니다.
명세의 HTTPS 운영 배포는 이 로컬 개발 HTTP 구성과 별도입니다.

## 각자 집에서 같은 환경 사용

계정·공개키 등록은 [팀 접속 안내](TEAM_DEVELOPMENT.md) 3~5단계를 따릅니다.
호스트는 `py tools/workspace.py share`로 전체 환경을 시작하고 Tailscale 주소에 SSH 게이트웨이를 엽니다.
팀원은 다음을 실행합니다. 실제 호스트 IP로 교체합니다.
```powershell
py tools/team_dev.py connect 100.101.102.103 --web
```
팀원의 API는 http://127.0.0.1:18000, 호스트 공통 웹은 http://127.0.0.1:18080 입니다.
팀원이 자신의 웹/관리자 코드를 수정할 때는 아래처럼 자기 PC의 개발 서버를 켜고 공통 API만 터널로 사용합니다.
VPN 로그인·장치 공유·키 등록·호스트 상시 켜짐은 실제 PC에서 필요합니다. GitHub에 파일을 올리는 것만으로 외부 접속이 개통되지는 않습니다.

## 웹·관리자 담당: 자동 새로고침 개발

Node 22 LTS(22.13 이상)를 사용합니다. 저장소 `.nvmrc`와 package-lock.json을 따릅니다.
```powershell
cd apps/web
Copy-Item .env.example .env.local
npm ci
npm run dev
```
관리자는 `apps/admin`에서 같은 순서로 실행하며 로컬 개발 포트는 3001입니다.
기본 .env.example은 공통 API 터널 18000을 사용합니다. 자기 DB/API를 쓰려면 INTERNAL_API_URL을 http://127.0.0.1:8000으로 바꿉니다.
Docker 웹은 재현 가능한 빌드 결과를 실행합니다. 소스 수정 후 `workspace.py up`으로 다시 빌드하거나 위 로컬 dev 모드로 작업합니다.
공통 비밀값을 NEXT_PUBLIC/EXPO_PUBLIC 변수에 넣지 않습니다. 이 변수들은 클라이언트에 공개됩니다.

## 확장 담당

Chrome의 chrome://extensions에서 개발자 모드 → 압축해제된 확장 로드 → `apps/extension` 선택.
SSH 터널을 연 뒤 확장 버튼의 API 확인으로 연결합니다. 개발 권한은 127.0.0.1만 허용합니다.
`npm ci`, `npm run check`로 manifest와 JS를 검사합니다. 화면 캡처·탭 감지·사이드바·스토어 배포는 별도 구현입니다.

## OCR·추천·수집 담당

`services/<담당>/devapp.py`가 연결 시작점입니다. 실제 코드를 붙일 때 health의 business_ready와 업무 엔드포인트를 함께 변경하고 계약/테스트를 추가합니다.
`services/dev_runtime`는 공통 연결·큐 검사용으로 실제 모델 코드를 억지로 함께 설치하지 않습니다.
개발 틀은 소스 마운트+uvicorn reload를 지원합니다. 작업자 코드는 변경 후 `workspace.py up`만으로 이미지 재빌드를 확인하고 필요하면 해당 컨테이너를 재시작합니다.

모델 의존성은 큰 이미지이므로 별도 CPU 환경으로 준비합니다. 처음 한 번 빌드할 때 큰 다운로드와 디스크 사용이 발생합니다.
```powershell
docker compose -f infra/workspace/ai.compose.yaml build
docker compose -f infra/workspace/ai.compose.yaml run --rm vision-cpu
docker compose -f infra/workspace/ai.compose.yaml run --rm recommendation-cpu
```
기본 명령은 설치된 실제 라이브러리의 import까지만 확인하며 네트워크를 차단합니다. 모델 가중치·언어·revision·임베딩 차원은 담당자 계약으로 확정한 뒤 설치합니다.
GPU/CUDA는 모든 팀원에게 강제하지 않습니다. GPU 환경은 담당 장비에 맞춘 별도 설정으로 검증합니다.
CPU 이미지의 최상위 의존성은 고정하며 전체 설치 결과는 이미지 `/opt/installed-packages.txt`에 기록합니다. 이 선택 환경의 전이 의존성은 아직 저장소 완전 잠금 대상이 아닙니다.

## Claude와 외부 수집

Claude SDK를 준비했지만 `LLM_MODE=disabled`로 기본 실행합니다. 환경 smoke/CI는 Claude 호출·지원 크레딧 소비·실제 사이트 크롤링·모델 가중치 다운로드를 하지 않습니다.
실제 연동 시 ANTHROPIC_API_KEY와 ANTHROPIC_MODEL은 서버 전용 비공개 환경에 설정하고 호출 횟수·토큰 상한·오류 대체를 구현합니다. 키가 존재한다는 이유만으로 자동 호출하지 않습니다.
수집기는 기존 `/internal/v2/crawl-runs/{run_id}/observations` 계약에 맞추고 COLLECTOR_TOKEN을 서버에서만 사용합니다. DB 직접 쓰기 계정을 공유하지 않습니다.

## 모바일 담당

Node 22.13 이상. `apps/mobile`에서 `.env.example`을 `.env.local`로 복사하고 `npm ci`, `npm start`.
Android 에뮬레이터의 10.0.2.2는 개발 PC를 가리킵니다. 예시는 PC의 SSH 터널 18000 연결용입니다.
Android Studio/SDK·에뮬레이터는 모바일 담당 PC에만 설치합니다. 실제 휴대폰의 localhost나 10.0.2.2는 같은 의미가 아닙니다.
실기기는 개발 PC와의 연결·HTTPS·접근 제한을 별도로 구성해야 합니다. Expo 개발 화면 실행은 다른 앱 캡처/오버레이를 검증한 것이 아니며, 그 기능에는 Android 네이티브 모듈과 실제 권한 검증이 필요합니다.
iOS 네이티브 빌드는 macOS/Xcode 환경이 필요합니다. CI의 `expo export --platform android`는 JS 번들 검증이며 APK/IPA 빌드·기기 테스트가 아닙니다.

## 협업·검증·남은 작업

- 각자의 이름 브랜치에서 담당 코드를 수정하고 PR로 공유합니다. 공통 변경은 팀원 1명 리뷰 후 main에 병합하고 각자 origin/main을 가져옵니다.
- `.ci/projects.json`은 API·OCR·추천·수집·공통 실행 틀·웹·관리자·확장·모바일의 9개 프로젝트 빌드를 활성화합니다. 큐·서비스 통합·실제 CPU 라이브러리 이미지는 Full development workspace 워크플로에서도 검증합니다. 실제 담당 기능의 CI는 코드 반입 후 추가합니다.
- 공통 환경 Python 의존성은 requirements.lock, Node는 각 package-lock.json을 커밋합니다. 기존 업무 API 의존성은 기존 명세를 유지합니다.
- `infra/workspace/.env`, 이미지, 모델 캐시, DB 백업은 Git/Docker 빌드 컨텍스트에서 제외합니다.
- 비공개 임시 이미지 TTL은 개발 초기값 1시간입니다. 실제 이미지 수명주기는 소유권·완료/실패/취소 삭제까지 구현해야 합니다. 현재 볼륨은 호스트 1대용이며 여러 서버로 확장할 때 공유 저장소로 교체합니다.
- 실제 회원·결제·상담·관리자 인증, 분석 Outbox/재시도/취소, 추천 품질, 모델 가중치, 생산 수집원과 성능 검증은 업무 구현 범위로 남습니다.
- 남은 환경 작업: 호스트·팀원 VPN 로그인/초대/키 등록, 다른 집에서 접속 검증, main 보호 규칙(소유자 권한), 모바일 담당·장치 확정.

참고: [Next.js 설치](https://nextjs.org/docs/app/getting-started/installation), [Celery Redis](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html), [PaddleOCR](https://www.paddleocr.ai/main/en/quick_start.html), [Sentence-Transformers](https://sbert.net/docs/installation.html).
