# 상품 수집·정규화

담당: 최준서 · 브랜치: `part/최준서-collector`

[팀원 개발환경 사용 안내](../../docs/LOCAL_DEVELOPMENT.md)에 따라 본인 브랜치에 공통 코드를 반영합니다. [전체 개발환경](../../docs/WORKSPACE.md)에서 `devapp.py`의 HTTP 개발 틀과 전용 Celery 큐를 실행합니다.

```powershell
# 저장소 루트에서 실행
py tools/workspace.py init
py tools/workspace.py up --scope full
py tools/workspace.py check --scope full
```

현재는 연결용 시작 코드입니다. `business_ready=false`이고 `/internal/process`는 501을 반환합니다. 실제 담당 기능은 아직 연결하지 않았습니다.

관측 적재 경로는 `POST /internal/v2/crawl-runs/{run_id}/observations`입니다. `services/api/fixtures/offer.json`과 실행한 API의 `/docs`를 확인하세요. 자기 PC의 `COLLECTOR_TOKEN`을 서버에서만 사용하고 실제 수집 도메인은 `CATALOG_URL_HOSTS`에 등록합니다.

기존 코드를 이 폴더에 반입하고 의존성 명세·잠금 파일·환경변수 예시·실행 방법·실제 테스트를 함께 갱신합니다. 업무 기능을 붙이면 API 계약과 `business_ready`도 실제 상태에 맞게 변경합니다. [협업 규칙](../../CONTRIBUTING.md)과 [CI 안내](../../.ci/README.md)를 따릅니다.
