#!/bin/sh
# 사용법 (NAS SSH, 저장소 루트에서): sudo sh infra/nas/nas.sh tokens|up|seed|ps|logs|stop|down
# infra/nas/.env에 NAS_VISION=1이면 Vision AI(kkulpick_vision)도 함께 관리합니다.
set -eu
cd "$(dirname "$0")/../.."
for f in infra/db/.env services/api/.env infra/nas/.env; do
  [ -f "$f" ] || { echo "missing $f (infra/nas/README.md 참고)"; exit 1; }
done
VISION_FILE=""
if grep -Eq '^NAS_VISION=1[[:space:]]*$' infra/nas/.env; then
  VISION_FILE="-f infra/nas/vision.compose.yaml"
fi
compose() {
  # shellcheck disable=SC2086
  docker compose -p kkulpick-nas \
    --env-file infra/db/.env --env-file services/api/.env --env-file infra/nas/.env \
    -f infra/db/compose.yaml -f infra/db/api.compose.yaml -f infra/nas/compose.yaml $VISION_FILE "$@"
}
rand() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
add_token() { # $1=파일 $2=이름: 없을 때만 무작위 64자를 추가(기존 값은 유지)
  if grep -Eq "^$2=.{32,}" "$1"; then echo "유지: $2 ($1)"
  else [ -z "$(tail -c1 "$1")" ] || echo >> "$1"; echo "$2=$(rand)" >> "$1"; echo "생성: $2 ($1)"; fi
}
case "${1:-}" in
  tokens)
    add_token services/api/.env ANALYSIS_WORKER_TOKEN
    add_token infra/nas/.env WORKSPACE_TOKEN
    echo "토큰은 공유·커밋하지 마세요. 적용: sudo sh infra/nas/nas.sh up" ;;
  up)   compose up -d --build --remove-orphans --wait --wait-timeout 1200 ;;
  seed) docker run --rm --network host -v "$PWD:/repo:ro" kkulpick-nas-api python /repo/services/api/dev.py seed ;;
  ps)   compose ps ;;
  logs) shift; compose logs --tail 100 "$@" ;;
  stop) compose stop ;;
  down) compose down ;;   # 볼륨(DB 데이터·OCR 모델)은 유지
  *) echo "usage: $0 tokens|up|seed|ps|logs [service]|stop|down"; exit 1 ;;
esac
