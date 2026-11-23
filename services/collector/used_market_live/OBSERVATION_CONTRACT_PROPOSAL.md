# 팀 DB/API 담당자 전달안: 중고 상태 확장·판매처·삭제 이벤트

검토용 계약 변경안이다. 팀 API/DB 코드와 기존 v2 이벤트는 수정하지 않았다.
기존 marketplace_live/docs/EBAY_OBSERVATION_CONTRACT_PROPOSAL.md의 unknown 재고 제안에 추가한다.

## 상태 확장

현재 v2 condition은 new/used만 허용하고 extra 필드를 거부한다. 리퍼/개봉/부품용을 new 또는 used에
몰아넣지 말고 서버의 확장 기능 지원을 합의한 뒤 아래 condition 및 condition_detail을 수용한다.
구버전 서버에는 새 필드를 보내지 않는다. v2 capability 협상 또는 v3 endpoint 중 팀이 선택하고
계약 테스트를 먼저 통과시킨다.

| eBay ID | 제안 condition | condition_detail |
| --- | --- | --- |
| 1000 | new | new |
| 1500 | open_box | new_other_open_box |
| 1750 | new_with_defects | new_with_defects |
| 2000 | refurbished | certified_refurbished |
| 2010/2020/2030 | refurbished | excellent/very_good/good_refurbished |
| 2500 | refurbished | seller_refurbished |
| 2750/2990/3000/3010/4000/5000/6000 | used | like_new/pre_owned_excellent/used/pre_owned_fair/very_good/good/acceptable |
| 7000 | for_parts | for_parts_or_not_working |

provider_condition_id/label과 category ID를 보존해 Graded/Ungraded 등 카테고리별 의미를 분리한다.
상품명에서 "새상품"이라는 단어를 찾아 상태를 판정하지 않는다. 번개장터 DAMAGED는 damaged로 구별하며
부품용이라고 단정하지 않는다. 현재 Used 프로필은 리퍼/개봉 상태 계약이 확장돼도 used만 수집한다.
이 상태들을 실제 수집하려면 별도 정책/동의가 필요하며 기존 eBay 일반 프로필에서 확장 지원을 검토한다.

## 필수 정보와 구매 가능 여부

신규 offer에는 name, 정확한 문자열 Decimal price, ISO currency, 검증된 HTTPS URL, 식별자,
판매처, condition, availability가 필요하다. 기존 v2의 availability는 숫자 재고가 아니다.
알 수 없는 availability는 unknown + pending_verification으로 수용하고 구매 가능 결과에는 노출하지 않는다.
exact_stock_quantity는 nullable이며 eBay Browse 추정값/임계값은 별도 estimated/threshold 필드로 보존한다.
null을 DB 기본값 0/1로 치환하지 않고 배송 옵션별 추정 수량도 합산하지 않는다.

seller 필드는 provider_seller_id와 display_name을 분리해 보존한다. 식별자/표시명이 없는 경우를 구별하고
개인 연락처·주소·채팅·신원 정보를 대체 필드로 수집하지 않는다. 기존 v2는 판매처를 저장하지 않으므로
이번 eBay Used에서도 RAM 검사만 하며 DB 보존 문제는 서버 계약 변경이 필요하다.
신규 국내 source 값/호스트/통화/권한 검증도 API enum에 명시적으로 추가해야 한다. eBay Used는
기존 source=ebay_browse와 source_listing_id/variant_key를 유지해 일반 eBay와 중복 offer가 생기지 않게 한다.

## 판매 상태 및 제거 계약

- active → available. sold → ended 및 sale_status=sold.
- inactive/deleted → 공개 노출 중단. ended와 구체적인 사유를 분리한다.
- reserved/unknown → availability unknown, 확인 전 구매 가능으로 표시하지 않는다.
- eBay OUT_OF_STOCK은 out_of_stock, 검증된 종료 시각 경과는 ended이며 판매 완료라고 단정하지 않는다.
- 검색 누락/404/410/403/타임아웃은 삭제 증거로 사용하지 않는다. 권한이 확인된 상세 상태/변경 피드 필요.

삭제/비활성은 일반 상품 upsert와 별도 tombstone API 이벤트를 제안한다.
필드: schema version, source, listing/variant ID, observed_at, stable event key,
action=withdraw/delete, authoritative reason 및 허가된 증거 참조.
원문 가격/이름이 삭제돼도 최소 ID 이벤트로 처리할 수 있어야 한다. 권한과 증거가 없는 삭제 요청은 격리한다.
DB 직접 DELETE/INSERT는 수집기에 허용하지 않는다. 회사의 개인정보 삭제·보유기간 계약에 따라
공개 노출 중단과 개인정보/원문 제거, 최소 감사 기록 보존을 각각 처리한다.

## 호환성 및 수락 기준

기존 원장/체크포인트/Observation body/key/outbox는 재작성하지 않는다. 재전송에는 동일 key/body를 쓴다.
확장 서버 먼저 배포 → capability 확인 → 합성 계약 테스트 → 승인된 소량 조회 → 별도 DB 승인 순으로 진행한다.
리퍼/개봉/부품용의 세부 상태 및 판매처가 왕복 보존되고, unknown이 재고 있음으로 노출되지 않아야 한다.
삭제 이벤트 재전송은 멱등이어야 하며 오래된 active가 최신 tombstone을 덮어쓰면 안 된다.
저장/재사용 허가, 가격 기준 확인과 팀 DB 소유자 승인 검사는 확장 후에도 유지한다.

본 문서는 전달용 산출물이며 실제 담당자에게 메시지를 발송하지 않았다.
