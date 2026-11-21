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
| `header` | `name`, `equals` / `contains` / `regex` | nagłówek odpowiedzi |
| `cookie` | `name` | wyłącznie nazwa cookie, bez wartości |
| `html` | `contains` / `regex` | ograniczony fragment body |
| `favicon` | `hash` | hash favicon z httpx |
| `path` | `path`, `status` | ścieżka względna, np. `/login` |
| `versionRegex` | `source`, `pattern` | wyciągnięcie wersji |

## Ograniczenia bezpieczeństwa

- `path` musi być względna i zaczynać się od `/`;
- zabronione są schematy `http://`, `https://` oraz hosty w ścieżce;
- regex ma limit długości wzorca, czasu wykonania i długości wejścia;
- body do analizy wynosi maksymalnie 64 KiB;
- wartości cookies nie są porównywane ani zapisywane w jawnej postaci;
- `matchAny: false` wymaga sumy wag zgodnych reguł; `true` kończy przy pierwszej trafionej regule z wagą.

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

## Przechowywanie

- wbudowane sygnatury: katalog `signatures/`;
- sygnatury użytkownika: baza PostgreSQL z wersjonowaniem;
- każda detekcja zapisuje `signature_id`, wersję, evidence i score.
