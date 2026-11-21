# Attack Surface Intelligence

## SurfaceX

Narzędzie do cyklicznego i bezpiecznego discovery dużych sieci, fingerprintingu usług oraz analizy zmian powierzchni ataku w czasie.

## Status

MVP kolejki skanów działa end-to-end: zapisane targety i przebiegi są trwałe w PostgreSQL, API publikuje batche przez Redis do Celery, a izolowany worker wykonuje `nmap` i ProjectDiscovery `httpx`. UI obsługuje kolejkę, postęp, anulowanie oraz eksport ukończonych obserwacji do opcjonalnego DefectDojo.

Pierwsza wersja skanuje wyłącznie targety zapisane przez użytkownika z rolą `admin` albo `operator`. Reconciler okresowo odtwarza z PostgreSQL osierocone zadania po utracie kolejki Redis. Harmonogramy użytkownika oraz pause/resume pozostają kolejnym etapem.

## Szybki start

Wymagania: Git oraz Docker Engine/Desktop z Compose (Linux, macOS albo Windows + WSL2).

```bash
git clone git@github.com:Maciejbe04/attack-surface-intelligence.git
cd attack-surface-intelligence
cp .env.example .env
chmod +x scripts/init-secrets.sh deploy/docker/*.sh
./scripts/init-secrets.sh
docker compose up --build
```

UI: [http://localhost:8080](http://localhost:8080) (albo port z `GATEWAY_HTTP_PORT` w `.env`)  
API health: `/api/health/` na tym samym porcie  

Domyślne konto wyłącznie dla lokalnego developmentu: `admin` / `changeme`. Przed uruchomieniem współdzielonego środowiska ustaw własne `BOOTSTRAP_ADMIN_PASSWORD` w `.env`.

Jeśli hostowy port `8080` jest zajęty, ustaw np. `GATEWAY_HTTP_PORT=18080`.

### DefectDojo

DefectDojo 3.5.202 działa jako opcjonalny profil i nie obciąża zwykłego uruchomienia:

```bash
docker compose --profile defectdojo up --build
```

- UI DefectDojo: [http://localhost:8081](http://localhost:8081)
- Użytkownik: `admin`
- Hasło: zawartość lokalnego pliku `secrets/defectdojo_admin_password`

Po zakończeniu skanu użyj przycisku **Send to DefectDojo**. SurfaceX wysyła aktywne hosty, otwarte usługi i wykryte technologie jako informacyjne findings przez oficjalny endpoint `reimport-scan`. Produkt, engagement i test są tworzone automatycznie.

Zatrzymanie bez usuwania wolumenów:

```bash
docker compose down
```

## Build

| Cel | Komenda |
|---|---|
| Cały stos lokalnie | `docker compose up --build` |
| Tylko build obrazów | `docker compose build` |
| Multi-arch Bake | `docker buildx bake` |

Obrazy:

- `surfacex-gateway` — jedyny publikowany port (`GATEWAY_HTTP_PORT`, domyślnie `8080`)
- `surfacex-web` — statyczny bundle React z multi-stage build (Vite `dist/` **nie** trafia do Gita)
- `surfacex-api` — Django/Gunicorn + Celery beat + backup
- `surfacex-worker` — Celery worker z `nmap` i przypiętym ProjectDiscovery httpx
- `defectdojo-*` — opcjonalny, przypięty stos DefectDojo uruchamiany profilem

## Artefakty, których nie commitować

`.gitignore` i `.dockerignore` blokują m.in.:

- `web/node_modules/`, `web/dist/`, `web/build/`
- `.env`, `secrets/*` (poza README/`.gitkeep`)
- `__pycache__/`, `.venv/`
- lokalne backupy

Frontend jest budowany wyłącznie w obrazie (`Dockerfile.web`). Nie wrzucaj gotowego bundla do repozytorium.

## Sieci

| Sieć | Usługi |
|---|---|
| `edge` | gateway, web |
| `backend` (internal) | api, scheduler, postgres, redis, backup (+ gateway do API) |
| `scanner` | worker (egress do celów) |
| `defectdojo` (internal) | uWSGI, Celery, PostgreSQL i Valkey DefectDojo |

Worker ma `NET_RAW` (SYN gdy możliwe; inaczej TCP connect). Nie dostaje hasła PostgreSQL — wyniki mają iść przez API. Opcjonalny nginx DefectDojo publikuje osobny port `DEFECTDOJO_HTTP_PORT` (domyślnie `8081`).

## Dokumentacja

- [Plan MVP](docs/mvp-plan.md)
- [Architektura](docs/architecture.md)
- [Model danych](docs/data-model.md)
- [Polityka skanowania](docs/scanning-policy.md)
- [Sygnatury](docs/signatures.md)
- [Import i eksport](docs/import-export.md)
- [RBAC](docs/rbac.md)
- [Szyfrowanie](docs/encryption.md)
- [Scenariusz demo](docs/demo-script.md)
- [Platformy lokalne](docs/local-platforms.md)
- [Logowanie i MFA](docs/auth-mfa.md)
- [ADR-001: wybór silnika HTTP fingerprintingu](docs/adr-001-http-fingerprinting.md)

## Poza zakresem MVP

- Terraform, Ansible i Kubernetes;
- eksploatacja podatności, brute force i logowanie do celów;
- WhatWeb i Nuclei jako obowiązkowe narzędzia;
- Windows Containers;
- wysokodostępny klaster produkcyjny.
