# SurfaceX — dokumentacja techniczna

> **Wzór do uzupełnienia.** Pola oznaczone `[DO WERYFIKACJI]` sprawdźcie i poprawcie przed wysłaniem. Reszta jest wypełniona na podstawie kodu i powinna się zgadzać.

## 1. Opis rozwiązania

SurfaceX to narzędzie do cyklicznego, bezpiecznego skanowania dużych sieci (ponad 10 000 IP): wykrywa aktywne hosty, usługi, technologie webowe, CMS-y, nagłówki i ciasteczka, własne sygnatury oraz rejestruje zmiany między kolejnymi skanami. Wyniki trafiają do dashboardu, eksportu JSON/CSV i do DefectDojo.

- **Zamawiający:** Centrum Bezpieczeństwa Informacji AGH (zadanie „Attack Surface Intelligence”).
- **Zespół:** `[DO WERYFIKACJI: imiona i nazwiska / role]`
- **Repozytorium:** https://github.com/Maciejbe04/attack-surface-intelligence

## 2. Architektura

```
Przeglądarka ─▶ Gateway (nginx) ─▶ API (Django REST) ─▶ PostgreSQL
                                        │
                                        ├─▶ Redis (kolejka)
                                        │        │
                                        │        ▼
                                        │   Worker (Celery) ── nmap, httpx, nuclei
                                        │        │
                                        └──◀─ wyniki przez wewnętrzne API (token)
                                        
Eksport ─▶ DefectDojo (API v2)
```

| Warstwa | Technologia |
|---|---|
| Backend / API | Django + Django REST Framework |
| Zadania w tle | Celery + Redis, Celery Beat (harmonogram, okna czasowe) |
| Baza | PostgreSQL |
| Frontend | React + TypeScript (Vite) |
| Narzędzia skanujące | nmap, ProjectDiscovery httpx |
| Uruchomienie | Docker Compose (`docker compose up`) |

- **Worker jest odizolowany:** nie zna hasła do bazy; wyniki odsyła do API tokenem (`X-Worker-Token`). Endpointy `/api/internal/` są zablokowane na gatewayu.
- **Skalowanie:** worker można zwielokrotnić (`docker compose up --scale worker=N`); globalne limity tempa dzielą się między procesy.

## 3. Uruchomienie

```bash
git clone https://github.com/Maciejbe04/attack-surface-intelligence.git
cd attack-surface-intelligence
cp .env.example .env
./scripts/init-secrets.sh      # generuje sekrety (hasła, klucze)
docker compose up --build
```

- UI: `http://localhost:8080` `[DO WERYFIKACJI: port na serwerze, np. 18080]`
- Domyślne konto: `admin` / `changeme` (zmień `BOOTSTRAP_ADMIN_PASSWORD` w `.env`).
- Testy backendu bez Dockera: `cd backend && python manage.py test apps --settings=config.settings_test`

## 4. Przepływ skanu

1. **Wejście:** formularz lub import CSV/JSON (IP, CIDR, domeny). Każdy cel przechodzi przez walidację i allowlistę.
2. **Podział:** duże zakresy CIDR dzielone na paczki (np. /24), każda z własnym pomiarem czasu i budżetem.
3. **Discovery:** nmap wykrywa aktywne hosty i porty (bez `-Pn` dla zakresów), potem `-sV` identyfikuje usługi.
4. **HTTP/HTTPS:** httpx zbiera tytuł, kod, nagłówki, ciasteczka, certyfikat TLS, technologie.
5. **Fingerprinting i sygnatury:** silnik reguł YAML dopasowuje nagłówki, ciasteczka, favicon, regex w HTML i ścieżki.
6. **Normalizacja i porównanie:** obserwacje zapisywane w bazie; liczony diff z poprzednim skanem (NEW / CHANGED / MISSING / GONE / FLAKY).
7. **Eksport:** JSON/CSV i DefectDojo (findingi informacyjne).

## 5. Kontrola intensywności i bezpieczeństwo działania

- Globalny limit tempa (nmap pakiety/s, httpx żądania/s) dzielony między workery.
- Budżet czasu na paczkę (poniżej miękkiego limitu Celery); nmap kończy sam, zamiast być zabity.
- Okna czasowe: skan zatrzymuje się na końcu okna i wznawia w następnym.
- Brak brute force, logowania do celów, exploitacji; przekierowania nie są śledzone.
- Allowlista globalna: skanowane są tylko zatwierdzone zakresy; cel spoza zakresu jest odrzucany przy zapisie i w workerze po rozwiązaniu DNS.

## 6. Role (RBAC)

| Rola | Zakres |
|---|---|
| admin | użytkownicy, role, allowlista, ustawienia globalne, audit log, pełny dostęp |
| operator | cele, grupy, skany, harmonogramy, sygnatury, allowlista, import, edycja znalezisk |
| analityk | odczyt, edycja znalezisk (tagi, notatki, nadpisania), eksport, import wyników |
| viewer | tylko odczyt |

Dane (cele, skany, grupy, wyniki, allowlista) są wspólne dla zespołu; rola decyduje o tym, co wolno zmieniać. Uprawnienia egzekwowane w API. Szczegóły: `docs/rbac.md`.

## 7. Import / eksport i integracje

- **Import celów:** CSV/JSON (`POST /api/targets/import/`).
- **Eksport wyników:** `GET /api/scans/<id>/export/?format=json|csv`.
- **Import wyników:** `POST /api/observations/import/`.
- **DefectDojo:** `POST /api/scans/<id>/export/defectdojo/` — findingi informacyjne przez API v2 (`reimport-scan`). Konfiguracja: `DEFECTDOJO_URL`, `DEFECTDOJO_API_TOKEN` w `.env`.

## 8. Bezpieczeństwo danych

- Hasła: Argon2id. Sekrety w plikach Dockera (`0600`), nie w repozytorium.
- Wrażliwe dowody skanów szyfrowane AES-256-GCM (`app_data_key`).
- Dziennik audytu: logowania, zlecenia skanów, eksporty, zmiany allowlisty, edycje znalezisk.
- Znane ograniczenia wersji hackathonowej (celowo otwarte na czas pracy): `docs/known-security-limitations.md`.

## 9. Elementy wykonane z pomocą AI, biblioteki i licencje

Patrz `docs/ai-and-dependencies.md`. `[DO WERYFIKACJI: uzupełnić narzędzia AI użyte przez zespół]`

## 10. Co oddajemy

- Repozytorium + ta dokumentacja.
- Prezentacja do 10 slajdów z działającym demo `[robimy ręcznie]`.
- Scenariusz demo: `docs/demo-script.md`.
