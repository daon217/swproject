# NAS 운영 준비 계층

기존 domeggook_live/marketplace_live/used_market_live/팀 API 파일을 수정하지 않고
실행 승인·영속 상태·비밀 파일·진단·식품 근거 추출을 연결하는 추가 패키지다.
실제 상품 조회·운영 DB 적재·Push·NAS 배포는 개발/테스트에서 실행하지 않는다.

## 소스별 준비 상태

| 소스 | 실제 통신 구현 | 현재 운영 판단 |
| --- | --- | --- |
| 도매꾹 | 기존 공식 Open API 검색/상세/refresh와 HTTP Outbox 재사용 | 과거 성공 이력 있음. 계정 예산/필드별 저장·재사용/가격/소유자 승인과 HTTPS 팀 API 설정 후 활성화 |
| eBay Browse | Production OAuth/검색/getItem, 이전 실제 소량 검증 성공 | used 정상 검증 이력. 리퍼/개봉/부품용은 현 v2 계약상 보류. 주기 수집 승인은 별도 |
| eBay Used | 공식 USED+상태 ID 필터, 상세 재검사, 일반 eBay 공유 예산/잠금 | 코드/Mock 검증 완료. 실제 Used 필터 조회는 이번에 실행하지 않음 |
| Serper.dev | POST shopping, X-API-KEY, 비용/credit 예약 및 HTTP Outbox | 코드/Mock 검증. 실제 응답에 condition/availability/currency/직접 판매 URL이 없으면 보류. 누락값을 추정하지 않음 |
| YES24 | 공식 검색/상세와 X-Api-Key 코드 재사용 | 조회 코드/Mock 검증. 지속 저장·재사용 허가 및 예외 계약 확인 전 DB 적재 비활성 |
| 번개장터 | 파트너 Open API는 공개 문서로 확인 | 프로젝트의 서명 계약/entitlement/저장 권한 없음. Mock만, live 불가 |
| 중고나라 | 승인된 상품 API/외부 저장 권한 미확인 | canonical Mock만, live 불가 |
| 11번가 | elevenst_offline JSON 정규화 및 live Protocol 경계 존재 | 실제 공식 HTTP transport 없음. Open API 센터 문서 접근도 이번 도구에서 503. 저장 권한·옵션/가격 의미 확인 필요, 운영 불가 |
| Smartify/Perfume Registry/Yappy Kids | real_feed_collectors에 기존 feed fetch/replay 구현 있음 | 2시간 수집·지속 저장 권한이 운영 설정으로 승인되지 않음. 기존 코드는 보존하고 새 운영 실행에서는 차단 |
| SearchAPI.io | 이전 구현/기록 보존 | 사용 공급자가 Serper이므로 retired, 운영 차단 |

접근 가능한 HTML/feed/API가 있다는 사실을 저장·재사용 허가로 취급하지 않는다.
허용된 HTML 수집 계약이 확보되기 전에는 새 HTML 네트워크 어댑터를 추가하지 않는다.
CAPTCHA, 차단, 로그인/비공개 인증, 프록시 우회는 구현하지 않았다.

## 코드 연결

OpsWorker는 기존 Worker의 요청 예산/영속 원장/체크포인트/재시도/Outbox를 상속한다.
EvidenceAdapter는 기존 정규화 body와 observation_key를 유지하고 카테고리·식품 근거를 RAM 메타데이터로 추가한다.
source_listing_id와 variant_key를 새로 만들지 않으며 신규·갱신 수는 팀 API ACK의 change_kind로 구분한다.
국내·해외 카테고리 ID를 근거 없는 공통 taxonomy로 변환하지 않는다. native label/path와 native ID를 구분한다.

eBay/Used의 알려진 ID는 체크포인트에 마지막 확인 시각/구매 가능 상태만 보존한다.
검색에서 빠진 ID도 예산 안에서 기본 1개/주기 상세 재조회한다. 주기당 refresh 수와 추적 ID 상한은
refresh_items_per_cycle(기본 1), max_tracked_items(기본 10000)로 제한한다. 원장·예산을 늘리지 않는다.
상한 초과는 refresh_tracking.coverage_limited에 표시한다. 모든 상품의 2시간 갱신을 보장하지 않는다.
예산이 부족한 상세 작업은 기존 체크포인트에 남아 다음 허용 시점에 재개된다.
404/410은 verification_required로 보류하고 기존 availability를 삭제/판매완료로 바꾸지 않는다.
403/401/429/5xx/불확실 결과는 기존 공급자 정책과 비용 기록을 유지한다.
도매꾹은 기존 discovery/refresh/삭제 불확실성 처리 경로를 그대로 재사용한다.

## 식품 정보

