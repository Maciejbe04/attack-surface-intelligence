# Polityka skanowania

## Zasady ogólne

System wykonuje wyłącznie discovery. Dozwolone są:

- ping / host discovery;
- skan portów TCP;
- identyfikacja usług przez nmap;
- bezpieczne `HEAD` i `GET` HTTP/HTTPS;
- odczyt certyfikatu TLS;
- deklaratywne sprawdzenia sygnatur na dozwolonych ścieżkach;
- pasywne rozpoznanie (crt.sh / RDAP) jako moduł `passive-discovery` — bez auto-expand inventory; szczegóły: `docs/passive-discovery.md`.

Zabronione są logowanie, brute force, fuzzing agresywny, eksploatacja podatności oraz śledzenie przekierowań poza allowlistę.

## Host discovery

Host jest uznawany za żywy, gdy spełniony jest co najmniej jeden warunek:

1. odpowiedź ICMP echo, albo
2. otwarty port z profilu discovery.

Brak odpowiedzi ICMP przy otwartym porcie nie oznacza hosta martwego. Brak obu sygnałów w pełnym pomiarze może prowadzić do `MISSING`, a potem `FLAKY` / `GONE`.

## Profile portów nmap

### `discovery-fast` (domyślny)

Szybki przegląd typowych usług:

```text
21,22,23,25,53,80,110,111,135,139,143,443,445,465,587,993,995,
1433,1521,2049,3306,3389,5432,5900,6379,8000,8080,8443,8888,9200,27017
```

### `discovery-web`

Skupiony na HTTP/HTTPS:

```text
80,443,8000,8080,8443,8888,3000,5000,7001,9000,9443
```

### `discovery-full`

Top 1000 portów nmap. Dozwolony tylko dla mniejszych zakresów albo poza szczytem obciążenia.

### Version detection

`-sV` uruchamiane jest wyłącznie dla otwartych portów po pierwszym przebiegu discovery. Nie stosuje się pełnego `-A` ani skryptów NSE wykraczających poza bezpieczną identyfikację usługi.

## Tryb skanu TCP

| Środowisko | Tryb | Uwagi |
|---|---|---|
| Linux z `NET_RAW` | SYN (`-sS`) | preferowany |
| Docker Desktop (macOS/Windows) / brak raw sockets | TCP connect (`-sT`) | automatyczny fallback |

Użyty tryb trafia do metadanych `scan_run`.

## httpx

Przypięta wersja MVP: `v1.6.9` (do potwierdzenia przy implementacji Dockerfile).

httpx otrzymuje wyłącznie endpointy HTTP/HTTPS wykryte przez nmap, na przykład:

```text
http://10.0.0.10:80
https://10.0.0.10:443
http://app.example.lab:8080
```

Przykładowe flagi bazowe:

```bash
httpx -l endpoints.txt \
  -silent \
  -json \
  -status-code \
  -title \
  -server \
  -tech-detect \
  -favicon \
  -tls-grab \
  -follow-redirects \
  -max-redirects 3 \
  -timeout 5 \
  -retries 1 \
  -rate-limit 50 \
  -threads 50
```

Ograniczenia:

- body maksymalnie 64 KiB do analizy sygnatur;
- brak automatycznego rozszerzania zakresu poza allowlistę;
- wspólny rate limit i deadline profilu skanu;
- wersja i pełna lista flag zapisane w metadanych przebiegu.

## Limity domyślne

| Parametr | Wartość |
|---|---|
| Maksymalna liczba IP po rozwinięciu | 50 000 |
| Ostrzeżenie przed startem | > 10 000 IP |
| Rozmiar batcha startowego | 256 IP |
| Równoległe workery | 2 |
| Równoległe procesy nmap na worker | 1 |
| HTTP requests / s / worker | 50 |
| Timeout HTTP | 5 s |
| Maksymalny import CSV/JSON | 20 MiB |
| Maksymalna liczba przekierowań | 3 |
| Grace period stop procesów | 15 s |

## Allowlista i DNS

1. Cel musi należeć do zatwierdzonej allowlisty CIDR lub domen.
2. Przed startem użytkownik widzi liczbę rozwiniętych adresów.
3. Domeny są rozwiązywane przy każdym przebiegu.
4. Każdy rozwiązany adres jest ponownie sprawdzany względem allowlisty bezpośrednio przed połączeniem.
5. Adres poza allowlistą jest odrzucany i audytowany.

## Okna czasowe

Każdy `scan_run` ma obowiązkowe `window_seconds` i `deadline_at`. Brak wartości w żądaniu stosuje `SCAN_DEFAULT_WINDOW_SECONDS` (domyślnie 3600 s).

- role inne niż `admin`: stałe 1 h w UI, maksymalnie 3600 s w API;
- `admin`: wybór 30 min, 1 h albo 2 h w UI; API dopuszcza do 86 400 s;
- te same ograniczenia obowiązują skan hostów, skan grupy oraz Resume.

Po deadline:

1. scheduler wysyła sygnał łagodnego zakończenia do nmap i httpx;
2. po grace period kończy procesy bezwarunkowo;
3. niedokończone batche otrzymują status `paused`;
4. wznowienie nie powtarza ukończonych batchy;
5. wynik częściowy nie obniża stanu do `MISSING` ani `GONE`.

## Kryteria pełnego pomiaru

Pomiar jest pełny tylko wtedy, gdy:

- batch został ukończony bez anulowania;
- nmap zakończył się kodem sukcesu albo kontrolowanym brakiem hostów;
- httpx zakończył partię albo nie było endpointów HTTP;
- wynik został przyjęty przez API.

Nieudany, anulowany lub częściowy przebieg nie zmienia statusu życiowego obserwacji.
