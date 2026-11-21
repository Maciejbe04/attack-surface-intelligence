# Import i eksport

## Wersjonowanie

Każdy plik CSV/JSON zawiera pole lub kolumnę `schema_version`. MVP używa `1`.

Nieznana wersja schematu powoduje odrzucenie importu z czytelnym błędem.

## Import celów

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

Wybrane obserwacje mogą być wysłane jako finding informacyjny:

- `idempotency_key = scan_run_id + host + port + technology`;
- evidence w załączniku lub opisie;
- ponowny eksport tego samego klucza aktualizuje finding zamiast tworzyć duplikat.
