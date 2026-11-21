#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRET_DIR="${ROOT}/secrets"
mkdir -p "${SECRET_DIR}"

gen() {
  local name="$1"
  local path="${SECRET_DIR}/${name}"
  if [[ -f "${path}" ]]; then
    echo "keep  ${name}"
    return
  fi
  openssl rand -base64 48 | tr -d '\n' >"${path}"
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
