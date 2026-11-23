# 로컬 조사 및 이전 산출물 대조

조사일: 2026-11-22. 원본 C:/Users/junse/Python/swproject와 Codex Documents 작업 폴더를 구분했다.
원본 브랜치 part/최준서-collector, HEAD a8be688. Codex 작업 폴더에는 .git이 없다.
원본의 API/수집기 변경과 미추적 디렉터리는 기존 작업이며 이번 작업에서 checkout/reset/clean/commit/push하지 않는다.
Git status는 no-optional-locks로 읽고 Git index 해시를 보존한다.

기존 343개/하위 사례 85개를 자연 시계·네트워크 차단 상태에서 재검증했다.
최신 used-markets-baseline의 적용 후 전체 파일 해시와 원본을 비교해 기존 305개 파일 및 index 상태를 확인했다.
이전 outputs의 stability/integration/readiness/Serper/eBay/Used 패치는 서로 다른 시점의 증분 산출물이다.
refinement 패치가 포함된 최신 적용 상태를 기준으로 확인했으며 오래된 패치를 일괄 재적용하지 않았다.
Codex work의 과거 후보 디렉터리는 과거 스냅샷이고 원본에 덮어쓰지 않았다.

관련 코드: domeggook_live 전체 실행/복구/전송, marketplace_live의 config/HTTP/OAuth/adapter/normalizer/
Worker/Outbox/probe/deploy, used_market_live, elevenst_offline, real_feed_collectors 및 팀 순수 계약/ingest를 조사했다.
food ingredients/allergens는 기존 detail_enrichment_v1/clean.py의 EXTRA_RULES 및 food profile에서 발견해 재사용했다.
번개장터/중고나라 신규 라이브 transport는 기존 조사와 동일하게 없고 Mock/차단 경계가 있다.
11번가의 live.py는 실제 HTTP 구현이 아닌 Protocol 경계다. 기존 feed는 일회 fetch/replay 경로로,
운영 자동 적재에 자동 등록하지 않았다.

비밀값 검사는 추적 파일 80개, 현재 stage 0개와 새 반영 후보에 대해 실제 비공개 env의 강한 값 일치 및
개인키/AWS/GitHub 토큰 패턴을 메모리에서 비교한다. 값은 출력하지 않는다.
현재 root .env는 추적되지 않는다. 원격/전체 Git 이력 감사는 실행하지 않았으므로 과거 유출 부재를 단정하지 않는다.
최종 숫자/파일 목록/검색 결과는 outputs의 git-secret-audit 및 apply-verification을 기준으로 본다.

공식 문서 재검토:

- YES24 https://developers.yes24.com/support/terms : 일시 캐시와 별도 DB 축적/재배포를 구분한다. 별도 허가 전 DB 비활성 유지.
- Serper https://serper.dev/terms : third-party content 권리 및 attribution 조건을 별도 확인해야 한다.
- eBay https://edp.ebay.com/api-docs/buy/ref-buy-browse-filters.html : 공식 중고 필터.
- 번개장터 https://api.bgzt.guide/ : 계약/파트너 계정 후 키 발급 조건.
- 중고나라 https://common.joongna.com/static/terms/TermsOfService_new.html : 사전 승낙 없는 정보 복제·제공 제한.
- 11번가 https://openapi.11st.co.kr/openapi/OpenApiFrontMain.tmall : 이번 도구에서는 503, 권한/전체 본문 미확인.
- 식품안전나라 https://www.foodsafetykorea.go.kr/portal/board/boardDetail.do?bbs_no=bbs001&menu_grp=MENU_NEW01&menu_no=3120&ntctxt_no=22276
- Docker https://docs.docker.com/compose/how-tos/use-secrets 및 https://docs.docker.com/reference/compose-file/services/

공식 문서 열람 외 상품 API/카탈로그 다운로드·운영 DB 접근은 하지 않았다.
Docker CLI/daemon이 없으므로 Compose JSON 구조·기본값·코드 COPY 범위·진입점만 정적/로컬 검증했다.
