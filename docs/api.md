# API SurfaceX

Publiczne API jest dostępne wyłącznie przez gateway (`/api/…`). Workery używają osobnych endpointów `/api/internal/…` z nagłówkiem `X-Worker-Token`.

Uwierzytelnianie sesyjne (cookie + opcjonalny nagłówek `X-Sessionid`). CSRF: w profilu produkcyjnym włączone; lokalny `local-dev` może wyłączyć ochronę CSRF.

## Auth

| Metoda | Ścieżka | Role | Opis |
|---|---|---|---|
| POST | `/api/auth/login/` | public | logowanie; może wymagać MFA |
| POST | `/api/auth/mfa/verify/` | public | weryfikacja TOTP |
| POST | `/api/auth/logout/` | zalogowany | wylogowanie |
| GET | `/api/auth/me/` | zalogowany | bieżący użytkownik i rola |
| GET/POST | `/api/auth/users/` | admin | lista / tworzenie użytkowników |
| PATCH/DELETE | `/api/auth/users/{id}/` | admin | zmiana roli/hasła/statusu |

## Cele i grupy

| Metoda | Ścieżka | Role | Opis |
|---|---|---|---|
| GET/POST | `/api/targets/` | odczyt: wszystkie; zapis: admin/operator | lista / dodanie celu |
| DELETE | `/api/targets/{id}/` | admin/operator | usunięcie |
| POST | `/api/targets/import/` | admin/operator | import TXT/CSV/JSON (limit 10k) |
| GET/POST | `/api/groups/` | odczyt: wszystkie; zapis: admin/operator | grupy |
| GET/PATCH/DELETE | `/api/groups/{id}/` | j.w. | szczegóły grupy |
| POST | `/api/groups/{id}/targets/` | admin/operator | dodaj/usuń cele |
| POST | `/api/groups/{id}/scan/` | admin/operator | skan całej grupy (`modules`, `client_request_id`, opcjonalnie `window_seconds`) |
| PUT/DELETE | `/api/groups/{id}/schedule/` | admin/operator | harmonogram |

## Pasywne rozpoznanie

| Metoda | Ścieżka | Role | Opis |
|---|---|---|---|
| POST | `/api/passive/discover/` | admin/operator | `{"query":"example.com"}` albo IP → poddomeny (crt.sh) + skrót RDAP; cache Redis 15 min; bez auto-skanu |

Odpowiedź: `query`, `type` (`domain`/`ip`), `subdomains`, `rdap` (lub `null`), `sources` (`ok`/`error`/`skipped`), `warnings`, `cached`. Częściowa awaria źródła nie blokuje drugiej. Wybrane hosty zapisuje się osobno przez `POST /api/targets/`.

## Skany i wyniki

| Metoda | Ścieżka | Role | Opis |
|---|---|---|---|
| GET/POST | `/api/scans/` | odczyt: wszystkie; start: admin/operator | lista / start (`target_ids`, `modules`, opcjonalnie `window_seconds`) |
| GET | `/api/scans/{id}/` | właściciel | szczegóły, eventy, batche, ETA |
| POST | `/api/scans/{id}/cancel/` | admin/operator | anulowanie |
| POST | `/api/scans/{id}/resume/` | admin/operator | wznowienie batchy `PAUSED`; opcjonalne `window_seconds` |
| GET | `/api/scans/{id}/observations/` | właściciel | obserwacje (+ filtry) |
| GET | `/api/scans/{id}/diff/` | właściciel | porównanie z poprzednim completed run w tym samym scope |
| GET | `/api/scans/{id}/export/?format=csv\|json` | admin/operator/analyst | eksport |
| POST | `/api/scans/{id}/export/defectdojo/` | admin/operator/analyst | ręczny eksport do DefectDojo |
| POST | `/api/observations/import/` | admin/operator/analyst | import wyników CSV/JSON |

Deadline skanu jest obowiązkowy nawet wtedy, gdy klient nie wysyła `window_seconds`: API stosuje wtedy globalne 3600 s. Role inne niż `admin` mogą podać maksymalnie 3600 s; `admin` maksymalnie 86 400 s. UI oferuje administratorowi 30 min / 1 h / 2 h, a pozostałym rolom stosuje stałe 1 h bez selektora.

## Allowlista, overrides, audit

| Metoda | Ścieżka | Role | Opis |
|---|---|---|---|
| GET/POST | `/api/allowlist/` | GET: authenticated; POST: admin | lista / dodanie wpisu |
| PATCH/DELETE | `/api/allowlist/{id}/` | admin | edycja / usunięcie |
| POST | `/api/overrides/` | admin/operator/analyst | upsert manual override |
| DELETE | `/api/overrides/{id}/` | admin/operator/analyst | usunięcie |
| GET | `/api/audit/` | admin | ostatnie wpisy audytu |

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
| GET | `/api/health/` | liveness API |

Szczegóły schematów plików: `docs/import-export.md`. Macierz ról: `docs/rbac.md`.
