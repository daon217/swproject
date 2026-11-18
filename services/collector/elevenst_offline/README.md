# 11번가 오프라인 수집 모듈

팀 저장소의 기존 수집기와 함께 사용하는 독립 모듈입니다. Python 3.10 이상 표준 라이브러리로 동작하며, import·CLI·테스트에서 내부 API를 호출하지 않습니다. `.env`를 읽지 않고 DB 및 백엔드 전송도 구현·활성화하지 않습니다. 도매꾹 수집기와 상태 경로를 공유하지 않습니다.

## 재사용한 코드와 변경 범위

- 기존 `ai-shopping-search-unified/crawler_engine/extractors/elevenst.py`의 JSON 순회·배열 탐색·후보 매핑을 `extractor.py`에 재사용했습니다. 전체 원본 프로젝트를 설치하거나 개인 경로를 import할 필요가 없습니다.
- 기존 13개 테스트(검색 소스 2개, JSON 추출기 9개, 공식 XML 수집기 2개)를 검토했습니다. JSON 추출기 9개를 `tests/test_original_extractor.py`로 이식했습니다. 내부 API 주소 생성이나 실제 XML 통신은 이 모듈에 이식하지 않았습니다. 상품 URL의 ID가 원본 ID와 일치하도록 두 종류의 테스트 입력을 보완했습니다.
- `domestic23/elevenst_parser.py`의 원본 ID·옵션 근거·불명확한 옵션 격리·보관 자료 구분 방식을 적용했습니다. 그 파일의 판매가 우선 처리 대신 이번 요구에 맞게 원본 JSON 추출기의 `finalPrc` 우선 처리를 유지합니다.
- 새 코드는 이 폴더에만 추가했습니다. 기존 도매꾹, 백엔드, PostgreSQL, 원본 상품·ID·격리 자료는 수정하지 않습니다.

## 데이터 계약

`source=elevenst`, `product_id=source_listing_id=원본 상품 ID`입니다. `variant_key`는 원본 `optionId`, `optionNo`, `variantId`의 일치하는 코드만 사용합니다. 이름·가격·URL 해시로 상품/옵션 ID를 만들지 않습니다. 충돌하는 식별자는 거절합니다.

옵션 유무가 불명확하면 `variant_key=null`, `identity_status=quarantine_required`로 분리합니다. 원본의 명시적인 옵션 없음 표시와 빈 옵션 목록이 함께 있을 때만 `confirmed_none`으로 처리합니다. 보관 추출 자료는 검증된 옵션 근거 없이는 판매 단위로 승격하지 않습니다.

상품명, `price`/`unit_price`, 통화, 구매 URL, 이미지 URL, 판매처, 카테고리, 원래 관측 시각을 메모리에서 정규화합니다. 공통 15개 필드를 제공하며 확보되지 않은 설명·사양 등은 `null`입니다. 통화·판매 조건·재고·옵션명은 임의로 추정하지 않습니다. 관측 시각이 없는 JSON은 `null`을 유지하고 실행 시각은 별도 `last_processed_at`에 기록합니다.

가격 순서: `finalPrc → salePrice → price → finalPrice → displayPrice → selPrc`. 비어 있거나 유효하지 않거나 0인 값은 건너뜁니다. 양의 정수 또는 올바른 천 단위 쉼표 문자열만 허용합니다. 소수·음수·불리언·NaN·임의 문자 혼합 가격은 숫자로 변환하지 않습니다. `finalPrc`의 할인 자격과 최종 결제금액은 확인되지 않았다는 상태를 함께 제공합니다.

구매 URL은 HTTPS의 `www.11st.co.kr`, `m.11st.co.kr`만 허용하고 `/products/{ID}` 또는 `/product/SellerProductDetail.tmall?prdNo={ID}`의 원본 ID 일치를 검사합니다. 이미지 URL은 HTTPS의 정확한 호스트 `cdn.011st.com`, `image.11st.co.kr`만 허용합니다. 프로토콜 상대 주소는 HTTPS로 확정합니다. 인증정보·제어문자·외부 호스트·비표준 포트는 거절합니다. 다른 CDN은 근거를 확인하고 테스트를 추가하기 전까지 허용하지 않습니다. URL 허용 목록은 콘텐츠 재이용 허가를 뜻하지 않습니다.

## 실행

