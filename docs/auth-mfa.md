# Logowanie i MFA

## Rekomendacja dla SurfaceX

Dla lokalnego MVP bez SaaS:

| Metoda | MVP | Uwagi |
|---|---|---|
| Hasło + sesja cookie | tak | Argon2id, sesja Django, CSRF |
| **TOTP (Authenticator)** | **tak — wybór MFA** | Google Authenticator / 1Password / Authy, działa offline |
| WebAuthn / passkey | później | najsilniejsze, więcej pracy w przeglądarce |
| E-mail / SMS OTP | nie | wymaga SMTP/SaaS, słabe lokalnie |

**MFA w SurfaceX = TOTP (RFC 6238).**

## Przepływ

1. `GET /api/auth/csrf/` — ustawia cookie CSRF.
2. `POST /api/auth/login/` — username + password.
3. Jeśli użytkownik ma `mfa_enabled`:
   - odpowiedź `{ mfa_required: true, mfa_token }`
   - UI prosi o 6-cyfrowy kod
   - `POST /api/auth/mfa/verify/` z `mfa_token` + `code`
4. Sesja cookie `HttpOnly`; `GET /api/auth/me/` zwraca użytkownika i rolę.
5. `POST /api/auth/logout/` kończy sesję.

Pending MFA token żyje 5 minut w Redis (cache).

## Włączenie MFA dla admina

```bash
docker compose exec api python manage.py bootstrap_admin --username admin --enable-mfa
```

Komenda wypisze `secret=` oraz `otpauth=` — dodaj do Authenticatora (Google / 1Password / Authy) jako nowe konto TOTP. Secret pokazywany jest raz.

Logowanie:

1. http://localhost:8080 (lub port `GATEWAY_HTTP_PORT` z `.env`)
2. `admin` / `changeme`
3. 6-cyfrowy kod z aplikacji

Domyślne konto lokalne:

- user: `admin`
- password: `changeme` (zmień w `.env`: `BOOTSTRAP_ADMIN_PASSWORD`)

## Poza MVP

- wymuszenie MFA dla roli `admin` / `operator`;
- szyfrowanie `mfa_secret` kluczem `app_data_key`;
- recovery codes;
- WebAuthn jako drugi czynnik albo zamiennik hasła.
