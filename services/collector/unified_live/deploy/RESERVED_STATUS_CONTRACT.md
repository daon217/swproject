# 팀 API 협의안: 예약 및 중고 판매 상태 (제안만, 2026-11-25)

팀원 소유 FastAPI/DB 스키마는 변경하지 않았다. Observation v2의 현재 허용 상태를 임의 확장하지 않는다.

현재: condition은 new/used만, availability는 available/out_of_stock/ended만 전송한다. HTML 예약 증거 reserved/예약/예약중은 raw native label과 metadata.listing_status=reserved, purchase_available=false로 기록하고 reserved_status_contract_required로 보류한다. 예약을 품절이나 판매 완료로 위장하지 않는다. 404/검색 누락은 verification_required이지 삭제/판매 완료 확정이 아니다.

제안: 새 버전/명시적 capability negotiation을 통해 condition_detail(new/used/refurbished/open_box/for_parts/unknown), listing_status(active/reserved/ended/deleted/inactive/unknown), stock_quantity(nullable integer), stock_quantity_kind(exact/estimated/unknown), purchase_available(nullable boolean), native_status 및 checked_at/source provenance를 지원한다. seller native ID/display name, 이미지·모델 식별 메타데이터의 영속 저장도 기존 제안에 따라 협의한다.

예약: exact stock_quantity가 없으면 null, 구매 가능 여부는 사이트의 명시 정보만 사용한다. 명시적 예약 상태 때문에 즉시 구매가 불가한 사례를 false로 기록해도 실재 수량은 추론하지 않는다. deleted/inactive 이벤트는 공급자 권한과 본문 생략 정책을 확인하고, 삭제 요청이 있다면 원문을 보존하는 대신 최소 식별자/증거 해시만 남기는 별도 보유기간 정책이 필요하다.

기존 observation_key/variant_key/source_listing_id, 멱등 ACK, 신규·갱신 판정 및 Outbox 재시도는 유지한다. 새 상태가 fingerprint에 포함되어 상태 전환이 변경 이벤트가 되도록 계약 테스트를 추가한다. 구버전 API는 표현 불가능한 상태를 계속 보류하며 기능 협의 없이 전송하지 않는다. 예산·보관 권한 또는 공급자 접근 권한을 이 제안으로 승인하지 않는다.
