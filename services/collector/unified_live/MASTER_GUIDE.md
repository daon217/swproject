# 통합 수집기 운영 지침 — 2026-11-23

원본 `C:\Users\junse\Python\swproject`에 직접 반영했다. Codex 작업 폴더는 검증 증거와 백업을 보관한다.
기존 수집기·원장·Outbox·food_evidence를 재사용하며 팀 API/SQL, Git index, 기존 합성 데이터는 보존했다.
이번 코드 변경은 unified_live와 collector_ops/IMPLEMENTATION_PROGRESS.md에 한정한다.

## 실제 검증 범위

- 전체482개 테스트+하위 사례145개 통과. 실패/오류/skip0. 외부 socket을 차단하고 실행했다.
- eBay Production Used: OAuth1+최신순 Used 검색1+상세1=HTTP3회200. 정상1/보류0.
  구매 가능=true, 정확한 재고 수량은 미상이다. 원문 영구 저장/팀 전송은0.
- Smartify 공식 피드3개는 v2 검증 통과. 별도 HTML은308 redirect로 중단하고 hold를 유지했다.
- Yappy 공식 피드3개는 v2와 실제 팀 Observation 모델 검증 통과. 실제 loopback HTTP/임시 SQLite에서
  ACK3, 동일 요청 replay3 후 행수3/중복0. 팀 FastAPI/운영 PostgreSQL의 저장 시험은 아니다.
- Yappy MCP 검색+상세3개는 seller/condition 누락으로 보류. 상세 HTML도 seller 누락으로 보류.
  피드의 v2 적합성과 판매처까지 포함하는 데이터 완전성은 구분해야 한다.
- 실제 Windows Edge 및 Linux Docker Chromium에서 합성 JS/XHR→JSON-LD 정규화와 외부 origin 차단 통과.
  실제 쇼핑몰 JavaScript 페이지의 추출 성공까지 확인한 것은 아니다.
- Compose2.20.1 config 검사, Linux 기본/브라우저 이미지 빌드, 기본 단발 컨테이너5개 실행 통과.
  검증 컨테이너는 local/network=none/비root/read-only이며 종료 후 제거했다.
- 자동 발견 후보19개(판매처17+식품정보2), 실제 공개 메타데이터 확인3개, 자동 활성0.
  인터넷 전체 검색이 아니라 제한된 공개 디렉터리와 게시 링크에서 후보를 추가하는 구조다.
- NAS SSH 인증 실패. NAS 배포/기존8개 컨테이너 변경/운영 DB 전달/Git Push 모두0.

## 실행 역할

| 모듈 | 실행·저장 경계 | 주기 |
|---|---|---|
| unified_live domeggook/serper/yes24 | 기존 어댑터/예산/체크포인트 재사용 | 일반≥7200초 |
| unified_live ebay_account | 일반+Used 단일 writer/공유 HTTP 원장, 개별 checkpoint/outbox | 일반7200, Used 허가 시≥60초 |
| discovery | 디렉터리→도메인 중복 제거→비활성 registry, metadata와 상품 품질 구분 | 하루1회, 기본3사이트 |
| fleet | 허가된 generic URL만 사이트별 child 최대8, 오류·재시작 격리 | 감독1초, 수집은 소스별 |
| feeds | 공식 피드→품질·권한→ChangeDelivery→ApprovedOutbox | ≥7200초 |
| public_sources | Smartify/Yappy/Perfume 공식 read-only 고정 경로, 최대3개 | 수동 소량 조회 |
| food_lookup | exact GTIN OpenFoodFacts3.6 근거 보충, 운영 전송 없음 | 정책 준비 후 수동1회 |

Used의 schedule.policy_reference가 비면 실제 간격은7200초다. 60초는 이전 주기 완료 후 최소 대기시간으로,
예산/Retry-After/백오프가 우선한다. 최신 목록과 기존 매물의 제한적 분산 점검을 함께 사용한다.
검색 누락/404/410은 판매 완료 근거가 아니다. 같은 계정의 일반/Used writer를 따로 띄우지 말고
Compose ebay 서비스 하나로 실행한다. 공유 원장과 잠금은 이전 요청 기록을 유지한다.

