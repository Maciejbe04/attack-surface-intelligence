# Laboratoria demonstracyjne SurfaceX

Trzy lokalne środowiska do testów i pokazu. Wszystkie usługi to atrapy (statyczne strony i banery, bez logowania i danych) w izolowanych sieciach Dockera. Kroki pokazu: [`docs/demo-script.md`](../docs/demo-script.md).

| Laboratorium | Uruchomienie | Do czego |
|---|---|---|
| `lab-target` | startuje razem ze stosem | pierwszy skan zaraz po instalacji |
| `demo/lab` | `./demo/lab/lab.sh up` | pełny pokaz: dwa skany, zmiany, role |
| `deploy/demo-lab` | `docker compose -f deploy/demo-lab/compose.yml up -d` | porty zmieniające się w czasie (`FLAKY`, `GONE`) |

## 1. `lab-target` — wbudowany cel

Usługa `lab-target` jest częścią `compose.yml` (sieć `scanner`, adres `172.30.0.10`): HTTP `80` i `8080`, TLS `443`, podstrony `/admin` i `/login`. Przy starcie API (`SEED_LAB_TARGET=1`) tworzy cele `lab-target.surfacex.local` i `172.30.0.10`, wpisy allowlisty oraz grupę **`lab-local`**. Podgląd z hosta: `http://127.0.0.1:18088`.

Użycie: zaznacz moduły na Dashboardzie i uruchom skan grupy `lab-local` w zakładce **Groups**.

## 2. `demo/lab` — sieć siedmiu hostów

```bash
./demo/lab/lab.sh up       # start laboratorium + podłączenie workera SurfaceX do sieci asi-lab
./demo/lab/lab.sh mutate   # zmiany między skanem 1 i 2
./demo/lab/lab.sh down     # usunięcie laboratorium
```

Sieć `asi-lab`, `10.77.0.0/24`. Wymaga działającego stosu SurfaceX i `openssl` (certyfikat testowy w `demo/lab/certs/`, poza Gitem).

| Adres | Usługa | Uwagi |
|---|---|---|
| `10.77.0.10` | strona wydziału (CMS) | WordPress, PHP 7.4.33, cookie `PHPSESSID` |
| `10.77.0.11` | panel administracyjny | przekierowanie do `/admin/` |
| `10.77.0.12` | środowisko staging | wersja 1 → po `mutate` wersja 2 i port `8443` |
| `10.77.0.13` | intranet HTTPS | certyfikat TLS, HSTS |
| `10.77.0.14` | kamera IP | „NetCam-2000” |
| `10.77.0.15` | serwer pomiarowy | wyłączany przez `mutate` |
| `10.77.0.16` | nowa aplikacja | uruchamiana przez `mutate` |

Przed skanem dodaj `10.77.0.0/24` do allowlisty i zaimportuj cele z [`lab/targets.csv`](lab/targets.csv) (albo [`lab/targets.json`](lab/targets.json)) — trafią do grupy „Lab demo”.

## 3. `deploy/demo-lab` — cel ze zmieniającymi się portami

Pojedynczy kontener, który co 90 s przechodzi do kolejnej fazy: otwiera i zamyka porty, zmienia banery, wersje, nagłówki i ciasteczka. Opis faz i sterowanie: [`deploy/demo-lab/README.md`](../deploy/demo-lab/README.md).

## Nagranie i prezentacja

| Plik | Rola |
|---|---|
| `record/run.sh` | resetuje dane, nagrywa przejście przez aplikację z napisami i renderuje prezentację (wymaga Node, Playwright i Google Chrome; zmienna `PW_DIR`) |
| `record/reset.sh` | **usuwa wszystkie dane skanów**, tworzy konta demonstracyjne i uruchamia `demo/lab` od fazy 1 — tylko dla środowiska demonstracyjnego |
| `record/demo.mjs` | scenariusz nagrania |
| `pitch/index.html`, `pitch/build.mjs` | slajdy prezentacji i ich eksport do PDF |

Wyniki nagrania trafiają do `demo/out/` (katalog poza Gitem).

## Laboratorium LXC zespołu (Proxmox)

Pliki [`targets.json`](targets.json) i [`allowlist.json`](allowlist.json) opisują trzy kontenery LXC w prywatnej sieci zespołu (`10.99.0.70–72`), używane podczas prac. To środowisko nie jest dostępne poza infrastrukturą zespołu; do samodzielnego odtworzenia pokazu służy `demo/lab`. Dane dostępowe do tych kontenerów nie są przechowywane w repozytorium.
