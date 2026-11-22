# Format sygnatur

## Zasady

Sygnatury są deklaratywne. Nie wolno umieszczać w nich kodu wykonywalnego, skryptów Ruby/Python ani wywołań zewnętrznych.

Dozwolone kontrole:

- nagłówek HTTP;
- nazwa cookie;
- fragment HTML;
- favicon hash;
- status dozwolonej ścieżki względnej;
- ograniczony regex wersji.

## Schemat YAML

```yaml
apiVersion: surfacex/v1
kind: Signature
metadata:
  id: wordpress-core
  name: WordPress
  category: cms
  version: 1
spec:
  matchAny: false
  rules:
    - type: header
      name: link
      contains: "rel=\"https://api.w.org/\""
      weight: 30
    - type: cookie
      name: wordpress_logged_in
      weight: 20
    - type: html
      contains: "wp-content"
      weight: 20
    - type: path
      path: "/wp-login.php"
      status: [200, 302]
      weight: 30
    - type: versionRegex
      source: html
      pattern: "content=\"WordPress ([0-9]+\\.[0-9]+(?:\\.[0-9]+)?)\""
      weight: 20
  confidence:
    low: [1, 39]
    medium: [40, 69]
    high: [70, 100]
```

## Typy reguł

| Typ | Pola | Opis |
|---|---|---|
| `header` | `name`, `equals` / `contains` / `regex` (bez nich: sama obecność) | nagłówek odpowiedzi |
| `cookie` | `name` | wyłącznie nazwa cookie, bez wartości |
| `html` | `contains` / `regex` | fragment treści strony |
| `favicon` | `hash` | hash favicony (mmh3) zwracany przez httpx |
| `path` | `path`, `status` | badany adres zawiera podaną ścieżkę i (opcjonalnie) ma jeden z podanych kodów |
| `status` | `status` | kod odpowiedzi HTTP |
| `versionRegex` | `source` (`html` albo nazwa nagłówka), `pattern` | wyciągnięcie wersji; pierwsza grupa wzorca trafia do pola `version` |

Każda reguła może mieć `weight` (domyślnie 10). Porównania tekstu nie rozróżniają wielkości liter.

## Ograniczenia bezpieczeństwa

- `path` musi być względna i zaczynać się od `/`; schematy `http://`, `https://` oraz hosty w ścieżce są odrzucane;
- wzorzec regex może mieć najwyżej 200 znaków i jest stosowany do pierwszych 32 KiB wejścia; błędny wzorzec jest pomijany;
- treść strony do analizy to najwyżej 64 KiB;
- wartości cookies nie są porównywane ani zapisywane;
- sygnatura nie wykonuje żadnych dodatkowych żądań — działa wyłącznie na odpowiedziach już zebranych przez httpx;
- `matchAny: false` sumuje wagi wszystkich trafionych reguł; `true` kończy na pierwszej trafionej regule.

## Confidence score

Domyślne wagi:

- charakterystyczny nagłówek: `30`;
- nazwa cookie: `20`;
- favicon hash: `40`;
- fragment HTML: `20`;
- jednoznaczny banner lub stopka: `30`.

Zgodne sygnały sumują się do maksymalnie `100`. Pojedynczy słaby sygnał nie może dać poziomu `high`.

## Przykład minimalny

```yaml
apiVersion: surfacex/v1
kind: Signature
metadata:
  id: nginx-server
  name: nginx
  category: http-server
  version: 1
spec:
  matchAny: true
  rules:
    - type: header
      name: server
      contains: "nginx"
      weight: 40
```

## Dodanie własnej sygnatury

1. Zapisz plik `signatures/<nazwa>.yaml` (jeden dokument `kind: Signature` na plik).
2. Przebuduj i uruchom ponownie obrazy, które zawierają katalog sygnatur:

   ```bash
   docker compose up --build -d api worker
   ```

3. Uruchom skan z modułem `signatures` albo `full-pipeline`.
4. Sprawdź wynik w **Findings**: obserwacje typu `signature` z polami `signature_id`, `technology`, `confidence`, `level`, `version` i `evidence` (lista trafionych reguł).

Sygnatury są wczytywane przy starcie procesu workera, dlatego zmiana pliku wymaga przebudowania obrazu. Plik z błędem składni YAML albo bez `kind: Signature` jest pomijany.

Wbudowany zestaw: `wordpress-core`, `nginx-server`, `apache-httpd`.

## Ograniczenia prototypu

- Sygnatury są plikami w repozytorium; nie ma edytora w UI ani wersjonowania w bazie.
- httpx odpytuje adres główny każdego endpointu (`scheme://host:port`), więc reguła `path` trafia tylko wtedy, gdy ścieżka jest częścią badanego adresu. Filtr `pathsExtra` modułu `signatures` jest walidowany, ale nie powoduje jeszcze dodatkowych żądań.
- Filtry `pack` i `minConfidence` modułu `signatures` nie zawężają jeszcze zestawu — dopasowywane są wszystkie wczytane sygnatury.
