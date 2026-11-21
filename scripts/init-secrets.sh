#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRET_DIR="${ROOT}/secrets"
mkdir -p "${SECRET_DIR}"

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 48 | tr -d '\n'
    return
  fi
  if command -v docker >/dev/null 2>&1; then
    docker run --rm alpine:3.20 \
      sh -c "head -c 48 /dev/urandom | base64 | tr -d '\n'"
    return
  fi
  echo "error: openssl or Docker is required to generate secrets" >&2
  return 1
}

random_hex_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 16 | tr -d '\n'
    return
  fi
  if command -v docker >/dev/null 2>&1; then
    docker run --rm alpine:3.20 \
      sh -c "head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n'"
    return
  fi
  echo "error: openssl or Docker is required to generate secrets" >&2
  return 1
}

gen() {
  local name="$1"
  local path="${SECRET_DIR}/${name}"
  if [[ -f "${path}" ]]; then
    echo "keep  ${name}"
    return
  fi
  random_secret >"${path}"
  chmod 600 "${path}"
  echo "create ${name}"
}

gen_hex() {
  local name="$1"
  local path="${SECRET_DIR}/${name}"
  if [[ -f "${path}" ]]; then
    echo "keep  ${name}"
    return
  fi
  random_hex_secret >"${path}"
  chmod 600 "${path}"
  echo "create ${name}"
}

gen postgres_password
gen django_secret_key
gen app_data_key
gen backup_key
gen session_hmac
gen worker_token
gen defectdojo_admin_password
gen_hex defectdojo_db_password
gen defectdojo_secret_key
gen_hex defectdojo_credential_key

DEFECTDOJO_DATABASE_URL="${SECRET_DIR}/defectdojo_database_url"
if [[ -f "${DEFECTDOJO_DATABASE_URL}" ]]; then
  echo "keep  defectdojo_database_url"
else
  printf "postgresql://defectdojo:%s@defectdojo-postgres:5432/defectdojo" \
    "$(cat "${SECRET_DIR}/defectdojo_db_password")" \
    >"${DEFECTDOJO_DATABASE_URL}"
  chmod 600 "${DEFECTDOJO_DATABASE_URL}"
  echo "create defectdojo_database_url"
fi

echo "Secrets ready in ${SECRET_DIR}"
