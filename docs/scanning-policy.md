# Polityka skanowania

## Zasady ogólne

System wykonuje wyłącznie discovery. Dozwolone są:

- wykrywanie aktywnych hostów (ICMP echo, TCP SYN ping);
- skan portów TCP;
- identyfikacja usług przez nmap `-sV`;
- pojedyncze żądania `GET` HTTP/HTTPS do wykrytych endpointów, pobranie favicony;
- odczyt certyfikatu TLS;
- dopasowanie deklaratywnych sygnatur do zebranych odpowiedzi;
- pasywne rozpoznanie (crt.sh / RDAP) jako moduł `passive-discovery` — bez automatycznego rozszerzania listy celów ([passive-discovery.md](passive-discovery.md)).

Skaner nie loguje się do usług, nie wysyła formularzy, nie stosuje brute force ani fuzzingu, nie eksploatuje podatności, nie używa `nmap -A` ani skryptów NSE i **nie śledzi przekierowań**.

## Wykrywanie hostów

| Tryb | Polecenie | Kiedy |
|---|---|---|
| Sam host discovery | `nmap -sn -PE -PS80,443 --host-timeout <N>s` | wybrany tylko moduł `host-discovery`; metoda `icmp`, `tcp` albo `icmp-tcp`, porty i timeout z filtrów |
| Skan portów | `nmap -Pn -sS\|-sT -p <porty> …` | moduły `port-scan`, `service-detect`, `full-pipeline` |

W fazie skanu portów nmap działa z `-Pn`, żeby nie pominąć hostów blokujących ICMP. Brak odpowiedzi w pełnym przebiegu prowadzi do stanu `MISSING`, a w kolejnych do `FLAKY` i `GONE` ([data-model.md](data-model.md)).

## Profile portów

### `discovery-fast` (domyślny)

```text
21,22,23,25,53,80,110,111,135,139,143,443,445,465,587,993,995,
1433,1521,2049,3306,3389,5432,5900,6379,8000,8080,8443,8888,9200,27017
```

### `discovery-web`

```text
80,443,3000,5000,7001,8000,8080,8443,8888,9000,9443
```

### `discovery-full`

Top 1000 portów nmap (`--top-ports 1000`). Dostępny w module `port-scan`; zalecany dla pojedynczych hostów i małych zakresów.

### `custom`

Lista do 1000 unikalnych portów podana przez użytkownika.

### Porty IoT/OT (`includeIoT`)

Opcja modułu `port-scan` dołącza do wybranego profilu:

```text
23,80,102,443,502,554,1883,2222,8000,8554,8883,9100,20000,37777,44818,47808,49152
```

## Polecenie nmap

```bash
nmap -Pn -sS -p <porty> -T3 --max-rate 200 -sV --version-intensity 5 --max-retries 1 -oX - <cel>
```

- `-sV` jest dodawane tylko wtedy, gdy wybrano `service-detect` lub `full-pipeline`;
- dla IPv6 dodawane jest `-6`;
- wynik XML jest parsowany w workerze; zapisywane są wyłącznie porty w stanie `open`.

## Tryb skanu TCP

| Środowisko | Tryb | Uwagi |
|---|---|---|
| Linux z działającym `NET_RAW` | SYN (`-sS`) | preferowany |
| Docker Desktop (macOS/Windows) lub brak raw sockets | TCP connect (`-sT`) | automatyczny fallback |

Worker sprawdza dostępność raw socket przed każdym batchem. Użyty tryb jest zapisany w `ScanBatch.result.metadata.scan_mode` i widoczny w konsoli aktywności.

## httpx

Wersja przypięta w obrazie workera: `v1.6.9` (`HTTPX_VERSION`), budowana ze źródeł.

httpx dostaje wyłącznie endpointy zbudowane z otwartych portów wykrytych przez nmap (porty WWW lub usługi rozpoznane jako HTTP/HTTPS), np. `http://10.0.0.10:80`, `https://10.0.0.10:443`. Gdy nmap nie jest uruchamiany (same moduły HTTP/TLS/sygnatur), sondowane są porty z filtrów modułu; dla zakresów CIDR taki skan nie generuje endpointów.

```bash
httpx -silent -json -status-code -title -server \
  -timeout 5 -retries 1 -rate-limit 50 -threads 50 \
  -include-response-header -favicon -include-response \
  -tech-detect -tls-grab
```

- `-tech-detect` zależy od filtra `techDetect` (domyślnie włączony w `full-pipeline`), `-tls-grab` od modułu `tls-cert` lub opcji `includeTls`;
- flaga `-follow-redirects` **nie jest używana**: odpowiedź `3xx` i nagłówek `Location` są zapisywane, ale skaner nie podąża dalej, bo adres docelowy mógłby leżeć poza allowlistą. Filtry `followRedirects` i `maxRedirects` modułu `http-fingerprint` są ignorowane;
- do bazy trafia skrócony rekord: bez pełnej treści odpowiedzi, z fragmentem body do 4000 znaków; sygnatury analizują do 64 KiB treści.

