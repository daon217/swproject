# Backend delivery integration — 배포 인수인계

기준: collector `b10665e`, 비교 대상 검토 일지 `bd18140`. 실제 계약은 backend `part/소병선-backend-test`의 `b51ffdcf6068918633001a65ce4e3d311f2cb1ec`에서 확인했다. 로컬의 미커밋 백엔드와 원격 main/기본 backend 브랜치에는 두 신규 API가 없어, 이 브랜치의 계약을 별도로 읽었다. 팀원 파일을 병합하거나 수정하지 않았다. GitHub 이슈 번호 조회는 404여서, 사용자가 전달한 #29~#33 설명과 현재 HEAD의 실행 코드를 대조했다.

| 항목 | HEAD 재현 | 변경 파일·함수 | 수정 후 동작 | 운영 설정·협의 |
|---|---|---|---|---|
| #29 | 재현: `ChangeDelivery._stage`가 모든 terminal 상태를 영구 차단. 실제 Outbox의 actionable 검사도 exhausted 복구를 막음 | `unified_live/changes.py::_stage`, `domeggook_live/domeggook_delivery.py::flush`, `marketplace_live/delivery.py::flush` | 같은 잘못된 데이터는 반복 전송하지 않음. 실제 내용이 바뀐 rejected/quarantine 데이터만 재검증. IDENTITY_CONFLICT·MISSING_IDENTITY·DOMAIN_CONFLICT·held·revoked는 자동 해제하지 않음. 일시 장애 소진은 900초 이상 대기 후 동일 키·본문을 최대 3개 복구 라운드로 재시도 | `backend_delivery.max_recovery_rounds=0`으로 소진 후 자동 복구 중지 가능. 기존 run/auth/무결성 hold는 임의 초기화하지 않음 |
| #30 | 재현: 409가 전체 Outbox hold 설정 | 공통 `DeliveryPipeline.flush`, `domeggook_backend.HTTPBackendTransport.__call__`, `safe_ack` | PAYLOAD_CONFLICT/DATA_CONFLICT/미상 409는 해당 항목 held·무결성 검토. 다음 정상 상품은 계속 전송. RUN_SOURCE_CONFLICT는 해당 출처 Outbox를 중지. 어느 409도 성공으로 처리하거나 자동 무한 재시도하지 않음 | 과거에 오류 코드 없이 기록된 global hold는 자동 해제 불가. 담당자가 원인을 확인해야 함 |
| #31 | 재현: unchanged_skipped에 백엔드 확인 없음 | `unified_live/delivery_extras.py::Extras.stage/checks/flush`, `changes.py::flush` | 변경 없는 상품의 최신 확인을 영속 큐에 모아 최대 500개 check-in. confirmed는 본문 재전송 없음. mismatch/unknown은 최신 전체 Observation을 새 이벤트로 stage. 응답 identity·건수 검증. 실패 보존·백오프·재시작 복구 | backend freshness 라우터 필요. 404/410은 현재 확인 필요 상태로 유지; 곧바로 ended를 만들지 않음. backend not_found는 suspect로 바꾸므로 종료 확정 정책은 별도 협의 |
| #32 | 재현: 매칭·판매처·식품 sidecar만 생성, 전송 없음 | `delivery_extras.py::extension/Extras`, `collector_ops/delivery_contract.py`, `backend_transport.py::origin_check`, `engine.py::page`, `food.py::evidence`, `collector_ops/evidence.py`, `runtime.py`, `unified_live/dome.py` | Observation ACK를 확인한 후 별도 Extension 큐·키·ACK 사용. seller_name/id, matching profile, 검증된 GTIN/EAN/ISBN-13 전송. 202 OFFER_NOT_YET_OBSERVED는 완료 아님; 동일 키·본문을 재전송. 재시작·503 복구. Extension 오류가 정상 Observation을 막지 않음 | extensions 라우터와 관련 DB migration이 이미 배포돼 있어야 함. URL 식품은 evidence_storage 및 해당 사용권한 필요. 실제 외부 식품 성공은 아직 0 |
| #33 | 재현: 로컬 수집 허용 목록만 확인, backend 목록은 모름 | `delivery_contract.py::catalog_review`, `ChangeDelivery.stage`, 공통 `prune`, `Outbox.stage`, `recover_delivery.py::recover`, Compose | 관리자 제공 backend 목록과 신규·이미 queued 상품을 대조. 미등록 출처/항목만 보류하며 다른 수집기는 계속. 422는 코드·필드 위치만 보존(입력값·메시지 제외). 자동으로 서버 allowlist를 늘리지 않음 | 아래 두 목록을 서버 담당자가 실제 backend 설정과 동일하게 복사. 목록이 없으면 서버 정책을 사전 확인할 수 없고 422 항목별 보류에 의존 |

## 실제 전송 계약

