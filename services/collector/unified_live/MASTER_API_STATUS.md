# 추가 공급자 상태 — 2026-11-23

기존 API_RESEARCH.md는 이전 시점의 조사 기록이다. 이번 실제 소량 조회를 아래에 별도로 기록한다.
키 발급/공개 접근과 지속 저장/경쟁서비스 재배포 권한은 다르다. 로컬 운영 config는 모두 비활성이다.

| 소스 | 실제 실행 / 기존 코드 | 인증·한도·저장 및 남은 일 |
|---|---|---|
| eBay/Used | Production OAuth1/Used검색1/getItem1, 정상1, 정확수량미상 | 기존권한·공유원장재사용; 60초는policy_reference와할당확인후; 팀PG전송0 |
| Smartify | 공식공개피드3개v2검증; HTML308보류 | [공식개발자문서](https://smartify.in/developers/): 익명읽기/캐시/인용, 경쟁카탈로그재배포별도제한. 자동저장허가로간주안함 |
| YappyKids | 공식피드3개v2적합; MCP검색+상세3개condition/seller보류 | [공식agents](https://www.yappykids.com/agents): 공개read-only MCP/피드, 60/분3000/일/IP. 운영피드로컬한도는더작게; attribution/판매처증거/팀host계약필요 |
| Perfume Registry | 공개metadata확인, 기존core변환기재사용 | [공식AI안내](https://perfumeregistry.com/ai), 이번상품조회없음. 원통화/업데이트/저장범위별도검증 |
| OpenFoodFacts | v3.6 exactGTIN evidence어댑터+Mock, 실조회0 | [공식API](https://openfoodfacts.github.io/openfoodfacts-server/api/): product15/분, search10/분, user-agent연락처/앱usage등록, ODbL/DbCL/이미지별조건. community이므로항상review, 아직policy준비안됨 |
| 롯데ON | 후보등록/공식API문서조사, transport미구현 | [GetStarted](https://api.lotteon.com/apiService/?apiNm=GetStarted), [가이드](https://api.lotteon.com/apiGuide): 판매자상품관리API. 전체소비자상품검색/타판매자저장권한으로해석안함 |
| SSG | 후보만비활성, 공식project검색API미확인 | 접근권한/현재공식문서/검색·저장조건필요. 추측endpoint/비공개API미사용 |
| 도매꾹 | 기존완성코드·회귀통과, 이번실조회0 | 기존field storage/가격/원장보존, 별도운영승인후 |
| Serper | 기존POST shopping/키loader재사용, 이번실조회0 | 유료credit/계정비용·재사용조건확인후, SearchAPI.io실행안함 |
| YES24 | 기존검색/상세/Mock통과, 이번실조회0 | 지속저장·재사용예외허가미확인, DB금지유지 |
| 번개장터/중고나라 | 기존Mock/partner gate보존 | 정식파트너접근·저장권없음, live불가/우회없음 |
| 11번가 | 기존offline변환기/테스트보존 | 공식project키·검색권·현재할당·저장조건미확인 |
| 쿠팡/G마켓/옥션/Etsy/Amazon/AliExpress | 기존공식경로조사재사용, 후보비활성 | 앱/제휴/판매자권한과소비자검색권을구분. project키·자격·캐시/재배포·할당확인없이는live미실행 |
| 네이버구쇼핑 | 재활성하지않음 | 이전확인된종료공지와현공식경로확인필요, 과거할당문서로복원금지 |
| 식품안전나라/공공식품API | 기존food_evidence연결/Mock, 실제publicAPI실행0 | 키/품목join/계약대기, 원재료사전을특정상품알레르기목록으로오해하지않음 |

발견registry는판매처17곳과식품정보2곳, enabled0이다. metadata검증3곳은상품7필드/저장권검증완료가아니다.
전체공급자실조회시도는상품/API19회(eBay3/Smartify5/Yappyfeed6/MCP5), 공개metadata8회별도.
재시도/반복검증상품을합산해새상품누적수로보고하지않는다. DB신규/변경은이번단계미판정/실행0.
