# Secrets

Files in this directory are gitignored except this README and `.gitkeep`.

Generate them with:

```bash
./scripts/init-secrets.sh
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
| `mfa_admin_secret` | lokalny zapis sekretu TOTP admina (opcjonalny, po `--enable-mfa`) |

## MFA (TOTP)

```bash
docker compose exec api python manage.py bootstrap_admin --enable-mfa
```

Dodaj `otpauth=` / `secret=` do Authenticatora. Sekret możesz też mieć w `secrets/mfa_admin_secret` (gitignored).