팀 저장소 루트에서 실행합니다. PowerShell에서 자신이 선택한 Python을 사용하세요. 아래 파일 경로는 예시이며 실제 원본 자료를 저장소로 복사하지 마세요.

```powershell
python -B -m services.collector.elevenst_offline --status
python -B -m services.collector.elevenst_offline --input C:\local\saved-listing.json --dry-run
python -B -m services.collector.elevenst_offline --input C:\local\saved-listing.json --observed-at 2026-11-18T00:00:00+00:00 --max-items 10
# 같은 명령을 다시 실행하면 미처리 위치부터 재개합니다.
python -B -m services.collector.elevenst_offline --input C:\local\products_unified.json --format snapshot --dry-run
python -B -m pytest -q -p no:cacheprovider services/collector/elevenst_offline/tests
```

`--format listing`은 보관된 원본 JSON 배열 탐색용입니다. 과거 자료에는 내부 API 원문 JSON이 없어서 해당 구조는 합성 JSON으로 검증합니다. `--format snapshot`은 기존에 추출한 상품 목록을 읽기 전용으로 재생하며 `source=elevenst`만 선택합니다. 추출 자료를 원본 API 응답으로 보고하지 않습니다. snapshot의 기존 관측 시각은 CLI에서 덮어쓸 수 없습니다.

기본 상태 폴더는 이 모듈의 Git 제외 `data/`이며 `--state-dir`로 별도 위치를 지정할 수 있습니다. 원본 자료나 다른 수집기의 상태 폴더를 지정하지 마세요. `--dry-run`과 상태 조회는 쓰기·HTTP 요청이 없습니다. CLI 출력에는 집계만 포함합니다.

동일 `(source, source_listing_id, variant_key)`는 한 번 등록하고, 다른 옵션은 별도 판매 단위로 구분합니다. 동일 보관 파일은 콘텐츠 해시/커서로 재처리를 생략합니다. 다른 응답에서 같은 ID를 만나면 신규 상품으로 늘리지 않습니다. 더 최신의 관측만 메모리 값을 갱신하고 오래된 응답이 가격을 덮어쓰지 않습니다.

체크포인트는 ID·옵션 코드·관측 시각·파일 해시·커서·페이지 번호 등의 제어 메타데이터만 원자적으로 교체합니다. OS 잠금으로 동시 쓰기를 차단하고 프로세스 종료 시 잠금이 해제됩니다. 파일 교체 실패 시 기존 체크포인트·메모리를 보존합니다. 손상된 체크포인트를 초기화하지 않고 실패합니다. 상품 내용은 프로세스 메모리에만 있으며 재시작 후 복원되는 DB가 아닙니다. 원본 재처리는 별도 빈 상태 경로에서 수행할 수 있습니다. 페이지 정보는 기록만 하며 자동 HTTP 페이지 탐색을 하지 않습니다.

## LIVE 활성화 전에 필요한 조건

현재 `--live`는 항상 종료 코드 2로 차단됩니다. 환경변수나 API 키만으로 활성화할 수 없습니다. `live.py`의 `OfficialAPITransport`가 향후 공식/제휴 전송 구현의 경계이며 현재 구현은 없습니다.

1. 공식 API 또는 제휴 계약에서 검색·상품 상세 접근 권한, 허용 경로·범위·호출량을 확인합니다.
2. 상품정보·이미지의 저장·외부 노출·보관 기간 및 갱신 조건을 확인하고 근거를 남깁니다.
3. 승인된 응답 구조를 사용하는 전용 전송기와 필드 어댑터를 추가하고 요청 원장·상한·백오프·401/403/429 중단을 검증합니다. 기존 내부 검색 API를 승인된 경로로 간주하지 않습니다.
4. 승인 유효기간·예산·옵션 식별·장애 복구를 검증한 후 명시적인 활성화 설정과 테스트를 추가합니다. 백엔드 쓰기 승인은 별도로 확인합니다.

이번 통합의 실제 HTTP 수집과 DB 전송은 모두 0회입니다. 오프라인/합성 테스트를 LIVE 성공 실적으로 집계하지 않습니다. 기존 로컬 26개 ID의 재생 검증은 별도 완료 보고서에 기록합니다. 실제 원본 JSON·상품 데이터·.env·체크포인트·로그·가상환경은 Git에 추가하지 않습니다.
