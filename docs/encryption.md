# Szyfrowanie

## Model

Aplikacja używa envelope encryption z AES-256-GCM.

Każda zaszyfrowana wartość zawiera:

```text
key_version | nonce | ciphertext | tag
```

Klucze DEK nie trafiają do obrazów ani repozytorium. Są montowane jako lokalne pliki `0600`.

## Pola szyfrowane

| Encja / obszar | Pole | Powód |
|---|---|---|
| `fingerprint_evidence` | surowe nagłówki | mogą zawierać tokeny |
| `fingerprint_evidence` | wartości cookies | dane sesyjne |
| `fingerprint_evidence` | fragmenty body / evidence | potencjalnie wrażliwe |
| `fingerprint_evidence` | bannery usług | mogą zawierać ścieżki wewnętrzne |
| `manual_overrides` | notatki | treść analityka |
| `integrations` | tokeny DefectDojo / API | sekrety |
| `scan_attempts` | wybrane surowe logi narzędzi | mogą zawierać dane odpowiedzi |

## Pola jawne

Pozostają indeksowalne i jawne:

- adres IP / host;
- port, protokół, nazwa usługi;
- kod HTTP;
- tytuł strony;
- nazwa technologii;
- poziom pewności;
- nazwa cookie bez wartości;
- data wygaśnięcia certyfikatu;
- stany cyklu życia;
- tagi nieoznaczone jako poufne.

## Rotacja kluczy

1. Operator dodaje nową wersję klucza.
2. Nowe zapisy używają najnowszej wersji.
3. Zadanie wsadowe przepisuje stare rekordy partiami.
4. Po zakończeniu migracji stary klucz można wyłączyć.
5. Rotacja nie wymaga postoju systemu.

## Backup

- backup PostgreSQL jest szyfrowany osobnym kluczem backupowym;
- klucz aplikacji nie jest tożsamy z kluczem backupu;
- test odtworzenia tworzy tymczasową bazę, stosuje migracje i wykonuje zapytanie kontrolne;
- nieudany test backupu jest raportowany w dashboardzie operacyjnym.

## Lokalne sekrety

Przykładowe pliki poza repozytorium:

```text
secrets/app_data_key
secrets/backup_key
secrets/session_hmac
secrets/worker_token
secrets/postgres_password
```

Uprawnienia plików: `0600`. Compose montuje je tylko do wymagających usług.
