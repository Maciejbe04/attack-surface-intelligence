# API SurfaceX

Publiczne API jest dostępne wyłącznie przez gateway (`/api/…`). Workery używają osobnych endpointów `/api/internal/…` z nagłówkiem `X-Worker-Token`.

Uwierzytelnianie sesyjne (cookie + opcjonalny nagłówek `X-Sessionid`). Brak sesji daje `401`, brak uprawnienia `403`. Ochronę CSRF włącza `CSRF_PROTECT=1`; w konfiguracji domyślnej (praca lokalna) jest wyłączona.

Dane są wspólne dla zespołu: każda zalogowana rola może czytać cele, grupy, skany, wyniki i allowlistę. Kolumna „Role” podaje, kto może wykonać operację.

## Auth

| Metoda | Ścieżka | Role | Opis |
|---|---|---|---|
| GET | `/api/auth/csrf/` | public | ustawia cookie CSRF |
| POST | `/api/auth/login/` | public | logowanie; może wymagać MFA |
| POST | `/api/auth/mfa/verify/` | public | weryfikacja TOTP |
| POST | `/api/auth/logout/` | zalogowany | wylogowanie |
| GET | `/api/auth/me/` | zalogowany | bieżący użytkownik i rola |
| GET/POST | `/api/auth/users/` | admin | lista / tworzenie użytkowników |
| PATCH/DELETE | `/api/auth/users/{id}/` | admin | zmiana roli/hasła/statusu |

## Cele i grupy

| Metoda | Ścieżka | Role | Opis |
|---|---|---|---|
| GET/POST | `/api/targets/` | odczyt: wszystkie; zapis: admin/operator | lista (filtry `?search=`, `?group=`, `?limit=1..100`) / dodanie celu |
| DELETE | `/api/targets/{id}/` | admin/operator | usunięcie (edycja celu nie jest dostępna) |
| POST | `/api/targets/import/` | admin/operator | import TXT/CSV/JSON (limit 10 000 celów, 5 MiB) |
| GET/POST | `/api/groups/` | odczyt: wszystkie; zapis: admin/operator | grupy |
| GET/PATCH/DELETE | `/api/groups/{id}/` | j.w. | szczegóły grupy |
| POST | `/api/groups/{id}/targets/` | admin/operator | dodaj/usuń cele |
| POST | `/api/groups/{id}/scan/` | admin/operator | skan całej grupy (`modules`, `client_request_id`, opcjonalnie `window_seconds`) |
| PUT/DELETE | `/api/groups/{id}/schedule/` | admin/operator | harmonogram |

## Pasywne rozpoznanie

| Metoda | Ścieżka | Role | Opis |
|---|---|---|---|
| POST | `/api/passive/discover/` | admin/operator | `{"query":"example.com"}` albo IP → poddomeny (crt.sh) + skrót RDAP; cache Redis 15 min; bez auto-skanu |

```json
{
  "query": "example.com",
  "type": "domain",
  "subdomains": ["api.example.com", "example.com", "www.example.com"],
  "rdap": {
    "handle": "D1234567-EXAMPLE",
    "name": "Example Org",
    "country": "US",
    "network": "",
    "asns": [],
    "nameservers": ["ns1.example.com"]
  },
  "sources": { "crt_sh": "ok", "rdap": "ok" },
  "warnings": [],
  "cached": false
}
```

Pola: `query` (znormalizowane), `type` (`domain`/`ip`), `subdomains` (puste dla IP), `rdap` (lub `null`), `sources` (`ok` / `error` / `not_applicable`), `warnings`, `cached`. Częściowa awaria źródła nie blokuje drugiej. Endpoint niczego nie zapisuje (UI go nie eksponuje — główna ścieżka to moduł skanu `passive-discovery`). Szczegóły: `docs/passive-discovery.md`.

## Skany i wyniki

| Metoda | Ścieżka | Role | Opis |
|---|---|---|---|
| GET/POST | `/api/scans/` | odczyt: wszystkie; start: admin/operator | lista / start (`target_ids`, `modules`, opcjonalnie `window_seconds`) |
| GET | `/api/scans/{id}/` | wszystkie | szczegóły, eventy, batche, ETA |
| POST | `/api/scans/{id}/cancel/` | admin/operator | anulowanie |
| POST | `/api/scans/{id}/resume/` | admin/operator | wznowienie batchy `PAUSED`; opcjonalne `window_seconds` |
| GET | `/api/scans/{id}/observations/` | wszystkie | obserwacje z korektami; filtry `?lifecycle=`, `?entity_type=`; do 2000 pozycji |
| GET | `/api/scans/{id}/diff/` | wszystkie | porównanie z poprzednim ukończonym przebiegiem o tych samych modułach i tej samej grupie lub liście celów; `?against=<id>` wskazuje inny przebieg |
| GET | `/api/scans/{id}/export/?format=csv\|json` | admin/operator/analyst | eksport zakończonego przebiegu |
| POST | `/api/scans/{id}/export/defectdojo/` | admin/operator/analyst | ręczny eksport do DefectDojo |
| POST | `/api/observations/import/` | admin/operator/analyst | import wyników JSON (`surfacex.export.v1`) |

Deadline skanu jest obowiązkowy nawet wtedy, gdy klient nie wysyła `window_seconds`: API stosuje wtedy globalne 3600 s. Role inne niż `admin` mogą podać maksymalnie 3600 s; `admin` maksymalnie 86 400 s. UI oferuje administratorowi 30 min / 1 h / 2 h, a pozostałym rolom stosuje stałe 1 h bez selektora.

## Allowlista, overrides, audit

| Metoda | Ścieżka | Role | Opis |
|---|---|---|---|
| GET/POST | `/api/allowlist/` | odczyt: wszystkie; zapis: admin/operator | lista / dodanie wpisu |
| PATCH/DELETE | `/api/allowlist/{id}/` | admin/operator | edycja (w tym pole `enabled`) / usunięcie |
| POST | `/api/overrides/` | admin/operator/analyst | upsert manual override |
| DELETE | `/api/overrides/{id}/` | admin/operator/analyst | usunięcie |
| GET | `/api/audit/` | admin | 200 ostatnich wpisów audytu |

W interfejsie formularz allowlisty jest dostępny dla roli `admin`; `operator` może zarządzać allowlistą przez API.

## Internal (worker)

Wymagany nagłówek `X-Worker-Token`. Bez sesji użytkownika.

| Metoda | Ścieżka | Opis |
|---|---|---|
| POST | `/api/internal/batches/reconcile/` | republish stale + pause po deadline |
| POST | `/api/internal/schedules/dispatch/` | uruchom due schedules |
| POST | `/api/internal/batches/{id}/claim/` | claim batch |
| POST | `/api/internal/batches/{id}/progress/` | postęp; może zwrócić `cancel_requested` po deadline |
| GET | `/api/internal/batches/{id}/cancel-check/` | poll cancel **oraz** pause okna |
| POST | `/api/internal/batches/{id}/complete/` | wynik; **409** gdy batch już `PAUSED` |
| POST | `/api/internal/batches/{id}/fail/` | błąd/cancel; `PAUSED` pozostaje `PAUSED` |

## Health

| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/api/health/` | liveness API i stan bazy (bez logowania) |
| GET | `/api/system/` | wersje komponentów i stan integracji DefectDojo (zalogowany) |

Gateway zwraca `404` dla `/api/internal/` — te endpointy są osiągalne tylko z sieci `backend`.

Szczegóły schematów plików: `docs/import-export.md`. Pasywne rozpoznanie: `docs/passive-discovery.md`. Macierz ról: `docs/rbac.md`.
