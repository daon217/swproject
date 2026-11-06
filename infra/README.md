# 개발환경 구성

일반적인 팀원 실행은 **[개발환경 사용 안내](../docs/LOCAL_DEVELOPMENT.md)**의 `tools/workspace.py`를 사용합니다.

| 구성 | 경로·안내 | 용도 |
| --- | --- | --- |
| 로컬 전체 실행 | [WORKSPACE](../docs/WORKSPACE.md), `workspace/` | 웹·API·작업 큐·개발 어댑터 |
| DB 기반 구성 | [db/README.md](db/README.md) | PostgreSQL 독립 DB 3개·권한·pgvector |
| 카탈로그 API | [API README](../services/api/README.md) | 마이그레이션·적재·가격/URL 변경·조회·벡터 저장/검색 |
| 선택 공용 접속 | [team/README.md](team/README.md) | VPN/SSH 게이트웨이·접근 등록·백업 도구 |

회원·고객센터 업무 기능, 실제 수집기·모델 가중치·운영 배포는 별도 구현 범위입니다. 폴더가 존재하거나 연결 검사가 성공했다고 해당 기능이 완성된 것은 아닙니다.
