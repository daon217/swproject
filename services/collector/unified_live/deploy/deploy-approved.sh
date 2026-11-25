#!/bin/sh
set -eu
test "${COLLECTOR_DEPLOYMENT_APPROVED:-no}" = yes || { echo 'explicit deployment approval required' >&2; exit 2; }
profile="${1:-discovery}"
case "$profile" in discovery|fleet|public_feed|ebay|ebay_used|domeggook|serper|yes24|url) ;; *) echo 'unknown collector profile' >&2; exit 2;; esac
release="$(pwd -P)"
case "$release" in /volume1/docker/kkulpick-collector-releases/*) ;; *) echo 'reviewed separate collector release required' >&2; exit 2;; esac
runtime="${COLLECTOR_RUNTIME_ENV:-/volume1/docker/kkulpick-collectors-v2/config/runtime.env}"
file=services/collector/unified_live/deploy/compose.yaml
test -f "$runtime"
test -f "$file"
docker compose --env-file "$runtime" -p kkulpick-collectors-v2 -f "$file" --profile "$profile" config -q
# Only the collector project is affected. No down/stop/rm/pull/reset/clean is issued.
docker compose --env-file "$runtime" -p kkulpick-collectors-v2 -f "$file" --profile "$profile" up -d --no-build
docker compose --env-file "$runtime" -p kkulpick-collectors-v2 -f "$file" --profile "$profile" ps
