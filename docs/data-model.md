# Model danych

## Encje

| Encja | Opis |
|---|---|
| `targets` | IP, CIDR, domeny i metadane allowlisty |
| `scan_profiles` | porty, limity, narzędzia, okna |
| `schedules` | harmonogram uruchomień |
| `scan_runs` | pojedynczy przebieg ze snapshotem konfiguracji |
| `scan_attempts` | próby wykonania batcha / narzędzia |
| `scan_batches` | idempotentne jednostki pracy |
| `observations` | znormalizowany wynik host/port/usługa/endpoint |
| `fingerprint_evidence` | dowody detekcji i score |
| `signatures` | deklaratywne reguły fingerprintingu |
| `manual_overrides` | trwałe edycje użytkownika |
| `users` / `roles` | tożsamość i RBAC |
| `audit_log` | historia zmian konfiguracji i wyników |

Implementacja kolejki MVP obejmuje `targets`, `scan_runs`, `scan_batches` i techniczny `queue_state`. Identyfikator dostarczenia oraz stan publikacji naprawczej są przechowywane na batchu, a `queue_state` zapamiętuje ostatnią epokę brokera potrzebną do wykrycia utraty danych Redis. Osobne `scan_attempts`, znormalizowane `observations` i `fingerprint_evidence` pozostają rozszerzeniem kolejnego etapu.

## Niemutowalne obserwacje

Surowa obserwacja skanera lub importu jest niemutowalna. Korekty użytkownika trafiają do `manual_overrides`.

Widok prezentowany UI:

```text
effective_view = observation ⊕ active_manual_override
```

Kolejny skan aktualizuje obserwację, ale nie usuwa override.

## Snapshot konfiguracji

`scan_run` zapisuje snapshot:

- listy celów po rozwinięciu i deduplikacji;
- profilu portów i limitów;
- wersji nmap / httpx;
- wersji aktywnych sygnatur;
- allowlisty obowiązującej w momencie startu.

Zmiany konfiguracji podczas aktywnego skanu obowiązują od następnego przebiegu.

## Źródło obserwacji

| `source` | Znaczenie |
|---|---|
| `scanner` | wynik workera |
| `import` | wynik wczytany z CSV/JSON |

Oba źródła przechodzą przez ten sam pipeline walidacji i normalizacji.

## Cykl życia

Cykl życia jest liczony osobno dla:

- hosta;
- portu / usługi;
- endpointu HTTP;
- technologii;
- certyfikatu.

Stany:

| Stan | Znaczenie |
|---|---|
| `NEW` | pierwszy raz zaobserwowany |
| `CHANGED` | zmienił się istotny atrybut |
| `MISSING` | pierwszy pełny pomiar bez odpowiedzi |
| `FLAKY` | przeplatane odpowiedzi i braki |
| `GONE` | domyślnie trzy kolejne pełne pomiary bez odpowiedzi |

Nieudany lub częściowy skan nie obniża stanu.

## Klucze logiczne

Przykładowe klucze deduplikacji:

- host: `ip` albo kanoniczna nazwa domeny;
- usługa: `host + port + protocol`;
- endpoint: `host + port + scheme + path`;
- technologia: `host + port + technology + signature_id`;
- certyfikat: `host + port + fingerprint`.

## Relacja worker → API

Worker nie zapisuje bezpośrednio do PostgreSQL. Wysyła wynik do wewnętrznego endpointu API, który:

1. uwierzytelnia token serwisowy;
2. waliduje schemat;
3. szyfruje pola wrażliwe;
4. zapisuje obserwacje i evidence;
5. uruchamia silnik różnic.
