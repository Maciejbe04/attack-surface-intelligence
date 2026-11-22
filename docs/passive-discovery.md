# Pasywne rozpoznanie (crt.sh + RDAP)

Bezkluczowe źródła Certificate Transparency i RDAP działają na dwa sposoby — **panel Targets** (ad-hoc) oraz **moduł skanu** `passive-discovery`. Żaden z nich nie dodaje automatycznie hostów do inventory ani nie omija allowlisty.

## Moduł skanu `passive-discovery`

Na Dashboardzie / w liście modułów zaznacz **Passive discovery** (samodzielnie albo razem z nmap/httpx — nie z `full-pipeline`).

W przebiegu worker dla każdego celu `domain`/`ip`:

1. odpytuje crt.sh (gdy `includeCrt` i domena) oraz RDAP (gdy `includeRdap`);
2. zapisuje wynik w payloadzie batcha `passive`;
3. normalizacja tworzy obserwację hosta `passive:{query}` z evidence `kind=passive` (RDAP + lista nazw CT).

CIDR jest pomijany z ostrzeżeniem. Awaria providera nie zabija batcha — trafia do `warnings` / `sources.*.error`. Moduł **nie** wchodzi automatycznie w `full-pipeline`.

## Panel Targets (ad-hoc)

1. `admin` / `operator` wpisuje domenę albo IP i klika **Discover**.
2. Panel pokazuje skrót RDAP oraz listę kandydatów (dla domeny: poddomeny z crt.sh; dla IP: sam adres zapytania).
3. Użytkownik zaznacza hosty i klika **Add selected targets**.
4. Każdy zapis idzie przez istniejące `POST /api/targets/` (allowlista, RBAC, audyt jak przy ręcznym dodaniu).

`viewer` i `analyst` nie widzą panelu (brak mutacji celów / discover).

## Źródła

| Źródło | Kiedy | Co zwraca |
|---|---|---|
| [crt.sh](https://crt.sh) | tylko domena | do 100 znormalizowanych nazw w zakresie zapytanej domeny (wildcardy → apex, deduplikacja, filtr poza domeną) |
| [rdap.org](https://rdap.org) | domena albo IP | skrót: `handle`, `name`, `country`, `network`, `asns`, `nameservers` (nameservery tylko dla domeny) |

Oba źródła są odpytywane równolegle. Awaria jednego nie blokuje drugiego (`sources.*.error` + wpis w `warnings`).

## Ograniczenia techniczne

- timeout HTTP 8 s, limit odpowiedzi 2 MiB, User-Agent `SurfaceX/… passive-discovery`;
- walidacja: IPv4/IPv6 albo FQDN (bez URL, bez `localhost`);
- wynik cache’owany w Redis na **15 minut** (klucz `passive-discovery:v1:{type}:{query}`);
- brak persistencji wyników discover w PostgreSQL — tylko to, co użytkownik zapisze jako target;
- publiczne providery mogą rate-limitować albo chwilowo zwracać błędy; SurfaceX nie omija limitów i nie przechowuje kluczy API.

## Uprawnienia i audyt

Discover: `admin` / `operator` (`POST /api/passive/discover/`). Akcja audytowana jako `passive.discover`.

Zapis hostów: jak CRUD celów — nadal obowiązuje allowlista przy późniejszym skanie.

## Poza zakresem

- brak auto-dodawania odkrytych subdomen do skanu / allowlisty;
- brak Shodan / SecurityTrails / innych płatnych API;
- brak osobnych tabel `passive_*`;
- brak bulk discover wielu domen naraz;
- brak włączenia pasywnego wewnątrz `full-pipeline`.

Kontrakt API: `docs/api.md`. Role: `docs/rbac.md`.
