# DB·회원·구독 개발 및 임시 데이터 관리

DB는 기존 3개를 유지한다. 회원·세션·구독·결제는 회원 DB, 상품 수집·이력·벡터·분석 작업은 상품 DB, 상담방·메시지는 고객센터 DB에 저장한다.
서지웅 프론트 미완성본의 회원·결제 데이터 형태를 참고했으며 확정 명세는 아니다.
DB 3개는 별도 Alembic 이력으로 관리한다. 한 DB의 마이그레이션 성공은 다른 DB의 성공을 보장하지 않으므로 모두 성공해야 API가 시작된다.

## 적용 및 사용

저장소 루트 PowerShell에서, 소병선 브랜치의 변경을 받은 뒤 실행한다. 현재 main에는 아직 병합되지 않았을 수 있다.

```powershell
py tools/workspace.py backup
py tools/workspace.py up --scope core
py tools/workspace.py check --scope core
```

기존 환경에서는 먼저 backup을 실행한다. 처음 설치한 비어 있는 환경에서는 init 후 up으로 시작한다.
up은 각 DB의 최신 마이그레이션까지 적용하고 API와 정리 작업을 실행한다. 최신 revision은 [백엔드 업무 안내](INDEPENDENT_BACKEND.md)의 적용 절을 참고한다. API 문서: http://127.0.0.1:8000/docs.
실제 결제는 기본 비활성화다. 테스트할 때만 services/api/.env에 다음을 직접 설정하고 up을 재실행한다(기존 키는 보존).

```dotenv
APP_ENV=development
BILLING_MODE=mock
MOCK_PAYMENT_OUTCOME=succeeded
```

BILLING_TEST_TOKEN은 미확인 모의 결제의 서버 확정을 시험할 때만 무작위 32자 이상으로 설정한다. 프론트에 넣지 않는다.
`failed`는 거절, `pending`은 결과 미확인 상태를 검증한다. 실제 PG 요청, 카드 정보 저장, 실제 돈 청구는 발생하지 않는다.
개인 .env, DB dump, 사용자 업로드 파일은 GitHub에 올리지 않는다.

## 상품 정리 임시 정책

| 데이터 | 임시 처리 |
|---|---|
| 품절·판매 종료 상품 | 즉시 기본 조회 제외. 상태 관측 시각으로 24시간 경과 후 상품/가격/URL/변경 이력 삭제 |
| 상품에만 속한 상세·벡터 | 다른 판매 상품에서 참조하지 않을 때 함께 삭제 |
| 삭제 식별 기록 | 수집처/상품 ID/옵션 ID/최신 관측 시각만 90일 유지 |
| 접근 차단·시간 초과 | 판매 종료로 간주하지 않음. 상품 유지 |
| 페이지 없음 | suspect로 숨김. 자동 물리 삭제 대상 아님 |
| 수집 원문 payload | 수신 후 7일 뒤 비움. 해시/관측 메타데이터는 유지 |
| 관측 메타·가격·변경·닫힌 URL 이력 | 90일. 참조되는 관측은 관련 이력 정리 후 제거 |
| 로그인 세션 | 7일 만료, 만료 세션 정리 |
| 로그인 요청 제한 기록 | 1일 후 정리 |
| 회원·구독·청구·결제 | 일반 정리에서 제외. 탈퇴 시 프로필 익명화·세션 제거, 과거 모의 결제 내역 보존 |
| 분석·상담·이미지 | [백엔드 업무 계약](../../contracts/independent-backend-v2.md)의 보관·삭제 정책 적용 |

한 시간마다 항목별 최대 500건을 정리한다. 이미 삭제할 권한이 부여된 임시 정책이며 up 후 자동 실행된다.
대량 적재로 정리량이 부족하면 batch/주기를 측정해서 조절한다. 원문 정리는 즉각 디스크 파일을 줄이지 않으며 PostgreSQL autovacuum이 공간을 재사용한다.
삭제와 수신은 동일 상품 식별자 잠금을 공유한다. 최신 재입고 데이터가 있으면 삭제 조건을 재확인하여 보존한다.
삭제 식별 시각 이전 데이터는 재생성하지 않는다. 30일보다 오래된 새로운 관측은 격리하여 삭제 기록 만료 이후 재생성을 막는다.
관측 메타데이터 삭제 이후에는 90일을 넘는 동일 키 중복 보장을 제공하지 않는다. 수집 키는 영구 재사용하지 않는다.

