#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

ok() { printf '  [OK]  %s\n' "$*"; }
bad() { printf '  [!!]  %s\n' "$*"; }
info() { printf '  [--]  %s\n' "$*"; }

echo "DefectDojo doctor"
echo "================="

if ! command -v docker >/dev/null 2>&1; then
  bad "Docker nie jest zainstalowany albo nie ma go w PATH"
  exit 1
fi
ok "Docker jest dostępny"

if ! docker compose version >/dev/null 2>&1; then
  bad "Brak Docker Compose (plugin 'docker compose')"
  exit 1
fi
ok "Docker Compose działa"

if [[ -f .env ]]; then
  ok "Jest plik .env"
  if grep -Eq '^[[:space:]]*COMPOSE_PROFILES=.*defectdojo' .env; then
    ok ".env ma COMPOSE_PROFILES z defectdojo — zwykłe 'docker compose up' uruchomi DD"
  else
    bad ".env NIE ma COMPOSE_PROFILES=defectdojo"
    info "Bez tego 'docker compose up' NIE startuje DefectDojo"
    info "Dodaj linię: COMPOSE_PROFILES=defectdojo"
    info "albo zawsze używaj: docker compose --profile defectdojo up -d"
  fi
else
  bad "Brak .env (skopiuj: cp .env.example .env)"
fi

echo
echo "Sekrety:"
REQUIRED="defectdojo_admin_password defectdojo_db_password defectdojo_database_url defectdojo_secret_key defectdojo_credential_key"
missing=0
for name in ${REQUIRED}; do
  if [[ -f "secrets/${name}" ]]; then
    ok "secrets/${name}"
  else
    bad "brak secrets/${name}"
    missing=1
  fi
done
if [[ "${missing}" -ne 0 ]]; then
  info "Naprawa: ./scripts/init-secrets.sh"
fi

echo
echo "Profil / kontenery:"
dd_services="$(docker compose --profile defectdojo config --services 2>/dev/null | grep '^defectdojo' || true)"
if [[ -z "${dd_services}" ]]; then
  bad "Compose nie widzi serwisów defectdojo*"
else
  ok "Compose zna serwisy defectdojo*"
  echo "${dd_services}" | sed 's/^/        /'
fi

running="$(docker compose --profile defectdojo ps --status running --services 2>/dev/null | grep '^defectdojo' || true)"
if [[ -n "${running}" ]]; then
  ok "Działające kontenery DD:"
  echo "${running}" | sed 's/^/        /'
else
  bad "Żaden kontener defectdojo* nie działa"
  info "Naprawa: ./scripts/start-defectdojo.sh"
fi

echo
echo "Obrazy / sieć:"
if docker image inspect "registry.defectdojo.com/defectdojo/defectdojo-django:3.5.202" >/dev/null 2>&1; then
  ok "Obraz defectdojo-django:3.5.202 jest lokalnie"
else
  bad "Brak lokalnego obrazu defectdojo-django:3.5.202"
  info "Wymagany pull z registry.defectdojo.com (firewall/VPN może blokować)"
  info "Test: docker pull registry.defectdojo.com/defectdojo/defectdojo-django:3.5.202"
fi

port=8081
if [[ -f .env ]]; then
  port_from_env="$(grep -E '^[[:space:]]*DEFECTDOJO_HTTP_PORT=' .env | tail -1 | cut -d= -f2- | tr -d '[:space:]' || true)"
  if [[ -n "${port_from_env}" ]]; then
    port="${port_from_env}"
  fi
fi
if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
  info "Port ${port} jest zajęty (OK jeśli to już DefectDojo)"
  lsof -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | sed 's/^/        /' || true
else
  info "Port ${port} wygląda na wolny (albo lsof niedostępne)"
fi

echo
echo "Initializer (ostatnie logi):"
if docker compose --profile defectdojo ps -a --services 2>/dev/null | grep -q '^defectdojo-initializer$'; then
  docker compose --profile defectdojo logs --tail 30 defectdojo-initializer 2>/dev/null | sed 's/^/        /' || true
  if docker compose --profile defectdojo ps -a defectdojo-initializer 2>/dev/null | grep -Eq 'Exited \(0\)'; then
    ok "Initializer zakończył się kodem 0"
  else
    bad "Initializer nie zakończył się sukcesem — uwsgi/nginx nie wstanie"
    info "Częsta naprawa po padniętym pierwszym starcie:"
    info "  docker compose --profile defectdojo down"
    info "  docker volume rm surfacex_defectdojo_postgres"
    info "  ./scripts/start-defectdojo.sh"
  fi
else
  info "Kontener initializer jeszcze nie istniał"
fi

echo
echo "Szybki start dla kolegi:"
cat <<'EOF'
  cd attack-surface-intelligence
  git pull
  cp -n .env.example .env
  # w .env musi być linia:
  # COMPOSE_PROFILES=defectdojo
  chmod +x scripts/*.sh
  ./scripts/init-secrets.sh
  ./scripts/start-defectdojo.sh
  # UI: http://localhost:8081  user: admin  hasło: cat secrets/defectdojo_admin_password
EOF
