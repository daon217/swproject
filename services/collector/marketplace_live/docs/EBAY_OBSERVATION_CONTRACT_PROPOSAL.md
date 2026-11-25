# 팀 API 담당자 검토안: 알 수 없는 구매 가능 상태와 eBay 세부 상태

제안 문서이며 API/DB 코드는 수정하지 않았다. 현 수집기는 미지원 상태를 계속 보류한다.
데이터 저장/재사용 허가, 가격 의미 확인, 소유자 승인 검사도 그대로 유지한다.

## 현재 계약 조사

services/api/kkulpick/models.py의 Observation은 condition을 new/used로 제한하고,
availability를 available/out_of_stock/ended 또는 생략 가능하게 정의한다. 숫자 재고 필드는 없다.
services/api/kkulpick/ingest.py는 신규 offer의 첫 관측에 name/price/currency/availability/url이
모두 없으면 INCOMPLETE_FIRST_OBSERVATION으로 격리한다. 따라서 availability를 생략하는 것은
기존 offer의 부분 업데이트에는 가능하지만 신규 상품 수용 문제를 해결하지 않는다.

즉 필수값은 확정 재고 수량이 아니라 구매 가능 상태다. Browse의 추정 수량을 확정 수량으로
전환하거나 누락 상태를 available/out_of_stock으로 채우는 해결책은 사용하지 않는다.
동일 상품의 기존 기록 존재 여부를 확인하지 않은 수집기가 부분 업데이트로 우회 전송하지도 않는다.

## 호환성을 갖춘 확장 제안

1. API가 지원하는 스키마 버전/기능을 먼저 협의한다. 새 버전(예: v3) 또는 명시 capability로
   availability=unknown을 허용하고 신규 offer를 pending_verification으로 수용한다.
   unknown은 구매 가능 상품 목록/가격 비교 대표값/재고 있는 상품 필터에서 제외한다.
2. availability와 quantity를 분리한다. exact_stock_quantity는 nullable 비음수 정수,
   estimated_quantity는 별도 nullable 필드, quantity_kind는 unknown/estimated/exact/threshold.
   threshold에는 값과 비교 연산자를 보존한다. eBay Browse는 exact_stock_quantity=null로만 전송한다.
   배송 옵션별 동일 재고를 합산하지 않으며 임계값을 실제 수량으로 계산하지 않는다.
3. condition_detail 및 provider_condition_id/label을 함께 허용한다. new_other_open_box,
   new_with_defects, certified/excellent/very_good/good/seller_refurbished, like_new,
   pre_owned_excellent/fair, very_good/good/acceptable, for_parts_or_not_working,
   graded/ungraded/unknown을 구분한다. 세부 상태가 손실되는 new/used 단독 분류는 금지한다.
   category ID 및 provider 원문으로 카테고리별 grading 의미를 해석하고 일반 마모 등급과 분리한다.
4. seller/provider merchant와 URL의 정합성도 별도 협의한다. 현 v2는 판매처를 저장하지 않으므로
   수집기는 RAM 검사만 한다. 기존 판매처 계약 제안과 함께 검토한다.
5. 마지막으로 알려진 availability와 이번 unknown 관측을 별도 시계/증거로 보관한다.
   새 unknown 관측이 과거 available을 최신 확정값처럼 재게시하지 않게 하고, 유효기간 경과 시
   공개 구매 가능 상태를 만료시킨다. 공급자별 조회 시각과 근거 필드를 기록한다.

## 출시 순서와 수락 기준

- 팀 API 담당자가 스키마/검증/마이그레이션/조회 필터를 구현하고 수집기와 계약 테스트로 합의한다.
- 기존 v2 이벤트 body, observation_key, outbox 항목은 재작성하지 않는다. 새 계약 이벤트만 새 버전으로
  만들고 source_listing_id/variant_key는 유지한다. 재시도에는 같은 body/key를 재사용한다.
- unknown 신규 상품은 pending으로 수용되지만 구매 가능으로 노출되지 않아야 한다.
- LIMITED_STOCK이며 수량 미상인 상품은 available + exact=null로 정상 수용되어야 한다.
- OUT_OF_STOCK 및 ended는 서로 구분하고, 모순된 증거는 공개 상품으로 승격하지 않는다.
- unknown → available 갱신은 관측 시각 순서로 처리하고 동일 이벤트 재전송은 중복 저장하지 않는다.
- open-box/refurbished/parts를 new로 노출하지 않는다. 세부 상태/판매처가 왕복 보존되어야 한다.
- null 수량을 DB 기본값 0/1로 대체하지 않는다. 임계값과 추정 수량도 exact에 저장하지 않는다.
- 저장·재사용 허가 및 가격 기준 검사는 확장 계약에서도 동일하게 강제한다.

계약 승인/구현 전에는 현재 보류가 안전한 동작이다. 이번 변경은 확실한 구매 가능 상태와
표현 가능한 condition만 현 v2로 만들며, DB 전송 권한을 추가하지 않는다.
