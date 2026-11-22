# Demo lab: cel ze zmieniającymi się portami

Lekki kontener (sam Python, bez zależności), który co `PHASE_SECONDS` (domyślnie 90 s) przechodzi do kolejnej fazy: otwiera i zamyka porty, zmienia banery, wersje, nagłówki i ciasteczka. Dzięki temu kolejne skany pokazują NEW / CHANGED / MISSING / GONE / FLAKY oraz ciekawe nagłówki i sygnatury. Do testów i demo.

## Uruchomienie

```bash
docker compose -f deploy/demo-lab/compose.yml up -d
```

- **Cel do skanowania:** `172.30.0.20` (sieć `surfacex-demo-lab`). Żeby worker SurfaceX go widział, podłącz go do tej sieci i dodaj `172.30.0.0/24` do allowlisty:
  ```bash
  docker network connect surfacex-demo-lab <kontener-workera>
  ```
- **Panel sterowania (tylko lokalnie):** `http://127.0.0.1:18765/state` (co jest otwarte) i `http://127.0.0.1:18765/next` (przeskocz fazę ręcznie na demo).
- **Tryb ręczny:** `PHASE_SECONDS=0 docker compose -f deploy/demo-lab/compose.yml up -d` — fazy zmieniają się tylko przez `/next`.

## Fazy

| Faza | Otwarte porty | Co pokazuje |
|---|---|---|
| A baseline | 2222, 8080, 8787, 9000 | wszystko NEW; ciekawe nagłówki (X-Powered-By, X-Debug-Token, X-Backend-Server) |
| B changes | 2222, 5000, 8080 | 8787/9000 MISSING, 8080 CHANGED, 5000 NEW (panel admina) |
| C returns | 2222, 5000, 8080, 8787, 9000 | 8787/9000 wracają jako FLAKY, SSH zmienia wersję |
| D exposure | 21, 2222, 8080, 8787 | 21 NEW (stary FTP), panel admina MISSING |

Profil skanu: port-scan custom `21,2222,5000,8080,8787,9000` + service-detect + http-fingerprint.

Usługi to atrapy (same banery i statyczne strony, bez logowania i danych). Kontener działa w izolowanej sieci, tylko do odczytu, z limitem 48 MB; na zewnątrz wystawiony jest wyłącznie panel sterowania na `127.0.0.1`.
