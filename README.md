# 꿀픽 온라인

상품·식품 화면 분석, 가격 비교와 대체 상품 탐색을 위한 팀 프로젝트입니다.

## 각자 PC에서 개발 시작

[팀원별 설치·브랜치·실행 안내](docs/LOCAL_DEVELOPMENT.md)를 따릅니다. 각자 Docker에서 독립 DB 3개와 백엔드를 실행합니다. VPN·공용 호스트·클라우드 가입은 필요하지 않습니다.
공통 설정은 현재 `part/소병선-backend`의 PR #3에 있으므로 안내에 따라 본인 브랜치에 반영하세요.

```powershell
py tools/workspace.py doctor
py tools/workspace.py init
py tools/workspace.py up --scope core
py tools/workspace.py seed
py tools/workspace.py check --scope core
```

웹·관리자는 core 실행 후 담당 폴더에서 `npm ci`, `npm run dev`. API 명세는 http://127.0.0.1:8000/docs 입니다.
[전체 환경](docs/WORKSPACE.md)은 `up --scope full`, `check --scope full`로 실행합니다.
개발용 연결 틀과 실제 업무 구현은 구분합니다. 기본 구성은 모델 추론·실제 수집·Claude API를 호출하지 않습니다.

## 현재 상태
FastAPI 카탈로그 API, PostgreSQL 독립 DB 3개, 가상 수집 데이터, pgvector 저장소와 팀 공통 접속 구성을 포함합니다. [로컬 개발 안내](docs/LOCAL_DEVELOPMENT.md)에서 각자 실행하고, 필요할 때만 [공용 서버 접속](docs/TEAM_DEVELOPMENT.md)을 설정합니다. [프로젝트별 빌드 자동화](.ci/README.md)는 코드 없는 영역의 빌드를 생략합니다.
각 담당자는 기존 코드를 기능 브랜치에서 가져오고 PR로 검토합니다.

## 프로젝트 구조
| 경로 | 역할 | WBS 담당 |
| --- | --- | --- |
| apps/web | Next.js 사용자 웹 | 김호진 |
| apps/extension | Chrome MV3 확장 | 서지웅 |
| apps/mobile | React Native 모바일 | 배정 필요 |
| apps/admin | 관리자 화면 | 배정 필요 |
| services/api | FastAPI 메인 업무 API | 소병선 |
| services/vision | 이미지 전처리·OCR | 이다온 |
| services/recommendation | 임베딩·성분 매칭·추천 | 박정우 |
| services/collector | 외부 상품 수집·정규화 | 최준서 |
| contracts | 서비스 간 API·이벤트 계약과 가상 샘플 | 관련 담당 공동 |
| infra | 공통 개발환경·DB·접속 구성 | 소병선 |

폴더 구분은 모든 영역의 독립 배포를 뜻하지 않습니다. 결제·고객센터·운영 책임자는 별도 배정합니다.

## 개발 시작
```bash
git clone https://github.com/daon217/swproject.git
cd swproject
git switch -c feat/api-auth
```
담당 폴더에 코드를 추가한 뒤 변경 파일을 확인하고 커밋·푸시합니다.
```bash
git status
git diff --check
git add <변경한-파일-경로>
git diff --cached
git commit -m "feat(api): 회원 인증 초기 구현"
git push -u origin feat/api-auth
```
GitHub에서 base를 main으로 지정해 PR을 생성합니다. 상세 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 확인하세요.

## 설계 기준
2026-11-02 「꿀픽 온라인 기술 명세서 — 3개 DB 확장 설계·결제·고객센터 포함」과 팀 WBS를 기준으로 합니다.
메인 백엔드는 FastAPI/Pydantic, 분석 작업은 Celery/Redis 방향입니다.
DB는 PostgreSQL 서버 하나 안의 회원·카탈로그·고객센터 독립 DB 3개입니다. 현재 카탈로그 업무 테이블 13개가 구현되었으며 회원·고객센터 업무 테이블은 아직 없습니다.
라이브러리 버전과 실행 명령은 담당 코드 반입 후 확정합니다. 과거 Java/Spring 목록과 다른 프로젝트 코드는 적용하지 않습니다.
명세의 보완안·미결정 정책은 구현 전에 합의합니다.

## 비밀정보와 실행 환경
실제 환경변수, 토큰, 인증서, 사용자 화면·개인정보는 커밋하지 않습니다.
각 실행 프로젝트는 필요한 변수만 담은 .env.example과 실행 방법을 추가합니다.
의존성 명세와 잠금 파일은 커밋하고 가상환경·node_modules·빌드 산출물은 제외합니다.
API/DB/공통 접속의 자동 검증은 GitHub Actions에서 확인합니다. 다른 파트의 실제 실행·통합은 해당 코드가 올라온 뒤 검증합니다. 각 팀원 PC에서 로컬 점검이 필요합니다. VPN은 선택적 공용 서버 접속에만 사용합니다.

## 저장소 관리자 후속 설정
main 브랜치 보호는 [관리자 설정 안내](.github/ADMIN_SETUP.md)를 따릅니다.

