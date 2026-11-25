# 범용 Linux Docker Compose 배포·복구 절차

아래는 NAS 접근 권한과 배포 승인을 받은 운영자가 실행할 절차다. 이번 작업에서는 실행하지 않았다.
NAS 제품명에 의존하지 않으며 local Linux bind volume을 전제로 한다. 여러 호스트에서 같은 계정/원장에
동시에 쓰거나 잠금 의미가 검증되지 않은 SMB/NFS 공유를 상태 저장소로 쓰지 않는다.

## 1. 코드·권한·백엔드 준비

원본 저장소는 part/최준서-collector 브랜치이며 기존 팀 API와 수집기 변경이 미커밋 상태다.
현재 Codex 작업 폴더는 Git 저장소가 아니다. 미커밋 파일을 덮어쓰는 checkout/reset/clean을 하지 않는다.
새 반영 대상은 collector_ops, food_evidence, synthetic_catalog이고 기존 marketplace_live/used_market_live 및
수정된 domeggook_live가 GitHub에 아직 없다면 이전 패치와 함께 별도 검토하여 반영해야 한다.
팀 API의 미추적 파일은 담당자가 따로 반영한다. 이번 작업이 자동으로 Git에 추가하거나 Push하지 않는다.

GitHub 반영 시 git add . 대신 검토한 파일 목록만 추가한다. .env, 실제 상품/DB handoff,
상태·로그·데이터셋·백업·키 파일은 제외한다. 로컬 감사는 현재 추적 파일/스테이지/반영 후보를 검사했으며
원격 GitHub·전체 Git 이력에 대한 유출 부재를 증명하지 않는다.

팀 FastAPI에서 source별 collector token 권한, /internal/v2/crawl-runs/{UUID}/observations,
허용 호스트/통화·가격 기준·저장 및 재사용 허가를 확인한다. 현재 HTTP transport는 HTTPS가 필요하다.
NAS 내부 HTTP 주소만 있다면 TLS reverse proxy를 준비하거나 팀과 transport 계약을 별도 검토한다.
인증서 검증을 끄지 않는다. 사설 CA는 CA 파일을 읽기 전용 mount하고 COLLECTOR_CA_FILE을 컨테이너 경로로 설정한다.
새 운영 계층만 CA 파일을 지원하며 기존 수집기 코드는 변경하지 않는다.

각 계정의 전체 사용량을 공급자 대시보드와 대조한다. 이전 수동 소량 테스트/다른 호스트의 사용량도
같은 계정 한도를 공유하지만 서로 다른 형식의 옛 probe 원장을 자동 합산하지는 않는다.
한 계정을 여러 호스트에서 돌리지 않고 유효한 할당량보다 작은 로컬 예산을 설정한다.
Serper는 월 credit/비용/통화를 명시하고, API 키 발급을 제3자 콘텐츠 저장 허가로 해석하지 않는다.
YES24는 지속 저장·재사용 및 예외 계약 확인 전 enabled=false를 유지한다.

## 2. NAS 디렉터리와 secret

권장 분리: releases(코드), config(권한·예산 JSON), secrets(키), state(원장/체크포인트/대기열), backups(상태 스냅샷).
config와 secrets는 Git checkout 밖에 둔다. secret 파일은 원시 값 하나만 포함하고 .env 전체를 넣지 않는다.

| 파일명 | 환경변수 |
| --- | --- |
| domeggook_api_key | DOMEGGOOK_API_KEY_FILE |
| serper_api_key | SERPER_API_KEY_FILE |
| ebay_client_id / ebay_client_secret | EBAY_CLIENT_ID_FILE / EBAY_CLIENT_SECRET_FILE |
| yes24_api_key | YES24_API_KEY_FILE |
| kkulpick_backend_token | KKULPICK_BACKEND_TOKEN_FILE |

