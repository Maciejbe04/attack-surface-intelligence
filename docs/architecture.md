# Architektura

## Założenia

Attack Surface Intelligence jest uruchamiane lokalnie przez Docker Compose. Ten sam zestaw obrazów Linux obsługuje `linux/amd64` i `linux/arm64`, w tym Docker Desktop na macOS (Intel/Apple Silicon) oraz Windows 10/11 z WSL2. Szczegóły hostów opisuje `docs/local-platforms.md`.

System rozdziela warstwę zarządzającą od wykonania skanów. API nie uruchamia nmap bezpośrednio, a workery nie mają dostępu administracyjnego do PostgreSQL ani do środowiska kontenerowego.

```mermaid
flowchart TB
  User[Użytkownik lokalny]
  Targets[Dozwolone cele skanu]
  DefectDojo[Opcjonalny DefectDojo]
  SecretFiles[Pliki sekretów 0600]
  ImageManifest[Obrazy linux amd64 i arm64]

  subgraph localHost [Lokalny host Linux macOS lub Windows]
    subgraph composeRuntime [Docker Compose]
      subgraph edgeNet [Sieć edge]
        Gateway[Gateway TLS]
        Web[Frontend React]
      end

      subgraph backendNet [Sieć backend internal]
        API[API Django]
        Scheduler[Celery Beat scheduler]
        Queue[(Redis)]
        Database[(PostgreSQL)]
        Backup[Zadanie backupu]
      end

      subgraph scannerNet [Sieć scanner egress]
        Worker[Celery worker nmap httpx i sygnatury]
      end

      DatabaseVolume[(Wolumen danych)]
      BackupVolume[(Szyfrowany backup)]
    end
  end

  User --> Gateway
  Gateway --> Web
  Gateway --> API
  API --> Database
  API --> Queue
  Scheduler --> Database
  Scheduler --> Queue
  Queue --> Worker
  Worker --> Targets
  Worker -->|"wyniki i evidence"| API
  Database --> DatabaseVolume
  Backup --> Database
  Backup --> BackupVolume
  API -.-> DefectDojo
  SecretFiles --> API
  SecretFiles --> Database
  SecretFiles --> Worker
  ImageManifest --> composeRuntime
```

## Komponenty

### Gateway

Jedyny punkt wejścia wystawiony poza sieci Docker Compose. Terminuje TLS, serwuje frontend oraz przekazuje żądania API. Pozostałe usługi nie publikują portów na hoście.

### Frontend

Aplikacja React/TypeScript udostępniająca:

- dashboard;
- zarządzanie celami i konfiguracją skanów;
- import oraz eksport;
- podgląd historii i różnic;
- edycję wyników;
- zarządzanie sygnaturami;
- interfejs dostosowany do uprawnień użytkownika.

### API

Aplikacja Django / Django REST Framework odpowiadająca za:

- uwierzytelnianie i RBAC;
- walidację danych wejściowych;
- zarządzanie celami, profilami i harmonogramami;
- trwałe ręczne nadpisania;
- przyjmowanie wyników workerów;
- porównywanie obserwacji;
- eksport CSV/JSON i integrację DefectDojo;
- audyt zmian;
- migracje ORM i admin panel wyłącznie dla `admin`.

API jest jedynym komponentem zapisującym wyniki workerów do PostgreSQL.

### Scheduler

Celery Beat / zadania okresowe:

- wyznaczają terminy skanów;
- zapisują snapshot konfiguracji przebiegu;
- rozwijają i deduplikują cele;
- dzielą pracę na idempotentne batche;
- pilnują deadline okna;
- zatrzymują i wznawiają pracę;
- obliczają postęp oraz ETA.

Scheduler korzysta z tego samego obrazu co API, ale działa jako oddzielny proces Celery Beat w Compose.

### Redis

Redis przechowuje:

- kolejkę zadań;
- lease workerów;
- retry i informacje o zadaniach aktywnych;
- sesje użytkowników;
- krótkotrwałe blokady koordynacyjne.

Redis nie jest źródłem prawdy; trwałe statusy przebiegów i batchy znajdują się w PostgreSQL. Celery Beat uruchamia reconciler domyślnie co 60 sekund. Broker przechowuje identyfikator swojej bieżącej epoki, a API zapamiętuje go w PostgreSQL. Zmiana epoki po utracie danych Redis powoduje ponowne opublikowanie wszystkich aktywnych batchy; bez zmiany epoki odzyskiwane są tylko zadania `running` bez aktualizacji od co najmniej 10 minut oraz wcześniejsze nieudane publikacje naprawcze. Reconciler nadaje zadaniu nowy `delivery_id`, unieważniając stare komunikaty i blokując zapis wyniku przez nieaktualną kopię zadania. Progi i limit jednej iteracji można zmienić przez `SCAN_RECONCILE_INTERVAL_SECONDS`, `SCAN_RECONCILE_STALE_SECONDS` i `SCAN_RECONCILE_BATCH_LIMIT`.

### Worker

Proces Celery worker wykonuje:

- discovery nmap;
- identyfikację portów i usług;
- wsadowe sondowanie HTTP/HTTPS przez ProjectDiscovery httpx;
- analizę TLS i wstępną detekcję technologii z JSONL httpx;
- customowe sygnatury;
- normalizację evidence i obliczanie confidence score;
- bezpieczne zbieranie evidence.

Worker otrzymuje jedynie token umożliwiający pobieranie zadań i przesyłanie wyników. Nie posiada poświadczeń administracyjnych bazy ani dostępu do socketu Dockera. Zadania Celery są publikowane przez Redis; wynik trafia z powrotem do API HTTP, a nie przez bezpośredni zapis ORM z sieci `scanner`.

