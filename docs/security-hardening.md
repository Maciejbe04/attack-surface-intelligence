# Utwardzenie: limity skanowania i logowania

Zmiany z gałęzi `feature/security-hardening`. Wszystkie są aktywne od razu i nie wymagają konfiguracji. Wartości domyślne są bezpieczne.

## 1. Globalny limit tempa skanowania

Wcześniej każdy skan mógł ustawić `maxRate` do 5000 pakietów/s, a dwa workery skanowały równolegle bez wspólnego limitu.

Teraz `apps/scans/runner.py` (`ScanLimits`) przycina każde wywołanie do części limitu całkowitego:

| Ustawienie (`.env`) | Domyślnie | Znaczenie |
|---|---|---|
| `SCAN_MAX_RATE_TOTAL` | 300 | pakiety/s nmapa dla całego skanera |
| `SCAN_HTTP_RATE_TOTAL` | 100 | żądania/s httpx dla całego skanera |
| `SCAN_WORKER_SLOTS` | `WORKER_CONCURRENCY` | liczba procesów, które mogą skanować naraz (we wszystkich kontenerach workera) |

Każdy proces dostaje `limit / sloty`. Przy wartościach domyślnych to 150 pakietów/s i 50 żądań/s, więc równoległe paczki razem nigdy nie przekroczą limitu.

- Wartość z UI jest używana, gdy jest niższa od limitu.
- Limit obejmuje też samo wykrywanie hostów (`-sn`), które wcześniej nie miało `--max-rate`.
- Liczba wątków httpx jest dopasowana do limitu.
- Faktycznie użyte limity są zapisywane w wyniku (`metadata.limits`), żeby było widać, z jakim tempem skanowaliśmy.

Przy skalowaniu workerów (`docker compose up --scale worker=3`) ustaw `SCAN_WORKER_SLOTS` na łączną liczbę procesów, na przykład `3 × WORKER_CONCURRENCY`.

## 2. Budżet czasu paczki

Wcześniej nmap i httpx dostawały po 180 s, a Celery zabija zadanie po 300 s (miękki limit 270 s). Paczka mogła zostać przerwana w połowie bez raportu.

Teraz:
- **Wspólny budżet:** wszystkie polecenia jednej paczki mieszczą się w `SCAN_BATCH_TIME_BUDGET`. Ta wartość jest liczona jako miękki limit Celery minus 30 s, czyli 240 s. Zapas jest na wysłanie wyniku do API.
- **Rezerwa na HTTP:** 30% budżetu jest zarezerwowane na fazę HTTP, a httpx dostaje tylko to, co faktycznie zostało.
- **Pojedynczy host:** nmap dostaje `--host-timeout`, więc sam kończy pracę i zwraca XML, zamiast zostać zabity.
- **Brak czasu na HTTP:** faza HTTP jest pomijana. Wyniki nmapa zostają, a w `metadata.http_skipped` jest powód.
- **Czasy:** w `metadata.timing` zapisujemy czas trwania nmapa i httpx.
- **Przekroczenie miękkiego limitu Celery:** paczka jest oznaczana jako nieudana z czytelnym błędem.

## 3. Logowanie

- **Limit nieudanych prób** (`apps/accounts/throttle.py`, `backends.py`). Liczymy je w Redisie w oknie 15 minut:
  - 5 prób na parę konto + IP,
  - 20 prób na konto ze wszystkich adresów,
  - 50 prób z jednego IP na różne konta (password spraying).

  Po przekroczeniu logowanie zwraca 429, nawet z poprawnym hasłem. Limit działa na poziomie backendu uwierzytelniania, więc obejmuje także `/admin/`. Klucze w Redisie są skrótami, nie zawierają loginów ani adresów IP. Adres klienta jest brany z `X-Real-IP`, które ustawia gateway (`TRUST_X_REAL_IP=1`).
- **`/admin/` a MFA:** po włączeniu MFA konto z MFA wejdzie do panelu admina tylko w sesji, która przeszła drugi krok logowania (`apps/mfa/admin_guard.py`). Dopóki `MFA_ENABLED=0`, nic się nie zmienia.
- **Stare `/api/auth/mfa/verify/`:** zły kod nie wydaje już nowego tokenu. Na jeden token przypada najwyżej 5 prób, a w Redisie leży tylko skrót tokenu.
- **`bootstrap_admin --enable-mfa` jest wyłączone.** Zapisywało sekret MFA jawnym tekstem i wypisywało go do logów kontenera.
- **Domyślne hasło `changeme`:** API ostrzega o nim w logu przy pierwszym starcie. Zmień `BOOTSTRAP_ADMIN_PASSWORD` w `.env` przed pierwszym uruchomieniem.

## Testy

```bash
cd backend
python manage.py test apps --settings=config.settings_test
```

Nowe testy są w plikach `apps/scans/tests/test_limits.py`, `apps/accounts/tests/test_security.py` i `apps/mfa/tests/test_admin_guard.py`.

## 4. Discovery: aktywne hosty, duże zakresy, allowlista, dowody HTTP

Zmiany z gałęzi `feature/discovery-fixes`.

- **Fałszywie aktywne hosty.** Skan portów na zakresie CIDR używał `-Pn`, więc nmap uznawał każdy adres za aktywny i cały zakres trafiał do wyników. Teraz zakres najpierw przechodzi wykrywanie hostów (`-PE -PS22,80,443,3389,8080 -PA80` albo ustawienia modułu Host discovery). Pojedynczy zapisany host nadal jest skanowany z `-Pn`, bo może ignorować ping. Parser odrzuca hosty, które są „up” tylko przez `-Pn` i nie mają otwartego portu, oraz hosty „down”.
- **Duże zakresy.** CIDR większy niż `/24` (`SCAN_BATCH_PREFIX_V4`) jest dzielony na osobne paczki, np. /16 daje 256 × /24. Każda paczka ma własny czas, postęp i budżet czasu. Limit zakresu wzrósł z 4096 do 65 536 adresów, a skan może mieć najwyżej `SCAN_MAX_BATCHES_PER_RUN` paczek (domyślnie 2048).
- **Allowlista** (`apps/scans/scope.py`). `SCAN_ALLOWED_NETWORKS` (CIDR) i `SCAN_ALLOWED_DOMAINS` (sufiksy domen) w `.env`; puste oznacza brak ograniczeń. Cel spoza zakresu jest odrzucany przy zapisie (400). Worker sprawdza go jeszcze raz tuż przed skanem: rozwiązuje domenę i odmawia, jeśli którykolwiek adres jest poza dozwolonymi sieciami. **Przed demo ustawić na zakresy labu AGH.**
- **Dowody HTTP.** httpx zbiera teraz nagłówki odpowiedzi, hash favicony (mmh3) i adres przekierowania (`-include-response-header -favicon -location`); przekierowania nadal nie są śledzone. Ciasteczka zapisujemy bez wartości: nazwa oraz flagi `Secure`, `HttpOnly` i `SameSite`, bo wartości to dane sesyjne. Treść odpowiedzi nie jest zapisywana. Klucze w JSON z httpx (`header`) potwierdzone w teście jednostkowym, ale **nie sprawdzone na prawdziwym httpx 1.6.9**.

Bez zmian: widoczność danych według właściciela. Testy Mateusza wymagają, żeby użytkownik widział tylko własne cele i skany, więc to decyzja dla zespołu (rola „Odczyt” w obecnej wersji nie widzi cudzych skanów).
