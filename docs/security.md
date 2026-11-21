# Bezpieczeństwo

## Threat model (MVP lokalne)

SurfaceX działa jako lokalny stos Compose. Zakładamy zaufanego operatora hosta i sieć labową. Nie jest to HA ani multi-tenant SaaS.

### Zaufane granice

- Gateway jest jedynym publicznym wejściem do UI/API.
- PostgreSQL i Redis są w sieci `backend` (internal).
- Worker jest w sieci `scanner` i ma egress do celów; **nie** dostaje hasła PostgreSQL ani socketu Dockera.
- Sekrety montowane jako pliki `0600` (`scripts/init-secrets.sh`), poza Git.

### Główne ryzyka

| Ryzyko | Kontrola |
|---|---|
| Skan poza zatwierdzonym zakresem | Allowlista IP/CIDR/domen; re-check DNS→IP przy claim |
| Nadmierny ruch / DoS celu | Limity portów, timeouty, rate, tylko HEAD/GET |
| Ucieczka procesów skanera | Process group + SIGTERM/SIGKILL; cancel i deadline → `cancel_requested` |
| Eskalacja roli | RBAC w API (`IsAdmin`, `IsAdminOrOperator`, `CanExportFindings`) |
| Wyciek evidence | AES-256-GCM envelope na wrażliwych polach (`docs/encryption.md`) |
| Podsłuch sesji | `HttpOnly` cookie; `Secure` przy HTTPS |
| ReDoS / SSRF w sygnaturach | Ścieżki względne, limity regex i body |

## Granice skanera

- Tylko discovery: brak logowania, brute force i exploitacji.
- HTTP: HEAD/GET, limit przekierowań i body; redirect poza allowlistę nie jest śledzony.
- Sygnatury deklaratywne (YAML) — bez dowolnego kodu.
- Adaptive nmap: SYN gdy raw socket dostępny, inaczej TCP connect; tryb w metadanych przebiegu.

## Okno skanu

Po `deadline_at` unfinished batche → `PAUSED`. Cancel-check i progress stosują pause od razu, więc worker zabija nmap/httpx. Late `complete` po pause jest odrzucany (409). Resume republishes tylko `PAUSED`.

## Świadome ograniczenia MVP

- Sesje Django DB (Redis = cache/Celery), nie Redis session store.
- Rotacja kluczy AES opisana w docs; pełny job rotacji nie jest jeszcze wdrożony.
- Pusta allowlista = brak egzekucji (admin musi dodać wpisy przed skanem produkcyjnym).
- Backup: AES-256-CBC (OpenSSL) osobnym kluczem — zob. `docs/backup-restore.md`.

## Audyt

Mutacje celów, skanów, allowlisty, użytkowników i overrides trafiają do `audit_log` (podgląd: admin).
