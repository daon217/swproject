# 독립 가상 상품 생성 및 격리 테스트 적재

실제 상품을 복사하지 않는 결정적 스트리밍 생성기다. 1천/1만/10만/100만 건을 지원한다.
국내 KRW/해외 USD, 신품/중고, 8개 카테고리를 생성한다. 식품/화장품은 가상 중고로 만들지 않는다.
가격대는 예제용 native 통화 범위이며 실제 환율·실판매가를 주장하지 않는다.
모든 ID/name/seller/observation_key에 SYNTHETIC, synthetic=true, 별도 schema_version과 예약 example.test URL을 사용한다.
실제 운영 Observation v2나 기존 provider source로 변환하지 않는다.
원재료/알레르기/안전 여부는 가상으로 채우지 않고 null이다.

```powershell
# 저장소 루트, HTTP/DB 접근 없음
.\.venv\Scripts\python.exe -m services.collector.synthetic_catalog --output C:\격리데이터\1000 --count 1000
.\.venv\Scripts\python.exe -m services.collector.synthetic_catalog --output C:\격리데이터\10000 --count 10000
.\.venv\Scripts\python.exe -m services.collector.synthetic_catalog --output C:\격리데이터\100000 --count 100000
.\.venv\Scripts\python.exe -m services.collector.synthetic_catalog --output C:\격리데이터\1000000 --count 1000000
# 중단 재개: 동일 output/count/seed/batch-size로 같은 명령을 다시 실행
```

기본 1만 건 단위 JSONL part와 manifest를 작성하며 메모리에 전체 상품 목록을 올리지 않는다.
각 part는 partial → fsync → atomic rename → manifest commit 순서다.
완료 part 해시를 재검증하고 manifest 직전 중단으로 남은 part도 결정적 재생성 해시와 일치할 때만 채택한다.
설정 불일치·손상·알 수 없는 기존 파일은 초기화/덮어쓰지 않는다. 같은 디렉터리 writer lock으로 중복 실행을 막는다.
seed는 생성 규칙에 포함되며 같은 설정/인덱스의 ID와 key는 재개 후에도 동일하다.
--max-parts로 일부만 생성 후 재개하는 로컬 장애 테스트도 가능하다.

로컬 검증에서는 네 단계 모두 생성했고 100만 건은 3만 건 후 중단/재개했다.
각 part 전체 해시와 전체 스트리밍 행 수를 확인하고 100만 건에서 1000개 레코드의 상세 검증을 표본 수행했다.
템플릿 필드/가격/마커/멱등성은 별도 단위 테스트로 검증한다.
생성된 실제 100만 행은 Codex work/synthetic-scale-validation/1000000에 있으며 결과 요약은 outputs에 있다.
운영 데이터 경로나 Git에 이 데이터셋을 넣지 않는다.

## 격리 테스트 DB 전용 API

팀 PostgreSQL이나 팀 FastAPI를 수정하지 않는다. test_api는 별도 loopback HTTP API와 SQLite 테스트 파일만 사용한다.
DB 파일명은 synthetic_*.sqlite3, namespace는 synthetic_ 접두어만 허용한다.
모든 레코드의 source/ID/URL/해시/synthetic 마커를 검사하며 실제 상품과 운영 v2를 거절한다.
namespace+record ID와 batch key를 멱등 처리하고 같은 key의 다른 body는 충돌로 거부한다.
SQL은 이 로컬 SQLite 테스트 파일 안에서만 사용하며 PostgreSQL driver/DSN을 지원하지 않는다.

```powershell
# 명시적 로컬 테스트용 토큰을 환경변수 KKULPICK_SYNTHETIC_TEST_TOKEN에 설정 후 실행.
# 토큰 값은 채팅·명령 인자·소스·Git·로그에 쓰지 않는다.
.\.venv\Scripts\python.exe -m services.collector.synthetic_catalog.test_api --db C:\격리DB\synthetic_catalog.sqlite3 --namespace synthetic_catalog --port 18779
```

다른 터미널에서 먼저 plan만 확인한다.

```powershell
.\.venv\Scripts\python.exe -m services.collector.synthetic_catalog.load_test --dataset C:\격리데이터\1000 --state-dir C:\격리적재원장 --url http://127.0.0.1:18779 --namespace synthetic_catalog --environment isolated_test
# 로컬 테스트 적재를 명시적으로 선택할 때만 위 명령에 --send를 추가
```

loader는 1000건 이하 배치로 스트리밍하며 literal 127.0.0.1의 명시 포트와 /test/synthetic-import만 사용한다.
production URL/DB DSN/원격 hostname/리다이렉트/자동 HTTP 재시도는 허용하지 않는다.
전송 전 reserved를 기록하고 ACK의 key/hash/count/state가 일치할 때만 완료 처리한다.
프로세스 중단/응답 유실/미확인 ACK는 보류하며 자동 POST 재전송하지 않는다.
같은 endpoint/namespace/dataset으로 재개해야 하며 포트도 임의로 바꾸지 않는다.
서버 /test/synthetic-receipt에서 인증된 영수증을 확인한 뒤 --receipt-file로 명시적으로 reconcile할 수 있다.
이 reconcile은 검토한 영수증의 key/hash/count를 확인하는 로컬 조작이며 자동 인증서명 검증 기능은 아니다.
영수증을 임의 생성하지 말고 실제 테스트 서버의 인증된 응답을 사용한다.

100만 건의 생성 검증과 DB 적재 성능은 별개다. 로컬 SQLite HTTP 검증은 합성 1000건만 수행했다.
테스트 PostgreSQL이 필요하면 팀이 별도 synthetic source/권한/격리 schema용 API를 승인·구현한 후 어댑터를 추가한다.
현재 loader를 운영 FastAPI endpoint로 바꾸거나 synthetic를 해제하는 우회 옵션은 없다.
