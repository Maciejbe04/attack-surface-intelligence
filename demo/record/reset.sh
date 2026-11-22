#!/usr/bin/env bash
# Wipes SurfaceX scan data (targets, groups, scans, observations) and restarts the demo lab in phase 1.
# DESTRUCTIVE for local scan data — demo environment only.
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose exec -T api python manage.py shell -c "
from apps.scans import models as m
for name in ['FingerprintEvidence','Observation','ScanEvent','ScanBatch','ScanRun','GroupSchedule','ManualOverride','AllowlistEntry','Target','TargetGroup','AuditLog']:
    model = getattr(m, name, None)
    if model: print(name, model.objects.all().delete()[0])
from django.contrib.auth.models import User
from apps.accounts.models import UserProfile
for name, role in [('operator','operator'),('analityk','analyst'),('audytor','viewer')]:
    u,_=User.objects.get_or_create(username=name); u.set_password('Demo-2026!'); u.save()
    p,_=UserProfile.objects.get_or_create(user=u); p.role=role; p.save()
"
# Local demo DefectDojo only: drop previous SurfaceX findings so the recording starts clean.
if docker compose ps -q defectdojo-uwsgi | grep -q .; then
  docker compose exec -T defectdojo-uwsgi sh -c 'DD_DATABASE_URL="$(cat /run/secrets/defectdojo_database_url)" DD_SECRET_KEY="$(cat /run/secrets/defectdojo_secret_key)" DD_CREDENTIAL_AES_256_KEY="$(cat /run/secrets/defectdojo_credential_key)" python manage.py shell -c "from dojo.models import Test; print(\"dojo tests deleted\", Test.objects.all().delete()[0])"' 2>/dev/null | tail -1
fi
./demo/lab/lab.sh down >/dev/null 2>&1 || true
./demo/lab/lab.sh up
