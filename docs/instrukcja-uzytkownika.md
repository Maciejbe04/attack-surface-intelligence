# Instrukcja użytkownika

Jak wykonać w SurfaceX typową pracę: dodać cele, uruchomić dwa skany, obejrzeć zmiany, opisać znalezisko, zaimportować i wyeksportować dane oraz zarządzać rolami. Uruchomienie stosu opisuje [README](../README.md).

Interfejs jest dostępny pod `http://localhost:8080`. Język (polski / angielski), tryb ciemny i wysoki kontrast przełącza się w nagłówku. Nazwy przycisków poniżej podano w wersji angielskiej.

## Zakładki

| Zakładka | Do czego służy | Kto może zmieniać |
|---|---|---|
| **Dashboard** | wybór modułów skanu, skan pojedynczego hosta, konsola aktywności, Curiosity, Changes over time, Latest findings | `admin`, `operator` |
| **Targets** | lista celów, dodawanie, import pliku, przypisywanie do grup, skan zaznaczonych | `admin`, `operator` |
| **Groups** | grupy hostów, skan grupy, harmonogram | `admin`, `operator` |
| **Scans** | historia przebiegów, log, Findings, Compare, eksport, Resume, Cancel | start i przerwanie: `admin`, `operator`; korekty i eksport: także `analyst` |
| **Allowlist** | zatwierdzone zakresy skanowania | `admin` |
| **Users** | konta i role (widoczna tylko dla `admin`) | `admin` |
| **System** | wersje komponentów, stan integracji DefectDojo, dziennik audytu (`admin`) | — |

Rola `viewer` widzi wszystkie dane, ale nie ma żadnych formularzy ani przycisków zmieniających stan.

## 1. Zakres: allowlista

Skaner odpyta tylko adresy objęte allowlistą.

1. Zaloguj się jako `admin` i otwórz **Allowlist**.
2. Dodaj wpis: pojedynczy adres IP, zakres CIDR (np. `10.77.0.0/24`) albo domenę (obejmuje też subdomeny).
3. Zbędny wpis usuń. Wyłączenie wpisu bez usuwania jest dostępne przez API (`PATCH /api/allowlist/{id}/`, pole `enabled`).

Dopóki allowlista jest pusta, system nie ogranicza zakresu — dodaj wpisy przed pracą na prawdziwej sieci.

## 2. Cele

**Ręcznie.** Zakładka **Targets** → **Add target**: adres IP, CIDR (do 4096 adresów) lub domena oraz opcjonalny komentarz.

**Z pliku.** Zakładka **Targets** → **Import hosts**:

- TXT — jeden adres w linii;
- CSV — kolumna `value` (albo `address` / `host`), opcjonalnie `type`, `comment`, `group`;
- JSON — obiekt z listą `targets`.

Limit to 10 000 celów i 5 MiB. Podczas importu można wskazać grupę (istniejącą albo nową) i od razu uruchomić skan (**Import and scan**) modułami wybranymi na Dashboardzie. Niepoprawne adresy, duplikaty i cele spoza allowlisty są pomijane i wymienione w podsumowaniu importu.

Przykład: [`demo/lab/targets.csv`](../demo/lab/targets.csv).

**Grupy.** Zaznacz hosty na liście i użyj **Add selected to group** albo utwórz grupę w zakładce **Groups** (**Create group**). Host może należeć do wielu grup.

Duży zakres (ponad 10 000 adresów) wprowadź jako listę podsieci `/24`, po jednej w wierszu — każda staje się osobną porcją pracy, wykonywaną równolegle.

## 3. Skan

1. Na **Dashboardzie** zaznacz moduły (**Discovery modules**). `full-pipeline` wykonuje cały łańcuch: porty, usługi, HTTP, TLS i sygnatury. Pozostałe moduły można łączyć dowolnie i dostrajać filtrami (**Module filters**), np. profil portów, tempo, porty IoT/OT.
2. Uruchom skan jednym ze sposobów:
   - pojedynczy host: wyszukaj go na Dashboardzie i kliknij **Run selected**;
   - zaznaczone hosty: **Targets** → **Scan selected**;
   - cała grupa: **Groups** → **Scan now**.
3. `admin` może wybrać okno skanu (**Scan window**: 30 min, 1 h, 2 h). Pozostałe role mają stałe okno 1 h.
4. Postęp, prognozę czasu zakończenia i komendy uruchamiane przez worker pokazuje **Activity console**.

**Przerwanie i wznowienie.** **Cancel** kończy skan. Po przekroczeniu okna czasowego skan zatrzymuje się sam, a przy przebiegu pojawia się **Resume** — wznowienie dokańcza tylko niewykonane porcje.

