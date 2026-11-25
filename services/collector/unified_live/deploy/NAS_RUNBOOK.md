# NAS 독립 프로젝트 실행 준비 — 배포는 아직 실행하지 않음

운영 NAS: /volume1/docker/swproject, main, Docker24.0.2 / Compose2.20.1 (사용자 제공).
기존 kkulpick-nas-*의 API/DB/추천/비전/maintenance 컨테이너는 조회·중지·재시작·수정하지 않았다.
새 프로젝트 이름은 kkulpick-collectors-v2이며 포트 바인딩/외부 기존 네트워크/고정 container_name이 없다.
브랜치 변경/reset/clean을 하지 않는다. NAS의 팀 변경과 새 collector release 경로를 분리한다.

## 승인 전 준비

1. 로컬 part/최준서-collector의 검토된 수집기 코드만 팀 절차로 반영. main 미커밋 작업을 덮어쓰지 않는다.
2. NAS 운영자에게 승인된 별도 release checkout 경로를 준비해 달라고 요청한다.
3. /volume1/docker/kkulpick-collectors-v2 아래 config/secrets/state/backups를 분리한다.
   API 키/토큰과 실제 설정은 Git 밖에 둔다. UID10001의 bind volume/secret 읽기·쓰기 권한을 확인한다.
4. config 예제는 전부 disabled이다. COLLECTOR_RUN_APPROVED=no / COLLECTOR_DELIVERY_APPROVED=no 유지.
   사용 소스의 약관/저장/재사용/예산/가격/팀 API source scope와 HTTPS 주소를 먼저 검토한다.
5. 기존 collector writer가 있다면 승인된 유지보수 창에 정상 종료 후 원장/Outbox/checkpoint를 함께 이관한다.
   기존 팀 NAS API/DB 컨테이너를 중지하라는 뜻이 아니다. 원장을 삭제하거나 새 빈 원장으로 교체하지 않는다.

## 승인받은 운영자가 실행할 명령 (이번 작업에서 실행하지 않음)

```sh
cd /승인된/collector-release
dc() { sudo docker compose --env-file /volume1/docker/kkulpick-collectors-v2/config/runtime.env -p kkulpick-collectors-v2 -f services/collector/unified_live/deploy/compose.yaml "$@"; }
dc --profile ebay config -q
dc --profile ebay build
# 여기까지 빌드/설정 검증; 팀 운영자 배포 승인 후에만 아래를 실행
dc --profile ebay up -d
dc --profile ebay ps
dc exec -T ebay python -m services.collector.unified_live --provider ebay_account --health --state-dir /state
dc exec -T ebay python -m services.collector.unified_live --provider ebay_account --status --state-dir /state
```

URL/serper/yes24/domeggook은 별도 profile. 서비스 이름 ebay는 일반+Used를 한 계정 worker에서 실행한다.
ebay_used profile도 같은 서비스만 선택하므로 두 별도 writer를 띄우지 않는다. 일반/Used의 권한과 활성 설정은
각 JSON에서 독립 관리한다. 일반7200/Used60은 설정·예산을 충족한 뒤에만 적용되며 status의 실효 주기를 확인한다.
예상 이름은 kkulpick-collectors-v2-ebay-1 등이며 실제 생성 여부/이름은 아직 미확인이다.

로그는 json-file 10m×3 rotation, read-only root/tmpfs/cap_drop/nonroot/init/restart unless-stopped,
healthcheck30초, SIGTERM 유예60초를 사용한다. 외부 서비스로의 HTTPS만 이용하며 기존 NAS DB 네트워크에
직접 연결하지 않는다. 팀 내부 API를 쓰려면 기존 컨테이너를 바꾸지 않고 접근 가능한 TLS 경로를 준비한다.
기본 Dockerfile은 Playwright/Chromium을 포함하지 않는다. JavaScript 실행은 승인된 테스트 환경에서
별도 버전 고정 이미지/브라우저 시험을 거친 뒤에만 켠다.

## 검증 및 롤백

- disabled 상태: heartbeat는 정상이어도 상품 수집/DB 성공이 아니다. 실제 성공/보류/변경/실패와 ACK 지표를 별도로 확인.
- live 조회 승인과 DB 전송 승인을 분리한다. DB 쓰기 검증은 실제 팀 API receipt와 담당자의 DB 확인으로 별도 수행.
- 재시작은 새 collector 프로젝트에만 적용하며 기존 NAS 컨테이너는 건드리지 않는다.
- 배포 전 기존 backup 모듈로 writer lock 확보 후 상태 snapshot을 별도 archive로 생성한다.
- 새 이미지가 상태 스키마와 호환되는지 확인하고 호환되지 않으면 이전 image와 대응 backup으로 운영자 승인 롤백.
  현재 통합 코드가 추가한 content_checkpoint 및 URL extension은 예전 실행기가 읽지 않는다.
  구버전은 내용 기반 전송 생략을 하지 않으므로 롤백 후 중복 관측 증가 가능성을 검토한다.
- git pull/checkout을 NAS의 팀 미커밋 폴더에서 자동 실행하지 않는다. release별로 검토된 commit을 사용한다.
- 대용량 합성 데이터 및 Release ZIP 4개는 collector image/volume/운영 PostgreSQL로 넣지 않는다.

이 개발 PC에는 Docker가 없어 이미지 빌드/Compose CLI/NAS 배포·재부팅·실제 주기·운영 ACK는 미검증이다.
정적 검증은 Dockerfile COPY/ignore·소스·Compose 구조·볼륨·권한 기본값만 증명한다.
