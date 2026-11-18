# 선택적 격리 PostgreSQL/API 검증

모의 테스트가 모두 통과한 뒤 **명시적으로 승인된 별도 환경**에서만 실행한다. 실제 상품·팀 공용/운영 DB를 사용하지 않는다. 기본 단위 테스트에는 DB가 필요 없다.

준비물:

- Windows PostgreSQL17.x의 승인된 bin 디렉터리. 바이너리는 이 저장소에 없고 도구가 자동 다운로드하지 않는다.
- 백엔드 담당 코드의 읽기 전용 services/api 경로: kkulpick/models.py, ingest.py, migrations/versions/catalog.sql·0002·0003.
- 이 저장소/백엔드와 분리된 새 work 디렉터리. 기존 팀 DB 경로나 중요 데이터 폴더를 지정하지 않는다.

```powershell
python -m pip install -r services/collector/domeggook_live/requirements-devtest.txt
python -m services.collector.domeggook_live.devtest --approve-synthetic `
  --work-dir '<approved-local-test-directory>' `
  --backend-dir '<readonly-backend-checkout>/services/api' `
  --pg-bin '<approved-postgresql>/bin'
```

도구는 먼저 단위/계약 테스트를 실행한다. 성공하면 독립 PostgreSQL 데이터 디렉터리와 새 DB/사용자/무작위 비밀번호를 만들고 루프백 전용 API를 실행한다. 현재 백엔드 모델/수신 함수를 읽기 전용으로 로드하고 catalog SQL+0002/0003을 새 DB에 적용한다. 회원/상담/벡터를 포함한 전체 팀 서비스 배포 테스트가 아니다.

synthetic provenance·domeggook_test source·TEST- ID·store.example.test URL만 사용한다. 실제 source는 API가403으로 거부한다. INSERT/갱신/동일 값 조회 시각/동시 동일 관측/중복 재전송/API 장애/커밋 후 응답 누락 모의/API·DB 재시작을 검사한다. 동일 매물 ID와 행 수를 확인하고 종료할 때 자신이 띄운 API/PG만 종료한다. 테스트는 기존 테스트 행도 삭제하지 않고 새 TEST- 식별자를 사용한다.

비밀값·로그·DB는 work 디렉터리에만 남는다. 이 디렉터리는 Git 외부 또는 data/local 아래에 두며 절대 commit하지 않는다. 결과 JSON의 집계만 공유한다. 현재 v2는 재고 수량 대신 availability를 갱신한다. 주기 대기는 모의이고 실제 HTTP/DB를 사용한3주기를 검증한다.
