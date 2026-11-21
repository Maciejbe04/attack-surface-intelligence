# Operacje

## Start / stop

```bash
./scripts/init-secrets.sh
docker compose up --build -d
docker compose ps
docker compose down          # bez usuwania wolumenów
```

UI: `http://localhost:${GATEWAY_HTTP_PORT:-8080}`  
Health: `/api/health/`

DefectDojo (profil): `./scripts/start-defectdojo.sh` — port `${DEFECTDOJO_HTTP_PORT:-8081}`.

## Usługi

| Usługa | Rola |
|---|---|
| `gateway` | TLS/HTTP edge |
| `web` | UI React |
| `api` | Django/DRF |
| `scheduler` | Celery beat (reconcile, schedules) |
| `worker` | Celery + nmap/httpx |
| `postgres` / `redis` | dane / broker |
| `backup` | zaszyfrowany `pg_dump` loop |

Sieci: `edge`, `backend` (internal), `scanner` — szczegóły w `docs/architecture.md`.

## Healthchecki i logi

```bash
docker compose ps
docker compose logs -f api worker scheduler
docker compose exec api python manage.py check
```

Worker bez tokenu lub API z read-only rootfs zgłosi błędy w logach claim/complete.

## Skalowanie workerów

```bash
docker compose up -d --scale worker=3
```

Limity pamięci/CPU w `compose.yml` / `.env`. Prefetch Celery = 1; visibility timeout ~360 s.

## Reconcile i okna

- Scheduler/reconcile republishuje stale `QUEUED`/`RUNNING` oraz stosuje deadline → `PAUSED`.
- `SCAN_RECONCILE_INTERVAL_SECONDS` / `SCAN_RECONCILE_STALE_SECONDS` w env.
- Cancel-check workera też pauzuje po deadline (kill bez czekania na reconcile).

## Harmonogramy grup

Celery beat wywołuje `internal/schedules/dispatch/`. Harmonogramy UTC: hourly / daily / weekly. Zakończone skany mogą auto-eksportować do DefectDojo.

## Backup

Zob. `docs/backup-restore.md`. Kontener `backup` zapisuje `*.sql.enc` do wolumenu `backup_data`.

## Typowe problemy

| Objaw | Co sprawdzić |
|---|---|
| 502 / maintenance | gateway + `api` healthy |
| Scan not queued / allowlist | zakładka Allowlist; wpisy właściciela |
| Worker nie claimuje | `WORKER_TOKEN`, sieć `scanner`, logi worker |
| DefectDojo down | `COMPOSE_PROFILES=defectdojo`, `./scripts/doctor-defectdojo.sh` |
| Sesja „wylogowuje” | ten sam origin (IP vs domena); `X-Sessionid` fallback w UI |

## Multi-arch

```bash
docker buildx bake
```

Obrazy `linux/amd64` i `linux/arm64` — `docker-bake.hcl`.
