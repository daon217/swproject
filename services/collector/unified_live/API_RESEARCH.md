# 공식 접근 경로 조사 (2026-11-23)

공식 문서만 검토했다. 상품 조회 요청·새 키 발급·약관 동의·유료 사용·프로젝트 권한 승인은 실행하지 않았다.
한도/비용/저장권은 계정·계약별로 달라지므로 확인되지 않은 숫자는 미확인으로 표시한다.
API 키 발급 자체가 타 판매자 콘텐츠의 지속 저장·재사용 허가는 아니다.

| 서비스 | 공식 경로/검색·URL | 발급/한도·비용 | 저장/재배포 및 현재 상태 |
|---|---|---|---|
| 도매꾹 | 기존 공식 검색/상세 코드 | 기존 원장/계정 정책 및 더 작은 로컬 예산 유지 | 기존 field storage grant/가격 승인 유지; 이전 실제 연결 이력, 이번 Mock만 |
| YES24 | [공식 포털](https://developers.yes24.com/), 검색/상세·상세 링크 | 계정 API Key; Basic 초과는 Partner 문의, 프로젝트 현 할당은 계정 확인 필요 | 지속 저장·재사용 예외 허가 전 저장 차단; 기존 구현, 신규 live 없음 |
| Serper | [Shopping 서비스](https://serper.dev/), 기존 POST /shopping | trial/credit 상품, 실제 단가·통화·계정 credit은 설정/대시보드 확인 | 검색 결과 콘텐츠의 제3자 권리 별도; 기존 구현, 누락 native 필드는 보류 |
| eBay / Used | [Browse](https://www.developer.ebay.com/develop/api/buy), 검색·getItem·itemWebUrl | Production OAuth와 Buy 권한; [계정 한도](https://developer.ebay.com/develop/get-started/api-call-limits) 확인, OAuth도 로컬 예산 예약 | 기존 코드/이전 live 이력. 신규 정책은 허가 대기, 최신순은 공식 sort=newlyListed 사용 |
| 11번가 | [공식 Open API 소개](https://techtalk.11stcorp.com/2023/pdf/TECH-TALK-2023_SESSION-04.pdf) | 현 portal 조회503; 프로젝트 검색 권한/숫자 한도/과금 미확인 | offline 어댑터만 확인; live 연결 완료로 표시하지 않음 |
| 쿠팡 | [공식 Partners 안내](https://partners.coupangcdn.com/partners-guide/partners-guide-20241216163254.pdf), 제휴 상품 API/딥링크 | Partners API 이용 자격·키·실제 한도 확인 필요; 판매자 API와 구별 | 검색 재사용·표시/제휴 조건 확인 필요; 프로젝트 신규 transport 없음 |
| 네이버쇼핑 | [종료 공지](https://developers.naver.com/notice/article/32564) | 기존 쇼핑 검색 서비스는 2026-07-31 종료 공지; 과거25,000/일 문서 적용 금지 | [FAQ](https://developers.naver.com/products/intro/faq/faq.md)는 별도 저장/재가공 제한. 종료 API 신규 구현 안 함 |
| G마켓/옥션 | [ESM Trading 상품 목록](https://etapi.gmarket.com/160) | 문서상 분당20회; 등록 판매자 상품 관리 맥락, 승인·현 계정 과금 미확인 | 전체 쇼핑몰 공개 검색 권한으로 간주하지 않음; 프로젝트 미연동 |
| Etsy | [공식 요청](https://developers.etsy.com/documentation/essentials/requests/), [Reference](https://developers.etsy.com/documentation/reference/) | App key와 API별 scope; [QPS/QPD는 앱 portal](https://developers.etsy.com/documentation/essentials/rate-limits/), 429 Retry-After | 앱/상업 접근 및 저장·표시 조건 검토 대기; 미연동 |
| Amazon | [현재 Creators API](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction), [PA-API 안내 경로](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/paapiv5-deprecation) | Associates/Creators의 현 자격·할당·비용 로그인 검토 필요; 오래된 PA-API 가정 사용 안 함 | 콘텐츠 캐시·표시·재배포 계약 미확인; 미연동 |
| AliExpress | [공식 affiliate.product.query 문서](https://developer.alibaba.com/docs/api.htm?apiId=45803), 상품 URL 응답 | app/제휴 권한 필요; 해당 문서는 무료API로 표시하지만 현 endpoint/할당/프로젝트 자격 재검토 필요 | 오래된 TOP 문서만으로 현재 gateway를 확정하지 않음; 미연동 |
| 번개장터 | 기존 파트너 API 조사/Mock | 프로젝트 파트너 계약·키·실제 한도 미확인 | 운영 차단, 비공개 엔드포인트/로그인 우회 없음 |
| 중고나라 | 기존 공식 접근 조사/Mock | 승인된 프로젝트 상품 검색 API·저장 권한 미확인 | 운영 차단 |

## 식품

[식약처 원재료 정보](https://www.data.go.kr/data/15058665/openapi.do)는 원재료의 이름/코드 등
기초 사전 데이터다. 포털은 무료/제한 없는 이용허락/개발10,000을 표시하지만 활용신청·키와
정확한 필드 연결을 확인해야 한다. 특정 판매 상품의 완성된 알레르기 목록으로 해석하지 않는다.
[원재료 정보 조회](https://www.data.go.kr/data/15111913/openapi.do)도 별도 신청/품목 식별 검토가 필요하다.
운영계정은 심의 대상으로 안내된다. 현재 프로젝트 키·검증된 상품 결합키가 없어 live 미연동이다.
[식품안전나라 I2790](https://www.foodsafetykorea.go.kr/api/openApiInfo.do?menu_grp=MENU_GRP31&menu_no=661&show_cnt=10&start_idx=1&svc_no=I2790&svc_type_cd=API_TYPE06)는
영양성분 응답이며 완전한 알레르기 API로 사용하지 않는다. 키가 URL 경로에 들어가는 문서 예제도 로그에 넣지 않는다.
[법령의 표시 규칙](https://www.law.go.kr/flDownload.do?bylClsCd=110201&flSeq=147458089&gubun=)은
원재료 함유와 동일 시설 혼입 경고를 구분한다. 코드는 표시 근거만 추출하며 개인의 섭취 안전을 판정하지 않는다.

우선순위: 기존 계정/허가 소스의 승인된 소량 검증 → 팀 계약 → Etsy/쿠팡 등 프로젝트 자격 검토.
공식 URL이 있다는 이유만으로 새로운 서비스를 연동 완료/무료 무제한/저장 허가로 표시하지 않는다.
