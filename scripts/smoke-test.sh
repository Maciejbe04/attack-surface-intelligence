#!/usr/bin/env bash
# End-to-end smoke against a running SurfaceX Compose stack.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${GATEWAY_HTTP_PORT:-8080}"
BASE="${SMOKE_BASE_URL:-http://127.0.0.1:${PORT}}"
USER_NAME="${BOOTSTRAP_ADMIN_USER:-admin}"
PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-changeme}"
COOKIE_JAR="$(mktemp)"
trap 'rm -f "${COOKIE_JAR}"' EXIT

fail=0
pass() { echo "  OK  $*"; }
bad()  { echo " FAIL $*"; fail=$((fail + 1)); }

echo "== SurfaceX smoke-test =="
echo "base: ${BASE}"

if ! curl -fsS -o /dev/null --connect-timeout 3 "${BASE}/api/health/"; then
  bad "health unreachable at ${BASE}/api/health/"
  echo "hint: docker compose up -d && wait for api healthy"
  exit 1
fi
pass "GET /api/health/"

health_json="$(curl -fsS "${BASE}/api/health/")"
if echo "${health_json}" | grep -q '"database":\s*true\|"database": true'; then
  pass "database healthy"
else
  bad "database not healthy: ${health_json}"
fi

# CSRF + login
csrf_json="$(curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" "${BASE}/api/auth/csrf/" 2>/dev/null || true)"
csrf="$(
  CSRF_JSON="${csrf_json}" python3 - <<'PY' 2>/dev/null || true
import json, os
raw = os.environ.get("CSRF_JSON") or ""
token = ""
try:
    token = str(json.loads(raw).get("csrfToken") or "")
except Exception:
    token = ""
print(token)
PY
)"
login_headers=(-H "Content-Type: application/json" -H "Referer: ${BASE}/")
if [[ -n "${csrf}" ]]; then
  login_headers+=(-H "X-CSRFToken: ${csrf}")
fi

login_body="$(printf '{"username":"%s","password":"%s"}' "${USER_NAME}" "${PASSWORD}")"
login_code="$(
  curl -sS -o /tmp/sx-smoke-login.json -w "%{http_code}" \
    -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
    "${login_headers[@]}" \
    -X POST "${BASE}/api/auth/login/" \
    --data "${login_body}"
)"

if [[ "${login_code}" == "200" ]]; then
  pass "POST /api/auth/login/ (${USER_NAME})"
elif [[ "${login_code}" == "401" ]] && grep -qi mfa /tmp/sx-smoke-login.json 2>/dev/null; then
  pass "login requires MFA (account OK)"
else
  bad "login HTTP ${login_code}: $(head -c 200 /tmp/sx-smoke-login.json 2>/dev/null || true)"
fi

me_code="$(
  curl -sS -o /tmp/sx-smoke-me.json -w "%{http_code}" \
    -b "${COOKIE_JAR}" "${BASE}/api/auth/me/"
)"
if [[ "${me_code}" == "200" ]]; then
  pass "GET /api/auth/me/"
else
  # Some deployments accept X-Sessionid from login body
  sessionid="$(
    python3 - <<'PY' 2>/dev/null || true
import json
try:
    data = json.load(open("/tmp/sx-smoke-login.json", encoding="utf-8"))
    print(data.get("sessionid") or "")
except Exception:
    print("")
PY
  )"
  if [[ -n "${sessionid}" ]]; then
    me_code="$(
      curl -sS -o /tmp/sx-smoke-me.json -w "%{http_code}" \
        -H "X-Sessionid: ${sessionid}" "${BASE}/api/auth/me/"
    )"
  fi
  if [[ "${me_code}" == "200" ]]; then
    pass "GET /api/auth/me/ (X-Sessionid)"
  else
    bad "GET /api/auth/me/ HTTP ${me_code}"
  fi
fi

auth_hdr=(-b "${COOKIE_JAR}")
if [[ -n "${sessionid:-}" ]]; then
  auth_hdr+=(-H "X-Sessionid: ${sessionid}")
fi

for path in /api/targets/ /api/scans/ /api/groups/; do
  code="$(curl -sS -o /dev/null -w "%{http_code}" "${auth_hdr[@]}" "${BASE}${path}")"
  if [[ "${code}" == "200" ]]; then
    pass "GET ${path}"
  else
    bad "GET ${path} HTTP ${code}"
  fi
done

# Compose service health snapshot (best-effort)
if docker compose ps --format '{{.Name}} {{.Status}}' >/tmp/sx-smoke-ps.txt 2>/dev/null; then
  if grep -q api /tmp/sx-smoke-ps.txt && grep -qi healthy /tmp/sx-smoke-ps.txt; then
    pass "compose services reported"
  else
    note_line="$(head -5 /tmp/sx-smoke-ps.txt | tr '\n' ' | ')"
    echo " WARN compose status: ${note_line}"
  fi
fi

echo
if [[ "${fail}" -gt 0 ]]; then
  echo "smoke FAILED (${fail})"
  exit 1
fi
echo "smoke PASSED"
exit 0