## Limity

Sufity są twarde — obowiązują niezależnie od wartości wpisanej w UI lub wysłanej do API (`runner.py`).

| Parametr | Domyślnie | Zakres w UI | Sufit |
|---|---|---|---|
| nmap `--max-rate` (pakiety/s) | 200 | 10–5000 | `SCAN_MAX_RATE_CEILING` = 1000 |
| nmap szablon czasowy | `T3` | `T2`–`T4` | `T4` → `T3`, chyba że `SCAN_ALLOW_AGGRESSIVE_TIMING=1` |
| nmap `--version-intensity` | 5 | 0–9 | `SCAN_VERSION_INTENSITY_CEILING` = 7 |
| nmap `--max-retries` | 1 | — | stałe |
| httpx `-rate-limit` (żądania/s) | 50 | 1–500 | `SCAN_HTTPX_RATE_CEILING` = 150 |
| httpx `-threads` | min(50, tempo) | — | `SCAN_HTTPX_THREADS_CEILING` = 50 |
| httpx `-timeout` | 5 s | 1–30 s | — |
| Czas jednego uruchomienia nmap lub httpx | 180 s | — | stały |
| Rozmiar wyjścia narzędzia | 2 MiB | — | stały |
| Rozmiar wyniku batcha | 1,8 MiB | — | stały |
| Obserwacje / endpointy na batch | 2000 | — | stałe |
| Zakres CIDR jednego celu | — | — | 4096 adresów |
| Cele w jednym skanie, grupie, imporcie | — | — | 10 000 |
| Plik importu celów | — | — | 5 MiB |
| Równoległe batche na kontener workera | 2 (`WORKER_CONCURRENCY`) | — | skalowanie: `--scale worker=N` |

Przekroczenie limitu czasu lub rozmiaru kończy batch błędem; pozostałe batche działają dalej. Limit 180 s oznacza, że przy skanie portów pojedynczy cel nie powinien być większy niż `/24` — większe zakresy należy podać jako listę podsieci.

## Allowlista i DNS

1. Allowlista jest globalna: wpisy IP, CIDR i domen (domena obejmuje subdomeny) obowiązują każdego użytkownika.
2. Cel jest sprawdzany przy zapisie, przy imporcie, przy starcie skanu i ponownie, gdy worker pobiera batch.
3. Domena dodana do allowlisty autoryzuje tę nazwę. Ustawienie `SCAN_ALLOWLIST_ENFORCE_RESOLVED_IP=1` wymaga dodatkowo, by adres IP rozwiązany z domeny mieścił się w zatwierdzonych zakresach IP/CIDR.
4. Cel spoza allowlisty jest odrzucany, a batch kończy się błędem z opisem.
5. Pusta allowlista (brak aktywnych wpisów) nie ogranicza zakresu.

## Okna czasowe

Każdy przebieg ma obowiązkowe `window_seconds` i `deadline_at`. Brak wartości w żądaniu oznacza `SCAN_DEFAULT_WINDOW_SECONDS` (domyślnie 3600 s).

- role inne niż `admin`: stałe 1 h w UI, najwyżej 3600 s w API;
- `admin`: 30 min, 1 h albo 2 h w UI; API dopuszcza do 86 400 s;
- te same ograniczenia obowiązują skan hostów, skan grupy oraz Resume.

Po `deadline_at`:

1. niedokończone batche dostają status `paused` (stosują to: reconciler co 60 s oraz każde zapytanie workera o postęp lub anulowanie);
2. worker odpytuje API co 2 s i po sygnale wysyła SIGTERM do grupy procesów nmap/httpx, a po 5 s SIGKILL;
3. spóźniony wynik wstrzymanego batcha jest odrzucany (HTTP 409);
4. przebieg otrzymuje status `partial` i można go wznowić — **Resume** kolejkuje tylko wstrzymane batche;
5. przebieg częściowy nie obniża stanów do `MISSING` ani `GONE`.

Automatyczne wznowienie w następnym oknie nie jest zaimplementowane; cykliczność zapewnia harmonogram grupy, który w kolejnym terminie uruchamia nowy przebieg ([groups-schedules.md](groups-schedules.md)).

## Kryteria pełnego pomiaru

Przebieg jest pełny (`completed`) tylko wtedy, gdy wszystkie batche zakończyły się sukcesem i ich wyniki zostały przyjęte przez API. Przebieg nieudany, anulowany lub częściowy nie zmienia stanów obserwacji nieobecnych.
