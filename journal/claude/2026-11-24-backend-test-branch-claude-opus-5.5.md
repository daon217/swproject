# [Claude Opus 5.5] 개발일지 · 2026-11-24 세션 1 — part/소병선-backend-test 1차 작업

- 작성: Claude (Opus 5.5)
- 브랜치: `part/소병선-backend-test` (`origin/maintest` 2c65ccd에서 생성, 로컬·미push)
- 사용자 요청: maintest를 가져와 백엔드 테스트 브랜치에서 작업. 관리자 백엔드 병합, maintest 문제점·끝없는 재시도 개선, 기능 점검, 애드픽 URL 변환 API(분당 60회, 미지원 URL은 HTTP 400), 예외 처리 검토.

---

## <a id="01"></a>#01 PR #15 CI UI 테스트 2개 실패 — 해결 (2e2a806)

**문제점** maintest의 "Team connected runtime", "Frontend backend integration" 워크플로가 계속 실패. main에서도 11/19부터 실패.

**원인**
- `tests/ui/console.spec.js:23`이 '답변 추가' 버튼을 찾지만, 이 라벨은 데모 모드 전용. 실제 모드는 '답변 보내기' (`apps/web/pages/counseling/index.js:355` `${demo ? '답변 추가' : '답변 보내기'}`).
- `tests/ui/guest-floating.spec.js:28`이 모바일 비회원 화면에서 '식품' 버튼을 누르지만 커밋 e7f7007에서 제거됨.
- maintest 코드 변경이 원인이 아니라, 화면 변경 후 테스트가 갱신되지 않음.

**해결 방안**: (A) 테스트를 현재 화면에 맞춤 ✅ / (B) 버튼을 되살림 — 의도적으로 제거한 UI라 기각.

**해결** console 테스트는 '답변 보내기'로, guest-floating은 확장에서만 식품/상품 전환을 검사하고 모바일은 버튼이 없음을 검사.

**검증** 로컬에서 Playwright 미실행. **CI에서 확인 필요.**

---

## <a id="02"></a>#02 catalog-context 보조 검색 50건 절단 — 해결 (2e2a806)

**문제점** 페이지 URL의 호스트 대소문자가 저장된 URL과 다를 때 쓰는 보조 검색이, 같은 호스트 상품이 50개를 넘으면 맞는 상품을 놓친다. 또 정규식 조건이라 인덱스를 못 타고 매 분석마다 전체 상품을 훑는다.

**원인** `services/recommendation/http_service.py` catalog_context: 호스트로 `LIMIT 50`을 먼저 가져온 뒤 Python에서 path/query를 비교.

**해결 방안**
| 선택지 | 채택 |
| --- | --- |
| A. path/query 비교를 SQL로 옮기고 LIMIT 1, 호스트 식 인덱스 추가 | ✅ |
| B. LIMIT을 늘림 | 근본 해결 아님 |
| C. 수집 시 URL 정규화만 의존 | 기존 데이터·다른 수집기 보장 불가 |

**해결** SQL에서 `호스트 식 = host AND path?query = ANY(변형 목록)`. `_suffix_variants()`로 빈 경로 ↔ `/`, 끝 슬래시 변형 처리. 마이그레이션 `0010_offer_url_host`로 `lower(substring(current_url from '^[a-zA-Z]+://([^/:?#]+)'))` 식 인덱스 추가.

**왜** 결과가 데이터 양에 따라 달라지는 정확성 버그라 상한 조정으로는 해결이 안 된다. 인덱스 식은 쿼리와 글자 그대로 같아야 플래너가 쓰므로 마이그레이션에 주석으로 고정.

**검증** 격리 DB에서 마이그레이션 0010 적용 확인, 기존 catalog-context 단위 테스트 통과.

---

## <a id="03"></a>#03 유사 상품 200건 상한 — 해결 (2e2a806)

**문제점** `/v2/offers/{id}/matches`가 브랜드만 같아도 후보로 잡고 가격순 200건에서 자른다. 저렴한 동일 브랜드 상품이 많으면 '브랜드+모델명 일치' 유사 상품이 잘린다.

**원인** `services/api/kkulpick/extensions.py` offer_matches의 ORDER BY가 정확 일치(GTIN·브랜드+모델번호/MPN)만 우선하고 나머지는 가격순.

**해결** 순위를 정확 일치(0) → 브랜드+모델명(1) → 나머지(2) → 가격 순으로 매긴 뒤 상한 적용.

**남은 과제** SQL은 `lower()`, Python은 `strip().casefold()`라 앞뒤 공백이 있는 브랜드는 SQL에서 안 맞는다. 확장 수집은 pydantic이 공백을 제거하므로 현재는 영향 작음.

---

## <a id="04"></a>#04 식품 오판 시 알레르기 경고 사라짐 — 부분 해결 (2e2a806)

