# 꿀픽 백엔드 API
소병선 담당. 회원·상품·고객센터의 독립 DB 3개에 업무 테이블과 별도 마이그레이션을 적용한다. 개발환경과 자동 검사는 실제 사이트·Claude·결제사 호출 없이 실행한다.

| 찾는 내용 | 기준 문서 |
| --- | --- |
| 공통 설치·실행·종료 | [로컬 개발환경](../../docs/LOCAL_DEVELOPMENT.md) |
| 상품 데이터 수신·중복 제거·갱신 | [수집 데이터 안내](../../docs/backend/CATALOG_INGESTION.md) |
| 회원·모의 결제·데이터 정리·성능 명령 | [DB 운영](../../docs/backend/DB_OPERATIONS.md) |
| 상담·관리자·제휴·탈퇴·분석 작업 | [백엔드 업무](../../docs/backend/INDEPENDENT_BACKEND.md) |
| 외부 호출 규격 | [API 계약 목록](../../contracts/README.md) |

아래는 카탈로그와 벡터 모듈의 상세 안내다. 문서의 실행 명령은 저장소 루트 기준이다.

## 팀원이 실행하기
Docker Compose v2 및 Python 3.10+가 있는 PC에서 저장소 루트에서 실행한다. API 컨테이너의 Python은 3.12다.
```sh
python services/api/dev.py init
python services/api/dev.py up
python services/api/dev.py seed
```
Windows에서 필요하면 python 대신 py를 사용한다. 기존 infra/db/.env와 DB volume은 유지한다. 각 DB의 owner 계정으로 3개 마이그레이션을 끝낸 후 별도 app 계정으로 API가 시작된다. /health는 상품·회원·상담 테이블에 대한 접근을 모두 확인한다.
- 브라우저: http://127.0.0.1:8000/docs 및 http://127.0.0.1:8000/health
- 웹: GET /v2/offers?selected_domain=product (또는 food). 최대 100건, next_cursor를 다음 요청의 after에 사용. 가격은 십진 문자열. 마지막 수집 상태 기준 판매 중 신품 목록이며 추천·상품 동일성 판정 결과가 아니다.
- 종료: python services/api/dev.py down. 데이터 볼륨 보존.
- 각자의 PC에 실행하는 개발환경이다. 회원 인증은 구현되어 있으며 외부 공개 운영 배포 검증은 별도다.
- services/api/.env: COLLECTOR_TOKEN, API_PORT(기본 8000), DEV_ORIGINS(쉼표로 나눈 개발 웹 origin), CATALOG_URL_HOSTS(허용하는 판매처 호스트명, 쉼표 구분). 비밀번호/토큰은 Git에 올리지 않는다.
- 테스트용 기본 URL 호스트는 store.example.test이며 다운로드하지 않는다. 실제 데이터 수신 전 허용 호스트와 수집원별 권한을 별도 설정한다. 이 단계의 단일 수집 토큰은 내부 로컬 통합용이다. 공개 서버에 그대로 배포하지 않는다.

## 준서: 실제 수집물이 없어도 테스트하는 계약
POST /internal/v2/crawl-runs/{run_id}/observations. UUID run_id를 생성하고 Authorization: Bearer <로컬 수집 토큰>을 보낸다. 첫 관측에서 실행을 생성하며 같은 실행의 source는 변경 불가. docs의 Authorize에서 로컬 토큰을 입력할 수 있다. fixtures/offer.json은 가상 상품 템플릿이며 seed가 observed_at(시간대 포함), observation_key를 추가한다. seed는 같은 매물의 가격을 12000 → 11500 KRW, URL을 original → updated로 바꾼 뒤 조회한다.
- 일반 수신 스키마 v2. 신규 성공 매물에 source, source_listing_id, variant_key, selected_domain, name, price(문자열), currency, url, availability가 필요하다. 선택 필드와 field_presence는 일치해야 한다. 실제 단일 옵션을 확인한 경우만 명시적인 고정 옵션 키를 사용한다.
- 다른 판매처·옵션은 별개다. 상품명/URL만으로 병합하지 않고 식별 불명은 quarantine. 최초 식별마다 catalog_items와 하위 유형을 만든다. 서로 다른 판매처의 동일 상품 자동 판정은 후속 단계다.
- 내부 수신 201, 재전송 200, 같은 source/observation_key의 다른 payload 409, 형식 오류 422, 인증 실패 401. 201은 관측 보관 결과로, 본문 state가 applied인지 확인한다. normalized_payload에는 허용된 필드만 저장한다.
- 가격/배송비·판매 상태·URL·설명·신품/중고 상태는 필드별 관측 시각으로 비교한다. 오래된 관측은 기록하고 현재값은 보존한다. 같은 시각 상충은 격리한다. 가격 변경 때만 가격 이력, URL 변경 때만 URL 이력/버전을 추가한다.
- 수신 시 갱신: 24시간 만료 조건을 제거했다. 새 관측이 도착하면 observed_at을 비교해 적용한다. not_found는 suspect로 일반 목록에서 제외하고 timeout/blocked/error는 현재 판매 상태를 보존한다. 수집 파일에 없다는 이유로 삭제하지 않는다. last_seen_at을 화면에 표시하며 실시간 가격이라고 보장하지 않는다.
- **변경 없음 확인(heartbeat)**: POST /internal/v2/listing-checks (수집 토큰). 본문 `{"source", "items":[{source_listing_id, variant_key, observed_at, price, currency, availability}]}`, 최대 500개.
  수집기가 다시 확인했는데 내용이 같아 관측을 보내지 않은 매물을 묶어 보낸다. 카탈로그의 price·currency·availability가 같을 때만 last_seen_at/last_checked_at을 앞으로 옮긴다(가격·상태와 그 관측 시각은 바꾸지 않음).
  응답 `{"confirmed": n, "mismatch": [...], "unknown": [...], "rejected": [...]}`. mismatch(카탈로그와 다름)·unknown(없음/삭제됨)은 전체 관측을 다시 보내야 한다. observed_at이 미래 5분 초과이거나 30일보다 오래되면 rejected.
