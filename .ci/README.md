# 빌드 자동화

main 대상 PR, main 푸시, Actions 수동 실행에서 Team build를 실행합니다.
CI configuration은 설정과 CI 제어 로직을 검증하고, Build / 프로젝트명은 설치 → 검사 → 빌드를 수행합니다.
현재 코드가 없어 8개 영역은 enabled=false입니다. 실제 빌드 job은 skipped이며 요약에 미실행을 명시합니다.
코드 또는 의존성 파일이 생겼는데 비활성 상태라면 설정 검사가 실패합니다.

## 코드 반입 시
1. 담당 폴더에 코드, 의존성·잠금 파일, 실제 테스트를 추가합니다.
2. projects.json의 enabled=true, version, install/check/build 명령을 채웁니다.
3. 아래 명령으로 검증하고 PR을 올립니다.
```bash
python .github/scripts/ci.py plan
python .github/scripts/ci.py run api install
python .github/scripts/ci.py run api check
python .github/scripts/ci.py run api build
```
명령은 프로젝트 폴더에서 실행됩니다. 각 명령은 인자 배열이며 셸 연산자 &&, 파이프를 해석하지 않습니다.
새 영역은 projects.json에 등록합니다. 활성 프로젝트 전체를 매번 검사하여 공통 계약 변경의 영향도 확인합니다.

## Python 예시
```json
{
  "name": "api", "path": "services/api", "runtime": "python",
  "enabled": true, "version": "3.12",
  "install": [["python", "-m", "pip", "install", "-r", "requirements-dev.txt"]],
  "check": [["python", "-m", "pytest"]],
  "build": [["python", "-m", "build"]]
}
```
이 예시는 pyproject.toml 패키지 빌드 설정과 requirements-dev.txt의 build/pytest 및 실제 테스트가 필요합니다.
Poetry/uv 등을 쓰면 도구 설치와 잠금 기반 설치 명령을 프로젝트에 맞춥니다. 예시 버전은 팀 전체 강제 버전이 아닙니다.

## Node/npm 예시
```json
{
  "name": "web", "path": "apps/web", "runtime": "node",
  "enabled": true, "version": "22.0",
  "install": [["npm", "ci"]],
  "check": [["npm", "run", "lint"], ["npm", "run", "test:ci"]],
  "build": [["npm", "run", "build"]]
}
```
package-lock.json과 실제 lint/test:ci/build 스크립트가 필요합니다. pnpm/yarn은 도구 설치와 잠금 설치 명령으로 변경합니다.
모바일 Node 검사는 APK/IPA 빌드를 대신하지 않습니다. 네이티브 빌드·서명은 담당 환경 확정 후 별도 job으로 구성합니다.

## 범위
읽기 전용 GITHUB_TOKEN, 자격정보를 남기지 않는 checkout, job 시간 제한을 사용합니다.
배포·외부 유료 API·운영 비밀키·실제 DB 연결은 없습니다. 테스트는 가짜 외부 의존성 또는 테스트 설정을 사용합니다.
실패를 무시하거나 테스트가 없을 때 성공 처리하는 옵션을 사용하지 마세요.
설정 검증용 Python 3.12와 서비스별 런타임은 별개입니다.
관리자는 실제 Actions 결과를 확인한 후 CI configuration과 필요한 Build 검사를 보호 규칙에 등록합니다.

## 참고
- https://docs.github.com/en/actions/tutorials/build-and-test-code/python
- https://docs.github.com/en/actions/tutorials/build-and-test-code/nodejs
