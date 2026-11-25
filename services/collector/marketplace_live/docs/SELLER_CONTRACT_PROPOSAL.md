# 판매처 보존 계약 변경 제안 — 구현·마이그레이션 미실행

대상 담당자: 팀 FastAPI / PostgreSQL 담당자. 이 문서는 제안이며 팀원 코드나
DB 스키마는 수정하지 않았습니다.

현재 `services/api/kkulpick/models.py`의 Observation은 extra=forbid이고 seller
필드가 없습니다. field_presence Literal에도 seller가 없습니다.
`services/api/kkulpick/ingest.py`의 필드별 merge 및 offers INSERT/UPDATE에도
판매처가 없습니다. 수집기의 `normalize.py`는 seller를 RAM 정규화 결과에만
보존하고 `delivery.py`는 strict Observation 본문만 outbox에 보냅니다.
따라서 실제 손실 지점은 수집기의 Observation 투영과 수신 계약입니다.
관측 JSON에 임의 필드를 추가하면 현재 서버는 422로 거부합니다.

## 제안 요청 규격

기존 v2 클라이언트는 유지하면서 선택 필드를 명시적으로 추가합니다.
서버 배포·계약 합의 전에 클라이언트가 보내지 않도록 capability/config gate가
필요합니다. 서버 변경 없이 수집기 모델만 느슨하게 만들지 않습니다.

```json
{
  "schema_version": 2,
  "source": "ebay_browse",
  "observation_key": "SYNTHETIC:new-event-hash",
  "seller": {"source_seller_id": "SYNTHETIC-ID", "display_name": "SYNTHETIC Shop"},
  "field_presence": ["name", "price", "currency", "availability", "url", "seller"]
}
```

위 예시는 seller 추가 부분만 설명한 발췌로, 완전한 제출 payload가 아닙니다.
seller.source_seller_id는 공급자가 실제로 제공한 경우만 사용하고, 이름으로
아이디를 만들어 내지 않습니다. display_name은 명확한 문자열·최대 길이·제어문자
검사를 적용합니다. 주소·연락처·개인 프로필·계정 토큰을 허용하지 않습니다.

field_presence와 actual model_fields_set 검증에 seller를 추가합니다. 생략은
기존값 유지입니다. 명시적 null에 의한 삭제는 별도 합의가 필요하며, 첫 버전에서는
seller=null 제출을 거부하는 편이 명확합니다. 원본 공급자에 판매처가 없으면
소스명/사이트명을 판매처로 임의 대체하지 않습니다.

## 저장·변경 이력

- seller는 여러 판매처가 공유하는 catalog_items가 아니라 offer 단위에 귀속합니다.
  예: offers.seller_source_id, seller_display_name, seller_observed_at.
- 선택적 정규화 테이블을 만들 경우 `(source, source_seller_id)` 기준으로 관리하며
  source_seller_id가 없으면 이름만으로 여러 판매자를 자동 병합하지 않습니다.
- 별도 seller_observed_at으로 오래된 관측/동일 시각 충돌을 기존 정책대로 처리합니다.
  seller 수정은 가격/통화 시각을 갱신하지 않습니다. 누락 시 이전값을 보존합니다.
- source_listing_id/variant_key와 판매처가 모순되면 식별 충돌로 격리합니다.
- offer_changes, changed_fields, 공개 조회 DTO에서 seller 노출 여부와 권한을 합의합니다.
  기존 offer는 nullable 상태로 두며 실제 증거 없이 backfill하지 않습니다.

## 멱등성·호환성

관측 key/hash는 새 seller payload를 포함해야 하지만, 이미 outbox에 저장된
관측의 본문이나 key를 덮어쓰지 않습니다. 기존 body는 그대로 재전송하고,
seller backfill은 새 시각/새 관측 key로 제출합니다. 동일 key로 seller만 추가하면
현재 PAYLOAD_CONFLICT 계약과 충돌하므로 금지합니다.

기존 v2 payload 재전송·source+observation_key 유일성·권한 검사·가격 이상
검사를 유지합니다. API의 수신과 조회 응답을 함께 점검합니다. 마이그레이션은
담당자가 검토 후 실행하고 rollback은 nullable 필드/기능 gate 중심으로 준비합니다.

## 권한과 승인 전 검증

판매자 표시명/계정 식별자는 개인정보가 될 수 있습니다. 공급자별 저장·표시·재사용·
보유기간·삭제 요청 처리 범위를 먼저 확인합니다. YES24는 지속 저장·재사용
허가 확인 전 DB 적재를 금지합니다. 키 발급만으로 이 권한을 추정하지 않습니다.

담당자 검증 항목: 기존 v2 무변경 수신, seller 포함 수신·조회, 생략 값 유지,
오래된 관측 무시, 동일 시각 충돌, 새 key backfill, 기존 immutable 재전송,
권한 만료/삭제, seller 유무와 관계없는 가격 이상 탐지, 허용되지 않은 추가 필드 거부.
