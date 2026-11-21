#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

COMPOSE=(docker compose --profile defectdojo)
REQUIRED_SECRETS=(
  defectdojo_admin_password
  defectdojo_db_password
  defectdojo_database_url
  defectdojo_secret_key
  defectdojo_credential_key
)

if [[ -f .env ]]; then
  if ! grep -Eq '^[[:space:]]*COMPOSE_PROFILES=.*defectdojo' .env; then
    echo "==> Adding COMPOSE_PROFILES=defectdojo to .env"
    printf '\n# Added by start-defectdojo.sh — required for plain docker compose up\nCOMPOSE_PROFILES=defectdojo\n' >>.env
  fi
elif [[ -f .env.example ]]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
fi

echo "==> Generating / refreshing local secrets"
./scripts/init-secrets.sh

missing=0
for name in "${REQUIRED_SECRETS[@]}"; do
  path="secrets/${name}"
  if [[ ! -f "${path}" ]]; then
    echo "error: missing secret file: ${path}" >&2
    missing=1
  fi
done
if [[ "${missing}" -ne 0 ]]; then
  echo "error: re-run ./scripts/init-secrets.sh and try again" >&2
  exit 1
fi

echo "==> Validating compose (profile defectdojo)"
"${COMPOSE[@]}" config --quiet

echo "==> Pulling DefectDojo images (registry.defectdojo.com)"
if ! "${COMPOSE[@]}" pull defectdojo defectdojo-uwsgi defectdojo-postgres defectdojo-valkey; then
  cat >&2 <<'EOF'
error: could not pull DefectDojo images.

Typical causes:
  - no internet / corporate firewall blocks registry.defectdojo.com
  - Docker Hub / registry rate limit
  - outdated Docker Desktop

Manual check:
  docker pull registry.defectdojo.com/defectdojo/defectdojo-django:3.5.202
EOF
  exit 1
fi

echo "==> Starting DefectDojo profile"
"${COMPOSE[@]}" up -d defectdojo-postgres defectdojo-valkey
"${COMPOSE[@]}" up -d defectdojo-initializer
"${COMPOSE[@]}" up -d defectdojo-uwsgi defectdojo-celeryworker defectdojo-celerybeat defectdojo

echo
"${COMPOSE[@]}" ps defectdojo defectdojo-uwsgi defectdojo-initializer defectdojo-postgres defectdojo-valkey

port="${DEFECTDOJO_HTTP_PORT:-8081}"
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  # Prefer values from .env when present.
  source .env
  set +a
  port="${DEFECTDOJO_HTTP_PORT:-8081}"
fi

cat <<EOF

DefectDojo should be at: http://localhost:${port}
Login: admin / changeme  (secrets/defectdojo_admin_password — default from init-secrets)

If initializer failed (uwsgi never starts):
  docker compose --profile defectdojo logs defectdojo-initializer
  # dirty Postgres volume after a failed first boot:
  docker compose --profile defectdojo down
  docker volume rm surfacex_defectdojo_postgres
  ./scripts/start-defectdojo.sh

If port ${port} is busy, set DEFECTDOJO_HTTP_PORT in .env and re-run.
EOF
