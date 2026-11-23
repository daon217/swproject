# 승인 기반 통합 수집 실행 계층

기존 수집기와 백엔드는 수정하지 않는다. JSON-LD/CSS URL 수집, eBay 최신 중고 60초,
내용 기반 전송 생략과 계정 공유 원장을 새 계층에서 연결한다. 실제 요청/DB 적재/배포 성공은
코드·Mock 성공과 별개다. 모든 예제는 비활성이다.

## 연결 관계

| 입력 | 재사용 | 실행 주기/한계 |
|---|---|---|
| 도매꾹 | QueueClient, DeliveryDiscoveryRun, FoodDelivery, 기존 권한·가격 검사 | 7,200초 이상, 기존 예산/원장 유지 |
| Serper/YES24/일반 eBay | 기존 Adapter, ProviderHTTP, OpsWorker, Observation v2, OpsOutbox | 7,200초 이상 |
| eBay Used | UsedAdapter의 공식 상태 필터 + OAuth/getItem | 승인된 소스 최소 주기 이상, 기본 목표 60초 |
| URL | 도메인 등록, 공개 HTTPS, JSON-LD 우선/CSS 설정 | 일반 7,200초 / 중고 60초 이상 |
| 번개장터/중고나라/11번가 | 기존 차단/Mock/offline 경계 | 운영 비활성 |

eBay Used의 schedule.policy_reference가 비면 보수적으로 7,200초다. 정책이 확인된 뒤에만
mode=used, provider_min_interval_seconds, 근거를 입력한다. 60초는 이전 작업 완료 후 다음 주기의
최소 대기시간이며 매분 완료나 전수 커버리지 보장이 아니다. 요청 간격·시간/일 예산·Retry-After가 우선한다.
일반 eBay/Used는 NAS에서 ebay_account 한 프로세스로 실행한다. 원래 ebay_browse 원장과 잠금을
공유하며 used checkpoint/outbox는 기존 ebay_used/ebay_browse에 둔다. 기존 writer와 동시 실행 불가.
최신 목록은 sort=newlyListed이며 query별 최신 itemOriginDate를 기록한다. 변경 상품을 놓치지 않도록
이 시각만으로 재조회 결과를 잘라내지 않는다. 기존 매물은 오래 확인하지 않은 것부터 제한 개수 점검한다.

## URL 등록/실행

URL 하나로 모든 쇼핑몰의 의미를 판정할 수는 없다. base_url, 검색 URL 템플릿, 쿼리,
수집/저장/재사용·약관 근거와 만료일, 허용 통화, 도메인, 예산을 등록한다.
JSON-LD Product/ItemList와 microdata 링크를 자동 분석한다. 구조화 정보가 부족하면 selectors에
검토한 CSS를 명시한다. 상품 목록 링크·다음 페이지·상세 필드 선택자를 지원한다.
추측한 가격/통화/판매처/신품 상태/재고를 채우지 않는다. 다중 offer/variant는 전용 어댑터 필요로 보류한다.
도매꾹/YES24/eBay 등 기존 어댑터 도메인은 범용 등록을 거절하고 해당 어댑터 사용을 안내한다.
robots 허용은 저장 라이선스가 아니다. live 요청은 terms_reference 및 storage/reuse를 포함한
유효 grant가 있어야 한다. URL 내 credential, 사설/loopback/혼합 DNS, redirect, 로그인/CAPTCHA는 차단한다.
TLS 검증을 유지하고 DNS에서 확인한 공개 IP로 접속한 뒤 원래 호스트 인증서를 검증한다.
중단된/결과 불확실 요청은 hold 상태로 남기며 자동 재전송하지 않는다. 429/5xx는 지연/재시도 상한을 적용한다.

```powershell
Set-Location C:\Users\junse\Python\swproject
$python = '.\.venv\Scripts\python.exe'
$cfg = 'services/collector/unified_live/deploy/config/url.json'
$state = 'C:\collector-local-review\url'
& $python -m services.collector.unified_live --provider url --config $cfg --state-dir $state --register
& $python -m services.collector.unified_live --provider url --config $cfg --state-dir $state --plan
& $python -m services.collector.unified_live --provider url --state-dir C:\collector-local-review\mock --mock
# eBay 계정 계획: 상품 요청 없음, 비활성 예제의 exit 1은 정상적인 승인 대기
& $python -m services.collector.unified_live --provider ebay_account --config services/collector/unified_live/deploy/config/ebay.json --used-config services/collector/unified_live/deploy/config/ebay_used.json --state-dir C:\collector-local-review\marketplace --plan
```

