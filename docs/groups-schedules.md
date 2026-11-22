# Grupy hostów i harmonogramy

## Model

| Encja | Opis |
|---|---|
| `TargetGroup` | nazwana grupa celów jednego właściciela; nazwa unikalna per właściciel (bez rozróżniania wielkości liter) |
| `TargetGroup.targets` | relacja wiele-do-wielu: host może należeć do kilku grup |
| `GroupSchedule` | maksymalnie jeden harmonogram na grupę |
| `ScanRun.group` / `ScanRun.schedule` | skąd pochodzi przebieg (skan grupy, import do grupy, harmonogram) |

Usunięcie grupy nie usuwa hostów ani dotychczasowych skanów (`SET_NULL`). Do grupy można dodać wyłącznie cele jej właściciela — także wtedy, gdy grupę edytuje `admin`.

## Uprawnienia

Odczyt grup: każdy zalogowany użytkownik (w zakresie własnych grup; `admin` widzi wszystkie). Tworzenie, zmiana członków, skan, harmonogram i usuwanie: `admin` i `operator`.

## API

| Metoda | Ścieżka | Opis |
|---|---|---|
| `GET` | `/api/targets/?search=&group=&limit=` | wyszukiwarka hostów; `search` przeszukuje adres i komentarz, `limit` (1–100) zwraca najpierw dokładne i prefiksowe dopasowania adresu |
| `GET`, `POST` | `/api/groups/` | lista (z `target_count` i `schedule`) / utworzenie `{name, description}` |
| `GET`, `PATCH`, `DELETE` | `/api/groups/<id>/` | szczegóły / zmiana nazwy lub opisu / usunięcie |
| `POST` | `/api/groups/<id>/targets/` | `{action: "add" | "remove", target_ids: []}`; odpowiedź zawiera `changed_count` |
| `POST` | `/api/groups/<id>/scan/` | `{modules, client_request_id, window_seconds?}` — skan wszystkich hostów grupy (limit 10 000) |
| `PUT`, `DELETE` | `/api/groups/<id>/schedule/` | zapis / usunięcie harmonogramu |

Każdy cel w odpowiedziach ma `groups: [{id, name}]`, a każdy skan `group_id`, `group_name` i `scheduled`.

`window_seconds` jest opcjonalne, ale sam deadline jest obowiązkowy. Brak pola oznacza globalną wartość domyślną (1 h). Użytkownik inny niż `admin` nie może żądać wartości większej niż 3600 s; UI nie pokazuje mu selektora i zawsze wysyła 1 h. Administrator może wybrać 30 min, 1 h lub 2 h.

## Harmonogram

```json
{
  "enabled": true,
  "frequency": "weekly",
  "interval_hours": 24,
  "time_of_day": "02:30",
  "weekday": 0,
  "modules": [{"id": "full-pipeline", "filters": {}}]
}
```

| `frequency` | Znaczenie |
|---|---|
| `hourly` | co `interval_hours` (1–168) godzin, licząc od zapisania i od każdego uruchomienia |
| `daily` | codziennie o `time_of_day` (UTC) |
| `weekly` | w dniu `weekday` (0 = poniedziałek … 6 = niedziela) o `time_of_day` (UTC) |

Moduły są zapisywane jako snapshot w momencie zapisu harmonogramu (UI bierze moduły zaznaczone na pulpicie). Każdy zapis przelicza `next_run_at`; wyłączony harmonogram nie ma następnego uruchomienia.

## Wykonanie

1. Celery Beat co 60 s publikuje `scans.dispatch_schedules` do kolejki `scan`.
2. Worker (bez dostępu do bazy) wywołuje `POST /api/internal/schedules/dispatch/` z `X-Worker-Token`.
3. API blokuje należne harmonogramy (`SELECT … FOR UPDATE SKIP LOCKED`, do 20 na wywołanie) i dla każdego tworzy przebieg dla wszystkich hostów grupy.
4. `client_request_id = schedule:<id>:<termin>` gwarantuje jeden przebieg na termin, nawet przy ponowieniu zadania.
5. Po zakończeniu skanu działa standardowy automatyczny eksport do DefectDojo.

Zasady:

- jeśli poprzedni przebieg z harmonogramu nadal trwa, termin jest pomijany (`last_status`), a następny wyliczany normalnie — skany się nie nakładają;
- pusta grupa lub nieprawidłowy snapshot modułów dają pominięcie z opisem w `last_status`;
- terminy przegapione podczas przestoju (np. wyłączony stos) wykonują się raz, bez nadrabiania wszystkich zaległych;
- dokładność to około minuty; przy zajętych workerach zadanie dyspozytora czeka w tej samej kolejce co skany, więc start może się opóźnić.
