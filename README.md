# SurfaceX — Attack Surface Intelligence

Narzędzie do cyklicznego, bezpiecznego discovery dużych sieci: wykrywa aktywne hosty i usługi, rozpoznaje technologie webowe, zbiera nagłówki, ciasteczka i certyfikaty TLS oraz pokazuje, co zmieniło się między kolejnymi skanami.

Rozwiązanie zadania **„Attack Surface Intelligence”** Centrum Bezpieczeństwa Informacji AGH (HackNation 2026). Zespół: **Molekuły**.

## Co potrafi

- **Cele:** IP, zakresy CIDR i domeny — z formularza albo z pliku TXT/CSV/JSON (do 10 000 celów), z grupami i komentarzami.
- **Discovery:** `nmap` (hosty, porty, usługi i wersje) oraz ProjectDiscovery `httpx` (tytuł, kod, nagłówki, ciasteczka, certyfikat TLS, technologie), uruchamiane równolegle przez workery Celery.
- **Fingerprinting:** wykrywanie CMS-ów, frameworków i serwerów, własne deklaratywne sygnatury YAML, wskazówki paneli administracyjnych i środowisk staging, porty IoT/OT.
- **Zmiany w czasie:** każda obserwacja dostaje stan `NEW`, `CHANGED`, `MISSING`, `FLAKY` albo `GONE` względem poprzedniego skanu; niestabilny host nie jest zgłaszany jako nieaktywny po jednym braku odpowiedzi.
- **Bezpieczne skanowanie:** allowlista, twarde limity tempa, obowiązkowe okno czasowe z pauzą i wznowieniem, brak logowania, brute force i eksploatacji.
- **Praca zespołu:** cztery role (`admin`, `operator`, `analyst`, `viewer`), trwałe ręczne korekty wyników (tagi, notatki), dziennik audytu.
- **Integracje:** eksport JSON/CSV, import wyników, automatyczna wysyłka do DefectDojo, harmonogramy skanów grup, pasywne źródła crt.sh i RDAP.
- **Ochrona danych:** szyfrowanie dowodów skanów i notatek AES-256-GCM, hasła Argon2id, szyfrowany backup.

## Szybki start

Wymagania: Git i Docker z Compose (Linux, macOS albo Windows + WSL2), ok. 8 GB RAM, wolne porty `8080`, `8081` i `18088`.

```bash
git clone https://github.com/Maciejbe04/attack-surface-intelligence.git
cd attack-surface-intelligence
cp .env.example .env
./scripts/preflight.sh        # kontrola środowiska
./scripts/init-secrets.sh     # sekrety w secrets/ (poza Gitem)
docker compose up --build -d
./scripts/smoke-test.sh       # oczekiwany wynik: smoke PASSED
```

Pierwszy build trwa kilka minut. Po starcie:

| Co | Adres | Konto lokalne |
|---|---|---|
| SurfaceX | http://localhost:8080 | `admin` / `changeme` |
| DefectDojo | http://localhost:8081 | `admin` / `changeme` |
| Cel demonstracyjny | http://localhost:18088 | — |

Konto `admin` / `changeme` jest przeznaczone wyłącznie do uruchomienia lokalnego — przed udostępnieniem instancji ustaw `BOOTSTRAP_ADMIN_PASSWORD` w `.env`.

Najczęstsze warianty:

- port `8080` zajęty → `GATEWAY_HTTP_PORT=18080` w `.env`;
- bez DefectDojo (mniej RAM) → usuń `COMPOSE_PROFILES=defectdojo` z `.env`;
- DefectDojo nie wstaje → `./scripts/doctor-defectdojo.sh`, potem `./scripts/start-defectdojo.sh`;
- zatrzymanie z zachowaniem danych → `docker compose down`.

## Pierwszy skan w 2 minuty

Stos startuje z wbudowanym celem `lab-target` oraz gotową grupą `lab-local`.

1. Zaloguj się na http://localhost:8080 jako `admin`.
2. Na **Dashboardzie** zaznacz moduł `full-pipeline` — skan grupy używa modułów wybranych na Dashboardzie.
3. W zakładce **Groups** kliknij **Scan now** przy grupie `lab-local`.
4. W zakładce **Scans** obserwuj postęp i konsolę aktywności, a po zakończeniu otwórz **Findings**, dodaj notatkę do wyniku (**Add override**) i pobierz **Export JSON** / **Export CSV**.
5. Wróć na **Dashboard**: sekcja **Curiosity** pokazuje najważniejsze znaleziska, a **Changes over time** zmiany między skanami.

Pełny scenariusz dwóch skanów ze zmianą środowiska (laboratorium 7 kontenerów): [docs/demo-script.md](docs/demo-script.md). Obsługa interfejsu krok po kroku: [docs/instrukcja-uzytkownika.md](docs/instrukcja-uzytkownika.md).

## Architektura w skrócie

```text
Przeglądarka → gateway (nginx :8080) → web (React)
                                     → api (Django REST) → PostgreSQL
                                                         → Redis → worker (Celery: nmap, httpx, sygnatury)
                                                                     │ wyniki przez /api/internal/ (token)
                                       api ◀─────────────────────────┘
                                       api ⇢ DefectDojo (opcjonalny profil)
```