등록은 로컬 설정 파일만 쓰고 외부 연결하지 않는다. 변경된 도메인 설정을 같은 registry에
조용히 덮어쓰지 않는다. 승인된 새 설정과 기존 checkpoint context의 이전 절차는 별도 검토한다.
상태를 지우고 설정 충돌을 우회하지 않는다. 운영 시작은 별도 승인 후 --watch.
COLLECTOR_RUN_APPROVED=yes는 외부 수집 승인, COLLECTOR_DELIVERY_APPROVED=yes는 팀 API 전송 승인이다.
기존 backend_enabled/owner/price/rights 검사는 여전히 모두 필요하다. 승인 flag만으로 권한을 부여하지 않는다.
키는 기존 *_FILE 또는 환경변수를 사용하며 .env를 자동 검색하지 않는다. URL은 별도 API 키가 필요 없지만
DB 전송에는 KKULPICK_BACKEND_TOKEN(_FILE)이 필요하다. 토큰 값은 CLI 인자로 전달하지 않는다.

## 변경/DB 계약

source + listing ID + variant가 상품 키다. observed_at/observation_key를 제외한 v2 내용이 같으면
새 전송을 만들지 않는다. 이전 이벤트 pending/불확실이면 원래 키와 본문을 유지하고 후속 변경은 재관측한다.
ACK 뒤에만 후속 변경을 큐에 추가한다. stage와 checkpoint 사이 장애는 시작 시 기존 Outbox 본문에서 복구한다.
seller/image/category/상세 상태/수량 등 미지원 정보는 URL checkpoint의 별도 listing-extension-v1에만 보존한다.
그 정보만 달라지면 metadata_change_contract_review로 집계하며 동일 v2 본문을 억지로 다시 보내지 않는다.
404/410이나 검색 누락은 verification_required이며 자동 판매 완료/삭제가 아니다. 예약/비활성 등
v2에 없는 상태는 보류한다. stock_quantity=null과 purchase_available=true는 동시에 가능하다.

식품은 기존 food_evidence와 정제기를 재사용하며 확장 근거를 작성한다. URL에서 발견한 식품은
계약 확장 전 전송 보류한다. 원문/정규화/함유/혼입/출처/시각/해시/검토 여부를 구분한다.
원문 저장은 evidence_storage=true와 별도 evidence_storage allowed_use가 함께 있어야 한다.
없으면 RAM에서만 처리한다. 미표시/없음 주장/OCR 불확실을 안전 판정으로 바꾸지 않고 safe_to_consume=null이다.
이 코드는 OCR을 실행하지 않는다. 이미지 전용 표시는 추출 완료가 아니다.

## JavaScript

render_javascript=true는 선택적 Playwright Chromium transport다. stealth/로그인 우회 기능은 없다.
모든 리소스를 같은 출처 SafeHTTP/robots/원장/예산으로 전달하고 외부 리소스·WebSocket·WebRTC·worker를 차단한다.
인증/POST XHR가 필요한 앱, 외부 CDN 의존 앱은 지원되지 않을 수 있다. Playwright/Chromium은 기본 이미지에
없으며 승인된 테스트 환경에서 버전 고정 설치 및 실제 브라우저 검증이 필요하다. Mock 렌더러 경로 검증을
실제 Chromium 또는 실제 쇼핑몰 렌더링 성공으로 해석하지 않는다. 이 항목은 부분 완료다.

## 보관

원본 도매꾹/marketplace/used/웹/식품/배포 파일은 유지한다. 이번 기존 파일 변경은
소유한 domeggook_live/tests/test_recovery.py의 KST 자정 의존 테스트 시각 고정뿐이다.
275만 합성 데이터/분류 생성기/manifest는 수정·재생성하지 않는다. 사용자 제공 Release 백업 완료 정보는
외부 조회로 다시 검증하지 않았다. 합성 데이터 적재는 팀 담당자의 별도 업무다.

## 2026-11-23 마스터 작업 결과

최신 실제 검증/운영 명령은 [MASTER_GUIDE.md](MASTER_GUIDE.md), 공급자별 상태는 [MASTER_API_STATUS.md](MASTER_API_STATUS.md), 팀 계약은 [MASTER_CONTRACT.md](MASTER_CONTRACT.md)를 참조한다. 이전 조사·검증 기록과 현재 live 결과를 구분한다.

## 일반 HTTP 백엔드 전송

현재 internal_http는 [INTERNAL_HTTP.md](INTERNAL_HTTP.md)의 명시적 URL로 일반 HTTP를 전송한다. Docker DNS/veth/서브넷/컨테이너/승인 파일 검사는 전송 경로에서 제거했다. 외부 상품 수집의 HTTPS 보안 정책과 기존 전송 스위치·인증·Outbox는 유지한다.
