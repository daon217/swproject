#!/bin/sh
# Local validation/build only. Does not restart existing NAS containers or deploy.
set -eu
action="${1:---check}"
case "$action" in --check|--build) ;; *) echo 'use --check or --build' >&2; exit 2;; esac
release="$(pwd -P)"
case "$release" in /volume1/docker/swproject|/volume1/docker/swproject/*) echo 'Use a separate reviewed release; preserve the team worktree' >&2; exit 2;; esac
runtime="${COLLECTOR_RUNTIME_ENV:-/volume1/docker/kkulpick-collectors-v2/config/runtime.env}"
file="services/collector/unified_live/deploy/compose.yaml"
test -f "$runtime"
test -f "$file"
docker compose version
docker compose --env-file "$runtime" -p kkulpick-collectors-v2 -f "$file" --profile discovery --profile ebay --profile url --profile public_feed config -q
if [ "$action" = --build ]; then
  docker compose --env-file "$runtime" -p kkulpick-collectors-v2 -f "$file" --profile discovery build
fi
echo 'collector preparation completed; no containers started'