**문제점** 사용자가 분석 종류를 고르지 않으면 워커가 키워드로 식품 여부를 판단한다. 식품인데 '상품'으로 판정되면 추천 서비스가 알레르기 항목을 비워 **경고 없이** 결과가 나간다.

**원인** `analysis_worker.food_evidence()`가 키워드 정규식 기반, `http_service.process()`는 product일 때 `allergens=[]`.

**해결 방안**: (A) 판별을 정교하게 — 근본적이지만 데이터·모델 필요 / (B) 판별이 추정일 때 알레르기 사용자에게 '검사하지 않았음' 경고 ✅ (안전 쪽으로 실패).

**해결** 워커가 종류를 스스로 추정해 product가 됐고 프로필에 알레르기가 있으면 알레르기별 `evidence='unknown'` 경고를 결과에 추가. 백엔드 `AllergyWarning.allergen`이 필수 문자열이라 알레르기 코드마다 하나씩 생성(처음엔 None으로 넣었다가 422로 작업이 실패하는 것을 발견해 수정).

**왜** 오판 자체를 없애기 전까지는 사용자가 '안전하다'고 오해하지 않게 하는 것이 우선.

**남은 과제** 키워드 범위 문제는 #19.

---

## <a id="05"></a>#05 분석 워커 예외 처리 — 해결 (2e2a806)

**문제점**
1. 타임아웃·연결 거부·5xx도 `retryable=False`로 즉시 영구 실패.
2. HTTP 오류가 아닌 예외(KeyError 외 TypeError 등)는 실패 보고 없이 임대 만료까지 작업을 붙잡음.
3. 404/409를 무조건 "임대가 사라짐"으로 보고 무시 → Vision 세션 만료(404)도 무시돼 작업이 멈춘 채 재큐잉 대기.

**원인** `process_job`의 except 분기가 출처(백엔드/Vision/추천)를 구분하지 않음.

**해결**
- 429·5xx·`httpx.TransportError` → `retryable=True` (백엔드가 시도 3회로 상한).
- 그 외 예외 → `RECOMMENDATION_FAILED`로 즉시 실패 보고(백엔드 Failure.code 허용 값 중 하나. 처음 쓴 `WORKER_ERROR`는 422가 나서 교체).
- 404/409는 요청 URL이 백엔드(`API_INTERNAL_URL`)일 때만 임대 상실로 간주.
- 실패 보고 자체가 실패하면 로그만 남김(임대 만료 후 백엔드가 처리).
- 테스트에서만 쓰이던 `infer_domain()`·`tokens()` 제거.

**검증** 새 단위 테스트 4개(Vision 404 보고, 일시 오류 retryable, 잘못된 응답 즉시 실패, 추정 product 경고) 포함 dev_runtime 26개 통과.

---

## <a id="06"></a>#06 임베딩 작업 끝없는 재시도 — 해결 (793dc1d)

**문제점** 계속 실패하는 임베딩 작업(잘못된 스냅샷, 모델 오류)이 최대 300초 간격으로 영원히 재시도. `--drain`도 영원히 실패.

**원인** `embedding_worker.retry()`에 시도 횟수 상한이 없음.

**해결 방안**: (A) N회 후 삭제 — 원인 추적 불가 / (B) N회 후 '보류(park)' 상태로 남기고 수동 재큐잉 ✅

**해결** `EMBEDDING_MAX_ATTEMPTS`(기본 8) 도달 시 `available_at='infinity'`, `last_error='exhausted:<예외 타입>'`, 에러 로그. claim은 `attempts < MAX`만 가져감. `--requeue-failed`로 재시도 예산 초기화. `--drain`은 대기/보류 개수를 따로 보고.

**왜** 삭제하면 검색에서 상품이 조용히 빠지고 원인도 사라진다. 보류는 눈에 보이고 고친 뒤 되살릴 수 있다.

**검증** 통합 테스트 `test_poison_job_is_parked_instead_of_retrying_forever` 통과.

---

## <a id="07"></a>#07 임베딩 1건씩 처리 — 해결 (793dc1d)

**문제점** 작업마다 계약 검증 쿼리 2번 + 추론 1번 + 트랜잭션 1번. 1만 건이면 1만 번.

**해결** `EMBEDDING_BATCH_SIZE`(기본 32)만큼 한 번에 임대·추론. 배치 추론이 실패하면 건별로 다시 시도해 문제 있는 1건만 실패 처리. 계약 검증은 연결당 1회.

**주의** 임대 시간은 5분. 배치 크기를 크게(예: 256) 올리면 CPU 추론이 임대를 넘길 수 있다.

**검증** `test_one_bad_item_does_not_block_the_batch` 통과.

---

## <a id="08"></a>#08 관리자 백엔드 병합 — 해결 (e18c36c)

