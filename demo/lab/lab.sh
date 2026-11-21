#!/usr/bin/env bash
# Demo lab helper. up: start lab + attach SurfaceX worker; mutate: changes for scan 2; down: remove.
set -euo pipefail
cd "$(dirname "$0")"
WORKER=$(docker ps --filter label=com.docker.compose.service=worker --filter label=com.docker.compose.project=surfacex -q | head -1)
attach() { [ -n "$WORKER" ] && { docker network connect asi-lab "$WORKER" 2>/dev/null || true; echo "worker attached to asi-lab"; } || echo "WARN: SurfaceX worker not running"; }
case "${1:-up}" in
  up)
    [ -f certs/lab.crt ] || openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=intranet.lab.local/O=Demo Lab" \
      -keyout certs/lab.key -out certs/lab.crt 2>/dev/null
    STAGING_CONF=staging-v1 docker compose up -d --remove-orphans
    attach ;;
  mutate)
    docker compose stop flaky                                   # disappeared host
    STAGING_CONF=staging-v2 docker compose up -d staging        # changed headers + new port 8443
    docker compose --profile phase2 up -d newapp                # new host
    attach ;;
  down) docker compose --profile phase2 down ;;
  *) echo "usage: $0 up|mutate|down"; exit 2 ;;
esac
