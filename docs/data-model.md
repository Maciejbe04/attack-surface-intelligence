# Model danych

Dane trwałe przechowuje PostgreSQL. Modele znajdują się w `backend/apps/scans/models.py` i `backend/apps/accounts/models.py`; tabele mają prefiksy `scans_` i `accounts_`.

## Encje

| Model | Opis | Najważniejsze pola |
|---|---|---|
| `Target` | zapisany cel skanu | `address`, `target_type` (`ip` / `cidr` / `domain`), `comment` |
| `TargetGroup` | nazwana grupa celów; cel może należeć do wielu grup | `name`, `description`, `targets` |
| `GroupSchedule` | harmonogram skanu grupy (najwyżej jeden na grupę) | `frequency`, `interval_hours`, `time_of_day`, `weekday`, `modules_snapshot`, `next_run_at`, `last_status` |
| `AllowlistEntry` | zatwierdzony zakres skanowania | `value`, `entry_type`, `enabled`, `comment` |
| `ScanRun` | jeden przebieg skanu | `status`, `modules_snapshot`, `window_seconds`, `deadline_at`, `progress`, `eta_seconds`, `resume_available`, `result_summary`, `defectdojo_export_status`, `started_at`, `finished_at` |
| `ScanBatch` | porcja pracy: jeden cel w przebiegu | `target_address`, `target_type`, `delivery_id`, `status`, `progress`, `result`, `error` |
| `ScanEvent` | wpis konsoli aktywności | `level`, `source`, `message` |
| `Observation` | znormalizowany wynik | `entity_type`, `entity_key`, `lifecycle`, `attrs`, `source`, `miss_streak` |
| `FingerprintEvidence` | dowód obserwacji | `kind`, `summary`, `ciphertext` (AES-256-GCM) |
| `ManualOverride` | trwała korekta użytkownika | `entity_key`, `tags`, `notes_ciphertext`, `attrs_patch`, `updated_by` |
| `AuditLog` | dziennik audytu | `actor`, `action`, `object_type`, `object_id`, `summary` |
| `QueueState` | epoka brokera do wykrycia utraty kolejki Redis | `broker_epoch` |
| `UserProfile` | rola i MFA użytkownika (rozszerza `auth.User`) | `role`, `mfa_enabled`, `mfa_secret` |

Sygnatury nie są przechowywane w bazie — to pliki YAML w katalogu `signatures/` ([signatures.md](signatures.md)).

Dane są wspólne dla zespołu: pole `owner` wskazuje autora rekordu, ale wszystkie role widzą te same cele, grupy, skany i wyniki.

## Stany przebiegu i batcha

`ScanRun.status`: `queued` → `running` → `completed` | `partial` | `failed` | `cancelled`; `cancel_requested` oznacza anulowanie w toku.

`ScanBatch.status`: `queued`, `running`, `completed`, `failed`, `cancelled`, `paused`. Stan `paused` nadaje koniec okna czasowego; przebieg z wstrzymanymi batchami ma status `partial` i `resume_available = true`.

`modules_snapshot` zapisuje konfigurację modułów z chwili startu — zmiana ustawień w trakcie skanu obowiązuje od następnego przebiegu. Użyty tryb nmap (`syn` / `connect`) oraz pełne linie poleceń nmap i httpx są zapisane w `ScanBatch.result.metadata`.

## Obserwacje

Każda obserwacja należy do jednego przebiegu i ma klucz logiczny, stabilny między przebiegami:

| `entity_type` | `entity_key` | Przykładowe atrybuty (`attrs`) |
|---|---|---|
| `host` | `host:<adres>` | `address`, `status` |
| `port` | `port:<adres>:<protokół>/<port>` | `service`, `product`, `version`, `state`, `curiosity` |
| `http` | `http:<url>` | `status_code`, `title`, `server`, `interesting_headers`, `security_headers_missing`, `cookies`, `cookie_tech` |
| `tech` | `tech:<url>:<technologia>` | `technology`, `confidence` |
| `cert` | `cert:<url>:<podmiot>` | podmiot, wystawca, data ważności |
| `signature` | `signature:<endpoint>:<technologia>` | `signature_id`, `confidence`, `level`, `version`, `evidence` |
| `host` (pasywna) | `passive:<zapytanie>` | dane RDAP i nazwy z Certificate Transparency |

Para (`run`, `entity_key`) jest unikalna.

| `source` | Znaczenie |
|---|---|
| `scanner` | wynik workera |
| `import` | wynik wczytany z pliku JSON |

## Niemutowalne obserwacje i trwałe korekty

Wynik skanera lub importu nie jest modyfikowany przez użytkownika. Korekta trafia do `ManualOverride`, przypiętego do `entity_key`:

```text
widok w UI = obserwacja ⊕ aktywna korekta (tagi, notatka, nadpisania atrybutów)
```

Kolejny skan tworzy nową obserwację o tym samym kluczu, więc korekta pozostaje przypięta i widoczna. Korekty są wspólne dla zespołu; przy kilku korektach tego samego klucza obowiązuje najnowsza.

## Cykl życia

Po zakończeniu przebiegu API porównuje jego obserwacje z **poprzednim ukończonym przebiegiem o tym samym zestawie modułów i tej samej grupie** (dla skanów bez grupy: o identycznej liście celów).

| Stan | Warunek |
|---|---|
| `NEW` | klucza nie było w przebiegu odniesienia (albo nie ma przebiegu odniesienia) |
| `CHANGED` | klucz istnieje, atrybuty się różnią |
| `UNCHANGED` | klucz istnieje, atrybuty bez zmian |
| `FLAKY` | obserwacja wróciła po stanie `MISSING` / `FLAKY` / `GONE` **albo** brakuje jej drugi raz z rzędu |
| `MISSING` | brak w pierwszym pełnym przebiegu |
| `GONE` | brak w trzecim i kolejnych pełnych przebiegach |

Dla obserwacji nieobecnych API tworzy w bieżącym przebiegu rekord z przeniesionymi atrybutami i licznikiem `miss_streak` zwiększonym o 1. Stany `MISSING` / `FLAKY` / `GONE` powstają tylko wtedy, gdy przebieg ma status `completed`; przebieg częściowy, anulowany lub nieudany nie obniża stanu.

Liczniki stanów trafiają do `ScanRun.result_summary.lifecycle`, a podsumowanie ciekawości do `result_summary.curiosity`.

## Relacja worker → API

Worker nie ma dostępu do PostgreSQL. Wysyła wynik do `/api/internal/batches/{id}/complete/`, a API:

1. uwierzytelnia token serwisowy (`X-Worker-Token`) i sprawdza `delivery_id`;
2. odrzuca wynik batcha wstrzymanego oknem czasowym (HTTP 409);
3. zapisuje wynik w `ScanBatch.result` i tworzy obserwacje;
4. szyfruje dowody (`FingerprintEvidence.ciphertext`);
5. po zakończeniu przebiegu liczy cykl życia i zleca eksport do DefectDojo.
