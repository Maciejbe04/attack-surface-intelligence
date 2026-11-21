# Attack Surface Intelligence

## SurfaceX

Narzędzie do cyklicznego i bezpiecznego discovery dużych sieci, fingerprintingu usług oraz analizy zmian powierzchni ataku w czasie.

## Status

Projekt jest w fazie dokumentacji i projektowania MVP. Kod aplikacji oraz `compose.yml` nie są jeszcze dostępne. Ten commit opisuje zakres, architekturę i kontrakty potrzebne do implementacji.

## Cel MVP

- bezpieczne skanowanie zakresów powyżej 10 000 adresów;
- discovery nmap oraz fingerprinting HTTP/TLS przez ProjectDiscovery httpx;
- deklaratywne sygnatury i confidence score;
- historia zmian `NEW/CHANGED/MISSING/FLAKY/GONE`;
- RBAC, trwałe overrides i szyfrowanie danych wrażliwych;
- lokalne uruchomienie przez Docker Compose na `linux/amd64` i `linux/arm64`.

## Stos

| Warstwa | Technologia |
|---|---|
| API / scheduler / worker | Go |
| UI | React / TypeScript |
| Dane | PostgreSQL |
| Kolejka i sesje | Redis |
| Discovery | nmap |
| HTTP / TLS fingerprint | ProjectDiscovery httpx |
| Uruchomienie | Docker Compose |

## Planowane uruchomienie

Po pojawieniu się `compose.yml` świeża instalacja będzie wymagała wyłącznie:

- Git;
- Docker Engine z Compose albo Docker Desktop;
- minimalnej ilości RAM i miejsca opisanej w dokumentacji operacyjnej.

Docelowa sekwencja:

```bash
git clone <repo>
cd attack-surface-intelligence
cp .env.example .env
./scripts/init-secrets.sh
docker compose up --build
```

Do czasu implementacji Compose powyższe komendy nie działają. Szczegóły architektury i polityk są w `docs/`.

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
- [ADR-001: wybór silnika HTTP fingerprintingu](docs/adr-001-http-fingerprinting.md)

## Poza zakresem MVP

- Terraform, Ansible i Kubernetes;
- eksploatacja podatności, brute force i logowanie do celów;
- WhatWeb i Nuclei jako obowiązkowe narzędzia;
- wysokodostępny klaster produkcyjny.
