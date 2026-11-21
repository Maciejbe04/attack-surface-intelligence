#!/usr/bin/env bash
set -euo pipefail

INTERVAL="${BACKUP_INTERVAL_SECONDS:-86400}"
PASSWORD="$(cat /run/secrets/postgres_password)"
BACKUP_KEY_FILE="/run/secrets/backup_key"
OUT_DIR="/backups"

mkdir -p "${OUT_DIR}"

echo "backup loop started; interval=${INTERVAL}s"
while true; do
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  RAW="${OUT_DIR}/surfacex-${STAMP}.sql"
  ENC="${RAW}.enc"
  if PGPASSWORD="${PASSWORD}" pg_dump \
    -h "${POSTGRES_HOST:-postgres}" \
    -U "${POSTGRES_USER:-surfacex}" \
    -d "${POSTGRES_DB:-surfacex}" \
    -f "${RAW}"; then
    openssl enc -aes-256-cbc -pbkdf2 -salt \
      -pass "file:${BACKUP_KEY_FILE}" \
      -in "${RAW}" -out "${ENC}"
    rm -f "${RAW}"
    echo "wrote ${ENC}"
  else
    echo "pg_dump failed; will retry after interval" >&2
    rm -f "${RAW}"
  fi
  sleep "${INTERVAL}"
done
