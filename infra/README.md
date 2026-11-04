# 개발환경

[DB 실행 안내](db/README.md): PostgreSQL 서버 1개, 독립 DB 3개(member/catalog/support), catalog pgvector.

로컬 개발용 Docker Compose 환경이며 실제 공용 DB 서버를 배포한 것은 아닙니다.
업무 테이블/Alembic, FastAPI, Redis, Celery는 다음 단계에서 추가합니다.
