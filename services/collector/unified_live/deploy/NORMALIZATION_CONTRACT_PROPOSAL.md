# 원문 unknown 처리와 팀 계약 협의안 — 2026-11-25

## 읽기 전용으로 확인한 현재 계약

팀 models.py와 수집기 Observation은 condition=new/used만 허용하며 기본값은 new다. 따라서 condition을 생략하여 unknown을 표현하면 신품이라는 잘못된 정보가 된다. 수집기는 condition이 없을 때 observation을 생성하지 않고 metadata.normalization_evidence.condition=unknown 및 condition_unknown_contract_required를 기록한다. 팀 API/DB 코드는 변경하지 않았다.

availability는 모델상 optional이지만 팀 ingest.py는 신규 상품의 첫 관찰에 name/price/currency/availability/url이 모두 field_presence에 있어야 한다. 없으면 INCOMPLETE_FIRST_OBSERVATION quarantine이다. 모델 검증 성공과 상품 적재 성공을 구분해야 한다. 새 상품의 재고 상태가 없으면 계속 보류한다. 기존 상품의 부분 갱신만 명시적 호출 문맥에서 필드를 생략할 수 있으며, 생략은 unknown 값 전송이나 기존 상태 초기화가 아니다. 일반 URLWorker는 새 상품/갱신 모두 기본 보수 규칙을 유지한다.

seller/image/stock_quantity는 현재 v2 본문 필드가 아니다. seller 보류는 HTML 수집기 자체 품질 조건이다. 검토된 단일 판매처 profile의 storefront_identity를 사용할 수 있게 했으나 source origin identity와 법적 판매자 이름을 구분한다. 원문 seller가 없으면 result.seller는 null이고 법적 판매자 검증은 false다. 도메인을 사람/사업자 표시명으로 위장하거나 v2에 새 seller 필드를 보내지 않는다. Marketplace에서 플랫폼 도메인을 개별 판매자 ID로 쓰지 않는다.

## 현재 가능한 수정

* Microdata를 페이지 일반 OG보다 우선하고 명시적 product OG 블록을 분리한다. 같은 근거 안에서 서로 충돌하면 여전히 보류한다.
* £/$ 등 원문 기호와 숫자 금액을 부분 추출할 수 있지만 기호만으로 ISO 통화를 결정하지 않는다. 명시 priceCurrency 또는 가격에 인쇄된 허용 ISO 코드만 사용한다. 가격·통화 쌍이 없으면 v2 상품을 만들지 않는다.
* In stock (22 available)처럼 명시된 원문은 재고 22와 available로 읽는다. 모르면 수량 null이며 available/0/1을 임의 생성하지 않는다. 수량/상태 충돌은 unknown으로 보류한다.
* 새 Microdata SKU/URL을 읽더라도 기존 전달 이력의 식별자를 자동 변경하지 않는다. 새 명시 selector로 전환하려면 별도 profile/context 검토가 필요하다. 옵션 미노출은 not_exposed이지 옵션이 존재하지 않는다는 주장이 아니다.

## 팀 담당자가 결정할 계약 변경안

기존 v2는 그대로 유지하고 version/capability 협의 후 condition=unknown과 availability=unknown(또는 명시 nullable)을 지원한다. condition 기본 new를 없애거나 source evidence 없이 기본값이 적용되지 않도록 한다. 신규 상품에서 unknown 상태를 허용하는 완전성 규칙과 DB 제약을 함께 변경해야 한다. 파이썬 모델의 enum만 바꾸면 충분하지 않다.

권장 확장: condition_native, availability_native, purchase_available(nullable bool), stock_quantity(nullable nonnegative int), stock_quantity_kind(exact/estimated/unknown), seller_identity(kind/domain/native_id/display_name/legal_seller_verified/reference), options_status 및 provenance. unknown 구매 가능 여부는 null이며 false나 재고 0으로 강제하지 않는다. unknown 상품의 추천/필터는 신품으로 취급하지 않도록 정의한다.

Observation 키/멱등성/ACK/가격 의미 검사와 가격 이상치 규칙을 유지한다. API의 applied와 quarantine ACK를 구분하고, 최초 unknown 생성·기존 known→unknown·부분 필드 생략·중복·같은 시각 충돌·가격 이상치 테스트를 추가한다. 잘못된 상태를 바꿔서 성공 건수를 만들지 않는다. 가격의 통화는 근거가 없으면 상품 가격 쌍을 유지 보류하며 source별 검증된 통화 표시 근거를 확보해야 한다.

이번 외부 원상품 7개는 모두 condition이 없었다. Books 3개는 명시 ISO 통화도 없고, WebScraper 3개는 availability가 없어 신규 생성 규칙에도 걸린다. 현재 계약에서 이 사실을 보존하면서 유효 상품 1개를 만드는 것은 불가능했다. 팀 승인을 받아 계약을 확장하거나 원문이 상태를 명시하는 허용 데이터를 확보해야 한다. 본 문서는 제안이며 운영 활성화/저장 권한 승인이 아니다.