- 상품 카드(기본 추천·제휴·분석 결과)에 `seen_at`(마지막으로 판매 확인된 시각)과 `stale`(CATALOG_STALE_HOURS, 기본 72시간 초과)을 포함한다. 추천 서비스는 RECO_MAX_STALENESS_HOURS(기본 0=끔)를 넘긴 매물을 후보에서 뺄 수 있다.
- **식품 알레르기 신고 코드**: 리스팅 확장의 `food_evidence.allergens_declared`는 아래 코드로 보낸다(회원 프로필·확장·모바일과 같은 코드).
  `egg milk buckwheat peanut soybean wheat mackerel crab shrimp pork peach tomato sulfite walnut chicken beef squid shellfish pine_nut`.
  `soy`, `대두`, `조개류`, `pine nut`처럼 별칭·한글 표시명은 저장 시 위 코드로 바뀐다. 코드가 아닌 문구(예: "새우 함유")는 그대로 저장되고 추천 서비스가 글자로 한 번 더 확인한다.
  추천 서비스는 이 코드를 표시 원문(`allergen_notice_raw`)과 별개로 항상 직접 판정한다(#59).
- food와 product는 분리 조회한다. 중고는 condition=used로 조회한다. 제휴·회원·상담 API는 위 업무별 문서를 참고한다. 실제 상품 상세정보 수집 연동은 별도다.

## 정우: 임베딩 연결
근거: 2026-10-06 pgvector 설계서 2~4절, 통합 기술 명세 10장. product / food별 테이블과 embedding_models 사용(성분 단위 ingredient 테이블은 사용하지 않아 2026-11-27 제거). Sentence-Transformers의 실제 모델명·가중치 revision·차원은 미정이다. 테스트의 3차원 배열은 인코더 결과가 아니다.
1. 모델 확정 후 catalog owner 연결에서 kkulpick.vectors.Contract와 register(conn, contract)로 불변 모델 계약과 모델 전용 HNSW 코사인 인덱스를 생성한다. 테스트 통과 후 해당 모델의 is_serving을 true로 변경한다. 기존 계약 수정 대신 새 ID를 등록한다.
2. 추천 작업자는 공개 텍스트만 사용해 계약의 입력 템플릿·접두사·정규화 규칙으로 인코딩한 후 put(conn, model_id, parent_id, content_version, values)로 저장한다. psycopg 동기 연결 대상이며 비동기 HTTP 요청 스레드에서 직접 호출하지 않는다.
3. candidates(conn, model_id, query_vector, limit)는 같은 모델·최신 content_version의 후보만 코사인 거리로 반환한다. HNSW m=16, ef_construction=64, 검색 ef_search=40. 여러 차원의 모델 등록을 위해 저장 컬럼은 vector, 인덱스는 모델별 vector(D) 캐스트와 고정 조건을 쓴다. 작은 후보 집합에서는 옵티마이저가 exact를 선택할 수 있다. 차원·영벡터 검증, 콘텐츠 버전 검증, 원본 텍스트 변경 시 기존 벡터 검색 제외. 가격 변경만으로 내용 버전을 올리지 않는다.
4. 실제 임베딩 작업 큐·재계산·모델 품질 평가·알레르기 검증은 별도다. 이 함수의 결과를 최저가나 안전한 식품 판정으로 그대로 사용하지 않는다.

## 검증
Catalog API integration CI는 실제 pgvector 컨테이너에서 Alembic upgrade, 샘플 적재, HTTP/DB/벡터 통합 테스트를 수행한다. 일반 빌드 CI는 입력 계약과 Python 패키지 빌드를 검사한다. 로컬 계약 테스트: services/api에서 pip install -r requirements-dev.txt 후 python -m pytest tests/test_contract.py. test_database.py는 격리한 테스트 DB에서만 실행한다. 운영 데이터에는 실행하지 않는다.

## 점검 후 보완 (2026-11-06)

런타임은 requirements.lock으로 설치합니다. FastAPI 0.137.2 / Starlette 1.3.1 조합으로 보안 권고를 반영하고 계약·DB 통합 검사를 수행합니다. 버전 변경 시 requirements.txt와 lock을 함께 갱신합니다.
JSON 요청 본문은 64 KiB 상한이며 초과하면 413입니다. 분석 multipart 요청은 전체 3 MiB, 이미지 1개 2 MiB로 제한하며 비공개 저장합니다. 헤더 검사는 이미지 디코딩·픽셀 제한을 대신하지 않으며 실제 작업자에서 추가 검증해야 합니다. 허용 origin의 GET/POST/PATCH/PUT/DELETE와 Authorization·Idempotency-Key를 지원합니다. CORS는 인증을 대신하지 않으며 수집·분석 작업자 토큰은 브라우저에 전달하지 않습니다.

## 실제 크롤링 데이터 가져오기

[수신 갱신·적재·검증 가이드](../../docs/backend/CATALOG_INGESTION.md)를 참고한다. `tools/catalog.py`는 JSON 배열을 한 건씩 인증 API로 보낸다. 원본 시각과 키를 보존하며 파일 재실행은 중복 적재하지 않는다.
