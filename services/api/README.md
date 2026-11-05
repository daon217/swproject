# 꿀픽 카탈로그 API · 개발 1단계
소병선 담당. 3개 DB 가운데 catalog에만 업무 테이블을 적용한다. 실제 수집 계정, 외부 사이트 호출, Claude 키, 임베딩 모델 다운로드 없이 실행한다.

## 팀원이 실행하기
Docker Compose v2 및 Python 3.10+가 있는 PC에서 저장소 루트에서 실행한다. API 컨테이너의 Python은 3.12다.
```sh
python services/api/dev.py init
python services/api/dev.py up
python services/api/dev.py seed
```
Windows에서 필요하면 python 대신 py를 사용한다. 기존 infra/db/.env와 DB volume은 유지한다. owner로 catalog 마이그레이션을 끝낸 후 별도 app 계정으로 API가 시작된다. /health는 실제 catalog의 offers 읽기까지 확인한다.
- 브라우저: http://127.0.0.1:8000/docs 및 http://127.0.0.1:8000/health
- 웹: GET /v2/offers?selected_domain=product (또는 food). 최대 100건, next_cursor를 다음 요청의 after에 사용. 가격은 십진 문자열. 신선한 판매 중 신품 목록이며 추천·상품 동일성 판정 결과가 아니다.
- 종료: python services/api/dev.py down. 데이터 볼륨 보존.
- 각자의 PC에 실행하는 환경이다. 공용 API/인증/운영 배포 전 단계.
- services/api/.env: COLLECTOR_TOKEN, API_PORT(기본 8000), DEV_ORIGINS(쉼표로 나눈 개발 웹 origin), CATALOG_URL_HOSTS(허용하는 판매처 호스트명, 쉼표 구분). 비밀번호/토큰은 Git에 올리지 않는다.
- 테스트용 기본 URL 호스트는 store.example.test이며 다운로드하지 않는다. 실제 데이터 수신 전 허용 호스트와 수집원별 권한을 별도 설정한다. 이 단계의 단일 수집 토큰은 내부 로컬 통합용이다. 공개 서버에 그대로 배포하지 않는다.

## 준서: 실제 수집물이 없어도 테스트하는 계약
POST /internal/v2/crawl-runs/{run_id}/observations. UUID run_id를 생성하고 Authorization: Bearer <로컬 수집 토큰>을 보낸다. 첫 관측에서 실행을 생성하며 같은 실행의 source는 변경 불가. docs의 Authorize에서 로컬 토큰을 입력할 수 있다. fixtures/offer.json은 가상 상품 템플릿이며 seed가 observed_at(시간대 포함), observation_key를 추가한다. seed는 같은 매물의 가격을 12000 → 11500 KRW, URL을 original → updated로 바꾼 뒤 조회한다.
- 일반 수신 스키마 v2. 신규 성공 매물에 source, source_listing_id, variant_key, selected_domain, name, price(문자열), currency, url, availability가 필요하다. 선택 필드와 field_presence는 일치해야 한다. 실제 단일 옵션을 확인한 경우만 명시적인 고정 옵션 키를 사용한다.
- 다른 판매처·옵션은 별개다. 상품명/URL만으로 병합하지 않고 식별 불명은 quarantine. 최초 식별마다 catalog_items와 하위 유형을 만든다. 서로 다른 판매처의 동일 상품 자동 판정은 후속 단계다.
- 내부 수신 201, 재전송 200, 같은 source/observation_key의 다른 payload 409, 형식 오류 422, 인증 실패 401. 201은 관측 보관 결과로, 본문 state가 applied인지 확인한다. normalized_payload에는 허용된 필드만 저장한다.
- 가격/배송비·판매 상태·URL은 필드별 관측 시각으로 비교한다. 오래된 관측은 기록하고 현재값은 보존한다. 같은 시각 상충은 격리한다. 가격 변경 때만 가격 이력, URL 변경 때만 URL 이력/버전을 추가한다.
- 초기 TTL 24시간: 가격·상태·URL 중 가장 오래된 시각 기준. not_found는 suspect로 제외, timeout/blocked/error는 신선도를 연장하지 않는다. 반복 재확인 스케줄러와 보관 기간별 삭제 작업은 후속이다.
- food와 product는 분리 조회한다. 중고 상세 스키마 v3·제휴·회원 및 상담 API는 이번 범위에 포함하지 않는다.

## 정우: 임베딩 연결
근거: 2026-10-06 pgvector 설계서 2~4절, 통합 기술 명세 10장. product / food / ingredient별 테이블과 embedding_models 사용. Sentence-Transformers의 실제 모델명·가중치 revision·차원은 미정이다. 테스트의 3차원 배열은 인코더 결과가 아니다.
1. 모델 확정 후 catalog owner 연결에서 kkulpick.vectors.Contract와 register(conn, contract)로 불변 모델 계약과 모델 전용 HNSW 코사인 인덱스를 생성한다. 테스트 통과 후 해당 모델의 is_serving을 true로 변경한다. 기존 계약 수정 대신 새 ID를 등록한다.
2. 추천 작업자는 공개 텍스트만 사용해 계약의 입력 템플릿·접두사·정규화 규칙으로 인코딩한 후 put(conn, model_id, parent_id, content_version, values)로 저장한다. psycopg 동기 연결 대상이며 비동기 HTTP 요청 스레드에서 직접 호출하지 않는다.
3. candidates(conn, model_id, query_vector, limit)는 같은 모델·최신 content_version의 후보만 코사인 거리로 반환한다. HNSW m=16, ef_construction=64, 검색 ef_search=40. 여러 차원의 모델 등록을 위해 저장 컬럼은 vector, 인덱스는 모델별 vector(D) 캐스트와 고정 조건을 쓴다. 작은 후보 집합에서는 옵티마이저가 exact를 선택할 수 있다. 차원·영벡터 검증, 콘텐츠 버전 검증, 원본 텍스트 변경 시 기존 벡터 검색 제외. 가격 변경만으로 내용 버전을 올리지 않는다.
4. 실제 임베딩 작업 큐·재계산·모델 품질 평가·알레르기 검증은 별도다. 이 함수의 결과를 최저가나 안전한 식품 판정으로 그대로 사용하지 않는다.

## 검증
Catalog API integration CI는 실제 pgvector 컨테이너에서 Alembic upgrade, 샘플 적재, HTTP/DB/벡터 통합 테스트를 수행한다. 일반 빌드 CI는 입력 계약과 Python 패키지 빌드를 검사한다. 로컬 계약 테스트: services/api에서 pip install -r requirements-dev.txt 후 python -m pytest tests/test_contract.py. test_database.py는 격리한 테스트 DB에서만 실행한다. 운영 데이터에는 실행하지 않는다.
