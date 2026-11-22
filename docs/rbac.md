# RBAC

## Role

| Rola | Zakres |
|---|---|
| `admin` | użytkownicy, role, sekrety, konfiguracja globalna, pełny dostęp |
| `operator` | cele, skany, harmonogramy, sygnatury |
| `analyst` | odczyt oraz edycja wyników, tagów, notatek i overrides |
| `viewer` | wyłącznie odczyt |

Uprawnienia są egzekwowane w API. UI jedynie ukrywa niedozwolone akcje.

**Wspólna przestrzeń zespołu:** cele, grupy, skany, wyniki, edycje znalezisk i allowlista są wspólne dla wszystkich użytkowników. Każda rola widzi te same dane, a rola decyduje tylko o tym, co wolno zmieniać. Allowlista i limity są polityką całego systemu: wpis dodany przez admina lub operatora obowiązuje każdy skan, niezależnie od tego, kto go zleca. Adres celu i nazwa grupy są unikalne w całym systemie.

## Macierz uprawnień

| Akcja | admin | operator | analyst | viewer |
|---|---|---|---|---|
| Logowanie / własna sesja | tak | tak | tak | tak |
| Zarządzanie użytkownikami i rolami | tak | nie | nie | nie |
| Rotacja kluczy i sekrety systemowe | tak | nie | nie | nie |
| Zarządzanie allowlistą (globalna, obowiązuje wszystkich) | tak | tak | nie | nie |
| Podgląd allowlisty | tak | tak | tak | tak |
| CRUD celów | tak | tak | nie | nie |
| Moduł passive-discovery (crt.sh / RDAP) | tak | tak | nie | nie |
| CRUD profili i harmonogramów | tak | tak | nie | nie |
| Start / stop / wznowienie skanu | tak | tak | nie | nie |
| Konfiguracja okna skanu | tak | nie (stałe 1 h) | nie | nie |
| CRUD sygnatur | tak | tak | nie | nie |
| Podgląd dashboardu i historii | tak | tak | tak | tak |
| Eksport CSV/JSON | tak | tak | tak | tak |
| Import celów | tak | tak | nie | nie |
| Import wyników | tak | tak | tak | nie |
| Manual override / tagi / notatki | tak | tak | tak | nie |
| Eksport do DefectDojo | tak | tak | tak | nie |
| Podgląd audit log | tak | nie | nie | nie |

## Uwierzytelnianie

- hasła: Argon2id;
- sesje: cookie Django (`HttpOnly`, `SameSite=Lax` lokalnie);
- opcjonalne MFA: TOTP (Authenticator) — szczegóły w `docs/auth-mfa.md`;
- flaga `Secure`: wymagana przy HTTPS; lokalnie bez TLS dopuszczalne jest wyłączenie `Secure` wyłącznie w profilu `local-dev`;
- limit prób logowania oraz audyt nieudanych logowań;
- sesja ma idle timeout i absolute timeout.

## Zasady egzekwowania

- brak uprawnienia = HTTP `403`;
- brak sesji = HTTP `401`;
- każda zmiana konfiguracji, wyniku, sygnatury lub roli trafia do `audit_log`;
- worker używa osobnego tokenu serwisowego z uprawnieniem wyłącznie do pobierania zadań i przesyłania wyników.
