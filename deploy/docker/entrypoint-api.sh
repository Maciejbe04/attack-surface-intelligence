#!/usr/bin/env bash
set -euo pipefail

python manage.py migrate --noinput
python manage.py bootstrap_admin --username "${BOOTSTRAP_ADMIN_USER:-admin}" --password "${BOOTSTRAP_ADMIN_PASSWORD:-changeme}"
# Demo inventory: lab-target host + lab-local group (disable with SEED_LAB_TARGET=0).
if [[ "${SEED_LAB_TARGET:-1}" == "1" ]]; then
  python manage.py seed_lab_target --username "${BOOTSTRAP_ADMIN_USER:-admin}"
fi
# Synthetic lifecycle history for the Dashboard chart (local demo: SEED_DEMO_CHART=1).
if [[ "${SEED_DEMO_CHART:-0}" == "1" ]]; then
  python manage.py seed_demo_chart --username "${BOOTSTRAP_ADMIN_USER:-admin}"
fi
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  --access-logfile - \
  --error-logfile -
