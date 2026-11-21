# Backup i odtworzenie

## Co jest backupowane

Kontener `backup` cyklicznie:

1. `pg_dump` bazy SurfaceX,
2. szyfruje plik `openssl enc -aes-256-cbc -pbkdf2` kluczem z `secrets/backup_key`,
3. zapisuje `surfacex-YYYYMMDDThhmmssZ.sql.enc` w wolumenie `backup_data`.

Interwał: `BACKUP_INTERVAL_SECONDS` (domyślnie 86400).

Klucz aplikacji (`APP_DATA_KEY` / evidence AES-GCM) **nie** jest tożsamy z kluczem backupu.

## Podgląd artefaktów

```bash
docker compose exec backup ls -la /backups
```

## Ręczny dump (awaryjnie)

```bash
docker compose exec -T postgres \
  pg_dump -U surfacex surfacex > /tmp/surfacex-manual.sql
openssl enc -aes-256-cbc -pbkdf2 -salt \
  -pass file:secrets/backup_key \
  -in /tmp/surfacex-manual.sql \
  -out /tmp/surfacex-manual.sql.enc
rm /tmp/surfacex-manual.sql
```

## Test odtworzenia (manualny)

1. Skopiuj najnowszy `*.sql.enc` z wolumenu.
2. Odszyfruj:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 \
  -pass file:secrets/backup_key \
  -in surfacex-….sql.enc -out restore.sql
```

3. Uruchom tymczasową bazę i wgraj dump:

```bash
docker run --rm -d --name sx-restore-pg \
  -e POSTGRES_PASSWORD=restore \
  -e POSTGRES_USER=surfacex \
  -e POSTGRES_DB=surfacex \
  postgres:16
docker exec -i sx-restore-pg psql -U surfacex -d surfacex < restore.sql
docker exec sx-restore-pg \
  psql -U surfacex -d surfacex -c "SELECT count(*) FROM scans_scanrun;"
docker rm -f sx-restore-pg
rm restore.sql
```

Oczekiwane: migracje/tabele obecne, zapytanie kontrolne bez błędu.

## Skrypty

```bash
./scripts/backup.sh                 # one-shot → backups/surfacex-*.sql.enc
./scripts/restore-test.sh           # odszyfruj + tymczasowy Postgres + SELECT kontrolny
./scripts/restore-test.sh path.enc  # wskazany plik
```

Kontener `backup` nadal robi cykliczny dump do wolumenu Compose.

## Ograniczenia MVP

- Backup nie obejmuje wolumenów DefectDojo (osobna baza).
- Utrata `backup_key` = brak odszyfrowania dumpów.
