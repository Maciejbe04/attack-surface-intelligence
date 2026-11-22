# Szyfrowanie

## Model

Wrażliwe pola są szyfrowane w aplikacji algorytmem **AES-256-GCM** przed zapisem do PostgreSQL (`backend/apps/scans/crypto.py`).

```text
sx1:<base64url( nonce[12 B] ‖ szyfrogram ‖ tag GCM )>
```

- Klucz pochodzi z sekretu `secrets/app_data_key` (plik `0600`, poza Gitem i poza obrazami). Jeżeli zawartość dekoduje się z base64 do co najmniej 32 bajtów, kluczem są pierwsze 32 bajty; w przeciwnym razie kluczem jest SHA-256 z zawartości.
- Każdy zapis używa losowego 96-bitowego nonce.
- Sekret dostają wyłącznie usługi `api` i `scheduler`. Worker nie ma klucza — wysyła wynik do API, które szyfruje go przed zapisem.

## Pola szyfrowane

| Model | Pole | Zawartość |
|---|---|---|
| `FingerprintEvidence` | `ciphertext` | dowód obserwacji: rekord hosta, portu (baner, produkt, wersja), odpowiedzi HTTP, technologii, certyfikatu, wynik RDAP/CT |
| `ManualOverride` | `notes_ciphertext` | notatka analityka |

## Pola jawne

Pozostają jawne, bo służą do wyszukiwania, filtrowania i porównywania przebiegów:

- adres IP / host, port, protokół, nazwa usługi, produkt i wersja;
- kod HTTP, tytuł strony, nagłówek `Server`, nazwy i wartości niestandardowych nagłówków (do 200 znaków);
- nazwy i flagi ciasteczek — wartości ciasteczek nie są zapisywane w obserwacji;
- nazwa technologii i poziom pewności;
- stany cyklu życia i tagi.

## Inne mechanizmy

| Obszar | Mechanizm |
|---|---|
| Hasła użytkowników | Argon2id (zapasowo PBKDF2) |
| Backup bazy | `pg_dump` szyfrowany `openssl enc -aes-256-cbc -pbkdf2` osobnym kluczem `backup_key` |
| Sekrety DefectDojo | osobne pliki `defectdojo_*`, w tym klucz AES-256 poświadczeń DefectDojo |

Klucz aplikacji nie jest tożsamy z kluczem backupu.

## Zachowanie przy błędach

- Brak sekretu `app_data_key`: `seal()` zwraca pusty ciąg, dowód jest zapisywany bez szyfrogramu (`meta.encrypted = false`), a notatka trafia do pola jawnego. `./scripts/init-secrets.sh` zawsze tworzy klucz, więc w poprawnie uruchomionym stosie ta ścieżka nie występuje.
- Zmiana lub utrata klucza: wcześniejszych szyfrogramów nie da się odczytać (`open_sealed()` zwraca `None`). Klucz należy objąć kopią zapasową niezależnie od backupu bazy.

## Lokalne sekrety

```text
secrets/app_data_key
secrets/backup_key
secrets/session_hmac
secrets/worker_token
secrets/postgres_password
secrets/django_secret_key
```

Pliki tworzy `./scripts/init-secrets.sh` z uprawnieniami `0600`. Compose montuje je tylko do usług, które ich potrzebują ([`secrets/README.md`](../secrets/README.md)).

## Ograniczenia prototypu

- **Surowy wynik batcha** (`ScanBatch.result`) jest zapisywany jako jawny JSON. Zawiera odpowiedź narzędzi: nagłówki HTTP i fragment treści strony (do 4000 znaków). Szyfrowane są rekordy dowodów i notatki, a nie cały wynik. Pełną poufność danych na dysku zapewnia dopiero szyfrowanie wolumenu hosta (np. LUKS, FileVault).
- **Rotacja klucza** jest ręczna: envelope nie zawiera wersji klucza, nie ma zadania przepisującego stare rekordy.
- **Sekret TOTP** (`UserProfile.mfa_secret`) jest przechowywany bez szyfrowania.
- PostgreSQL nie ma włączonego szyfrowania na poziomie silnika (TDE).
