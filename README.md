# Attack Surface Intelligence

## SurfaceX

Narzędzie do cyklicznego i bezpiecznego discovery dużych sieci, fingerprintingu usług oraz analizy zmian powierzchni ataku w czasie.

## Status

Scaffold Docker Compose jest gotowy: gateway, web (React), API (Django), Celery beat/worker, PostgreSQL, Redis i backup. Logika skanowania MVP jest jeszcze w budowie; UI ma ekran startowy z healthcheckiem API.

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

UI: [http://localhost:8080](http://localhost:8080)  
API health: [http://localhost:8080/api/health/](http://localhost:8080/api/health/)

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

Worker ma `NET_RAW` (SYN gdy możliwe; inaczej TCP connect). Nie dostaje hasła PostgreSQL — wyniki mają iść przez API.

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
- [ADR-001: wybór silnika HTTP fingerprintingu](docs/adr-001-http-fingerprinting.md)

## Poza zakresem MVP

- Terraform, Ansible i Kubernetes;
- eksploatacja podatności, brute force i logowanie do celów;
- WhatWeb i Nuclei jako obowiązkowe narzędzia;
- Windows Containers;
- wysokodostępny klaster produkcyjny.
