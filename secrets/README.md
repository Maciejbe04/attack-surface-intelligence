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
