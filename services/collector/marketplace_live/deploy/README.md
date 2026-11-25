# 독립 Docker 실행 준비

정정: 해외 Shopping 서비스명은 `serper`, 소스는 `serper_google_shopping`,
환경 파일 경로 변수는 `SERPER_ENV_FILE`, 키는 `SERPER_API_KEY`입니다.
아래 SearchAPI 명령은 이전 기록이며 실행하지 마세요. 최신 안내는
`../docs/SERPER.md`를 사용합니다. YES24/eBay/도매꾹 코드는 변경하지 않습니다.

이 설정은 작성·정적 검사만 했습니다. 실제 Docker 빌드/기동, NAS 배포는
수행하지 않았습니다. 해당 작업을 승인받은 후 NAS 환경에서 검증하세요.

1. `.env.example`의 경로 값을 외부 `paths.env`에 준비합니다. 비밀 값은 이
   파일이 아니라 공급자별 외부 env_file에 둡니다. 저장소에는 넣지 않습니다.
2. 도매꾹 env: DOMEGGOOK_API_KEY와 승인된 KKULPICK_BACKEND_TOKEN.
   YES24 env: YES24_API_KEY만 필요합니다. SearchAPI env: SEARCHAPI_API_KEY,
   eBay env: EBAY_CLIENT_ID/EBAY_CLIENT_SECRET. 해외 운영 저장을 승인받은
   경우에만 그 소스의 env에 KKULPICK_BACKEND_TOKEN을 추가합니다.
3. lookup config는 `lookup.example.json`에서 준비하고, collection config는
   기존 `config.example.json`에서 실제 권한·비용·저장 허가에 맞춰 별도로 준비합니다.
   YES24는 lookup-only로 유지하며 운영 저장 플래그를 켜지 않습니다.
4. 도매꾹의 기존 전체 data/원장/체크포인트/outbox를 그대로 마운트합니다.
   새 volume으로 이력을 초기화하지 않습니다. 해외 상태는 source별 경로에
   보존하며 호스트와 컨테이너에서 동일 공급자 원장을 공유해야 합니다.
5. bind mount 디렉터리는 UID/GID 10001이 쓸 수 있어야 합니다. 잠금/atomic
   rename이 보장되는 NAS 로컬 파일시스템을 사용하고 동시에 두 호스트에서
   같은 source를 실행하지 않습니다.

승인 후 이 deploy 디렉터리에서 사용할 명령 예시:

```text
docker compose --env-file <external-paths.env> --profile lookup build yes24
docker compose --env-file <external-paths.env> --profile lookup run --rm --no-deps yes24
```

위 yes24 기본 명령은 `--plan`이라 공급자 HTTP가 없습니다. 해당 공급자의
실제 요청을 따로 승인받은 후에만 다음 override로 최대 3개 조회를 실행합니다.

```text
docker compose --env-file <external-paths.env> --profile lookup run --rm --no-deps yes24 python -m services.collector.marketplace_live.probe --source yes24_api --live --max-products 3
```

독립 운영 수집을 승인받았고 설정의 권한과 비용 검증을 마친 경우에만:

```text
docker compose --env-file <external-paths.env> --profile overseas up -d ebay
docker compose --env-file <external-paths.env> --profile overseas up -d searchapi
docker compose --env-file <external-paths.env> --profile domeggook up -d domeggook
```

각 서비스는 별도 PID·env_file·source state·잠금·수집 예산·outbox를 사용합니다.
YES24를 2시간 무인 저장 watch로 바꾸는 설정은 제공하지 않습니다. 도매꾹과
해외 source watch의 주기는 기존 정책상 최소 7,200초입니다.

테스트/운영 토큰과 config를 혼용하지 마세요. 실제 상품 조회 probe에는 토큰을
줄 필요가 없고 DB 클라이언트도 없습니다. 서비스 상태는 `--status`로 확인하고,
컨테이너가 살아 있다는 사실만으로 수집이나 DB 적용 성공을 판단하지 않습니다.
`docker compose config`를 출력하면 env_file 값이 노출될 수 있으므로 비밀이
포함된 출력을 로그·이슈·Git에 첨부하지 마세요.
