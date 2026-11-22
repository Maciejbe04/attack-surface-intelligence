# Plan MVP Attack Surface Intelligence

## Cel

System ma cyklicznie i bezpiecznie obserwować dużą infrastrukturę, wykrywać aktywne hosty oraz usługi, identyfikować technologie HTTP/HTTPS i pokazywać zmiany między kolejnymi skanami.

MVP obejmuje:

- import IP, CIDR i domen ręcznie oraz z CSV/JSON;
- import wyników skanów z CSV/JSON;
- obsługę ponad 10 000 adresów;
- harmonogramy, okna czasowe, ograniczanie tempa i wznawianie;
- wykrywanie hostów, portów i podstawowych usług;
- fingerprinting HTTP/HTTPS, TLS, CMS i technologii;
- deklaratywne, bezpieczne sygnatury;
- historię i porównywanie obserwacji;
- RBAC z czterema poziomami dostępu;
- trwałe ręczne edycje wyników;
- szyfrowanie danych wrażliwych;
- dashboard oraz eksport CSV/JSON;
- opcjonalną integrację z DefectDojo.

System służy wyłącznie do discovery. Nie wykonuje logowania, brute force ani prób wykorzystania podatności.

## Stos technologiczny

- Python / Django / Django REST Framework: API, uwierzytelnianie, RBAC i persystencja;
- Celery: scheduler, batche i workery skanujące;
- React/TypeScript: interfejs użytkownika;
- PostgreSQL: główne źródło prawdy;
- Redis: sesje, broker Celery i koordynacja zadań;
- Docker Compose: lokalne uruchamianie całego stosu;
- nmap: discovery i identyfikacja portów oraz usług;
- ProjectDiscovery httpx: wydajne sondowanie HTTP/HTTPS, TLS i wstępna detekcja technologii;
- własny silnik sygnatur w Pythonie: normalizacja evidence i obliczanie poziomu pewności.

Oficjalnie wspierane platformy:

- Linux `amd64`;
- Linux `arm64`;
- macOS Intel przez Docker Desktop;
- macOS Apple Silicon przez Docker Desktop;
- Windows 10/11 przez Docker Desktop z WSL2 i kontenerami Linux.

Szczegóły uruchomienia na hostach opisuje `docs/local-platforms.md`.

## Model danych i trwałe edycje

Podstawowe encje:

- `targets`;
- `scan_profiles`;
- `schedules`;
- `scan_runs`;
- `scan_attempts`;
- `scan_batches`;
- `observations`;
- `fingerprint_evidence`;
- `signatures`;
- `manual_overrides`;
- `users`;
- `roles`;
- `audit_log`.

Szczegóły relacji, kluczy i cyklu życia opisuje `docs/data-model.md`.

Surowa obserwacja skanera jest niemutowalna. Edycje użytkownika zapisują się jako osobny `manual_override`. Widok prezentowany użytkownikowi składa aktualną obserwację z ręcznym nadpisaniem, dlatego kolejny skan nie usuwa notatek, tagów ani korekt analityka.

Konfigurację można edytować podczas aktywnego skanu. Rozpoczęty przebieg korzysta z własnego snapshotu konfiguracji, a zmiany obowiązują od następnego przebiegu.

Import wyników korzysta z tego samego pipeline normalizacji i walidacji co wyniki workerów. Źródło obserwacji jest oznaczone jako `scanner` albo `import`.

## RBAC i uwierzytelnianie

System posiada cztery role:

- `admin`: użytkownicy, role, sekrety, konfiguracja oraz pełny dostęp;
- `operator`: dodawanie, usuwanie i modyfikacja celów, skanów i sygnatur;
- `analyst`: odczyt oraz edycja wyników, tagów, notatek i overrides;
- `viewer`: wyłącznie odczyt.

Uprawnienia są egzekwowane przez API, a nie tylko przez interfejs. Każda zmiana konfiguracji, wyniku, sygnatury lub roli trafia do `audit_log`.

Hasła są haszowane Argon2id. Losowe identyfikatory sesji są przechowywane w Redisie i przekazywane w cookie `HttpOnly`, `SameSite=Strict`. Flaga `Secure` jest wymagana przy HTTPS; lokalny profil bez TLS może ją wyłączyć wyłącznie w `local-dev`. Sesje mają czas bezczynności i maksymalny czas życia. Próby logowania są ograniczane tempem i audytowane. Szczegóły ról opisuje `docs/rbac.md`.

## Szyfrowanie danych

Wrażliwe dane są szyfrowane envelope encryption z AES-256-GCM. Dotyczy to:

- wartości cookies;
- surowych nagłówków;
- bannerów;
- treści evidence;
- ręcznych notatek;
- danych i tokenów integracji.