## 로컬 재개 — 외부 요청 없는 명령

```powershell
Set-Location C:\Users\junse\Python\swproject
$python = '.\.venv\Scripts\python.exe'
$deploy = 'services/collector/unified_live/deploy'
$state = 'C:\collector-local-review\master'
$env:COLLECTOR_RUN_APPROVED = 'no'
$env:COLLECTOR_DELIVERY_APPROVED = 'no'
$env:DISCOVERY_METADATA_APPROVED = 'no'
& $python -m services.collector.unified_live.discovery --state-dir "$state\discovery" --plan
& $python -m services.collector.unified_live.discovery --state-dir "$state\discovery" --scan
& $python -m services.collector.unified_live.discovery --state-dir "$state\discovery" --status
& $python -m services.collector.unified_live.fleet --state-dir "$state\fleet" --discovery-state "$state\discovery" --grants "$deploy/config/discovery-grants.json" --plan
& $python -m services.collector.unified_live.feeds --config "$deploy/config/public-feed.json" --state-dir "$state\feeds" --plan
& $python -m services.collector.unified_live --provider url --state-dir "$state\mock" --mock
& $python -m services.collector.unified_live --provider ebay_account --config "$deploy/config/ebay.json" --used-config "$deploy/config/ebay_used.json" --state-dir "$state\marketplace" --plan
```

권한 대기 중인 예제에서 plan exit1은 정상적인 실행 차단이다. 설정/상태 오류는exit2.
--watch --max-ticks 1은 한 번 감독하고 종료하며 비활성 설정이면 통신 없이 heartbeat만 저장한다.
유효 설정의 --once/--watch는 외부 요청을 할 수 있으므로 승인된 소스에서만 사용한다.
기존 live 검증 state는 예산 소비/hold 이력이 있다. 이력을 지우고 재사용하지 않는다.

## 환경변수와 시크릿

| 이름 | 용도 |
|---|---|
| DOMEGGOOK_API_KEY(_FILE) | 기존 도매꾹 API |
| SERPER_API_KEY(_FILE) | Serper POST /shopping. SearchAPI.io 키가 아님 |
| EBAY_CLIENT_ID(_FILE), EBAY_CLIENT_SECRET(_FILE) | Production OAuth, 토큰 출력 금지 |
| YES24_API_KEY(_FILE) | 공식 검색/상세. 지속 저장 허가 전 DB 금지 |
| KKULPICK_BACKEND_TOKEN(_FILE) | 클라이언트 Bearer32자 이상, env/file 충돌 시 차단 |
| COLLECTOR_RUN_APPROVED | 소스 수집 승인. 권한/가격/예산 검사도 별도로 필요 |
| COLLECTOR_DELIVERY_APPROVED | 팀 API 전송 독립 승인, 기본no |
| DISCOVERY_METADATA_APPROVED | 공개 metadata 조회 승인, 기본no |
| KKULPICK_STATE_DIR / COLLECTOR_CONFIG / COLLECTOR_USED_CONFIG | 명시적 state/설정 |
| OPENFOODFACTS_CONTACT_EMAIL | 연락처. usage등록/라이선스 확인도 별도로 필요 |
| COLLECTOR_BROWSER_CHANNEL | 로컬 msedge/chrome 허용, Linux는 기본Chromium |

자동 .env 탐색은 하지 않는다. 이번 실재 확인에서는 swproject/.env에 공급자 키 이름이 없고,
C:\Users\junse\Python\ai-shopping-search-unified\.env에 발행된 키 이름이 있었다.
기존 명시적 loader로 필요한 키만 메모리에 읽었다. 환경 파일을 복제하거나 변경하지 않았다.
NAS는 Compose secret 파일을 UID10001이 읽을 수 있도록 관리한다. runtime.env에는 비밀값을 넣지 않는다.
키를 CLI 인자/로그/Git에 넣지 않는다. 서버 측 현재 토큰 이름은 COLLECTOR_TOKEN이다.

