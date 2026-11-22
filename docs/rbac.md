# RBAC

## Role

| Rola | Zakres |
|---|---|
| `admin` | użytkownicy i role, dziennik audytu, dłuższe okno skanu oraz wszystko, co niższe role |
| `operator` | cele, grupy, harmonogramy, allowlista, uruchamianie i przerywanie skanów |
| `analyst` | odczyt oraz edycja wyników (tagi, notatki, nadpisania), import wyników, eksport |
| `viewer` | wyłącznie odczyt |

Odpowiadają one rolom z treści zadania: Administracja → `admin`; Dodawanie, usuwanie, modyfikacja → `operator`; Modyfikacja i odczyt → `analyst`; Odczyt → `viewer`.

Uprawnienia są egzekwowane w API (klasy `IsAdmin`, `IsAdminOrOperator`, `CanExportFindings` w `backend/apps/scans/permissions.py`). UI jedynie ukrywa niedozwolone akcje. Zestaw ról jest stały; administrator tworzy konta i przypisuje im jedną z czterech ról (zakładka **Users**, `/api/auth/users/`). Konto bez profilu roli jest traktowane jak `viewer`.

**Wspólna przestrzeń zespołu:** cele, grupy, skany, wyniki, edycje znalezisk i allowlista są wspólne dla wszystkich użytkowników. Każda rola widzi te same dane, a rola decyduje tylko o tym, co wolno zmieniać. Allowlista i limity są polityką całego systemu: wpis dodany przez admina lub operatora obowiązuje każdy skan, niezależnie od tego, kto go zleca. Adres celu i nazwa grupy są unikalne w całym systemie.

## Macierz uprawnień

| Akcja | admin | operator | analyst | viewer |
|---|---|---|---|---|
| Logowanie / własna sesja | tak | tak | tak | tak |
| Zarządzanie użytkownikami i rolami | tak | nie | nie | nie |
| Zarządzanie allowlistą (globalna, obowiązuje wszystkich) | tak | tak (przez API) | nie | nie |
| Podgląd allowlisty | tak | tak | tak | tak |
| Dodawanie i usuwanie celów | tak | tak | nie | nie |
| Grupy i harmonogramy | tak | tak | nie | nie |
| Moduł passive-discovery (crt.sh / RDAP) | tak | tak | nie | nie |
| Start / stop / wznowienie skanu | tak | tak | nie | nie |
| Konfiguracja okna skanu | tak | nie (stałe 1 h) | nie | nie |
| Podgląd dashboardu i historii | tak | tak | tak | tak |
| Eksport CSV/JSON | tak | tak | tak | nie |
| Import celów | tak | tak | nie | nie |
| Import wyników | tak | tak | tak | nie |
| Manual override / tagi / notatki | tak | tak | tak | nie |
| Eksport do DefectDojo | tak | tak | tak | nie |
| Podgląd audit log | tak | nie | nie | nie |

## Uwierzytelnianie

- hasła: Argon2id;
- sesje: cookie Django (`HttpOnly`, `SameSite=Lax`), przechowywane w bazie i odświeżane przy każdym żądaniu;
- opcjonalne MFA: TOTP (Authenticator) — szczegóły w [auth-mfa.md](auth-mfa.md);
- flaga `Secure` ciasteczek: `SECURE_COOKIES=1` (wymagane przy HTTPS; lokalnie bez TLS domyślnie wyłączone);
- nieudane logowania są zapisywane w audycie (`auth.login_failure`); limit prób logowania nie jest zaimplementowany;
- zablokowane konto (`is_active = false`) nie może się zalogować.

## Zasady egzekwowania

- brak uprawnienia = HTTP `403`;
- brak sesji = HTTP `401`;
- zmiany celów, grup, harmonogramów, allowlisty, korekt wyników i kont użytkowników oraz uruchomienia skanów, eksporty i importy trafiają do dziennika audytu (podgląd: `admin`);
- administrator nie może odebrać sobie roli `admin` ani zablokować własnego konta;
- worker używa osobnego tokenu serwisowego (`X-Worker-Token`) z dostępem wyłącznie do endpointów `/api/internal/`.