Na zgodnym Linuksie worker używa SYN scan. Na Docker Desktop lub bez raw sockets przechodzi na TCP connect scan. Tryb skanu jest zapisany przy wyniku. Domyślne profile portów, limity i flagi httpx opisuje `docs/scanning-policy.md`.

Pipeline workera:

```text
nmap → endpointy HTTP(S) → httpx JSONL → własne sygnatury → evidence → confidence score
```

httpx jest uruchamiany dla partii endpointów, a jego JSONL jest przetwarzany strumieniowo w Pythonie. Wersja narzędzia, użyte opcje i limity trafiają do metadanych przebiegu. Detekcje technologii są dowodami wejściowymi dla wspólnego modelu pewności, a nie bezwarunkowym wynikiem.

Własny moduł Pythona uzupełnia dane wymagane przez deklaratywne sygnatury, w szczególności nazwy cookies, ograniczone fragmenty HTML i dozwolone ścieżki. WhatWeb oraz Nuclei nie są obowiązkowymi elementami architektury MVP.

WhatWeb może zostać dodany w przyszłości jako opcjonalny, domyślnie wyłączony drugi etap dla ręcznie wybranych endpointów wymagających głębszej identyfikacji. Nie może działać dla całego zakresu bez osobnego limitu ruchu ani przyjmować pluginów dostarczonych przez użytkownika. Jego wyniki muszą zostać zapisane jako evidence i ocenione przez ten sam model pewności co wyniki httpx. Uzasadnienie wyboru opisuje `docs/adr-001-http-fingerprinting.md`.

### PostgreSQL

PostgreSQL przechowuje:

- konfigurację;
- snapshoty przebiegów;
- obserwacje;
- evidence;
- ręczne overrides;
- historię zmian;
- użytkowników i role;
- log audytowy.

Wrażliwe pola są szyfrowane przez aplikację AES-256-GCM przed zapisem.

### Backup

Oddzielne zadanie Compose tworzy szyfrowany backup PostgreSQL. Backup trafia do osobnego wolumenu lub wskazanego katalogu lokalnego. Skrypt testowy odtwarza go do tymczasowej bazy i wykonuje migracje oraz zapytanie kontrolne.

## Sieci

### `edge`

Łączy gateway z frontendem. Gateway posiada również kontrolowane połączenie z API.

### `backend`

Sieć oznaczona jako `internal`, przeznaczona dla API, schedulera, Redis, PostgreSQL i zadania backupu. PostgreSQL i Redis nie są publikowane na hoście.

### `scanner`

Sieć z kontrolowanym wyjściem do dozwolonych celów. Podłączone są do niej wyłącznie workery. API, frontend, Redis i PostgreSQL nie mają dostępu do sieci skanowanej.

## Przepływ skanu

1. Operator dodaje cele i konfigurację.
2. API waliduje dane i zapisuje je w PostgreSQL.
3. Scheduler tworzy snapshot przebiegu i batche.
4. Batche trafiają do Redis.
5. Worker pobiera zadanie i ponownie waliduje cel.
6. Worker uruchamia nmap, przekazuje wykryte endpointy HTTP/HTTPS do httpx i wykonuje własne sygnatury.
7. Wynik wraz z evidence trafia do wewnętrznego API.
8. API normalizuje i szyfruje dane wrażliwe.
9. Silnik różnic porównuje obserwację z poprzednim pełnym przebiegiem.
10. Dashboard pokazuje wynik, stan i poziom pewności.

## Separacja bezpieczeństwa

- Gateway jest jedyną usługą wystawioną na hoście.
- PostgreSQL i Redis działają wyłącznie w sieci wewnętrznej.
- Worker jest jedynym komponentem z wyjściem skanującym.
- Tylko worker może otrzymać `NET_RAW`.
- `NET_ADMIN` jest wyłączone, dopóki konkretny test nie wykaże konieczności.
- Żadna usługa nie montuje socketu Dockera.
- Kontenery używają `no-new-privileges`, limitów procesów oraz read-only filesystem tam, gdzie to możliwe.
- Sekrety są montowane z lokalnych plików `0600`.

## Wieloarchitekturowość

Własne obrazy są budowane przez `docker buildx bake` dla:

- `linux/amd64`;
- `linux/arm64`.

Obrazy Pythona/Django budują się dla `TARGETOS/TARGETARCH` z wheels bez zbędnej kompilacji natywnej. nmap pochodzi z repozytorium pakietów obrazu bazowego dla właściwej architektury. Przypięta wersja ProjectDiscovery httpx jest budowana ze źródeł dla docelowej architektury w wieloetapowym Dockerfile workera. Frontend jest zestawem statycznych plików niezależnych od CPU.

Ten sam commit musi przejść build, migracje, healthcheck, logowanie, import, testowy skan i eksport na obu architekturach.

## Ograniczenia MVP

- Docker Compose nie zapewnia wysokiej dostępności.
- Awaria lokalnego hosta zatrzymuje wszystkie usługi.
- Redis i PostgreSQL działają jako pojedyncze instancje.
- Docker Desktop na macOS i Windows nie zapewnia identycznej semantyki sieci jak natywny Linux, dlatego worker wykorzystuje TCP connect scan.
- Windows jest wspierany wyłącznie przez Docker Desktop + WSL2 i kontenery Linux; Windows Containers są poza zakresem.
- DefectDojo pozostaje integracją opcjonalną.

Ograniczenia są akceptowalne dla lokalnego prototypu konkursowego i muszą być jawnie opisane podczas demonstracji.
