# 홈페이지 실수집에서 확인한 계약 장애 — 백엔드 담당자 검토안

백엔드 및 팀원 코드는 수정하지 않았다. 기준 계약은 719cb8e 작업 때 읽은 backend-test b51ffdc의 Observation 모델·ingest 규칙이다.

## 상태 미제공

외부 Oxylabs 데모의 상품 3건은 이름·가격·통화·이미지·URL은 있지만 itemCondition/condition이 없었다. `new`나 `used`를 추론할 근거가 없다. 현재 Observation은 condition이 new/used이며 기본값 new다. 누락해 기본값을 적용하는 것도 원문에 없는 신품 상태 생성이므로 하지 않는다.

제안: 명시적 unknown 상태를 API·DB 제약·조회/추천 계약에 함께 추가한다. 버전/기능 협상이 된 뒤에만 수집기가 사용하도록 한다. 기존 v2 서버에는 unknown/null/비표준 값을 보내지 않는다. Used 전용 수집기는 unknown을 중고로 취급하지 않는다. backend DB migration 및 팀 클라이언트/추천 처리 변경은 담당자 범위다.

## 판매처 정보

실제 Observation 스키마에는 seller_name이 필수가 아니고 Extension MatchingProfile의 seller_id/name도 optional이다. 새 homepage 모드에서는 이것을 추가 필수값으로 막지 않도록 정합성을 맞췄다. 판매처명이 없으면 None이며 도메인을 법적 판매처명으로 생성하지 않는다. source/URL과 기존 provenance의 source_origin만 유지한다.

필요하면 향후 확장 계약에 seller_site_host/identity_basis 및 legal_seller_verified를 추가할 수 있다. 현재 서버가 받지 않는 필드는 전송하지 않는다. 기존 홈페이지 모드 이외 수집기의 판매처 품질 기준은 이번에 해제하지 않았다.

## 집계 가격과 옵션

web-scraping.dev 상세 3건의 JSON-LD는 AggregateOffer였다. lowPrice/highPrice/offerCount를 단일 상품 가격·수량으로 치환하지 않는다. 실제 공개 옵션별 URL에서 단일 Offer/SKU와 선택된 옵션 근거가 확인되는 어댑터, 또는 별도의 가격 범위 계약이 필요하다. 현 Observation에 가격 범위·임의 default 옵션을 밀어 넣지 않는다.

## 재고와 이미지

InStock 같은 원문 상태와 실제 수량은 별개다. 수량이 없다고 0/1을 생성하지 않는다. 신규 Observation의 availability가 실제 없으면 기존 계약상 보류한다. 이미지 URL 추출은 다운로드·시각 분석 성공과 다르며 별도 이미지 이용 권한과 URL 검증이 필요하다.

## 운영 전 확인

관리자는 소스별 수집·저장·재사용 권한, backend host/currency/image-host 목록, 가격 단위 의미, unknown·옵션 정책을 확인해야 한다. 원문 필드가 계약을 충족하는 사이트에서는 새 homepage 경로로 기존 Observation/Extension 큐를 사용한다. 모든 일반 쇼핑몰이 자동으로 운영 가능하다고 판단하지 않는다.