Jawne pozostają jedynie metadane wymagane do indeksowania, np. kod HTTP, nazwa technologii czy nazwa cookie bez wartości.

Zaszyfrowana wartość zawiera wersję klucza, nonce, ciphertext oraz tag. Rotacja klucza działa partiami bez zatrzymywania systemu. Klucze są montowane jako lokalne sekrety, nie trafiają do obrazu ani repozytorium.

Backup PostgreSQL jest szyfrowany osobnym kluczem i cyklicznie testowany przez odtworzenie do tymczasowej bazy. Listę pól i procedurę rotacji opisuje `docs/encryption.md`.

## Skanowanie, okna i estymacja

Scheduler:

1. rozwija CIDR i domeny;
2. waliduje oraz deduplikuje cele;
3. zapisuje snapshot konfiguracji;
4. dzieli zakres na idempotentne batche;
5. publikuje zadania do Redis;
6. śledzi postęp, deadline i checkpointy.

Każdy przebieg posiada `window_start` oraz `deadline`. Po zakończeniu okna scheduler zatrzymuje aktywne procesy, oznacza pozostałe batche jako `paused` i wznawia je w następnym oknie bez powtarzania ukończonej pracy.

nmap i httpx działają w osobnych grupach procesów. Najpierw otrzymują sygnał łagodnego zakończenia, a po upływie grace period są bezwarunkowo kończone. Wynik częściowy nie wpływa na status `MISSING` ani `GONE`.

ETA wykorzystuje EWMA przepustowości poprzednich batchy dla danego profilu skanu. Rozmiar batcha jest dynamiczny:

```text
zmierzone IP/s × pozostały czas × współczynnik bezpieczeństwa
```

Dashboard pokazuje czas trwania, postęp, prognozę zakończenia i informację, czy skan zmieści się w skonfigurowanym oknie.

## Bezpieczeństwo skanera

- Cele muszą należeć do zatwierdzonej allowlisty CIDR lub domen.
- Przed uruchomieniem użytkownik widzi liczbę rozwiniętych adresów.
- Obowiązują limity liczby IP, portów, równoległości i rozmiaru importu.
- Domeny są rozwiązywane przy każdym przebiegu.
- Każdy rozwiązany adres jest ponownie sprawdzany względem allowlisty bezpośrednio przed połączeniem.
- HTTP używa wyłącznie `HEAD` i `GET`.
- Ograniczone są przekierowania, rozmiar body i czas zapytania.
- Przekierowania poza zatwierdzony zakres nie są śledzone.
- Sygnatury mogą używać wyłącznie ścieżek względnych.
- Regexy mają limity czasu oraz długości wejścia.
- Worker nie otrzymuje socketu Dockera ani administracyjnych danych logowania do bazy.

Worker przy starcie testuje dostępność raw sockets. Na zgodnym Linuksie używa skanu SYN. Na Docker Desktop albo przy braku wymaganych możliwości automatycznie przechodzi na TCP connect scan. Użyty tryb jest zapisywany w metadanych przebiegu.

## Fingerprinting

Oficjalny pipeline fingerprintingu:

```text
nmap → endpointy HTTP(S) → httpx JSONL → własne sygnatury → evidence → confidence score
```

nmap wykrywa aktywne hosty, porty i podstawowe usługi. httpx otrzymuje wyłącznie endpointy HTTP/HTTPS znalezione podczas discovery i przetwarza je partiami, zamiast uruchamiać osobny proces dla każdego adresu.

httpx odpowiada za:

- status i tytuł HTTP;
- przekierowania;
- podstawowe nagłówki i nazwę serwera;
- informacje o certyfikacie TLS;
- favicon hash;
- wstępną detekcję technologii.

Własny moduł Pythona normalizuje JSONL z httpx, zbiera ograniczone dane wymagane przez customowe sygnatury i tworzy evidence dla:

- nagłówków;
- nazw cookies;
- ograniczone fragmenty HTML;
- bezpiecznych ścieżek, np. `/login`, `/admin` lub `/version`;
- wyników technologicznych zwróconych przez httpx.

httpx jest źródłem dowodów, a nie bezwarunkową prawdą. Każdy fingerprint przechodzi przez wspólny model confidence score. Nie używamy WhatWeb ani Nuclei jako obowiązkowego elementu MVP.

Wymagania operacyjne httpx:

- przypięta, jawnie udokumentowana wersja;
- uruchamianie wsadowe i strumieniowe przetwarzanie JSONL;
- wspólny rate limit oraz deadline profilu skanu;
- limit przekierowań, odpowiedzi i czasu;
- brak automatycznego rozszerzania celu poza allowlistę;
- zapis wersji narzędzia i użytych opcji w metadanych przebiegu.