| Usługa | Rola |
|---|---|
| `gateway` | jedyny port SurfaceX wystawiony na hoście |
| `web` | interfejs React/TypeScript |
| `api` | REST API, RBAC, normalizacja wyników, porównania, eksport |
| `scheduler` | Celery Beat: harmonogramy i odtwarzanie kolejki |
| `worker` | wykonanie skanów; jedyna usługa z ruchem do skanowanych sieci, bez dostępu do bazy |
| `postgres`, `redis` | dane trwałe; kolejka i cache |
| `backup` | cykliczny, zaszyfrowany zrzut bazy |
| `lab-target` | wbudowany cel demonstracyjny |
| `defectdojo*` | opcjonalny DefectDojo 3.5.202 |

Sieci: `edge` (wejście), `backend` (wewnętrzna, bez wyjścia na zewnątrz), `scanner` (ruch do celów), `defectdojo` (wewnętrzna). Szczegóły: [docs/architecture.md](docs/architecture.md).

## Dokumentacja

Zacznij od **[dokumentacji technicznej](docs/dokumentacja-techniczna.md)** — opisuje całość, zawiera mapę wymagań zadania i listę znanych ograniczeń.

| Temat | Dokument |
|---|---|
| Całość rozwiązania, mapa wymagań | [docs/dokumentacja-techniczna.md](docs/dokumentacja-techniczna.md) |
| Obsługa interfejsu | [docs/instrukcja-uzytkownika.md](docs/instrukcja-uzytkownika.md) |
| Scenariusz demonstracji, laboratoria | [docs/demo-script.md](docs/demo-script.md), [demo/README.md](demo/README.md) |
| Architektura, sieci, granice zaufania | [docs/architecture.md](docs/architecture.md) |
| API REST | [docs/api.md](docs/api.md) |
| Model danych i cykl życia obserwacji | [docs/data-model.md](docs/data-model.md) |
| Zasady i limity skanowania | [docs/scanning-policy.md](docs/scanning-policy.md) |
| Własne sygnatury | [docs/signatures.md](docs/signatures.md) |
| Import, eksport, DefectDojo | [docs/import-export.md](docs/import-export.md) |
| Grupy i harmonogramy | [docs/groups-schedules.md](docs/groups-schedules.md) |
| Pasywne rozpoznanie (crt.sh, RDAP) | [docs/passive-discovery.md](docs/passive-discovery.md) |
| Role i uprawnienia, logowanie, MFA | [docs/rbac.md](docs/rbac.md), [docs/auth-mfa.md](docs/auth-mfa.md) |
| Szyfrowanie, model zagrożeń | [docs/encryption.md](docs/encryption.md), [docs/security.md](docs/security.md) |
| Eksploatacja, backup i odtworzenie | [docs/operations.md](docs/operations.md), [docs/backup-restore.md](docs/backup-restore.md) |
| Platformy (Linux, macOS, Windows; amd64, arm64) | [docs/local-platforms.md](docs/local-platforms.md) |
| Licencje, wykorzystanie AI, zgodność z regulaminem | [docs/ai-and-dependencies.md](docs/ai-and-dependencies.md) |
| Decyzja architektoniczna: httpx | [docs/adr-001-http-fingerprinting.md](docs/adr-001-http-fingerprinting.md) |

## Testy

```bash
docker compose exec -T api python manage.py test apps --settings=config.settings_test   # 97 testów
./scripts/smoke-test.sh                                                                  # test dymny instancji
./scripts/backup.sh && ./scripts/restore-test.sh                                         # backup i odtworzenie
```

## Struktura repozytorium

| Katalog | Zawartość |
|---|---|
| `backend/` | API Django, logika skanów, zadania Celery, testy |
| `web/` | frontend React/TypeScript (bundle powstaje wyłącznie w obrazie) |
| `signatures/` | sygnatury detekcyjne YAML |
| `schemas/` | schemat JSON formatu eksportu |
| `deploy/` | Dockerfile, konfiguracja nginx, cel demonstracyjny, ustawienia DefectDojo |
| `scripts/` | preflight, sekrety, test dymny, backup, diagnostyka DefectDojo |
| `demo/` | laboratorium demonstracyjne, nagranie i prezentacja |
| `docs/` | dokumentacja |

Sekretów, pliku `.env`, katalogów `node_modules/` i `dist/` ani lokalnych backupów nie commitujemy — pilnują tego `.gitignore` i `.dockerignore`.

## Zakres i ograniczenia

SurfaceX wykonuje wyłącznie rozpoznanie: nie loguje się do usług, nie zgaduje haseł, nie eksploatuje podatności i nie śledzi przekierowań. Skanuj tylko sieci, do których masz uprawnienia — zakres wymusza allowlista.

Prototyp powstał w 24 godziny i działa jako lokalny stos Docker Compose (bez wysokiej dostępności, bez Kubernetes). Konfiguracja domyślna jest przeznaczona do pracy lokalnej i w laboratorium. Pełna lista świadomych ograniczeń: [rozdział 16 dokumentacji technicznej](docs/dokumentacja-techniczna.md#16-znane-ograniczenia).
