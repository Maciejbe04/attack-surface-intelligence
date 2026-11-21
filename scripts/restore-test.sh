#!/usr/bin/env bash
# Decrypt a SurfaceX backup and verify restore into a temporary Postgres.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

KEY_FILE="${ROOT}/secrets/backup_key"
if [[ ! -f "${KEY_FILE}" ]]; then
  echo "error: missing ${KEY_FILE} — run ./scripts/init-secrets.sh" >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "error: openssl required" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker required" >&2
  exit 1
fi

ENC_PATH="${1:-}"
if [[ -z "${ENC_PATH}" ]]; then
  # Prefer host backups/ from backup.sh, else copy newest from compose volume.
  if compgen -G "${ROOT}/backups/surfacex-*.sql.enc" >/dev/null; then
    ENC_PATH="$(ls -1t "${ROOT}/backups"/surfacex-*.sql.enc | head -1)"
  else
    echo "no local backups/ — creating one via ./scripts/backup.sh"
    "${ROOT}/scripts/backup.sh"
    ENC_PATH="$(ls -1t "${ROOT}/backups"/surfacex-*.sql.enc | head -1)"
  fi
fi

if [[ ! -f "${ENC_PATH}" ]]; then
  echo "error: backup file not found: ${ENC_PATH}" >&2
  exit 1
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"; docker rm -f sx-restore-pg >/dev/null 2>&1 || true' EXIT
SQL="${WORKDIR}/restore.sql"

echo "== SurfaceX restore-test =="
echo "backup: ${ENC_PATH}"

openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass "file:${KEY_FILE}" \
  -in "${ENC_PATH}" -out "${SQL}"
echo "  OK  decrypted"

docker rm -f sx-restore-pg >/dev/null 2>&1 || true
docker run -d --name sx-restore-pg \
  -e POSTGRES_PASSWORD=restore \
  -e POSTGRES_USER=surfacex \
  -e POSTGRES_DB=surfacex \
  postgres:16 >/dev/null

echo "  OK  temporary postgres started"
for _ in $(seq 1 30); do
  if docker exec sx-restore-pg pg_isready -U surfacex -d surfacex >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! docker exec sx-restore-pg pg_isready -U surfacex -d surfacex >/dev/null 2>&1; then
  echo " FAIL temp postgres not ready" >&2
  exit 1
fi

docker exec -i sx-restore-pg psql -U surfacex -d surfacex < "${SQL}" >/tmp/sx-restore-load.log 2>&1 \
  || {
    echo " FAIL psql restore failed — see /tmp/sx-restore-load.log" >&2
    tail -20 /tmp/sx-restore-load.log >&2 || true
    exit 1
  }
echo "  OK  dump applied"

COUNT="$(
  docker exec sx-restore-pg \
    psql -U surfacex -d surfacex -Atc "SELECT count(*) FROM scans_scanrun;" 2>/dev/null \
    || echo "missing"
)"
if [[ "${COUNT}" == "missing" ]]; then
  # Older dumps / empty schema edge: fall back to table list
  TABLES="$(
    docker exec sx-restore-pg \
      psql -U surfacex -d surfacex -Atc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
  )"
  if [[ "${TABLES}" -gt 0 ]]; then
    echo "  OK  control query: ${TABLES} public tables (scans_scanrun absent — empty/new DB dump?)"
  else
    echo " FAIL no tables after restore" >&2
    exit 1
  fi
else
  echo "  OK  control query: scans_scanrun count=${COUNT}"
fi

echo "restore-test PASSED"
exit 0
