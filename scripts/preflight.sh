#!/usr/bin/env bash
# Check host readiness for SurfaceX (Docker Compose local run).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

ok=0
warn=0
fail=0

pass() { echo "  OK  $*"; ok=$((ok + 1)); }
note() { echo " WARN $*"; warn=$((warn + 1)); }
bad()  { echo " FAIL $*"; fail=$((fail + 1)); }

echo "== SurfaceX preflight =="
echo "host: $(uname -s) $(uname -m)"

if command -v docker >/dev/null 2>&1; then
  pass "docker: $(docker version --format '{{.Server.Version}}' 2>/dev/null || docker --version)"
else
  bad "docker not found"
fi

if docker compose version >/dev/null 2>&1; then
  pass "docker compose: $(docker compose version --short 2>/dev/null || echo present)"
else
  bad "docker compose plugin missing"
fi

arch="$(uname -m)"
case "${arch}" in
  x86_64|amd64) pass "arch amd64-compatible (${arch})" ;;
  arm64|aarch64) pass "arch arm64-compatible (${arch})" ;;
  *) note "unusual arch ${arch} — bake targets are linux/amd64+arm64" ;;
esac

if command -v openssl >/dev/null 2>&1; then
  pass "openssl available"
else
  note "openssl missing (needed for backup/restore scripts)"
fi

# Disk / memory hints (best-effort)
if command -v df >/dev/null 2>&1; then
  avail_kb="$(df -Pk "${ROOT}" | awk 'NR==2 {print $4}')"
  if [[ -n "${avail_kb}" && "${avail_kb}" -ge 5242880 ]]; then
    pass "disk free ≥ ~5 GiB on project volume"
  elif [[ -n "${avail_kb}" ]]; then
    note "low disk (~$((avail_kb / 1024)) MiB free) — recommend ≥5 GiB"
  fi
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  mem_gb="$(sysctl -n hw.memsize 2>/dev/null | awk '{printf "%d", $1/1024/1024/1024}')"
  if [[ -n "${mem_gb}" && "${mem_gb}" -ge 8 ]]; then
    pass "RAM ~${mem_gb} GiB"
  elif [[ -n "${mem_gb}" ]]; then
    note "RAM ~${mem_gb} GiB — recommend ≥8 GiB (more with DefectDojo)"
  fi
elif [[ -r /proc/meminfo ]]; then
  mem_gb="$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)"
  if [[ "${mem_gb}" -ge 8 ]]; then
    pass "RAM ~${mem_gb} GiB"
  else
    note "RAM ~${mem_gb} GiB — recommend ≥8 GiB"
  fi
fi

gateway_port="${GATEWAY_HTTP_PORT:-8080}"
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  gateway_port="$(grep -E '^GATEWAY_HTTP_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)"
  gateway_port="${gateway_port:-8080}"
  pass ".env present"
else
  note ".env missing — copy from .env.example before up"
fi

if command -v lsof >/dev/null 2>&1; then
  if lsof -iTCP:"${gateway_port}" -sTCP:LISTEN >/dev/null 2>&1; then
    note "port ${gateway_port} already listening (set GATEWAY_HTTP_PORT if conflict)"
  else
    pass "port ${gateway_port} appears free"
  fi
fi

if docker info >/dev/null 2>&1; then
  pass "docker daemon reachable"
  if docker run --rm --network none alpine:3.20 true >/dev/null 2>&1; then
    pass "can run containers"
  else
    note "could not run alpine test container"
  fi
else
  bad "docker daemon not reachable"
fi

echo
echo "summary: ok=${ok} warn=${warn} fail=${fail}"
if [[ "${fail}" -gt 0 ]]; then
  exit 1
fi
exit 0