Docker는 /run/secrets/{파일명}으로 mount한다. 코드는 환경변수 값 또는 명시된 secret 파일을 읽으며
서로 충돌하면 중단한다. Backend 토큰은 최소 32자다. 값·전체 환경변수·확장된 Docker 설정을 로그에 찍지 않는다.
UID/GID 10001이 자신에게 제공된 파일/volume을 읽고 쓸 수 있어야 한다. 팀 공유 파일의 소유권을 임의로 바꾸지 않는다.
Compose file-backed secret은 호스트 권한이 적용되므로 실제 NAS에서 읽기 권한을 확인해야 한다.
선택한 서비스에 필요한 secret만 준비한다. 개발자가 현재 키 파일을 NAS나 GitHub로 복사한 것은 아니다.

deploy/config/*.json과 settings.example을 별도 config 디렉터리로 복사한다.
예제는 enabled=false이며 API 예산·스토리지 허가·가격 확인이 자동으로 승인되지 않는다.
COLLECTOR_RUN_APPROVED=no인 상태에서도 컨테이너를 띄워 idle/heartbeat만 확인할 수 있다.
실제 권한 검토 후에만 해당 소스의 enabled/rights/backend 설정과 COLLECTOR_RUN_APPROVED=yes를 적용한다.
food_policy는 기본 hold_until_contract다. 식품 데이터 저장을 허용하는 계약이 생기기 전 안전 검사 없이 해제하지 않는다.

## 3. 기존 상태 이관

먼저 모든 기존 writer를 정상 종료한다. 일반 eBay와 Used는 동일 marketplace 루트의
ebay_browse/request_ledger.json 및 lock을 공유해야 한다. 별도 빈 원장으로 사용량을 초기화하지 않는다.
도매꾹은 기존 STATE_ROOT 아래 domeggook_ops와 domeggook_open 전체를 보존한다.
마켓플레이스의 source별 폴더, ebay_used 폴더, outbox와 UUID, request ledger, checkpoint를 함께 이관한다.
Mock/synthetic 상태를 운영 디렉터리로 복사하지 않는다.

```sh
# 기존 writer 종료 후, 배포 승인된 환경에서만 실행
python -m services.collector.collector_ops.backup --state-root /srv/kkulpick/state --archive /srv/kkulpick/backups/before-release-YYYYMMDD-HHMM.tar
```

backup은 기존 writer.lock을 획득하지 못하면 거부하고, 외부 새 archive만 생성한다.
원장을 지우지 않으며 기존 archive를 덮어쓰지 않는다. heartbeat와 잠금 파일은 스냅샷에서 제외한다.
새 writer가 생기는 경쟁을 피하려면 lock 검사뿐 아니라 실제 writer 종료도 필요하다.
이관 후 해시/건수/권한과 state 경로를 확인한다. outbox의 run_id/body/key를 재생성하지 않는다.

## 4. 비활성 smoke 및 승인 후 수집

```sh
# 저장소 루트. NAS 배포 승인 후 실행할 예시이며 현재 실행하지 않음.
dc() { docker compose --env-file /srv/kkulpick/config/runtime.env -p kkulpick-collectors -f services/collector/collector_ops/deploy/compose.yaml "$@"; }
dc config -q
dc --profile ebay build
dc --profile ebay up -d
dc exec -T ebay python -m services.collector.collector_ops --provider ebay --status
dc run --rm ebay python -m services.collector.collector_ops --provider ebay --plan
```

config -q는 비밀값을 확장 출력하지 않는다. 기본 비활성 설정에서는 상품/API/DB 요청이 없어야 한다.
Mock은 --profile mock, 생성기는 --profile synthetic이며 network_mode=none이다.
NAS Docker/이미지 빌드는 이 개발 PC에서 검증하지 못했다. 최초 smoke에서 dependency 설치,
CPU 아키텍처(pydantic-core wheel), secret/volume 권한, DNS/TLS, Docker Compose 버전을 확인한다.
requirements.lock은 이 로컬 회귀 테스트의 설치 버전을 기준으로 고정했지만 Linux 빌드 성공을 대신하지 않는다.

실제 수집 승인 후 JSON의 enabled=true와 유효한 권한 근거, HTTPS 팀 API, backend_owner_approved,
price_semantics_confirmed, backend_enabled 및 secret을 검토한다. 이후 해당 서비스만 재생성한다.

```sh
# config/runtime.env 및 권한 JSON을 승인된 값으로 바꾼 뒤에만
dc --profile ebay up -d --force-recreate
dc exec -T ebay python -m services.collector.collector_ops --provider ebay --status
```

같은 방법으로 domeggook/serper를 독립 활성화한다. ebay 대신 ebay_used를 선택할 수 있다.
일반 ebay와 ebay_used를 동시에 켜지 않는다. 코드의 공유 writer lock도 중복 실행을 차단한다.
YES24/국내 미승인 소스/11번가/feed는 권한 또는 native transport가 확인될 때까지 활성화하지 않는다.
새 소스의 첫 상품 조회와 최초 팀 DB 적재는 각각 소량 범위로 별도 승인·검증한다.

## 5. 2시간 스케줄·재시작·모니터링

한 주기가 완료된 시점부터 최소 7200초 후 다음 주기를 시작한다. 외부 cron을 추가해 중복 실행하지 않는다.
restart=unless-stopped로 NAS/프로세스 재시작 후 동일 상태를 재사용한다. 명시적으로 stop한 서비스는
정책상 자동 복귀하지 않을 수 있으므로 운영자가 다시 up한다.
inflight/불확실 provider 요청은 기록을 보존하고 기존 최소 지연·리뷰 정책을 적용한다.
HTTP 백엔드 전송은 동일 body/key의 멱등 재시도만 수행한다. ACK가 없다는 이유로 새 key를 만들지 않는다.
429/Retry-After, 인증 hold, 예산, backpressure와 보류 사유를 --status에서 확인한다.
DB 신규/갱신은 DB_ack_created/updated이며 products_success는 로컬 처리 결과다.
식품 보류, refresh verification_required, coverage_limited와 oldest_check_at도 모니터링한다.
기본 stale ID 재조회는 1개/주기로 제한돼 전체 ID의 2시간 갱신을 보장하지 않는다.

health는 프로세스 heartbeat 검사다. disabled/권한 대기도 프로세스 health는 정상일 수 있다.
Docker healthcheck가 unhealthy가 됐다는 이유만으로 Docker가 자동 재시작하는 것은 아니다.
NAS 알림/외부 모니터링을 연결하고 인증/권한/정합성 hold는 사람이 검토한다.
보류를 숨기려고 상태 파일이나 대기열을 삭제하지 않는다.

## 6. GitHub 업데이트와 안전한 재배포

1. 팀에서 검토/승인된 commit SHA를 확정하고 별도 GitHub 반영을 완료한다. 이 작업은 Push하지 않았다.
2. NAS의 별도 release checkout에서 fetch 후 `git worktree add --detach /srv/kkulpick/releases/NEW_SHA NEW_SHA`처럼
   새 디렉터리를 만든다. 기존 실행 checkout의 미커밋 내용을 reset/clean하지 않는다.
3. 새 release에서 오프라인 테스트/secret 검사/compose config -q/이미지 build를 끝낸다.
   config/secrets/state는 같은 외부 경로를 사용하고 이미지 tag는 SHA로 고정한다.
4. 모든 관련 writer를 정상 종료하고 새 이름의 상태 backup과 해시를 보관한다.
5. 새 release의 compose로 선택 서비스만 up --force-recreate한다. 키/설정 변경도 재생성해야 새 bind mount가 확실히 적용된다.
6. health·status·원장 연속성·대기열 ACK·신규/갱신/보류를 확인한다. 추가 공급자 호출은 승인된 예산 안에서만 한다.
7. 롤백은 이전 image/release로 하되 현재 원장/outbox를 초기화하지 않는다. checkpoint schema 호환성을 먼저 확인한다.
   상태 복원은 자동 덮어쓰기 대신 writer 종료 후 비어 있는 새 디렉터리에 backup을 풀고 별도 검증/승인을 거친다.

DB migration, 팀 API 변경, 운영 데이터 삭제, 자동 Git Push를 배포 스크립트에 포함하지 않았다.
