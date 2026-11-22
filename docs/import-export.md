# Import i eksport

## Import celów

```http
POST /api/targets/import/
Content-Type: multipart/form-data
```

Role: `admin`, `operator`. W UI: zakładka **Targets** → **Import hosts**.

| Pole | Opis |
|---|---|
| `file` | plik TXT, CSV albo JSON (rozpoznawany po rozszerzeniu lub zawartości) |
| `start_scan` | domyślnie `true` — po imporcie kolejkuje skan zaimportowanych celów |
| `modules` | opcjonalny JSON z modułami skanu; domyślnie `full-pipeline` |
| `group_id` | ID istniejącej grupy, do której trafią wszystkie cele z pliku |
| `group_name` | alternatywnie nazwa grupy; tworzona, jeśli nie istnieje (bez rozróżniania wielkości liter) |

Limity: **10 000 celów** i **5 MiB** na plik; zakres CIDR do 4096 adresów.

### TXT

Jeden adres w linii (IP, CIDR albo domena). Typ celu jest rozpoznawany automatycznie.

### CSV

Wymagana kolumna z adresem: `value` (albo `address`, `host`, `target`, `ip`). Kolumny opcjonalne: `type` (`ip` / `cidr` / `domain`), `comment` (albo `notes`), `group` (albo `groups`, `group_name`). Pozostałe kolumny są ignorowane.

```csv
value,type,comment,group
10.77.0.10,ip,Strona wydziału (CMS),Lab demo
10.77.0.0/24,cidr,Podsieć laboratorium,Lab demo;DMZ
app.example.lab,domain,Portal,Web
```

### JSON

```json
{
  "schema_version": 1,
  "targets": [
    { "value": "10.0.0.0/24", "type": "cidr", "comment": "sieć testowa", "groups": ["lab", "dmz"] },
    { "value": "app.example.lab", "type": "domain", "comment": "portal" },
    { "value": "10.0.0.15" }
  ]
}
```

Element listy może być też samym napisem z adresem. `schema_version` inne niż `1` powoduje odrzucenie pliku.

### Grupy

Grupy można podać per wiersz (kolumna `group` w CSV, pole `group` / `groups` w JSON). Kilka grup rozdziela się `;` lub `|` (w JSON także listą). Brakujące grupy są tworzone. Grupa z formularza i grupy z wierszy sumują się.

### Walidacja

- każdy adres przechodzi tę samą normalizację co cel dodany ręcznie (IPv4/IPv6, kanoniczny CIDR, domena z obsługą IDN);
- niepoprawne wiersze są pomijane i zwracane w `parse_errors` (do 50 komunikatów);
- duplikaty w pliku są liczone w `skipped_duplicates_in_file`, a cele już istniejące w `existing_count`;
- cele spoza allowlisty są odrzucane.

Odpowiedź zawiera `created_count`, `existing_count`, `total_count`, `target_ids`, `groups[]` (`{id, name, created, added_count}`) oraz `scan` z utworzonym przebiegiem, jeśli skan został uruchomiony.

## Eksport wyników

```http
GET /api/scans/<id>/export/?format=json
GET /api/scans/<id>/export/?format=csv
```

Role: `admin`, `operator`, `analyst`. Eksportować można tylko zakończony przebieg (inaczej HTTP 409). Każdy eksport jest zapisywany w audycie (`scan.export`).

### JSON — `surfacex.export.v1`

Schemat: [`schemas/surfacex.export.v1.json`](../schemas/surfacex.export.v1.json).

```json
{
  "schema": "surfacex.export.v1",
  "exported_at": "2026-11-22T08:15:00+00:00",
  "run": {
    "id": 12,
    "status": "completed",
    "group_id": 3,
    "finished_at": "2026-11-22T08:14:31+00:00",
    "modules": [{ "id": "full-pipeline", "filters": {} }],
    "result_summary": { "lifecycle": { "NEW": 4, "CHANGED": 1, "MISSING": 1 } }
  },
  "observations": [
    {
      "id": 481,
      "entity_type": "port",
      "entity_key": "port:10.77.0.11:tcp/80",
      "lifecycle": "CHANGED",
      "target_address": "10.77.0.11",
      "attrs": { "address": "10.77.0.11", "port": 80, "protocol": "tcp", "service": "http", "product": "nginx", "version": "1.27.0" },
      "miss_streak": 0,
      "source": "scanner"
    }
  ]
}
```

### CSV

Jeden wiersz na obserwację:

```csv
entity_type,entity_key,lifecycle,target_address,source,miss_streak,attrs_json
port,port:10.77.0.11:tcp/80,CHANGED,10.77.0.11,scanner,0,"{""address"":""10.77.0.11"",""port"":80,""service"":""http""}"
```

Kolumna `attrs_json` zawiera atrybuty obserwacji jako JSON.

## Import wyników

```http
POST /api/observations/import/
Content-Type: application/json
```

Role: `admin`, `operator`, `analyst`. Przyjmowany jest JSON w formacie eksportu `surfacex.export.v1` (inna wartość pola `schema` jest odrzucana).

- Bez `run.id` powstaje nowy, ukończony przebieg oznaczony jako import.
- Z `run.id` obserwacje są dopisywane do istniejącego przebiegu (aktualizacja po `entity_key`).
- Obserwacje trafiają do tych samych tabel co wyniki skanera, ze źródłem `import`, i są widoczne w **Findings**, eksporcie i porównaniach.
- Import nie modyfikuje ręcznych korekt (`ManualOverride`).
- Operacja jest zapisywana w audycie (`observations.import`).

Odpowiedź: `{ "run_id": 13, "created": 42, "total": 42 }`.

Wyniki importuje się wyłącznie w formacie JSON; CSV służy do eksportu.

## DefectDojo

Po zakończeniu skanu z co najmniej jednym ukończonym batchem SurfaceX wysyła raport automatycznie. Ręczny fallback:

```http
POST /api/scans/<id>/export/defectdojo/
```

Eksporter tworzy raport `Generic Findings Import` i przesyła go przez `POST /api/v2/reimport-scan/`. Jako findings trafiają:

- aktywne hosty (poziom `Info`);
- otwarte porty i usługi wraz z produktem i wersją (poziom wg oceny ciekawości portu: `High`, `Medium`, `Low` albo `Info`);
- technologie wykryte przez httpx i sygnatury SurfaceX.

`unique_id_from_tool` jest stabilnym skrótem typu obserwacji, hosta, portu, protokołu, endpointu i technologii. Nie zawiera identyfikatora przebiegu, dzięki czemu ponowny eksport aktualizuje istniejące findings. Eksport ustawia `close_old_findings=false`, ponieważ pojedynczy przebieg może obejmować tylko część zapisanych celów.

Status wysyłki (`pending`, `sending`, `sent`, `failed`, `skipped`) jest zapisany przy przebiegu i widoczny na liście skanów. Wyniki modułu pasywnego nie są wysyłane; skan wyłącznie pasywny kończy eksport jako `skipped`.

Lokalny stos uruchamia się profilem `defectdojo`. Dla zewnętrznej instancji ustaw `DEFECTDOJO_URL` oraz `DEFECTDOJO_API_TOKEN`. Nazwy Product Type, Product, Engagement i Test konfiguruje się zmiennymi `DEFECTDOJO_*` z `.env.example`.