### Dlaczego httpx zamiast WhatWeb

ProjectDiscovery httpx jest podstawowym narzędziem MVP, ponieważ:

- działa jako lekki, przypięty binarny CLI wywoływany z workera Celery;
- przetwarza duże listy endpointów współbieżnie;
- udostępnia strumieniowy JSONL łatwy do parsowania w Pythonie;
- ma wbudowaną kontrolę tempa, timeoutów i równoległości;
- buduje się natywnie dla `linux/amd64` i `linux/arm64` w obrazie workera;
- ma mniejszy narzut uruchomieniowy niż stos Ruby;
- dostarcza wystarczające dane HTTP/TLS i wstępne fingerprinty technologii.

Uwaga: ProjectDiscovery httpx to zewnętrzne CLI w obrazie workera. Nie mylić go z pakietem Pythona o nazwie `httpx`.

WhatWeb posiada rozbudowany system pluginów i może zapewnić głębsze rozpoznanie części CMS-ów lub starszych technologii, ale:

- ma większy koszt uruchomienia i pamięci;
- wymaga ostrożniejszego batchowania przy ponad 10 000 adresów;
- część trybów agresywności wykonuje dodatkowe żądania;
- pluginy są wykonywalnym kodem Ruby i nie mogą być bezpiecznym formatem sygnatur użytkownika;
- komplikuje wieloarchitekturowy obraz workera.

WhatWeb nie jest częścią obowiązkowego MVP. W przyszłości może działać jako wyłączony domyślnie drugi etap tylko dla ręcznie wybranych endpointów:

```text
wszystkie endpointy → httpx
wybrane endpointy → opcjonalny WhatWeb deep fingerprint
```

Jego wynik również musiałby zostać znormalizowany jako evidence i przejść przez wspólny confidence score. Szczegóły decyzji opisuje `docs/adr-001-http-fingerprinting.md`.

Każda detekcja przechowuje dowody i score `0–100`. Domyślne wagi:

- charakterystyczny nagłówek: `30`;
- nazwa cookie: `20`;
- favicon hash: `40`;
- fragment HTML: `20`;
- jednoznaczny banner lub stopka: `30`.

Zgodne i niezależne sygnały sumują się do maksymalnie 100. Pojedynczy słaby sygnał nie może uzyskać wysokiej pewności.

Poziomy:

- `low`: 1–39;
- `medium`: 40–69;
- `high`: 70–100.

Customowe sygnatury są deklaratywne i mogą sprawdzać nagłówek, nazwę cookie, fragment HTML, favicon hash, status dozwolonej ścieżki lub ograniczony regex wersji. Format YAML i przykłady opisuje `docs/signatures.md`. Politykę portów, flag httpx i limitów opisuje `docs/scanning-policy.md`.

## Historia i stany

Cykl życia jest liczony osobno dla:

- hosta;
- portu i usługi;
- endpointu HTTP;
- technologii;
- certyfikatu.

Zamknięcie pojedynczego portu nie oznacza zniknięcia hosta.

Stany:

- `NEW`: element pojawił się po raz pierwszy;
- `CHANGED`: zmienił się istotny atrybut;
- `MISSING`: pierwszy pełny pomiar bez odpowiedzi;
- `FLAKY`: odpowiedzi przeplatają się z poprawnymi brakami;
- `GONE`: domyślnie trzy kolejne pełne pomiary bez odpowiedzi.

Nieudany, anulowany lub częściowy skan nie obniża stanu obserwowanego elementu.

## Dashboard i integracje

Dashboard pokazuje:

- nowe, zmienione i znikające hosty oraz usługi;
- hosty niestabilne;
- wykryte technologie;
- certyfikaty zbliżające się do wygaśnięcia;
- wyniki customowych sygnatur;
- czas, ETA i postęp skanów.

Import i eksport CSV/JSON używa wersjonowanego schematu opisanego w `docs/import-export.md`. Wybrane obserwacje mogą być przesyłane do DefectDojo jako finding informacyjny z idempotency key i evidence.

## Lokalne uruchomienie i wiele architektur

`compose.yml` nie wymusza `linux/amd64`, nie używa `network_mode: host`, ścieżek właściwych dla pojedynczego systemu ani binariów kopiowanych z hosta.

Obrazy Django, Celery i frontendu budują się dla `TARGETOS/TARGETARCH`. Zależności Pythona pochodzą z wheels zgodnych z docelową architekturą; unikamy pakietów wymagających lokalnej kompilacji C, o ile to możliwe. Przypięta wersja ProjectDiscovery httpx jest budowana ze źródeł w wieloetapowym Dockerfile workera. Frontend buduje się do statycznych zasobów niezależnych od CPU.

