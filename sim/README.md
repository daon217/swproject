# 실제 구동 시뮬레이션 스크립트

[journal/2026-11-24-runtime-simulation-claude-opus-5.5.md](../journal/2026-11-24-runtime-simulation-claude-opus-5.5.md)에서 사용한 드라이버.
compose 네트워크 안에서 실행한다(`python:3.12-slim` + `httpx==0.28.1` + `psycopg[binary]==3.2.12`).

- `sim.py stage1|gap|after`: 실제 수집 원본 적재, 임베딩 대기열 확인, 추천 호출
- `sim_e2e.py e2e|admin_flow`: 회원·분석·확장 선도착·관리자·애드픽 흐름

필요한 환경변수: `COLLECTOR_TOKEN`, `WORKSPACE_TOKEN`, `CATALOG_OWNER_PASSWORD` 등 DB 비밀번호(검증용 무작위 값).
`/sim/real.json`에 `services/collector/handoffs/real_db_test_300_20261115/observations_v2_REAL_300.json`을 둔다.
