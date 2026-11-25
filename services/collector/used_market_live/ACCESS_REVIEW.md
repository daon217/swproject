# 국내 중고시장 접근·저장 권한 조사 (2026-11-22)

저장소 전체 코드/문서 검색 결과 marketplace_live/docs/USED_MARKET_ACCESS.md만 있었고
번개장터/중고나라 상품 어댑터는 없었다. 기존 모듈 중 재사용할 별도 국내 수집 코드는 발견하지 못했다.
프로젝트 .env 및 이전 eBay 키 파일에서 국내 공급자 관련 변수 이름은 발견되지 않았다.
키 값은 출력하지 않았고 자격 증명의 존재만으로 권한이 있다고 판단하지 않는다.

번개장터에는 파트너용 Bunjang Open API와 카탈로그 다운로드 문서가 있다.
공식 소개는 계약 체결과 파트너 계정 설정 후 키를 발급받도록 안내한다.
인증 문서는 access/secret 기반 단기 JWT Bearer를 설명한다. 이 프로젝트의 서명된 계약,
entitlement, 호출 제한, 저장/재사용/재배포 범위 및 보유기간은 확인되지 않았다.
따라서 JWT 발급·카탈로그 다운로드·상품 요청 코드는 구현하지 않았다.

공식 카탈로그의 pid/name/price/condition/saleStatus/uid/quantity 필드에 대한 합성 Mock 변환만 제공한다.
실제 카탈로그가 명시하지 않는 통화, 공개 상품 URL, 판매처 표시명은 자동 생성하지 않는다.
uid는 판매처 이름으로 위장하지 않는다. DAMAGED를 단순 중고나 부품용으로 덮어쓰지 않는다.
원문/사진/설명/판매자 개인정보의 저장 허가도 별도 계약 검토 대상이다.

중고나라의 현행 공식 약관 제20조 금지행위는 사전 승낙 없는 서비스 정보의 복제/출판 등 사용과
제3자 제공을 제한한다. 사이트의 판매자 등록/제휴 기능이나 다른 목적의 API 연동을
외부 상품 수집·축적 권한으로 해석하지 않았다. 이번 조사에서는 승인된 상품 API 문서와
프로젝트 접근 권한을 확인하지 못했다. 비공개 검색 API나 우회 프록시는 사용하지 않는다.

국내 두 프로필의 --once/--watch는 설정과 환경변수에 관계없이 운영 차단이다.
해제하려면 서명된 계약, 승인 endpoint/인증, 실제 native schema, 권한/저장/재사용/개인정보 범위,
호출·비용 한도 및 팀 API 지원을 확인한 뒤 별도 구현·테스트·실행 승인이 필요하다.
이번 Mock canonical DTO는 실제 공급자 응답 스키마가 아니다. Mock만 통과했다고 운영 준비 완료로 표시하지 않는다.

공식 문서만 읽었으며 상품 API 호출, 로그인, 카탈로그 다운로드, 제휴 문의 발송은 하지 않았다.

- https://api.bgzt.guide/ (파트너 계약 및 키 발급 조건)
- https://api.bgzt.guide/doc-662202 (인증)
- https://api.bgzt.guide/api-10619068 (카탈로그 필드; 실제 다운로드는 하지 않음)
- https://common.joongna.com/static/terms/TermsOfService_new.html (약관)
- https://web.joongna.com/privacy-policy
- https://edp.ebay.com/api-docs/buy/ref-buy-browse-filters.html (공식 conditions/conditionIds 필터)