`docker buildx bake` buduje obrazy `linux/amd64` i `linux/arm64`. Emulacja QEMU służy do walidacji, natomiast lokalnie uruchamiany jest natywny wariant.

Świeża instalacja wymaga jedynie:

- Git;
- Docker Engine z Compose albo Docker Desktop;
- udokumentowanej minimalnej ilości RAM i miejsca.

Nie wymaga lokalnej instalacji Pythona, Node.js, PostgreSQL, Redis, nmap ani httpx.

## Kryteria akceptacji

- Import ręczny, CSV i JSON obsługuje cele oraz wyniki.
- 10 000 adresów jest walidowane i kolejkowane bez blokowania interfejsu.
- Duplikaty są raportowane i pomijane.
- Edycje są dostępne podczas aktywnego skanu zgodnie z rolą.
- Manual override pozostaje po kolejnym skanie.
- Koniec okna nie pozostawia procesów potomnych.
- Ukończone batche nie są powtarzane po wznowieniu.
- Dashboard pokazuje czas, postęp i ETA.
- httpx przetwarza endpointy partiami, respektuje rate limit i generuje poprawnie normalizowany JSONL na obu architekturach.
- Nieudany pomiar nie powoduje `MISSING` ani `GONE`.
- Test obejmuje nowy host, usługę, zmianę technologii, zmianę certyfikatu, pojedynczy brak, `FLAKY` i `GONE`.
- Viewer nie wykonuje zapisu.
- Analyst nie zarządza celami ani harmonogramem.
- Operator nie zarządza użytkownikami.
- W bazie nie występują jawne wartości wrażliwych pól.
- Zaszyfrowany backup można poprawnie odtworzyć.
- Ten sam commit przechodzi smoke test na `linux/amd64` i `linux/arm64`.
- Smoke test obejmuje Docker Desktop na Windows (WSL2, kontenery Linux) dla `linux/amd64`.
- Demo wykonuje dwa przebiegi oraz eksport CSV/JSON.

## Plan realizacji

1. Utworzenie monorepo Django/Celery i wieloarchitekturowego Docker Compose.
2. Model PostgreSQL, migracje, logowanie, sesje i RBAC.
3. Formularze oraz import celów i wyników CSV/JSON.
4. Scheduler, kolejka, batche, checkpointy i okna czasowe.
5. Discovery nmap oraz wsadowy HTTP/TLS fingerprinting przez ProjectDiscovery httpx.
6. Deklaratywne sygnatury i score pewności.
7. Historia, diff oraz stany `NEW/CHANGED/MISSING/FLAKY/GONE`.
8. Dashboard, trwałe edycje i eksport.
9. Szyfrowanie, backup i rotacja kluczy.
10. Test ponad 10 000 adresów, demo, dokumentacja i prezentacja.

## Docelowa struktura repozytorium

```text
backend/
  manage.py
  config/
  apps/
    accounts/
    targets/
    scans/
    fingerprints/
    audit/
  services/
    crypto/
    diff/
    fingerprint/
    scanner/
workers/
  celery_app.py
web/
deploy/docker/
docs/
schemas/
signatures/
tests/lab/
demo/
scripts/
compose.yml
compose.demo.yml
docker-bake.hcl
```

## Dokumentacja

Dostępne:

- `README.md`: status projektu i indeks;
- `docs/mvp-plan.md`: zakres MVP i kryteria akceptacji;
- `docs/architecture.md`: komponenty, sieci i przepływ danych;
- `docs/data-model.md`: obserwacje, historia i overrides;
- `docs/scanning-policy.md`: porty, limity, nmap i httpx;
- `docs/signatures.md`: format własnych sygnatur;
- `docs/import-export.md`: wersjonowane formaty CSV/JSON;
- `docs/passive-discovery.md`: moduł crt.sh + RDAP;
- `docs/rbac.md`: macierz uprawnień;
- `docs/encryption.md`: pola, klucze i rotacja;
- `docs/demo-script.md`: demonstracja dwóch skanów;
- `docs/local-platforms.md`: Linux/macOS/Windows, amd64/arm64 i tryby nmap;
- `docs/auth-mfa.md`: logowanie i TOTP MFA;
- `docs/adr-001-http-fingerprinting.md`: wybór httpx.

Uzupełnione:

- `docs/api.md`: kontrakt endpointów;
- `docs/security.md`: threat model i ograniczenia;
- `docs/operations.md`: healthchecki i skalowanie workerów;
- `docs/backup-restore.md`: backup i procedura odtworzenia;
- `demo/`: cele labowe i skrypt jury.

Uzupełnione także:

- `scripts/preflight.sh`, `smoke-test.sh`, `backup.sh`, `restore-test.sh`.

Prezentacja jury (≤10 slajdów) jest poza repozytorium.