```powershell
py tools/workspace.py maintenance --scope core
py tools/workspace.py maintenance --scope core --apply
```

첫 명령은 이번 배치의 예정 건수만, 두 번째는 실제 정리한다. dry-run과 apply 사이 새 데이터가 도착하면 건수가 달라질 수 있다.
백업은 기존 backup 명령으로 별도 저장하며 자동 삭제하지 않는다. 중요한 데이터가 생기면 하루 1회 및 스키마 변경 전 백업을 실행한다.
현재는 자동 오프사이트 백업이 아니다. 각 DB의 개별 스냅샷이므로 DB 간 단일 시점 보장은 없다.

## 입력 품질·오류 처리

지원 통화 기본값은 KRW/USD/AUD/EUR/INR/GBP/JPY/CNY. CATALOG_CURRENCIES로 프로젝트 지원 목록을 변경할 수 있다.
같은 통화에서 최신 가격이 기존 값의 10배 초과 또는 1/10 미만이면 PRICE_ANOMALY로 격리한다. 무료/대폭 할인도 포함될 수 있다.
이는 임시 이상치 규칙이며 실제 가격의 진위를 보증하지 않는다. 최초 가격이나 통화 변경에는 비율 검사를 적용하지 않는다.
운영 확인 후 규칙을 조정하고 새 observation_key로 재수신해야 한다. 동일 키 재전송으로 격리 결정을 바꾸지 않는다.
CATALOG_PRICE_RATIO=0은 규칙 해제이며 기본값이 아니다. 같은 시각 충돌·누락 식별자·과거 데이터는 별도 사유로 기록한다.

입력 오류 422, 인증 401, 권한 403, 중복/상태 충돌 409, 결제 실패 402, 요청 제한 429, DB 일시 오류 503, 예상 못한 오류 500.
응답에 request_id를 포함한다. SQL/비밀번호/토큰/요청 원문은 오류 응답에 노출하지 않는다. DB 작업 실패는 트랜잭션을 롤백한다.
503으로 결제 응답이 끊겼다면 같은 Idempotency-Key로 재조회/재요청한다. 새로운 키로 무조건 재시도하지 않는다.

## 성능 검증

GitHub Catalog API integration에서 실제 Docker API와 PostgreSQL에 아래 검사를 수행한다.

```powershell
py -m pip install -r services/api/requirements-dev.txt
py tools/performance.py --allow-write --rows 1000 --requests 500 --workers 8 --cleanup
```

각 실행은 고유 perf_* 수집처를 생성한다. 기본 신규 1000건, 갱신 100건, 중복 100건, 조회 500회와 전체 페이지 순회 검증. CI에서는 10000건·동시 요청 16개 검사도 추가 수행한다.
p50/p95/p99, 초당 처리량, 오류 수, 고유 상품 개수, DB 전체 크기를 JSON으로 기록한다.
기본 임시 통과 기준: 오류 0, 행 수 일치, 조회 p95 <= 1000ms, 쓰기 p95 <= 1500ms. 사업 성능 목표는 아니며 CI 심각한 퇴행 탐지용이다.
localhost만 허용하고 --allow-write가 필요하다. --cleanup은 해당 실행 데이터만 삭제한다. 결과: data/benchmarks/latest.json 및 Actions artifact(7일).
10000건 이상은 --rows로 늘릴 수 있다. 측정 시 CPU/RAM/데이터 크기·동시성·네트워크를 함께 기록한다. CI는 query-plans.json에 실제 쿼리 계획·인덱스 크기 비교도 보관한다. 테스트용 데이터는 롤백하며 운영 DB에서 이 검사를 실행하지 않는다.
이 결과는 소규모 기본 성능 검증이며 실사용 동시 이용자 수나 대량 크롤링 처리 능력을 보증하지 않는다. OCR/임베딩/외부 결제 호출은 포함하지 않는다.

참고 문서:
- https://www.postgresql.org/docs/current/explicit-locking.html
- https://fastapi.tiangolo.com/tutorial/handling-errors/
- API 계약: [회원·구독](../../contracts/member-billing-v2.md)
