# Źródła, narzędzia, wykorzystanie AI i zgodność z regulaminem

Wykaz elementów wykonanych z pomocą AI, użytych bibliotek, frameworków, narzędzi i materiałów zewnętrznych wraz z licencjami. Stan na 22.11.2026.

## 1. Elementy wykonane z pomocą AI

Projekt powstał z wykorzystaniem asystentów AI. Wygenerowany kod został przejrzany, uruchomiony i przetestowany przez zespół (`python manage.py test apps --settings=config.settings_test`, 97 testów).

| Narzędzie AI | Charakter użycia |
|---|---|
| Claude Code (Anthropic) | agent programistyczny w repozytorium |
| Cursor | edytor z asystentem AI |
| GitHub Copilot | podpowiedzi kodu w edytorze |
| ChatGPT (OpenAI) | konsultacje i szkice rozwiązań poza repozytorium |

Narzędzia wspierały zespół we wszystkich warstwach projektu: backend (API, model danych, logika skanów, integracja DefectDojo), frontend, konfiguracja Docker Compose, testy i dokumentacja.

Z pomocą Claude Code powstały w szczególności: wspólna przestrzeń zespołu i globalna allowlista, twarde limity intensywności skanu, wykrywanie aktywnych hostów, zbieranie i analiza ciekawych nagłówków oraz ciasteczek, dane favicony i treści strony dla sygnatur, opcja skanowania portów IoT/OT, pomijanie RDAP dla adresów prywatnych, backend MFA, testy do tych elementów oraz dokumentacja techniczna.

Instrukcje dla asystentów (katalogi `.claude/skills/` i `.cursor/skills/`) są częścią repozytorium.

## 2. Biblioteki i frameworki — backend (Python)

Wersje przypięte w `backend/requirements.txt`.

| Biblioteka | Wersja | Licencja |
|---|---|---|
| Django | 5.1.7 | BSD-3-Clause |
| Django REST Framework | 3.15.2 | BSD-3-Clause |
| django-cors-headers | 4.7.0 | MIT |
| Celery | 5.4.0 | BSD-3-Clause |
| redis-py | 6.2.0 | MIT |
| psycopg (3) | 3.2.6 | LGPL-3.0 |
| gunicorn | 23.0.0 | MIT |
| argon2-cffi | 23.1.0 | MIT |
| python-dotenv | 1.0.1 | BSD-3-Clause |
| pyotp | 2.9.0 | MIT |
| cryptography | 44.0.2 | Apache-2.0 / BSD-3-Clause |
| PyYAML | 6.0.2 | MIT |

## 3. Biblioteki — frontend

Wersje z `web/package.json`. Interfejs nie korzysta z zewnętrznych bibliotek komponentów, czcionek sieciowych ani CDN.

| Biblioteka | Wersja | Licencja |
|---|---|---|
| React, react-dom | 19 | MIT |
| Vite | 6 | MIT |
| @vitejs/plugin-react | 4 | MIT |
| TypeScript | 5.7 | Apache-2.0 |

## 4. Narzędzia i usługi w kontenerach

| Narzędzie | Wersja / obraz | Licencja | Uwagi |
|---|---|---|---|
| nmap | pakiet Debian 12 (bookworm) | Nmap Public Source License (NPSL) | bezpłatny; licencja własna, niezatwierdzona przez OSI; narzędzie wskazane w treści zadania |
| ProjectDiscovery httpx | v1.6.9, budowany ze źródeł | MIT | zawiera reguły detekcji technologii (Wappalyzer, MIT) |
| Go (etap budowania httpx) | 1.23 | BSD-3-Clause | tylko w etapie build obrazu workera |
| PostgreSQL | 15 (`postgres:15-alpine`) | PostgreSQL License | baza SurfaceX |
| Redis | 7 (`redis:7-alpine`) | od 7.4 RSALv2 / SSPLv1 (wcześniej BSD-3) | bezpłatny do użytku, licencja niezatwierdzona przez OSI; zamiennik OSS: Valkey (BSD-3) |
| nginx | 1.27 (`nginx:1.27-alpine`) | BSD-2-Clause | gateway, serwowanie frontendu, cele demonstracyjne |
| Python | 3.12 (`python:3.12-slim-bookworm`) | PSF License | obrazy API i workera |
| Node.js | 22 (`node:22-bookworm-slim`) | MIT | tylko etap budowania frontendu |
| DefectDojo | 3.5.202 | BSD-3-Clause | opcjonalny profil; integracja przez API v2 |
| PostgreSQL (DefectDojo) | 18.6 | PostgreSQL License | baza opcjonalnego DefectDojo |
| Valkey (DefectDojo) | 9.1.2 | BSD-3-Clause | broker opcjonalnego DefectDojo |
| Docker Engine / Compose | — | Apache-2.0 | środowisko uruchomieniowe |

## 5. Materiały i usługi zewnętrzne

- Treść zadania i wymagania CBI AGH „Attack Surface Intelligence” (HackNation 2026).
- Dokumentacja API DefectDojo: https://demo.defectdojo.org/api/v2/oa3/swagger-ui/
- Dokumentacja nmap: https://nmap.org/docs.html
- Publiczne usługi odpytywane wyłącznie przez moduł `passive-discovery`: crt.sh (Certificate Transparency) i rdap.org (RDAP). Nie wymagają kluczy API; moduł jest opcjonalny.
- Szablony środowisk testowych dostarczone przez AGH — używane wyłącznie do testów, nie są częścią rozwiązania.

## 6. Oświadczenie zgodności (Regulamin zadania CBI AGH, §4)

- **§4 ust. 1–2:** członkowie zespołu są twórcami swojego wkładu i oświadczają, że rozwiązanie jest wolne od wad prawnych oraz nie narusza praw osób trzecich. Kod własny powstał w ramach zadania; kod stron trzecich jest używany wyłącznie jako zależności na licencjach wymienionych wyżej.
- **Licencje:** wszystkie zależności są bezpłatne i nie wymagają zakupu licencji. Dwie pozycje mają licencje niezatwierdzone przez OSI: **nmap (NPSL)** — narzędzie wskazane w treści zadania — oraz **Redis ≥ 7.4 (RSALv2/SSPLv1)**, który można zastąpić Valkey (BSD-3) bez zmian w kodzie aplikacji.
- **Przekazanie praw:** w razie wygranej przekazaniu podlega kod źródłowy i dokumentacja z tego repozytorium, zgodnie z §4 ust. 3–8.
- **Dane:** rozwiązanie skanuje wyłącznie zakres udostępniony przez AGH oraz własne środowiska testowe; nie przetwarza danych osobowych uczestników.

## 7. Pozostała dokumentacja

Pełna dokumentacja techniczna: [dokumentacja-techniczna.md](dokumentacja-techniczna.md). Znane ograniczenia rozwiązania opisuje jej rozdział 16.