## 발견 후보 활성화

discovery-grants.json은 초기{}다. 원격 directory가 enabled/허가/품질/임의 어댑터를 지정할 수 없다.
독립된 계약 확인자가 marketplace_id별로 discovery-grant.example.json을 검토해 작성해야 한다.
reference/terms_reference/만료일/lookup+systematic_collection+storage+reuse, allowed_hosts,
통화/가격 근거/backend owner/예산과 실제 상품 품질·metadata 접근 검증이 모두 필요하다.
API 후보가 선택되어도 fleet가 API worker를 임의 생성하지 않는다. 기존 Compose profile을 사용한다.
generic 파서는 JSON-LD→native HTML→검토된 JS 순이며 불충분하면 전용 파서 검토 후보로 남긴다.
--live-metadata는 대량 상품 수집 승인이 아니다. 별도 lookup grant가 있으면 상세 preview 최대1개를 허용한다.
자동 선택자 제안은 저장 라이선스나 가격·판매처의 정확성 증명이 아니다.
feed는 merchant_name/merchant_reference를 공식 게시자 근거로 확인해야 한다. description 원문은
description_storage, 식품 근거 원문은 별도 evidence_storage 사용 허가가 필요하다.
Smartify의 캐시·인용 허용과 경쟁 카탈로그 재배포 제한을 함께 확인해야 한다.

## 정규화·복구·상태

v2 body와 listing-extension-v1을 분리한다. source/ID/variant, decimal 금액/원통화, URL, native 상태를
검증한다. refurbished/open_box/for_parts/reserved처럼 계약에 없는 상태는 보류한다.
seller/category/image/country/GTIN/출처/확장 시각/합성표시는 확장 쪽에 둔다. stock_quantity=null은
미상이며 purchase_available=true여도 수량0/1로 채우지 않는다. 이미지가 없으면 만들어 넣지 않는다.
GTIN check digit와 동일성을 검증하고 상품명만으로 식품 자료를 결합하지 않는다.
JSON-LD 참조 충돌/다중 가격/통화 누락/CAPTCHA/redirect/private DNS는 보류한다.
Outbox/원장/checkpoint/lock을 영속 보관한다. 시각만 변한 관측은 새 전송을 만들지 않는다.
ACK된 body/metadata hash로 신규/변경/미변경을 집계한다. 확장만의 변경은 계약 검토로 집계한다.
불확실 요청은 hold, checkpoint에 남은 Outbox가 사라져도 중단한다. 이력 삭제로 자동 복구하지 않는다.
429/5xx는 동일 key/body의 상한 있는 backoff, 409/인증/권한/계약 불일치는 검토 대상으로 남긴다.
status/heartbeat에는 마지막 수집·성공·실패와 신규/변경/미변경/보류/실패/ACK/대기 건수가 있다.
heartbeat 정상은 실제 상품 수집 또는 DB 적재 성공과 다르다.

## 식품·알레르기

기존 food_evidence와 한·영 라벨 정규화를 재사용한다. 원문/정규화/함유/혼입 가능성/함량/출처/
시각/hash/검토 여부를 분리한다. 표시 없음은 미확인이며 safe_to_consume는 항상null이다.
OCR은 실행하지 않는다. 이미지 표시만 있는 상품은 추출 성공이 아니다.
OpenFoodFacts는 community 근거이며 제조사 공식 보증이 아니다. 추정 tags를 포장의 공식 함유 표시로
격상하지 않는다. 연락처/usage등록/ODbL·DbCL 등 확인 전 plan만 허용하며 이번 실조회는0이다.
공공 식품 API도 키·식별 join이 미확인이다. 현재 v2에 식품 근거 필드가 없어 hold_until_contract를 유지한다.

## NAS 준비·승인 후 명령

