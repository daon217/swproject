# 꿀픽 온라인

상품·식품 화면 분석, 가격 비교와 대체 상품 탐색을 위한 팀 프로젝트입니다.

## 팀원은 여기서 시작하세요

**[팀원 개발환경 사용 안내](docs/LOCAL_DEVELOPMENT.md)** — 설치 → 본인 브랜치에 공통 코드 반영 → 실행 → 담당 작업 → 백업·종료 순서입니다.

현재 기본 방식은 **각자 PC의 Docker에서 서버와 DB를 실행**하는 것입니다. GitHub로 코드를 공유하며 각 PC의 DB 데이터·비밀번호·백업은 자동 공유되지 않습니다. 로컬 개발에 VPN·공용 서버·클라우드 가입·Claude 키는 필요하지 않습니다.

공통 환경 반영 상태는 [PR #3](https://github.com/daon217/swproject/pull/3)에서 확인하세요. 아직 병합 전이면 안내의 `part/소병선-backend` 반영 절차를 따르고, 병합 후에는 `origin/main`을 반영합니다.

### 최초 실행

Git·Python 3.11 이상·Docker Desktop을 준비하고 **본인 브랜치에 공통 코드를 반영한 뒤**, 저장소 루트의 PowerShell에서 실행합니다.

```powershell
py tools/workspace.py doctor
py tools/workspace.py init
py tools/workspace.py up --scope core
py tools/workspace.py seed
py tools/workspace.py check --scope core
```

API 문서: http://127.0.0.1:8000/docs. 평소에는 `up --scope core`, 종료할 때는 `py tools/workspace.py stop`을 사용합니다. 정상 종료 후 DB 데이터는 유지됩니다.

웹·관리자 소스 개발은 core 실행 후 담당 폴더에서 `npm ci`, `npm run dev`를 사용합니다. 전체 연결 환경이 필요하면 [full 실행 안내](docs/WORKSPACE.md)를 따릅니다.

## 문서 찾아보기

| 필요한 내용 | 안내 |
| --- | --- |
| 설치·실행·명령어·문제 해결 | [팀원 개발환경 사용 안내](docs/LOCAL_DEVELOPMENT.md) |
| 전체 문서와 코드 위치 | [문서 목록](docs/README.md) |
| 브랜치·커밋·PR·기존 코드 반입 | [협업 규칙](CONTRIBUTING.md) |
| 웹·작업 큐·OCR·추천 개발 틀 | [전체 개발환경](docs/WORKSPACE.md) |
| 자동 검사·빌드 결과 확인 | [CI 안내](.ci/README.md) |
| API·이벤트 계약 | [계약 안내](contracts/README.md) |
| 선택적인 공용 서버/VPN 접속 | [공용 서버 안내](docs/TEAM_DEVELOPMENT.md) |

## 담당자와 코드 위치

| 담당 | 브랜치 | 코드 위치 |
| --- | --- | --- |
| 소병선 — 백엔드·공통 환경 | `part/소병선-backend` | `services/api`, `infra`, `tools` |
| 이다온 — 이미지 분석 | `part/이다온-vision` | `services/vision` |
| 박정우 — 임베딩·추천 | `part/박정우-recommendation` | `services/recommendation` |
| 최준서 — 수집 | `part/최준서-collector` | `services/collector` |
| 김호진 — 웹 | `part/김호진-web` | `apps/web` |
| 서지웅 — 확장 | `part/서지웅-extension` | `apps/extension` |
| 배정 필요 — 모바일·관리자 | 담당 확정 후 추가 | `apps/mobile`, `apps/admin` |

폴더 구분은 모든 영역의 독립 배포를 뜻하지 않습니다. 결제·고객센터·운영 책임자는 별도 배정합니다.

## 구현 상태와 설계 기준

- 제공: 독립 PostgreSQL DB 3개, 카탈로그 업무 테이블 13개, 가상 수집 데이터 적재·상품 조회 API, pgvector 저장·검색 모듈, 로컬 실행·백업 도구.
- 제공: 웹·관리자·확장·모바일 시작 코드, OCR·추천·수집 HTTP 개발 틀, Redis·Celery·비공개 임시 저장소, 9개 프로젝트 검사·빌드 설정.
- 미완료: 회원·고객센터 업무 테이블, 회원·결제·상담·관리자 업무 기능, 실제 수집·OCR·추천 통합, 모델 가중치와 운영 배포.
- 기본 환경 점검은 실제 크롤링·모델 추론·Claude 유료 호출을 하지 않습니다. 검사 통과는 서비스 기능 전체 완성을 뜻하지 않습니다.

2026-11-02 기술 명세서와 팀 WBS를 기준으로 합니다. FastAPI/Pydantic, Celery/Redis, PostgreSQL/pgvector를 사용하며 과거 Java/Spring 목록은 적용하지 않습니다. 실행 버전은 코드의 의존성 명세·잠금 파일과 `.python-version`, `.nvmrc`를 기준으로 합니다.

## 작업 공유

본인의 이름 브랜치에서 작업 → 변경 파일 확인·커밋·푸시 → `main` 대상 PR → 팀원 1명 이상 검토 → merge commit 순서입니다. 반복 사용하는 `part/*` 브랜치는 병합 후에도 유지합니다.

실제 `.env`, API 키, 비밀번호, 인증서, 개인정보, DB 백업은 커밋하지 않습니다. 의존성 명세와 잠금 파일은 커밋합니다. 자세한 절차는 [협업 규칙](CONTRIBUTING.md)을 따릅니다.

저장소 소유자의 브랜치 보호 설정은 [관리자 안내](.github/ADMIN_SETUP.md)에 있습니다. 문서가 있다는 사실이 실제 설정 완료를 의미하지는 않습니다.
