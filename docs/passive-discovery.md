# Pasywne rozpoznanie (crt.sh + RDAP)

Bezkluczowy moduł skanu `passive-discovery`: Certificate Transparency i RDAP dla zapisanych celów w przebiegu. **Nie** dodaje automatycznie hostów do inventory i **nie** omija allowlisty.

## Moduł skanu `passive-discovery`

Na Dashboardzie / w liście modułów zaznacz **Passive discovery** (samodzielnie albo razem z nmap/httpx — nie z `full-pipeline`).

W przebiegu worker dla każdego celu `domain`/`ip`:

1. odpytuje crt.sh (gdy `includeCrt` i domena) oraz RDAP (gdy `includeRdap`);
2. zapisuje wynik w payloadzie batcha `passive`;
3. normalizacja tworzy obserwację hosta `passive:{query}` z evidence `kind=passive` (RDAP + lista nazw CT).

CIDR jest pomijany z ostrzeżeniem. Awaria providera nie zabija batcha — trafia do `warnings` / `sources.*.error`. Moduł **nie** wchodzi automatycznie w `full-pipeline`.

Opcjonalnie dostępne jest też `POST /api/passive/discover/` (admin/operator) do ad-hoc lookup bez skanu — UI go nie eksponuje.

## Źródła

| Źródło | Kiedy | Co zwraca |
|---|---|---|
| [crt.sh](https://crt.sh) | tylko domena | do 100 znormalizowanych nazw w zakresie zapytanej domeny (wildcardy → apex, deduplikacja, filtr poza domeną) |
| [rdap.org](https://rdap.org) | domena albo IP | skrót: `handle`, `name`, `country`, `network`, `asns`, `nameservers` (nameservery tylko dla domeny) |

Oba źródła są odpytywane równolegle. Awaria jednego nie blokuje drugiego.

## Ograniczenia techniczne

- timeout HTTP 8 s, limit odpowiedzi 2 MiB, User-Agent `SurfaceX/… passive-discovery`;
- walidacja: IPv4/IPv6 albo FQDN (bez URL, bez `localhost`);
- wynik ad-hoc API cache’owany w Redis na **15 minut**;
- publiczne providery mogą rate-limitować; SurfaceX nie omija limitów i nie przechowuje kluczy API.

## Uprawnienia i audyt

Moduł: jak start skanu (`admin` / `operator`). Ad-hoc API: `passive.discover` w audycie.

## SurfaceX vs DefectDojo

Wynik pasywny trafia wyłącznie do Findings / obserwacji w SurfaceX (`passive:{query}`). Eksport DefectDojo **nie** wysyła CRT/RDAP — buduje findings tylko z aktywnego discovery (host/port/http/tech). Skan wyłącznie pasywny kończy auto-export jako `SKIPPED`.

## Poza zakresem

- brak panelu Discover na Targets;
- brak auto-dodawania odkrytych subdomen do skanu / allowlisty;
- brak Shodan / SecurityTrails / innych płatnych API;
- brak osobnych tabel `passive_*`;
- brak bulk discover wielu domen naraz;
- brak włączenia pasywnego wewnątrz `full-pipeline`;
- brak pushu pasywnych findings do DefectDojo.

Kontrakt API: `docs/api.md`. Role: `docs/rbac.md`.
