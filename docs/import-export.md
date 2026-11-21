# Import i eksport

## Wersjonowanie

Każdy plik CSV/JSON zawiera pole lub kolumnę `schema_version`. MVP używa `1`.

Nieznana wersja schematu powoduje odrzucenie importu z czytelnym błędem.

## Import celów

Endpoint:

```http
POST /api/targets/import/
Content-Type: multipart/form-data
```

Pola:

- `file` — TXT (jeden host w linii), CSV (`value`/`address`/`host`) lub JSON (`targets[]`)
- `start_scan` — domyślnie `true`; po imporcie kolejkuje skan
- `modules` — opcjonalny JSON wybranych modułów (domyślnie `full-pipeline`)
- `group_id` — opcjonalne ID istniejącej grupy; wszystkie hosty z pliku do niej trafiają
- `group_name` — alternatywnie nazwa grupy; tworzona, jeśli nie istnieje (porównanie bez rozróżniania wielkości liter)
- limit: 10 000 hostów / 5 MiB

Grupy można też podać per wiersz: kolumna `group` (lub `groups`, `group_name`) w CSV albo pole `group`/`groups` w JSON. Kilka grup rozdziela się `;` lub `|` (w JSON także listą). Brakujące grupy są tworzone. Host występujący w pliku kilka razy trafia do wszystkich wymienionych grup. Grupa z formularza i grupy z wierszy sumują się.

```csv
address,group,comment
10.0.0.10,DMZ;Web,front
10.0.0.11,DMZ,
```

Odpowiedź zawiera `groups[]`: `{id, name, created, added_count}` dla każdej grupy, do której coś dodano. Skan uruchomiony przez import z `group_id`/`group_name` jest oznaczony tą grupą.

### JSON

```json
{
  "schema_version": 1,
  "targets": [
    {
      "value": "10.0.0.0/24",
      "type": "cidr",
      "tags": ["lab", "dmz"],
      "allowlisted": true,
      "notes": "sieć testowa"
    },
    {
      "value": "app.example.lab",
      "type": "domain",
      "tags": ["web"],
      "allowlisted": true
    },
    {
      "value": "10.0.0.15",
      "type": "ip",
      "tags": ["jump"],
      "allowlisted": true
    }
  ]
}
```

### CSV

```csv
schema_version,value,type,tags,allowlisted,notes
1,10.0.0.0/24,cidr,"lab;dmz",true,sieć testowa
1,app.example.lab,domain,web,true,
1,10.0.0.15,ip,jump,true,
```

## Import wyników obserwacji

Import przechodzi przez ten sam pipeline normalizacji co wyniki workerów. Źródło ustawiane jest na `import`.

### JSON

```json
{
  "schema_version": 1,
  "source": "import",
  "observed_at": "2026-11-21T12:00:00Z",
  "observations": [
    {
      "host": "10.0.0.15",
      "port": 443,
      "protocol": "tcp",
      "service": "https",
      "http": {
        "url": "https://10.0.0.15/",
        "status": 200,
        "title": "Portal",
        "server": "nginx",
        "technologies": ["nginx", "React"]
      },
      "tls": {
        "not_after": "2027-01-01T00:00:00Z",
        "subject_cn": "app.example.lab",
        "issuer": "Example CA"
      },
      "fingerprints": [
        {
          "technology": "nginx",
          "confidence": 80,
          "evidence": [
            {
              "type": "header",
              "name": "server",
              "value_redacted": "nginx"
            }
          ]
        }
      ]
    }
  ]
}
```

### CSV

```csv
schema_version,host,port,protocol,service,http_status,http_title,technology,confidence,observed_at
1,10.0.0.15,443,tcp,https,200,Portal,nginx,80,2026-11-21T12:00:00Z
```

Jeden wiersz CSV opisuje jedną technologię na hoście/porcie. Pełne evidence jest dostępne tylko w JSON.

## Eksport

Eksport używa tych samych schematów. Dodatkowo może zawierać:

- `lifecycle_state` (`NEW`, `CHANGED`, `MISSING`, `FLAKY`, `GONE`);
- `manual_override` (tagi, notatki, korekty);
- `scan_run_id`;
- `confidence`.

## Walidacja i deduplikacja

- niepoprawny CIDR, IP lub domena jest odrzucana;
- cele poza allowlistą są odrzucane;
- duplikaty są raportowane i pomijane;
- limit rozmiaru pliku: 20 MiB;
- import wyników nie nadpisuje `manual_override`.

## DefectDojo (opcjonalnie)

Ukończony lub częściowo ukończony przebieg można wysłać z UI albo przez:

```text
Po zakończeniu skanu z co najmniej jednym ukończonym batchem SurfaceX
wysyła raport automatycznie. Endpoint poniżej zostaje jako ręczny fallback:

POST /api/scans/<scan_run_id>/export/defectdojo/
```

Eksporter tworzy raport `Generic Findings Import` i przesyła go przez
`POST /api/v2/reimport-scan/`. Jako findings poziomu `Info` trafiają:

- aktywne hosty;
- otwarte porty i usługi wraz z produktem oraz wersją;
- technologie wykryte przez httpx i sygnatury SurfaceX.

`unique_id_from_tool` jest stabilnym skrótem typu obserwacji, hosta, portu,
protokołu, endpointu i technologii. Nie zawiera identyfikatora przebiegu,
dzięki czemu ponowny eksport aktualizuje istniejące findings. Eksport ustawia
`close_old_findings=false`, ponieważ pojedynczy przebieg może obejmować tylko
część zapisanych targetów.

Lokalny stos uruchamia się profilem `defectdojo`. Dla zewnętrznej instancji
ustaw `DEFECTDOJO_URL` oraz `DEFECTDOJO_API_TOKEN`. Nazwy Product Type,
Product, Engagement i Test konfiguruje się zmiennymi `DEFECTDOJO_*`
opisanymi w `.env.example`.