기존 /volume1/docker/swproject를 pull/reset/clean하지 않는다. 별도
/volume1/docker/kkulpick-collector-releases/<reviewed-release>에 검토된 release를 준비한다.
project=kkulpick-collectors-v2, 포트 공개/고정 container_name/기존 네트워크 변경 없음.
backend_delivery.base_url에는 승인된 팀 API HTTPS 주소를 쓴다. 기존 서비스 네트워크에 무단 연결하지 않고
도달성·TLS·CATALOG_URL_HOSTS/통화·source/token·가격·저장 권한을 관리자가 확인한다.

```sh
# NAS 관리자가 접근/배포 승인을 확인한 뒤 실행. 이번 작업에서는 실행하지 않음.
cd /volume1/docker/kkulpick-collector-releases/<reviewed-release>
sh services/collector/unified_live/deploy/prepare-nas.sh --check
# /volume1/docker/kkulpick-collectors-v2/config,secrets,state 를 관리자가 준비.
# UID10001 접근권한 확인. 빈 파일로 secret을 대신하지 않음.
sh services/collector/unified_live/deploy/prepare-nas.sh --build
# 처음에는 runtime/config 모두 no/disabled. discovery는 오프라인 후보 등록만 실행.
COLLECTOR_DEPLOYMENT_APPROVED=yes sh services/collector/unified_live/deploy/deploy-approved.sh discovery
# 해당 소스의 수집·저장·전송 승인이 끝난 뒤만 개별 profile 실행
COLLECTOR_DEPLOYMENT_APPROVED=yes sh services/collector/unified_live/deploy/deploy-approved.sh ebay
docker compose --env-file /volume1/docker/kkulpick-collectors-v2/config/runtime.env -p kkulpick-collectors-v2 -f services/collector/unified_live/deploy/compose.yaml --profile ebay ps
```

NAS sudo 정책에 따라 실행하고 승인 변수가 sudo 과정에서 유실되지 않도록 관리자 측에서 설정한다.
prepare-nas --build는 기본 이미지만 만든다. JS가 필요하면 같은 release tag의 기본 이미지 빌드 후
browser.override.yaml을 명시하여 url 이미지를 빌드한다. fleet의 JS child에도 같은 browser image가 필요하다.
리소스가 부족하면 JS만 비활성으로 두고 HTML 수집을 계속한다. NAS 전체 설정/기존 서비스를 변경하지 않는다.
unless-stopped와 영속 state로 재시작하며, 중간 요청은 불확실 hold가 될 수 있다.
GitHub 업데이트는 검토된 commit을 별도 release로 배포하고, diff/secret검사→config-q→build→승인→
대상 profile 갱신 순이다. rollback도 같은 독립 project만 대상으로 하며 원장/큐/key/body는 유지한다.
NAS 인증 실패로 실제 컨테이너/volume 권한/재부팅 복구/팀 API 도달/PG ACK는 아직 검증하지 못했다.

## 안전한 빌드와 회귀

원본에 접근 제한된 cache가 있으면 권한을 바꾸거나 지우지 않는다. deploy/build-context.py의
--repo/--output으로 Docker COPY 입력만 새 외부 폴더에 export한다. 기존 출력과 같은 repo 경로는 거절한다.
납품 runtime bundle도 이 allowlist를 사용하며 .env/.git/DB/state/원문/275만 데이터셋은 제외한다.
이번 기본 BuildKit 경로의 PROTOCOL_ERROR는 legacy builder와 clean context로 해결했다.
브라우저 이미지는 Playwright1.65.2, Chromium과 libatomic1을 포함하고 비root 실행을 확인했다.

회귀는 repo venv, 외부 절대 cache_dir, PYTHONDONTWRITEBYTECODE=1, 격리된 KKULPICK_STATE_DIR로 실행한다.
Codex work/offline/sitecustomize.py를 PYTHONPATH 맨 앞에 두어 socket을 차단한다. 최종 보고서의 정확한
테스트 디렉터리 목록과 명령을 사용한다. 운영 integration 수동 실행 스크립트는 실행하지 않는다.
문서/Compose만 바꾸면 config 검사, Python 변경은 관련 테스트와 전체 회귀를 다시 실행한다.
