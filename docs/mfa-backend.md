# MFA backend (TOTP): gotowe, jeszcze niewłączone

Moduł `backend/apps/mfa` zawiera kompletny backend MFA: zapisywanie sekretów, kody odzyskiwania, blokadę po nieudanych próbach i endpointy REST. **Jest uśpiony.** Nie zmienia obecnego logowania (`apps/accounts`) ani frontendu, dopóki ktoś go świadomie nie włączy (sekcja „Jak włączyć”).

## Co jest w środku

| Plik | Zawartość |
|---|---|
| `crypto.py` | AES-256-GCM, klucze pochodne HKDF-SHA256 z `app_data_key`, rotacja kluczy, HMAC-SHA256 |
| `totp.py` | generowanie sekretu (160 bitów), porównanie kodu w stałym czasie |
| `models.py` | `MfaCredential` (zaszyfrowany sekret), `MfaRecoveryCode` (tylko skrót HMAC) |
| `services.py` | rejestracja, weryfikacja, kody odzyskiwania, blokada, wyłączenie, rotacja |
| `challenge.py` | drugi krok logowania: jednorazowy token po poprawnym haśle |
| `views.py`, `urls.py` | REST API (jeszcze niepodpięte do `config/urls.py`) |
| `management/commands/` | `mfa_reset`, `mfa_rotate_keys` |
| `tests/` | 47 testów |

## Model bezpieczeństwa

**Nic nie jest zapisywane jawnym tekstem.**

| Dane | Jak są chronione |
|---|---|
| Sekret TOTP | AES-256-GCM, losowy 96-bitowy nonce przy każdym zapisie. Szyfrogram jest powiązany z `user_id` (associated data), więc skopiowany do wiersza innego użytkownika nie da się odszyfrować. Odszyfrowywany tylko w pamięci, na czas sprawdzenia kodu. |
| Klucz szyfrowania | Nie leży w bazie ani w repo. Pochodzi z sekretu Dockera `app_data_key` (plik `0600`). Dla każdego celu jest osobny podklucz HKDF-SHA256 (`mfa-totp-secret`, `mfa-recovery-code`). Brak klucza albo klucz krótszy niż 32 znaki: aplikacja odmawia działania (fail closed), zamiast zapisać dane bez szyfrowania. |
| Kody odzyskiwania | 10 kodów po 50 bitów entropii (`XXXXX-XXXXX`). Pokazywane raz, zapisywane tylko jako HMAC-SHA256 z tajnym kluczem i `user_id`. Każdy działa raz, a zużycie jest atomowe w bazie. |
| Token drugiego kroku logowania | 256 bitów losowości. W Redisie leży tylko jego SHA-256, nie sam token. Jednorazowy, ważny 5 minut, ginie po 5 złych kodach. Zły kod **nie** wydaje nowego tokenu. |
| Odpowiedzi z sekretem | `Cache-Control: no-store`, więc przeglądarka i proxy ich nie zapisują. |
| Logi | Tylko zdarzenia i `user_id` (logger `surfacex.security.mfa`), nigdy sekret ani kod. |

**Ochrona przed atakami:**
- **Powtórzenie kodu:** zapamiętujemy ostatni użyty krok czasowy TOTP, a ten sam albo starszy kod jest odrzucany atomowo w bazie.
- **Zgadywanie kodu:** po 10 nieudanych próbach (kody i hasła razem) konto ma 15 minut blokady drugiego czynnika. Do tego obowiązuje limit 5 prób na jeden token logowania.
- **Przejęta sesja:** rejestracja, wyłączenie MFA i nowe kody odzyskiwania wymagają podania aktualnego hasła. Wyłączenie i nowe kody wymagają też kodu z aplikacji.
- **Analiza czasu odpowiedzi:** kody są porównywane `hmac.compare_digest`, bez przerywania pętli.
- **Rejestracja:** wygasa po 15 minutach bez potwierdzenia. MFA włącza się dopiero po podaniu działającego kodu, więc źle zeskanowany kod QR nie zablokuje konta.

