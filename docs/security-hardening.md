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