**Harmonogram.** **Groups** → **Edit schedule**: co N godzin, codziennie albo co tydzień o podanej godzinie UTC. Harmonogram zapamiętuje moduły zaznaczone w chwili zapisu.

## 4. Wyniki i znaleziska

Zakładka **Scans** → wybierz przebieg → **Findings**. Lista zawiera hosty, porty, endpointy HTTP, technologie, certyfikaty i trafienia sygnatur. Dla każdej pozycji widać:

- stan względem poprzedniego skanu: `NEW`, `CHANGED`, `UNCHANGED`, `MISSING`, `FLAKY`, `GONE`;
- ocenę ciekawości (**Curiosity**) dla portów;
- dla HTTP: tytuł, kod, serwer, ciekawe nagłówki, brakujące nagłówki bezpieczeństwa i ciasteczka z flagami.

Listę można filtrować po stanie i typie obserwacji.

### Edycja znaleziska

1. Przy wybranej pozycji kliknij **Add override** (albo **Edit override**).
2. Wpisz tagi (oddzielone przecinkami) i notatkę, zapisz przez **Save override**.

Korekta jest przypięta do obserwacji, a nie do skanu: można ją zmieniać w dowolnym momencie i pozostaje widoczna po każdym kolejnym skanie. Dane ze skanera pozostają nietknięte. Korekty mogą edytować `admin`, `operator` i `analyst`.

## 5. Zmiany między skanami

1. Uruchom drugi skan **tej samej grupy** (albo tej samej listy hostów) **tymi samymi modułami** — tylko takie przebiegi są porównywane.
2. W **Findings** drugiego przebiegu każda pozycja ma stan względem poprzedniego ukończonego skanu.
3. **Compare** pokazuje zestawienie: dodane, usunięte i zmienione obserwacje wraz z wartościami przed i po. Można wskazać, z którym wcześniejszym przebiegiem porównać.

Jak czytać stany znikających usług:

| Kolejny pełny skan bez odpowiedzi | Stan |
|---|---|
| pierwszy | `MISSING` |
| drugi | `FLAKY` |
| trzeci i dalsze | `GONE` |

Usługa, która wróciła po nieobecności, jest oznaczana `FLAKY`. Skan przerwany lub niepełny nie zmienia tych stanów.

Wykres **Changes over time** na Dashboardzie pokazuje liczbę zmian w zakresie 24 h, 7 dni, 30 dni lub całej historii.

## 6. Eksport i import wyników

- **Export JSON** / **Export CSV** przy przebiegu w zakładce **Scans** — dostępne po zakończeniu skanu dla ról `admin`, `operator`, `analyst`.
- Import wyników: `POST /api/observations/import/` z plikiem JSON w formacie eksportu (`surfacex.export.v1`). Powstaje ukończony przebieg ze źródłem `import`, widoczny w zakładce **Scans** jak każdy inny.

```bash
curl -b cookies.txt -H 'Content-Type: application/json' \
  --data @scan-12.json http://localhost:8080/api/observations/import/
```

Formaty plików: [import-export.md](import-export.md).

## 7. DefectDojo

Po każdym zakończonym skanie wyniki trafiają automatycznie do DefectDojo (`http://localhost:8081`). Status wysyłki widać przy przebiegu w zakładce **Scans**, a konfigurację integracji w zakładce **System**. Każdy host, usługa i technologia jest osobnym findingiem w produkcie „Attack Surface”; ponowny skan aktualizuje istniejące findings.

## 8. Użytkownicy i role

Zakładka **Users** (tylko `admin`): utworzenie konta, wybór roli, zmiana hasła, blokada i usunięcie.

| Rola | Uprawnienia |
|---|---|
| `admin` | wszystko, w tym użytkownicy, allowlista, dziennik audytu, dłuższe okno skanu |
| `operator` | cele, grupy, harmonogramy, uruchamianie i przerywanie skanów, import celów |
| `analyst` | korekty znalezisk, import wyników, eksport |
| `viewer` | tylko odczyt |

Próba wykonania niedozwolonej operacji przez API kończy się odpowiedzią `403`. Dziennik audytu (zakładka **System**, rola `admin`) zawiera m.in. nieudane logowania, zmiany celów i allowlisty, uruchomienia skanów, eksporty i korekty.

Drugi składnik logowania (TOTP): [auth-mfa.md](auth-mfa.md).

## 9. Własna sygnatura

1. Dodaj plik YAML do katalogu `signatures/` — format i przykłady: [signatures.md](signatures.md).
2. Przebuduj obrazy: `docker compose up --build -d api worker`.
3. Uruchom skan z modułem `signatures` albo `full-pipeline`. Trafienia pojawią się w **Findings** jako pozycje typu sygnatura, z poziomem pewności i listą dopasowanych reguł.
