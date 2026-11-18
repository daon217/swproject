#!/bin/sh
# 사용법 (NAS SSH, 저장소 루트에서): sudo sh infra/nas/nas.sh up|ps|logs|stop|down
set -eu
cd "$(dirname "$0")/../.."
for f in infra/db/.env services/api/.env infra/nas/.env; do
  [ -f "$f" ] || { echo "missing $f (README 참고)"; exit 1; }
done
compose() {
  docker compose -p kkulpick-nas \
    --env-file infra/db/.env --env-file services/api/.env --env-file infra/nas/.env \
    -f infra/db/compose.yaml -f infra/db/api.compose.yaml -f infra/nas/compose.yaml "$@"
}
case "${1:-}" in
  up)   compose up -d --build --wait --wait-timeout 600 ;;
  seed) docker run --rm --network host -v "$PWD:/repo:ro" kkulpick-nas-api python /repo/services/api/dev.py seed ;;  # 빌드된 API 이미지로 127.0.0.1 API에 샘플 적재
  ps)   compose ps ;;
  logs) compose logs --tail 100 ;;
  stop) compose stop ;;
  down) compose down ;;   # 볼륨(DB 데이터)은 유지. 삭제하려면 직접 down -v
  *) echo "usage: $0 up|seed|ps|logs|stop|down"; exit 1 ;;
esac