- Observation: `POST /internal/v2/crawl-runs/{run_id}/observations`, 기존 v2 스키마 그대로.
- Extension: `POST /internal/v2/crawl-runs/{run_id}/extensions`. 최상위는 `schema_version=listing-extension-v1`, `source`, `source_listing_id`, **Observation과 같은 variant_key**, 별도의 `observation_key`, `observed_at`, `product_url`, `is_synthetic`, `matching_profile` 및/또는 `food_evidence`이다. 로컬 sidecar 전체를 그대로 POST하지 않는다.
- matching_profile: brand/manufacturer/model_name/model_number/mpn, identifiers(type=gtin/mpn/sku), image_url(s), color/size/options/category, seller_id/name. 확정되지 않은 exact_match_confirmed는 false. GTIN 검증을 통과하지 못한 ISBN-10 등을 GTIN으로 꾸미지 않는다.
- food_evidence: ingredients_raw, ingredients(문자열 목록), allergen_notice_raw, cross_contact_raw, allergens_declared, evidence_status. 원문·정규화 분리. 미제공은 not_reported. soy→soybean, sulfites→sulfite 코드를 맞추되 원문은 유지. safe_to_consume 같은 안전 추정 필드는 전송하지 않는다.
- Extension 200/201 + applied/recorded만 완료 ACK, quarantine는 검토. 202 pending는 백엔드가 보관했더라도 최종 적용 성공으로 집계하지 않는다.
- check-in: `POST /internal/v2/listing-checks`, `{source,items:[{source_listing_id,variant_key,observed_at,price,currency,availability}]}`. 최대 500개. confirmed 수와 mismatch/unknown/rejected의 항목 identity가 일치해야 신뢰한다.
- backend 공통 오류: error.code/detail과 validation fields 위치만 기록. RUN_SOURCE_CONFLICT/PAYLOAD_CONFLICT/EXTENSION_PAYLOAD_CONFLICT/DATA_CONFLICT는 무결성 검토; INVALID_INPUT은 자동 성공/무한 재시도하지 않음.
- 모든 요청은 동일한 설정 origin과 고정 라우트만 사용. redirect·proxy·다른 호스트 토큰 전달 금지, 인증서 검증 유지. 외부 수집의 HTTPS/DNS/SSRF/robots/예산/이용권한 코드는 완화하지 않음.

## 권한·미완료 사항

- 실제 외부 식품 수집 0건, 외부 성분 추출 0건, 외부 상품 Extension ACK 0건. 이번에는 외부 공급자 API를 호출하지 않았다. 합성 HTML/FastAPI/SQLite 성공을 실수집으로 계산하지 않는다.
- URL 식품은 원문과 필수 상품 필드가 실제 존재하고 condition=new이며 `evidence_storage=true`와 rights.allowed_uses의 evidence_storage가 있을 때만 food Observation 및 evidence를 생성한다. 저장·재사용 권한, 가격 의미, 필수값 검사를 유지한다.
- 도매꾹 및 기존 API 경로의 food_policy 기본 hold_until_contract는 보존했다. 원문 이용권한과 food domain 전환이 확인되지 않은 상품을 일반 상품으로 위장하거나 일괄 해제하지 않는다. 일반 도매꾹 상품의 매칭 확장정보는 기존 bridge를 통해 전달 가능하나, storage_grants의 각 확장 필드 또는 matching_profile 전체에 유효한 재사용 권한이 있어야 한다. 기존 가격/상품명 권한을 브랜드·이미지·판매처 권한으로 확대 해석하지 않는다.
- YES24: 가격은 원래 salePrice, 통화 currency, 옵션 sku, 상태 condition/availability 경로이다. NAS 실제 응답 원문이 없고 다른 필드명이 맞다는 근거가 없어 추측 매핑을 추가하지 않았다. 누락 5개를 명시적으로 진단하며 계속 보류한다. exception_agreement_reference 등 기존 지속 저장/재사용 승인도 필요하다.
- eBay 일반·Used, 60초/7200초, 공유 요청 원장·예산은 기존 구현을 재사용한다. 이 작업에서 실제 eBay 호출을 재실행하지 않았다. 번개장터·중고나라의 권한 대기는 유지한다.
- 운영 PostgreSQL SQL/ACK 적용 의미를 SQLite로 완전히 대체 검증했다고 주장하지 않는다. 아래 로컬 검증은 요청 계약·수집기 큐·HTTP 흐름 테스트이며 실제 backend SQL은 실행하지 않았다.
- backend 담당자 협의: NAS 배포 API가 위 commit 계약과 동일한지, extensions/freshness 및 migration 적용 여부, host/currency/image-host 목록, missing unknown condition/availability/variant 정책, ISBN-10 및 신품 개봉/리퍼/부품용 표현, 404 반복 확인 후 suspect/ended 전환 정책. 기존 계약에 없는 값을 임의 전송하지 않는다.

## 서버 관리자 최소 설정

```ini
COLLECTOR_BACKEND_TRANSPORT=internal_http
COLLECTOR_BACKEND_BASE_URL=http://api:8000
COLLECTOR_DELIVERY_APPROVED=yes
# 아래 값은 예시. 실제 backend CATALOG_URL_HOSTS/CATALOG_CURRENCIES와 일치시킬 것.
COLLECTOR_BACKEND_CATALOG_HOSTS=shop.example.com,www.ebay.com,www.yes24.com
COLLECTOR_BACKEND_CATALOG_CURRENCIES=KRW,USD
```

