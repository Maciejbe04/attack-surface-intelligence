#!/usr/bin/env bash
# One-shot encrypted PostgreSQL backup for SurfaceX.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

OUT_DIR="${BACKUP_OUT_DIR:-${ROOT}/backups}"
mkdir -p "${OUT_DIR}"

KEY_FILE="${ROOT}/secrets/backup_key"
if [[ ! -f "${KEY_FILE}" ]]; then
  echo "error: missing ${KEY_FILE} — run ./scripts/init-secrets.sh" >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "error: openssl required" >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RAW="${OUT_DIR}/surfacex-${STAMP}.sql"
ENC="${RAW}.enc"

echo "dumping postgres via compose service…"
docker compose exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-surfacex}" "${POSTGRES_DB:-surfacex}" > "${RAW}"

openssl enc -aes-256-cbc -pbkdf2 -salt \
  -pass "file:${KEY_FILE}" \
  -in "${RAW}" -out "${ENC}"
rm -f "${RAW}"

echo "wrote ${ENC}"
ls -lh "${ENC}"
