# Scenariusz demonstracyjny

Cel: dwa pełne przebiegi skanu oraz eksport zmian w czasie poniżej 15 minut.

Lab referencyjny: trzy LXC ze stroną statyczną — szczegóły w [`demo/README.md`](../demo/README.md).

## Przygotowanie

1. Stos: `./scripts/init-secrets.sh && docker compose up --build -d`.
2. Lab HTTP (Proxmox lxcvnet albo lokalne odpowiedniki):
   - host A `10.99.0.70` — Lab Alpha (nginx);
   - host B `10.99.0.71` — Lab Bravo;
   - host C `10.99.0.72` — Lab Charlie (do wyłączenia przed drugim skanem).
3. Allowlista: wpisy IP `10.99.0.70–72` (tylko admin; operator ma podgląd).
4. Import celów z [`demo/targets.json`](../demo/targets.json) albo użyj grupy `lab-lxc`.
5. Zaloguj się jako `operator` (albo `admin`).

## Przebieg 1

1. Uruchom skan grupy `lab-lxc` (moduł full-pipeline). Opcjonalnie ustaw krótkie okno, żeby pokazać pause/kill.
2. Pokaż postęp, ETA i tryb nmap (`syn` / `connect`) w konsoli skanu.
3. Po zakończeniu wskaż:
   - hosty `NEW`;
   - fingerprint / confidence (np. nginx / lab headers);
   - evidence HTTP;
   - **Ciekawość** na dashboardzie (hosty, porty, login paths).
4. Jako `analyst` dodaj notatkę/override do hosta A (`10.99.0.70`).

## Zmiana środowiska

Przed drugim skanem (na Proxmox):

```bash
pct exec 220 -- bash -lc 'sed -i "s/Lab Alpha/Lab Alpha CHANGED/" /var/www/html/index.html'
pct exec 222 -- systemctl stop nginx
```

Opcjonalnie dodaj nowy host D do grupy.

## Przebieg 2

1. Uruchom ten sam zakres / grupę.
2. Findings / Compare:
   - host A tytuł: `CHANGED`;
   - host C: `MISSING` (po completed run bez odpowiedzi);
   - override z przebiegu 1 nadal widoczny na A.
3. Trzeci completed run bez C → ścieżka do `FLAKY`/`GONE`.

## Eksport i RBAC

1. Eksport CSV i JSON (`schema_version` 1).
2. Opcjonalnie DefectDojo — status w liście skanów.
3. `viewer` — brak zapisu; `analyst` — brak startu skanu (403); `admin` — audit log.

## Okno skanu (kill)

Przy przekroczonym `window_seconds`: unfinished → `PAUSED`, worker dostaje `cancel_requested` i kończy nmap/httpx; late complete jest odrzucany. **Resume** wznawia tylko wstrzymane batche.

## Kryteria sukcesu demo

- dwa ukończone skany;
- widoczne `NEW` i `CHANGED` (oraz `MISSING` po wyłączeniu C);
- zachowany manual override;
- eksport CSV/JSON;
- brak osieroconych procesów nmap/httpx po cancel/deadline.