- 주소는 실제 NAS FastAPI origin으로 지정한다. 기존 관리자 지정 HTTP 주소도 지원한다. 토큰은 기존 `KKULPICK_BACKEND_TOKEN_FILE=/run/secrets/kkulpick_backend_token`; 값은 로그/Git에 넣지 않는다. 추가 HTTP 승인 파일은 없다.
- URL 수집 설정에는 선택적으로 `backend_catalog:{url_hosts:[...],currencies:[...]}`를 넣을 수 있다. 환경변수 복사본이 있으면 우선한다. 이는 수집/저장 권한을 승인하는 설정이 아니다.
- `COLLECTOR_RUN_APPROVED`, 공급자 키, 권한 reference/만료, backend_enabled/backend_owner_approved/price_semantics_confirmed는 기존대로 필요하다. 새 설정이 자동 승인하지 않는다.
- 상태 볼륨을 반드시 그대로 연결: backend_outbox.json, content_checkpoint.json, **delivery_extras.json**, 공급자 요청 원장·체크포인트. 삭제/초기화/별도 동시 writer 실행 금지. 새 delivery_extras.json은 기존 상품을 다음에 실제 재확인할 때 채워지며 과거 원문을 합성하지 않는다.

## 배포 절차 (관리자가 실행; 이번 작업에서는 NAS 미접속)

1. 현재 수집기 설정/시크릿/볼륨과 배포 버전을 백업한다. 기존 8개 운영 서비스를 일괄 재시작하지 않는다.
2. 깨끗한 별도 release checkout에서 collector 브랜치를 정상 fetch/pull --ff-only한다. 서버의 미커밋 파일을 reset/덮어쓰지 않는다.
3. 위 backend 계약 및 migration을 담당자가 확인한다. 이 수집기 변경으로 backend migration을 자동 실행하지 않는다.
4. 기존 clean build-context exporter로 저장소 밖의 새 디렉터리에 빌드 입력만 내보낸다. .env/.git/데이터 파일을 빌더로 보내지 않는다. 기존 배포 문서의 Dockerfile/Compose 사용법을 유지한다.
5. 해당 release의 `services/collector/unified_live/deploy/compose.yaml`과 실제 env-file로 `docker compose config` 확인. 기본 배송 스위치는 no. 별도 source 허용/보관 승인을 갖춘 프로필만 선택한다.
6. 관리자 확인 후 변경된 수집기 서비스만 `up -d --no-deps <service>`로 갱신. 서비스명은 domeggook, serper, ebay(일반·Used 공유 writer), yes24, url, fleet, public_feed, discovery이다. `down -v`, 전체 NAS 재시작, 운영 DB 직접 변경 금지.
7. --status 및 heartbeat/report에서 Observation delivered/quarantine/held/catalog_held/exhausted, catalog_review, extensions_and_checks의 큐/ACK/보류/확인 건수 확인. 프로세스 health를 실제 상품 적재 성공으로 간주하지 않는다.
8. backend 담당자가 NAS에서 실제 신규 등록·업데이트·중복 방지·Extension 적용을 확인한다. 로컬 테스트 결과와 별도로 기록한다.

이미 422를 받은 URL/currency 항목은 운영자가 backend 목록 등록을 완료하고 **해당 collector writer를 정지한 후**, source와 backend_catalog를 포함한 비공개 단일-source JSON으로 다음 오프라인 도구를 사용할 수 있다:

```bash
python -m services.collector.collector_ops.recover_delivery --outbox /state/SOURCE/backend_outbox.json --config /run/source-with-backend-catalog.json
# plan의 대상·권한·목록 확인 후만 적용. HTTP/DB 요청은 하지 않으며 원본 백업 후 같은 키/본문을 pending으로 복구.
python -m services.collector.collector_ops.recover_delivery --outbox /state/SOURCE/backend_outbox.json --config /run/source-with-backend-catalog.json --apply
```

이 도구는 url/currency 오류 위치가 명시된 422와 보존된 원래 본문만 대상으로 한다. 다른 검증 오류, 과거 본문이 이미 제거된 항목, 409·인증·무결성 global hold는 자동 해제하지 않는다. 기존 본문이 없으면 다음 실제 재수집/수정된 데이터와 담당자 검토가 필요하다.

## 로컬 검증 재현

```bash
# 배포용 기본 이미지에는 devtest 모듈을 넣지 않는다. 테스트 전용 이미지에서만 실행.
python -m services.collector.unified_live.devtest.delivery_integration_lab
```

이 lab은 합성 HTML → 실제 URLWorker/parser → Outbox → 내부 HTTP FastAPI → 격리 SQLite → ACK/Extension/check-in을 실행한다. FastAPI/uvicorn은 테스트 이미지 의존성이고 운영 수집기의 필수 의존성으로 추가하지 않았다. Docker network_mode=none, read_only, tmpfs, 무권한 사용자, cap_drop=ALL로 검증했다. 실제 외부 상품 및 NAS 결과를 대체하지 않는다. 최종 테스트 수치는 DELIVERY_INTEGRATION_RESULTS.json 참고.
