# Źródła, narzędzia, wykorzystanie AI i zgodność z regulaminem

Dokument wymagany do zgłoszenia: elementy wykonane z pomocą AI, użyte biblioteki, frameworki, narzędzia, materiały zewnętrzne oraz ich licencje. Pola `[DO UZUPEŁNIENIA]` sprawdźcie i wypełnijcie przed wysłaniem.

## 1. Elementy wykonane z pomocą AI

Projekt powstał z wykorzystaniem asystentów AI. Cały wygenerowany kod został przejrzany, uruchomiony i przetestowany przez zespół (`python manage.py test apps --settings=config.settings_test`).

| Narzędzie AI | Kto | Zakres (przykładowo) |
|---|---|---|
| `[DO UZUPEŁNIENIA: np. Cursor / GitHub Copilot / Claude]` | `[członek zespołu]` | `[np. backend skanów, model danych, frontend, compose, integracja DefectDojo]` |
| Claude Code (Anthropic) | `[członek zespołu]` | wspólna przestrzeń zespołu i globalna allowlista; limity intensywności skanu; wykrywanie aktywnych hostów; zbieranie i analiza ciekawych nagłówków/ciasteczek; favicon/body dla sygnatur; checkbox skanowania IoT/OT; pomijanie RDAP dla adresów prywatnych; backend MFA; dokumentacja techniczna; testy do powyższych |

> Uwaga: lista powyżej jest przykładowa. Uzupełnijcie o faktyczne narzędzia i zakresy każdego członka zespołu.

## 2. Biblioteki i frameworki — backend (Python)

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

| Biblioteka | Wersja | Licencja |
|---|---|---|
| React, react-dom | 19 | MIT |
| Vite | 6 | MIT |
| @vitejs/plugin-react | 4 | MIT |
| TypeScript | 5.7 | Apache-2.0 |

## 4. Narzędzia i usługi w kontenerach

| Narzędzie | Licencja | Uwagi |
|---|---|---|
| nmap | Nmap Public Source License (NPSL) | darmowy; licencja własna, **nie zatwierdzona przez OSI** — do weryfikacji z wymaganiami |
| ProjectDiscovery httpx | MIT | |
| PostgreSQL 16 | PostgreSQL License (zbliżona do MIT/BSD) | |
| Redis 7 | od 7.4 RSALv2 / SSPLv1 (wcześniej BSD-3) | darmowy do użytku, **nie OSI**; zamiennik OSS: Valkey (BSD-3) — do weryfikacji |
| nginx | BSD-2-Clause | gateway i serwowanie frontendu |
| DefectDojo | BSD-3-Clause | integracja przez API v2 |
| Python (obraz bazowy) | PSF License | |
| Node.js (obraz bazowy, build frontendu) | MIT | |

## 5. Materiały zewnętrzne

- Treść zadania i wymagania AGH CBI „Attack Surface Intelligence” (HackNation 2026).
- Dokumentacja API DefectDojo: https://demo.defectdojo.org/api/v2/oa3/swagger-ui/
- Dokumentacja nmap: https://nmap.org/docs.html
- Baza reguł detekcji technologii (silnik Wappalyzer w httpx), licencja MIT.
- Szablony środowisk testowych dostarczone przez AGH (`lab.zip`) — używane wyłącznie do testów, nie są częścią rozwiązania.

## 6. Oświadczenie zgodności (Regulamin CBI AGH, §4)

- **§4.1–4.2:** Zespół jest twórcą swojego wkładu i oświadcza, że rozwiązanie jest wolne od wad prawnych oraz nie narusza praw osób trzecich. Cały kod własny powstał w ramach zadania; kod stron trzecich użyto wyłącznie jako zależności na wolnych/otwartych licencjach wymienionych wyżej.
- **Licencje:** wszystkie zależności są darmowe/open source. Dwie pozycje do potwierdzenia pod kątem definicji „open source / bez licencji” z treści zadania: **nmap (NPSL)** i **Redis ≥ 7.4 (RSALv2/SSPL)** — oba są darmowe w użyciu, ale ich licencje nie są zatwierdzone przez OSI. W razie wątpliwości Redis można zastąpić Valkey (BSD-3), a nmap pozostaje standardem w zadaniu („narzędzia typu nmap”).
- **Przekazanie praw:** w razie wygranej przekazaniu podlega kod źródłowy i dokumentacja (ta w katalogu `docs/`), zgodnie z §4.6–4.8.
- **Dane:** rozwiązanie skanuje wyłącznie zakres udostępniony przez AGH / własne środowiska testowe; nie przetwarza danych osobowych uczestników.

## 7. Pozostała dokumentacja

Pełna dokumentacja techniczna: `docs/dokumentacja-techniczna.md`. Pozostałe dokumenty szczegółowe: architektura, model danych, RBAC, szyfrowanie, polityka skanowania, sygnatury, import/eksport, znane ograniczenia bezpieczeństwa.
