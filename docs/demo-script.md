# Scenariusz demonstracyjny

Cel: pokazać dwa pełne przebiegi skanu oraz eksport zmian w czasie poniżej 15 minut.

## Przygotowanie

1. Uruchomić lokalny lab z co najmniej:
   - hostem A: HTTP na `:80` z nagłówkiem `Server: nginx`;
   - hostem B: HTTPS na `:443` z certyfikatem ważnym > 30 dni;
   - hostem C: tymczasowo wyłączonym przed drugim skanem.
2. Zaimportować cele z `demo/targets.json`.
3. Zalogować się jako `operator`.

## Przebieg 1

1. Utworzyć profil `discovery-web`.
2. Uruchomić skan na allowlistowanym zakresie lab.
3. Pokazać postęp, ETA i metadane trybu nmap.
4. Po zakończeniu wskazać:
   - hosty `NEW`;
   - wykryty nginx z confidence ≥ 40;
   - certyfikat hosta B;
   - evidence z httpx.
5. Jako `analyst` dodać notatkę i tag do hosta A.

## Zmiana środowiska

Przed drugim skanem:

1. zmienić tytuł strony na hoście A;
2. wymienić albo skrócić ważność certyfikatu na hoście B;
3. wyłączyć host C;
4. dodać nowy host D z otwartym `:8080`.

## Przebieg 2

1. Uruchomić ten sam profil.
2. Pokazać stany:
   - host A / tytuł: `CHANGED`;
   - certyfikat B: `CHANGED`;
   - host C: `MISSING`;
   - host D: `NEW`.
3. Potwierdzić, że notatka i tag z przebiegu 1 pozostały na hoście A.
4. Opcjonalnie wykonać trzeci i czwarty przebieg bez hosta C, aby pokazać przejście `MISSING → FLAKY/GONE`.

## Eksport i RBAC

1. Wyeksportować wynik do CSV i JSON.
2. Zalogować się jako `viewer` i pokazać brak przycisków zapisu.
3. Spróbować startu skanu jako `analyst` — oczekiwane `403`.
4. Pokazać wpisy w `audit_log` jako `admin`.

## Kryteria sukcesu demo

- dwa ukończone skany;
- widoczne `NEW` i `CHANGED`;
- zachowany manual override;
- eksport CSV/JSON zgodny ze schematem `1`;
- brak procesów nmap/httpx po zamknięciu okna lub zakończeniu demo.