**문제점** 김호진 웹이 쓰는 `/v2/admin/auth/*`, `/v2/admin/catalog/offers/delete`, overview 일별 구독자가 maintest에 없음. 404가 나면 웹이 로컬 우회(관리자 토큰 위임 등)로 빠짐 → #20.

**해결** `codex/separate-admin-signup`(855192d, 52c486e)의 `contracts/ docs/ services/`만 패치로 적용. 웹 변경은 제외(웹은 김호진 브랜치 것을 사용). 충돌은 `api.py` 라우터 목록 한 줄.

**왜** 웹을 병합하기 전에 백엔드가 있어야 404 우회가 동작하지 않는다. merge 대신 패치 적용을 택한 이유: 웹 파일을 버리는 merge 커밋을 만들면 나중에 그 브랜치가 "이미 병합됨"으로 보여 혼란.

**검증** 격리 DB에서 API 통합 테스트 85개 통과(관리자 가입·승인·삭제 포함).

---

## <a id="09"></a>#09 애드픽 URL 변환 API — 해결, 가정 포함 (e4b4678)

**요구** 애드픽 API 키로 쇼핑몰 URL을 제휴 링크로 변환. 분당 60회, 미지원 URL은 애드픽이 HTTP 400.

**해결** `POST /v2/links/convert` (`services/api/kkulpick/adpick.py`)
- 키는 `services/api/.env`의 `ADPICK_API_KEY`에만. 응답·로그에 남기지 않음. 엔드포인트는 `ADPICK_API_URL`(HTTPS 필수).
- 애드픽 400 → 400 `AFFILIATE_URL_UNSUPPORTED`, 1시간 부정 캐시(같은 URL 재호출 방지).
- 성공 24시간 캐시(프로세스 메모리).
- 분당 한도: DB 고정 1분 창(`app.auth_attempts` 재사용)으로 API 워커 전체 공유. 클라이언트별 10회 → 전체 60회 순서로 확인(한 클라이언트가 전체 예산을 못 쓰게).
- 애드픽 429 → 429 `AFFILIATE_LINK_BUSY`, 401/403 → 503 `AFFILIATE_LINK_NOT_CONFIGURED`, 그 외 장애 → 503 `AFFILIATE_LINK_UNAVAILABLE`.
- http(s) 외, 계정정보 포함, 사설/로컬 주소는 422로 애드픽 호출 전에 거절.
- HTTP는 표준 라이브러리 urllib을 스레드에서 실행(새 의존성 없음).

**가정 (확인 필요)** 애드픽 공개 API 문서를 찾지 못함. 요청 형식을 POST JSON `{"url": ...}`, 헤더 `Authorization: Bearer <키>`로 가정. `ADPICK_AUTH_HEADER`, `ADPICK_AUTH_SCHEME`, `ADPICK_URL_PARAM`으로 조정 가능. 응답에서 링크를 찾는 필드 후보: affiliate_url, deeplink, short_url, link, url, result (data 하위 포함).

**검증** `tests/test_adpick.py` (DB 없이, 업스트림 모킹) 통과.

**남은 과제** 무인증 문제 #16, 프록시 IP 문제 #17.

---

## <a id="10"></a>#10 SQL 코드 오류가 503으로 숨겨짐 — 해결 (e4b4678)

**문제점** 모든 `SQLAlchemyError`가 503 `DATABASE_UNAVAILABLE`(재시도 가능)로 응답. 잘못된 SQL·권한 누락·파라미터 타입 오류(maintest 마지막 커밋이 고친 asyncpg 타입 오류 같은 것)도 "잠시 후 재시도"로 보여 버그가 가려짐. DB 연결 거부 같은 네트워크 오류는 처리기가 없어 500.

**해결** (`services/api/kkulpick/errors.py`)
- `ProgrammingError`, `DataError` → 500 `INTERNAL_ERROR` + traceback 로그.
- 그 외 SQLAlchemy 오류 → 기존대로 503 (교착·직렬화 실패 등 일시적일 수 있음).
- `ConnectionError`, `TimeoutError`, `socket.gaierror` → 503 `DEPENDENCY_UNAVAILABLE`. 다른 OSError(파일 없음 등)는 500 유지.
- 처리되지 않은 예외도 traceback 로그(지역 변수 값은 포함되지 않음).

**왜** 일시 장애와 코드 결함을 구분해야 클라이언트 재시도와 개발자 대응이 각각 맞게 동작한다.

**검증** 기존 `test_errors.py`(OperationalError → 503) 통과.

---

## 이 세션의 검증 환경
[VERIFY.md](../../guide/VERIFY.md) 참고. Windows에서는 psycopg async가 ProactorEventLoop에서 동작하지 않아 통합 테스트를 Linux 컨테이너에서 실행했다.
