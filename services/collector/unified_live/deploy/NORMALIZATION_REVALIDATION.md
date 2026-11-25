# 정규화 재검증 및 재현 안내 — 2026-11-25

이번 작업은 Discovery 확장이 아니다. 기존 외부 데모 원상품 7개와 같은 TestingURL 상품의 다른 Microdata/OG 표현 2개를 검사했다. 고유 상품은 7개이며 페이지 표현은 9개다. 두 추가 표현을 새 상품으로 집계하지 않는다.

## 수정 내용

analysis: 상품 Microdata 우선, 단일 product OG 블록 선택, 기존 native 값 충돌 보류 유지. parser/evidence: 부분 가격/ISO 근거·명시 unknown·수량 라벨·판매처 source identity·옵션/식별자 근거를 기록한다. marketplace finish: 명시적 기존 상품 부분 갱신의 선택적 availability를 지원하지만 다른 API 수집기의 기본 필수값 검사는 유지한다. matching은 optional availability를 안전하게 처리한다. engine은 새 storefront policy를 context에 포함하며 기존 context는 그대로다.

원문 £ 가격을 통화가 없는 상태로 money()에 넘겨 예외가 나던 문제를 수정했다. 원문 숫자 금액 51.77 등을 보존하되 currency는 unknown/null이다. native priceCurrency/가격의 ISO 표기가 있어야 가격 쌍을 전송한다. Microdata/OG의 실제 이름·이미지를 복구했으나 condition을 new로 만들어내지 않는다.

storefront_identity는 optional profile이다. domain은 allowed_product_hosts와 같고 single_merchant=true, 같은 출처 reference, 유효 expires_at이 있어야 한다. 이 정보가 없거나 만료되면 native seller 품질 조건을 유지한다. 이를 추가하면 기존 context와 달라지므로 자동 reset/덮어쓰지 않는다. source origin 식별자의 채택이지 법적 판매자/사업자 표시명의 확인이 아니다. 실제 데모 profile에서도 seller 표시명은 null이다.

## 안전한 실제 조회 재현

```sh
python -m services.collector.unified_live.devtest.inspect_normalization --profiles /run/profiles.json --state-dir /state/bulk/domains --output /outputs/native-diagnostics.json
# 기본 요청 0회. 기존 lookup 권한과 호출 예산이 확인된 경우만 --run 추가.
```

profiles는 host/approval/urls/currencies/selectors/sample_kind와 optional storefront_identity의 배열이다. 호스트 중복 writer는 거부한다. approval은 기존 lookup reference/terms_reference/expires_at/allowed_uses/allowed_hosts/test_allowed를 사용한다. 한 호스트 5개 URL, 전역 동시성 3, 시간/일 예산·최소 간격·공개 HTTPS/TLS/robots/SSRF를 적용한다. 기존 Batch 도메인 원장과 lock을 공유한다. 토큰/API 키는 필요 없으며 전용 API 플랫폼의 일반 HTML 우회는 거부한다. 원문 HTML은 저장하지 않는다. 출력은 실제 native fields/normalized/missing/evidence JSON과 CSV다. 유효 Observation이 있어도 이 진단 도구는 백엔드를 호출하지 않는다.

## 백엔드 검증

devtest.normalization_lab은 /run/external-derived.json의 실제 외부 파생값을 바꾸지 않고 strict v2·최초 관찰 필수값을 확인한다. 적격 body만 loopback HTTP FastAPI로 보낸다. SQLite는 collector_test_external.sqlite라는 격리 namespace만 사용한다. condition이 unknown이면 누락시켜 기본 new가 되게 하지 않고 전송하지 않는다. applied만 성공으로 집계한다.

이번 입력에서는 외부 상품 적격 0, POST 0, applied ACK 0, SQLite 상품 0이다. FastAPI/SQLite를 시작했다는 사실을 외부 상품 적재 성공으로 보고하지 않는다. 별도의 synthetic 양성 대조군은 기존 TLS/Batch/Fleet/실제 자식 워커/HTTP ACK/SQLite 및 신규·가격·판매 완료·예약 보류·중복·재시도·리다이렉트를 검사한다. Docker는 network=none이며 .test 주소의 loopback 핀은 테스트 모듈에만 존재한다. 운영 source policy의 사설 IP/TLS 예외는 추가하지 않았다.

local_receipt는 팀 ingest의 INCOMPLETE_FIRST_OBSERVATION을 반영한다. 모델 optional을 신규 적재 허용으로 잘못 해석하는 양성 결과를 막는다. 팀 FastAPI/DB 코드는 읽기만 했다.

## 중고 경로 및 한계

eBay Used는 기존 Production OAuth/Browse 공식 USED+conditionIds 필터/getItem/단일 ebay_account 공유 원장을 유지한다. 신규·가격 변경·itemEndDate/판매 완료·중복·주기는 기존 전체 테스트와 로컬 통합으로 재검증한다. 이번 실제 API 호출은 0회다. 기본 schedule.policy_reference는 아직 비어 있어 60초 운영 승인을 만들지 않는다. 번개장터·중고나라는 계약/접근/보관·재사용 권한 대기 상태를 유지하며 비공개 API나 로그인/차단 우회를 구현하지 않는다.

## 결과와 남은 조건

외부 원상품 7개 추출 유지, 동일 상품 추가 2형식의 이름·이미지 복구. 실제 유효 v2 상품/외부 상품 ACK 목표는 0개로 미달이다. 코드로 해결한 예외와 추출 누락, v2 condition/신규 availability 계약 문제를 분리해 기록했다. 계약 제안은 NORMALIZATION_CONTRACT_PROPOSAL.md를 참고한다. 원문 상태·통화가 없는 사실을 코드 수정으로 없앨 수는 없다.

NAS/운영 PostgreSQL 변경, API 키 로그/커밋, 팀원 파일 수정은 하지 않았다. 기존 API 한도·전송 승인·가격 검사를 유지했다. 외부 조회는 기존 요청 원장을 보존한 명시적 demo lookup이며 운영 저장/재사용 허가로 확대하지 않았다.
