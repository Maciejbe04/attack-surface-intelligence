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

gen postgres_password
gen django_secret_key
gen app_data_key
gen backup_key
gen session_hmac
gen worker_token

echo "Secrets ready in ${SECRET_DIR}"
