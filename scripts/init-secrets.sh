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

# Docker Compose on Windows/Git Bash often creates a *directory* for a missing
# secret file when compose starts before init-secrets. Replace those stubs.
ensure_secret_file_path() {
  local path="$1"
  local name="$2"
  if [[ -d "${path}" ]]; then
    if [[ -n "$(find "${path}" -mindepth 1 -maxdepth 1 2>/dev/null | head -n 1)" ]]; then
      echo "error: ${name} is a non-empty directory; move it aside and re-run:" >&2
      echo "  mv \"${path}\" \"${path}.bak.\$(date +%s)\"" >&2
      return 1
    fi
    rmdir "${path}"
    echo "fix  ${name} (was empty directory — usually Docker created it before secrets existed)"
  elif [[ -e "${path}" && ! -f "${path}" ]]; then
    echo "error: ${name} exists but is not a regular file (${path})" >&2
    return 1
  fi
}

gen() {
  local name="$1"
  local path="${SECRET_DIR}/${name}"
  ensure_secret_file_path "${path}" "${name}"
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
  ensure_secret_file_path "${path}" "${name}"
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
DB_PASSWORD_FILE="${SECRET_DIR}/defectdojo_db_password"
ensure_secret_file_path "${DEFECTDOJO_DATABASE_URL}" "defectdojo_database_url"
EXPECTED_DATABASE_URL="$(
  printf "postgresql://defectdojo:%s@defectdojo-postgres:5432/defectdojo" \
    "$(cat "${DB_PASSWORD_FILE}")"
)"
if [[ -f "${DEFECTDOJO_DATABASE_URL}" ]] \
  && [[ "$(cat "${DEFECTDOJO_DATABASE_URL}")" == "${EXPECTED_DATABASE_URL}" ]]; then
  echo "keep  defectdojo_database_url"
else
  printf "%s" "${EXPECTED_DATABASE_URL}" >"${DEFECTDOJO_DATABASE_URL}"
  chmod 600 "${DEFECTDOJO_DATABASE_URL}"
  echo "update defectdojo_database_url"
fi

echo "Secrets ready in ${SECRET_DIR}"
echo "Tip: always run this script before the first 'docker compose up' (especially on Windows)."
