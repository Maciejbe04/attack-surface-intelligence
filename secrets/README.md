# Secrets

Files in this directory are gitignored except this README and `.gitkeep`.

Generate them with:

```bash
./scripts/init-secrets.sh
```

**Windows / Git Bash:** uruchom `init-secrets.sh` **zanim** pierwszy raz wystartujesz Compose.
Jeśli Compose wystartuje bez plików w `secrets/`, Docker często tworzy **puste katalogi** o nazwach sekretów (`defectdojo_admin_password` itd.). Skrypt usuwa takie puste stuby i zapisuje normalne pliki. Gdy katalog nie jest pusty:

```bash
mv secrets/defectdojo_admin_password "secrets/defectdojo_admin_password.bak.$(date +%s)"
./scripts/init-secrets.sh
```

DefectDojo wymaga osobnego profilu Compose oraz kompletnych sekretów `defectdojo_*`.
Najprostszy start:

```bash
./scripts/start-defectdojo.sh
```

Expected files (mode `0600`):

| File | Used by |
|---|---|
| `postgres_password` | postgres, api, scheduler, backup |
| `django_secret_key` | api, scheduler |
| `app_data_key` | api |
| `backup_key` | backup |
| `session_hmac` | api |
| `worker_token` | api, worker |
| `defectdojo_admin_password` | api, DefectDojo initializer |
| `defectdojo_db_password` | DefectDojo PostgreSQL |
| `defectdojo_database_url` | DefectDojo Django services |
| `defectdojo_secret_key` | DefectDojo Django services |
| `defectdojo_credential_key` | szyfrowanie poświadczeń DefectDojo |
| `mfa_admin_secret` | lokalny zapis sekretu TOTP admina (opcjonalny, po `--enable-mfa`) |

## MFA (TOTP)

```bash
docker compose exec api python manage.py bootstrap_admin --enable-mfa
```

Dodaj `otpauth=` / `secret=` do Authenticatora. Sekret możesz też mieć w `secrets/mfa_admin_secret` (gitignored).
