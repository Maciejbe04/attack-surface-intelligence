# Scenariusz demonstracyjny

**Cel:** w kilkanaście minut pokazać dwa pełne przebiegi skanu, wykryte zmiany, trwałą edycję znaleziska, eksport, role i DefectDojo. Scenariusz jest powtarzalny i działa w całości lokalnie, na laboratorium z repozytorium ([`demo/README.md`](../demo/README.md)).

## Wymagania

- działający stos SurfaceX z profilem DefectDojo (`docker compose up --build -d`, `./scripts/smoke-test.sh` → `smoke PASSED`);
- `openssl` na hoście (skrypt laboratorium generuje certyfikat testowy);
- konto `admin` / `changeme`.

## Przygotowanie

```bash
./demo/lab/lab.sh up
```

Skrypt uruchamia sześć kontenerów w izolowanej sieci `asi-lab` (`10.77.0.0/24`) i podłącza do niej worker SurfaceX.

| Adres | Co udaje | Na co zwrócić uwagę |
|---|---|---|
| `10.77.0.10` | strona wydziału (CMS) | WordPress, `X-Powered-By: PHP/7.4.33`, cookie `PHPSESSID`, `/wp-login.php` |
| `10.77.0.11` | panel administracyjny | przekierowanie `302` do `/admin/`, tytuł „Admin Panel – Login” |
| `10.77.0.12` | środowisko staging | nagłówki `X-Environment: staging`, `X-App-Version` |
| `10.77.0.13` | intranet HTTPS | certyfikat TLS, HSTS, przekierowanie z HTTP na HTTPS |
| `10.77.0.14` | kamera IP | tytuł „NetCam-2000 IP Camera”, `X-Powered-By: Express` |
| `10.77.0.15` | serwer pomiarowy (niestabilny) | porty 80 i 8080; zniknie przed drugim skanem |
| `10.77.0.16` | nowa aplikacja | pojawi się dopiero przed drugim skanem |

Opcjonalnie utwórz konta demonstracyjne `operator`, `analityk` (rola `analyst`) i `audytor` (rola `viewer`) w zakładce **Users** — będą potrzebne w kroku o rolach.

## Przebieg 1

1. Zaloguj się jako `admin` na http://localhost:8080.
2. **Allowlist** → dodaj `10.77.0.0/24`. Bez tego wpisu import i skan odrzucą adresy laboratorium.
3. **Dashboard** → zaznacz moduł `full-pipeline` (albo zestaw: port scan, service detection, HTTP fingerprint, TLS certificate, custom signatures). Zapamiętaj wybór — drugi skan musi użyć tych samych modułów.
4. **Targets** → **Import hosts** → wgraj [`demo/lab/targets.csv`](../demo/lab/targets.csv). Siedem hostów trafia do grupy „Lab demo”, każdy z komentarzem.
5. **Groups** → przy grupie „Lab demo” kliknij **Scan now**. Opcjonalnie pokaż **Edit schedule** (np. codziennie o 02:00 UTC).
6. W konsoli aktywności wskaż: osobny batch na każdy host, linię poleceń nmap (tryb `syn` albo `connect`, `--max-rate`), postęp i ETA.

Po zakończeniu (**Scans** → **Findings**):

- wszystkie obserwacje mają stan `NEW`;
- kolumna **Curiosity** wyróżnia porty wymagające uwagi;
- tytuły zdradzają staging, kamerę IP i panel administracyjny;
- technologie: WordPress, PHP 7.4.33, nginx; sygnatura `wordpress-core`;
- ciekawe nagłówki (`X-Powered-By`, `X-Environment`, `X-App-Version`) i cookie `PHPSESSID` z flagami;
- **Dashboard**: sekcja **Curiosity** z pozycją „Admin / login / staging hints”.

Następnie:

7. Przy technologii PHP kliknij **Add override**, dodaj tag i notatkę (np. „PHP 7.4 bez wsparcia — do wymiany”), zapisz.
8. Pobierz **Export JSON** i **Export CSV**.
9. Otwórz DefectDojo (http://localhost:8081) i pokaż findings w produkcie „Attack Surface”.

## Zmiana środowiska

```bash
./demo/lab/lab.sh mutate
```

Skrypt wyłącza serwer pomiarowy (`10.77.0.15`), podmienia staging na wersję 2 (inny tytuł i nagłówki, dodatkowy port `8443`) i uruchamia nową aplikację (`10.77.0.16`).

## Przebieg 2

1. **Groups** → „Lab demo” → **Scan now** (te same moduły co w przebiegu 1).
2. **Scans** → **Findings** drugiego przebiegu:
   - `NEW` — host `10.77.0.16` z usługą HTTP oraz port `8443` na stagingu;
   - `CHANGED` — staging: tytuł „Staging – Portal Studenta v2.4.0-rc1 (DEBUG)” i zmienione nagłówki;
   - `MISSING` — usługi serwera pomiarowego `10.77.0.15` (porty 80 i 8080, strona HTTP);
   - notatka przy PHP z przebiegu 1 jest nadal widoczna.
3. **Compare** → zestawienie dodanych, usuniętych i zmienionych obserwacji z wartościami przed i po.
4. **Dashboard** → **Changes over time** pokazuje słupki zmian.

Opcjonalnie trzeci i czwarty skan bez zmian w laboratorium: `10.77.0.15` przechodzi kolejno w `FLAKY` i `GONE`. Jeśli wcześniej przywrócisz serwer (`docker compose -f demo/lab/compose.yml start flaky`), wróci ze stanem `FLAKY`.

## Role

1. Zaloguj się jako użytkownik z rolą `viewer`: brak formularzy, przycisków skanu i edycji.
2. Pokaż odmowę w API:

   ```bash
   curl -s -c /tmp/sx.txt -H 'Content-Type: application/json' \
     -d '{"username":"audytor","password":"<hasło>"}' http://localhost:8080/api/auth/login/
   curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/sx.txt -X POST \
     -H 'Content-Type: application/json' -d '{}' http://localhost:8080/api/scans/
   # oczekiwane: 403
   ```

3. Rola `analyst` może dodać korektę i wyeksportować wyniki, ale nie uruchomi skanu (`403`).
4. Jako `admin` otwórz **System** → dziennik audytu: import, start skanów, eksporty, korekta.

## Okno skanu (opcjonalnie)

Jako `admin` ustaw **Scan window** na 30 minut i uruchom skan większej grupy. Po przekroczeniu okna niedokończone batche przechodzą w `PAUSED`, worker kończy procesy nmap/httpx, a przy przebiegu pojawia się **Resume**, które dokańcza tylko wstrzymane batche.

## Kryteria sukcesu

- dwa ukończone skany tej samej grupy;
- widoczne `NEW`, `CHANGED` i `MISSING`;
- korekta z przebiegu 1 zachowana w przebiegu 2;
- eksport JSON i CSV pobrany;
- findings widoczne w DefectDojo;
- rola `viewer` bez możliwości zmiany danych.

## Sprzątanie

```bash
./demo/lab/lab.sh down
```

Dane skanów pozostają w bazie. Skrypt `demo/record/reset.sh` przywraca stan początkowy do nagrania — **usuwa wszystkie cele, grupy, skany, wyniki, allowlistę i dziennik audytu**, dlatego nadaje się wyłącznie do środowiska demonstracyjnego.
