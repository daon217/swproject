# 자동 검사·빌드 안내

`main` 대상 PR, `main` 푸시, Actions 수동 실행에서 Team build를 실행합니다. 담당 브랜치에 push만 하고 main 대상 PR을 열지 않은 상태에서는 이 워크플로가 자동 실행되지 않습니다.

현재 [projects.json](projects.json)의 **9개 프로젝트가 모두 enabled=true**입니다. `CI configuration`은 설정·실행 도구를 검사하고 `Build / 프로젝트명`은 설치 → 검사 → 빌드를 수행합니다.

## 프로젝트별 현재 검사 범위

| 프로젝트 | 경로 | 검사·빌드 |
| --- | --- | --- |
| api | services/api | API 계약 테스트·Python wheel |
| vision | services/vision | 개발 HTTP 어댑터 검사·wheel |
| recommendation | services/recommendation | 개발 HTTP 어댑터 검사·wheel |
| collector | services/collector | 개발 HTTP 어댑터 검사·wheel |
| dev-runtime | services/dev_runtime | 공통 런타임 테스트·wheel |
| web | apps/web | TypeScript 검사·Next.js 빌드 |
| admin | apps/admin | TypeScript 검사·Next.js 빌드 |
| extension | apps/extension | manifest/JavaScript 검사·빌드 스크립트 |
| mobile | apps/mobile | TypeScript 검사·Android JS 번들 |

정확한 명령·런타임 버전은 projects.json과 각 패키지 명세를 기준으로 합니다. 모바일 검사는 APK/IPA·실기기 검증이 아니며, 어댑터 검사는 실제 OCR·추천·수집 기능 검증이 아닙니다.

## 결과 확인

1. GitHub PR의 Checks 또는 저장소 Actions 탭을 엽니다.
2. 최신 커밋의 워크플로를 선택합니다. 이전 커밋의 성공과 구분합니다.
3. 실패한 job의 Install / Check / Build 로그를 확인합니다.
4. 오류를 수정해 같은 브랜치에 push하면 열린 main 대상 PR에서 다시 검사합니다.

Team build 외에 [워크플로 폴더](../.github/workflows)의 DB·카탈로그 API·공용 접근/백업·전체 개발환경 검사가 있습니다. 각 워크플로의 트리거와 경로 필터에 따라 실행 범위가 달라집니다. 실제 PostgreSQL 등은 CI의 임시 환경에서 실행하며 팀원의 로컬 DB에 연결하지 않습니다.

## 코드 반입·명령 변경

1. 담당 폴더의 소스·의존성 명세·잠금 파일·테스트를 갱신합니다.
2. projects.json의 해당 프로젝트 install/check/build 명령도 실제 코드에 맞게 변경합니다. 이미 활성화된 프로젝트를 검사 회피 목적으로 비활성화하지 않습니다.
3. 저장소 루트에서 설정 계획을 확인합니다.

```powershell
py .github/scripts/ci.py plan
```

개별 단계를 로컬에서 재현할 때는 프로젝트 런타임·가상환경을 준비한 뒤 실행합니다. install은 현재 Python 환경에 패키지를 설치하므로 전역 환경보다 프로젝트용 가상환경을 사용하세요.

```powershell
# api는 본인 프로젝트 이름으로 변경
python .github/scripts/ci.py run api install
python .github/scripts/ci.py run api check
python .github/scripts/ci.py run api build
```

명령은 프로젝트 폴더에서 실행됩니다. 설정의 각 명령은 인자 배열이며 셸 연산자나 파이프를 해석하지 않습니다. 새 영역은 projects.json에 등록합니다. 없는 npm 스크립트나 실행하지 않는 테스트를 성공한 것으로 표기하지 않습니다.

## 검증 범위

읽기 전용 GITHUB_TOKEN, 자격정보를 남기지 않는 checkout, job 시간 제한을 사용합니다. 운영 배포·운영 DB 연결·실제 사이트 크롤링·Claude 유료 호출은 하지 않습니다. 실제 팀원 PC 실행과 업무 통합은 별도로 확인합니다.

소유자는 실제 Actions의 검사 이름과 결과를 확인한 뒤 [브랜치 보호 설정](../.github/ADMIN_SETUP.md)에 필요한 검사를 등록합니다. 문서가 있다고 보호 규칙이 자동으로 설정되지는 않습니다.
