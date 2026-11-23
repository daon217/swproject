#!/bin/sh
# Host-side, read-only Docker inspection. NEVER mount the daemon socket in a worker.
# Admin must approve the exact IDs, directory and Python environment before starting.
set -eu
: "${REVIEW_NETWORK_ID:?full approved network ID required}"
: "${REVIEW_COLLECTOR_ID:?full approved collector container ID required}"
: "${REVIEW_BACKEND_ID:?full approved ingest container ID required}"
: "${REVIEW_SERVICE:?approved service DNS alias required}"
: "${REVIEW_PORT:?approved service port required}"
: "${REVIEW_REFERENCE:?independent admin access-control approval reference required}"
: "${REVIEW_OUTPUT_DIR:?admin-owned worker-specific directory required}"
: "${REVIEW_PYTHON:?absolute prepared Python executable required}"
case "$REVIEW_PYTHON" in /*) ;; *) echo 'absolute Python path required' >&2; exit 2;; esac
case "$REVIEW_OUTPUT_DIR" in /*) ;; *) echo 'absolute review directory required' >&2; exit 2;; esac
umask 077
mkdir -p "$REVIEW_OUTPUT_DIR"
test ! -L "$REVIEW_OUTPUT_DIR" || exit 2
chmod 755 "$REVIEW_OUTPUT_DIR"
# Force the local Linux daemon; never inherit a remote/NAS Docker context.
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
docker_local() { docker -H unix:///var/run/docker.sock "$@"; }
revoke() {
  "$REVIEW_PYTHON" -c 'import json,os,sys,tempfile; from pathlib import Path; p=Path(sys.argv[1]); fd,t=tempfile.mkstemp(dir=p); f=os.fdopen(fd,"w");json.dump({"version":1,"approved":False},f);f.flush();os.fsync(f.fileno());f.close();os.chmod(t,0o644);os.replace(t,p/"internal-network-review.json")' "$REVIEW_OUTPUT_DIR"
}
temporary=''
cleanup() {
  if [ -n "$temporary" ]; then
    rm -f -- "$temporary/network.json" "$temporary/collector.json" "$temporary/backend.json"
    rmdir -- "$temporary"
    temporary=''
  fi
}
finish() { revoke; cleanup; }
trap finish EXIT
trap 'exit 0' INT TERM
# Deliberately exclude Config.Env (may contain API keys) from snapshots.
format='{"Id":{{json .Id}},"Config":{"Hostname":{{json .Config.Hostname}}},"State":{"Running":{{json .State.Running}}},"HostConfig":{"NetworkMode":{{json .HostConfig.NetworkMode}},"Privileged":{{json .HostConfig.Privileged}},"CapDrop":{{json .HostConfig.CapDrop}},"CapAdd":{{json .HostConfig.CapAdd}}},"NetworkSettings":{"Networks":{{json .NetworkSettings.Networks}},"Ports":{{json .NetworkSettings.Ports}}},"Mounts":{{json .Mounts}}}'
# Optional admin-owned allowlist for several explicitly trusted workers on one network.
set -- --trusted-container-id "$REVIEW_COLLECTOR_ID" --trusted-container-id "$REVIEW_BACKEND_ID"
if [ -n "${REVIEW_TRUSTED_IDS_FILE:-}" ]; then
  set --
  while IFS= read -r id || [ -n "$id" ]; do
    [ -z "$id" ] || set -- "$@" --trusted-container-id "$id"
  done < "$REVIEW_TRUSTED_IDS_FILE"
fi
while :; do
  temporary="$(mktemp -d "$REVIEW_OUTPUT_DIR/.inspect.XXXXXX")"
  if docker_local network inspect "$REVIEW_NETWORK_ID" > "$temporary/network.json" &&
     docker_local inspect --format "$format" "$REVIEW_COLLECTOR_ID" > "$temporary/collector.json" &&
     docker_local inspect --format "$format" "$REVIEW_BACKEND_ID" > "$temporary/backend.json"; then
    if "$REVIEW_PYTHON" -m services.collector.collector_ops.internal_network \
      --network-inspect "$temporary/network.json" --collector-inspect "$temporary/collector.json" --backend-inspect "$temporary/backend.json" \
      "$@" \
      --service "$REVIEW_SERVICE" --port "$REVIEW_PORT" --review-reference "$REVIEW_REFERENCE" \
      --admin-network-review-confirmed --output "$REVIEW_OUTPUT_DIR/internal-network-review.json" > /dev/null; then
      chmod 644 "$REVIEW_OUTPUT_DIR/internal-network-review.json"
    else revoke; fi
  else revoke; fi
  cleanup
  sleep 30
done
