# 꿀픽 온라인

상품·식품 화면 분석, 가격 비교와 대체 상품 탐색을 위한 팀 프로젝트입니다.

## 현재 상태
이 저장소는 팀 협업을 위한 초기 설정만 포함합니다. 서비스 코드, DB, 배포, CI 빌드 검증은 아직 구성하지 않았습니다.
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
| infra | 개발·운영 환경 구성 | 배정 필요 |

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
DB는 회원·카탈로그·고객센터의 독립 PostgreSQL 3개로 계획하며 실제 DB 작업은 다음 단계로 미룹니다.
라이브러리 버전과 실행 명령은 담당 코드 반입 후 확정합니다. 과거 Java/Spring 목록과 다른 프로젝트 코드는 적용하지 않습니다.
명세의 보완안·미결정 정책은 구현 전에 합의합니다.

## 비밀정보와 실행 환경
실제 환경변수, 토큰, 인증서, 사용자 화면·개인정보는 커밋하지 않습니다.
각 실행 프로젝트는 필요한 변수만 담은 .env.example과 실행 방법을 추가합니다.
의존성 명세와 잠금 파일은 커밋하고 가상환경·node_modules·빌드 산출물은 제외합니다.
아직 실행 가능한 서비스나 자동 테스트 성공을 보장하지 않습니다.

## 저장소 관리자 후속 설정
main 브랜치 보호는 [관리자 설정 안내](.github/ADMIN_SETUP.md)를 따릅니다.