food_evidence는 기존 real_feed_collectors/detail_enrichment_v1/clean.py의 refine와
product_refinement.clean을 재사용한다. HTTP/OCR/AI를 새로 호출하지 않는다.
실제 응답에 들어온 설명/HTML만 처리하며 이미지에만 있는 원재료를 만들어 넣지 않는다.
도매꾹은 detail_content_license_usable=true일 때만 설명을 파서에 전달한다.
출처 URL/소스/필드/관측 시각/원문 해시/원문과 정규화된 원재료·알레르기·혼입 문구를 RAM에서 분리한다.
알레르기 미표시는 not_reported, "없음" 주장도 negative_claim_unverified이며 safe_to_consume은 항상 null이다.
알 수 없는 알레르기 용어도 버리지 않고 별도 보존한다. 법정 표시 전체를 판정하거나 진단하지 않는다.

현 v2에는 식품 전용 필드가 없다. 기본 food_policy=hold_until_contract는 식품 상품을 계약 보류한다.
새 food_evidence의 원문/식품 메타데이터는 체크포인트·원장·로그·v2 body에 추가 저장하지 않는다.
운영자가 명시적으로 base_product_only를 선택하면 기존 상품 필드만 전송할 수 있지만
식품 정보는 계속 저장되지 않으며 안전성도 판정하지 않는다. 권한/가격 검사 해제와는 별개다.
정식 영속화를 위한 제안은 CONTRACT_GAPS.md에 있다.

## 로컬 명령 (저장소 루트)

```powershell
$python = '.\.venv\Scripts\python.exe'
$config = 'services\collector\collector_ops\deploy\config\ebay.json'
$state = 'C:\기존마켓플레이스상태루트'
& $python -m services.collector.collector_ops --provider ebay --plan --config $config --state-dir $state
& $python -m services.collector.collector_ops --provider ebay --status --config $config --state-dir $state
& $python -m services.collector.collector_ops --provider ebay --mock --state-dir C:\격리Mock경로
& $python -m services.collector.collector_ops --provider domeggook --mock --state-dir C:\격리Mock경로
& $python -m services.collector.collector_ops --provider serper --mock --state-dir C:\격리Mock경로
& $python -m services.collector.collector_ops --provider yes24 --mock --state-dir C:\격리Mock경로
& $python -m services.collector.collector_ops --provider ebay_used --mock --state-dir C:\격리Mock경로
```

--plan/--status/--health는 HTTP와 비밀값 읽기를 하지 않는다. plan은 키/secret 파일의 존재만 표시한다.
--mock은 기존 공급자 모의 응답 → 실제 정규화 → synthetic_only Outbox → in-process API ACK를 처리한다.
Mock API는 DB를 쓰지 않고, 실제 HTTP transport로 교체하면 거부한다. 모의 대기열을 운영 상태로 복사하지 않는다.

실제 --watch는 COLLECTOR_RUN_APPROVED=yes, enabled=true, 유효한 수집/저장/재사용 근거,
backend_enabled/owner/price 승인, 키와 최소 32자 backend 토큰, HTTPS 팀 API를 모두 요구한다.
부족하면 비밀값을 읽거나 상품을 요청하지 않고 disabled_or_permission_wait heartbeat만 기록한다.
예제는 모두 enabled=false다. 설정 자체를 실행 승인으로 취급하지 않는다.
YES24 저장은 예외 계약 없이 통과하지 못하고 국내 미승인 소스는 환경변수로도 활성화할 수 없다.

## 지표와 의미

--status는 수집 시각, 로컬 성공/보류/실패, 공급자 실패, 다음 주기, 원장 사용량, 대기열 상태,
DB_ack_created/updated/unchanged/quarantined, 식품 보류 및 refresh 커버리지를 표시한다.
로컬 성공은 DB 적재 성공과 다르다. DB 건수는 ACK 확인분만 증가한다.
도매꾹은 기존 누적 source_metrics와 현재 성공/격리/실패 listing 상태를 구분한다.
heartbeat는 20초마다 갱신하며 --health는 120초 이내 갱신 여부만 검사한다.
healthy는 프로세스가 살아 있다는 뜻이며 수집 권한/상품 성공을 뜻하지 않는다.
stale는 2개 주기 이상 성공이 없을 때 표시하며 성공 이력이 없으면 null이다.

## 검증 범위

기존 343개 테스트와 새 기능 테스트, 실제 100만 건 로컬 생성/행 수/해시,
loopback 전용 합성 SQLite API 테스트를 수행한다. 소켓 차단 회귀 테스트에는 운영 DB를 포함하지 않는다.
Docker CLI/daemon이 없어 이미지 빌드·실제 컨테이너 실행은 미검증이다.
NAS/실제 팀 API 도달성·토큰 권한·계정 한도·저장 허가·최초 운영 적재는 별도 승인 후 확인해야 한다.

상세 Linux 절차는 NAS_RUNBOOK.md, DB 계약 제안은 CONTRACT_GAPS.md,
가상 데이터 생성/격리 적재는 ../synthetic_catalog/README.md를 참조한다.
