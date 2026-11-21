# Lab demo SurfaceX

Scenariusz jury na trzech małych LXC ze stroną statyczną (`lab-lxc`).

## Hosty labowe (Proxmox / lxcvnet)

| CT | Hostname | IP | Strona |
|---|---|---|---|
| 220 | lab-web-a | `10.99.0.70` | Lab Alpha |
| 221 | lab-web-b | `10.99.0.71` | Lab Bravo |
| 222 | lab-web-c | `10.99.0.72` | Lab Charlie |

Root na LXC: `LabTest#2026`. HTTP `:80` (nginx).

## Szybka ścieżka (UI)

1. Zaloguj się jako `admin` lub `operator`.
2. Zakładka **Allowlist** — upewnij się, że są `10.99.0.70–72` (live już zseedowane dla admin/jacek).
3. **Targets → Import** — wgraj `demo/targets.json` (lub użyj istniejącej grupy `lab-lxc`).
4. Uruchom skan grupy **`lab-lxc`** z oknem np. 15 minut (`window_seconds`).
5. Po zakończeniu: Findings → lifecycle `NEW`, technologies / confidence, Compare.
6. Jako `analyst` dodaj override/notatkę na `10.99.0.70`.
7. Zmień lab (poniżej), uruchom drugi skan, pokaż `CHANGED` / `MISSING`.
8. Eksport CSV/JSON + opcjonalnie DefectDojo.

## Zmiany między skanami (na LXC)

```bash
# Host A — zmiana tytułu (CHANGED)
pct exec 220 -- bash -lc 'sed -i "s/Lab Alpha/Lab Alpha CHANGED/" /var/www/html/index.html'

# Host C — wyłączenie HTTP (MISSING przy kolejnym completed run)
pct exec 222 -- systemctl stop nginx

# Po demo przywróć:
pct exec 220 -- bash -lc 'sed -i "s/Lab Alpha CHANGED/Lab Alpha/" /var/www/html/index.html'
pct exec 222 -- systemctl start nginx
```

## Okno skanu (kill)

Przy `window_seconds` krótszym niż czas skanu unfinished batche przechodzą w `PAUSED`, worker dostaje `cancel_requested` i zabija nmap/httpx. Resume wznawia tylko wstrzymane batche.

## Pliki

- `targets.json` — import celów labowych
- `allowlist.json` — referencyjna lista (UI CRUD; brak bulk API)
- Kroki jury: `docs/demo-script.md`