## API (po włączeniu, prefiks `/api/auth/mfa/`)

| Metoda i ścieżka | Kto | Body | Wynik |
|---|---|---|---|
| `GET status/` | zalogowany | — | `enrolled`, `pending_enrollment`, `recovery_codes_remaining`, `locked_out` |
| `POST enroll/` | zalogowany | `password` | `secret`, `otpauth_uri` (do kodu QR), `expires_in`; pokazywane raz |
| `POST enroll/confirm/` | zalogowany | `code` | `recovery_codes` (pokazywane raz) |
| `POST recovery-codes/` | zalogowany | `password`, `code` (TOTP) | nowe `recovery_codes` |
| `POST disable/` | zalogowany | `password`, `code` | MFA wyłączone |
| `POST challenge/` | anonim | `mfa_token`, `code` (TOTP albo kod odzyskiwania) | sesja + `user` |

Błędy mają pola `detail` i `code`: `invalid_code` (400), `password_required` (403), `already_enrolled`/`not_enrolled` (409), `enrollment_expired` (410), `locked_out` (429), `challenge_invalid` (401). Gdy `MFA_ENABLED` jest wyłączone, każdy endpoint zwraca 404.

## Jak włączyć (gdy front i logowanie będą gotowe)

1. **Przebudować obrazy:** doszła zależność `cryptography`. Wykonać `docker compose up --build`.
2. **Włączyć flagę:** w `.env` ustawić `MFA_ENABLED=1`.
3. **Podpiąć trasy:** w `backend/config/urls.py` dodać
   ```python
   path("api/auth/mfa/", include("apps.mfa.urls")),
   ```
4. **Podmienić sprawdzenie w `apps/accounts/views.py` → `login_view`:** zamiast `if profile.mfa_enabled and profile.mfa_secret:` użyć
   ```python
   from apps.mfa import challenge, services as mfa
   if mfa.login_requires_mfa(user):
       return Response({"mfa_required": True, "mfa_token": challenge.issue_challenge(user), ...})
   ```
5. **Frontend:** drugi krok logowania wysyła kod na `POST /api/auth/mfa/challenge/` (zamiast starego `/api/auth/mfa/verify/`). Do tego ekran rejestracji: kod QR z `otpauth_uri`, potwierdzenie kodem i jednorazowe wyświetlenie kodów odzyskiwania.
6. **Usunąć starą ścieżkę z jawnym sekretem:** pole `UserProfile.mfa_secret`, widok `mfa_verify` i `apps/accounts/mfa.py`. Flaga `bootstrap_admin --enable-mfa` jest już wyłączona (`docs/security-hardening.md`).
7. **Panel `/admin/`:** po włączeniu konto z MFA wejdzie tam tylko po zalogowaniu przez konsolę z drugim krokiem (`apps/mfa/admin_guard.py`).

## Operacje

```bash
# Użytkownik zgubił telefon i nie ma kodów odzyskiwania:
docker compose exec api python manage.py mfa_reset --username jan --yes

# Rotacja klucza: nowy klucz w secrets/app_data_key, stary w secrets/app_data_key_previous
# (podmontować go do api w compose.yml), potem:
docker compose exec api python manage.py mfa_rotate_keys
# Po udanej rotacji usunąć app_data_key_previous.
```

## Testy

Bez Dockera, na SQLite w pamięci:

```bash
cd backend
python manage.py test apps.mfa --settings=config.settings_test
```

## Czego ten moduł nie robi

- Nie ogranicza liczby prób **hasła** w `login_view`. To osobna rzecz w `apps/accounts`; warto dodać limit per IP i per konto.
- Nie zmienia domyślnego konta `admin` / `changeme`. Na demo hasło trzeba zmienić w `.env`.
- Nie wymusza MFA dla ról. Pod wymuszenie jest gotowe: po drugim kroku sesja dostaje znacznik `mfa_verified_at`, więc da się to dodać jednym middleware'em.
