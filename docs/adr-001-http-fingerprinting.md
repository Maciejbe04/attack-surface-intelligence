# ADR-001: Podstawowy silnik HTTP fingerprintingu

## Status

Accepted

## Kontekst

System musi cyklicznie przetwarzać ponad 10 000 adresów, działać lokalnie przez Docker Compose oraz obsługiwać `linux/amd64` i `linux/arm64`.

Po discovery nmap potrzebne jest narzędzie zbierające informacje HTTP/HTTPS i wstępnie wykrywające technologie. Rozważane były ProjectDiscovery httpx oraz WhatWeb.

## Decyzja

Podstawowym narzędziem HTTP fingerprintingu będzie ProjectDiscovery httpx:

```text
nmap → httpx JSONL → własne sygnatury → evidence → confidence score
```

httpx będzie:

- uruchamiany wsadowo dla endpointów wykrytych przez nmap;
- ograniczany wspólnym rate limitem i deadline skanu;
- przypięty do konkretnej wersji;
- budowany natywnie dla `linux/amd64` i `linux/arm64`;
- przetwarzany strumieniowo przez parser JSONL;
- traktowany jako źródło evidence, a nie ostateczna prawda.

Własny moduł Go uzupełni dane wymagane przez deklaratywne sygnatury oraz obliczy wspólny confidence score.

## Dlaczego nie WhatWeb jako podstawa

WhatWeb ma rozbudowaną bazę pluginów i może dokładniej identyfikować część CMS-ów, ale jest mniej odpowiedni dla głównej ścieżki MVP:

- środowisko Ruby zwiększa rozmiar i złożoność obrazu;
- koszt uruchamiania jest większy;
- skanowanie dużych list wymaga ostrożniejszego batchowania;
- agresywne tryby mogą wykonywać dodatkowe żądania;
- pluginy są wykonywalnym kodem Ruby;
- pluginy WhatWeb nie mogą być formatem sygnatur tworzonych przez użytkowników.

## Opcjonalny drugi etap

WhatWeb może zostać dodany później jako domyślnie wyłączony moduł dla ręcznie wybranych endpointów:

```text
wszystkie endpointy → httpx
wybrane endpointy → WhatWeb deep fingerprint
```

Taki moduł musi:

- mieć własny limit ruchu i timeout;
- używać wyłącznie przypiętych, zweryfikowanych pluginów;
- nie umożliwiać przesyłania kodu Ruby przez użytkowników;
- zapisywać wersję i konfigurację narzędzia;
- normalizować wyniki jako evidence;
- korzystać ze wspólnego confidence score.

Nie jest to element obowiązkowego MVP.

## Konsekwencje

Korzyści:

- lepsza wydajność dla dużych zakresów;
- prostszy wieloarchitekturowy worker;
- spójność ze stosem Go;
- łatwiejsze strumieniowe przetwarzanie;
- prostsze egzekwowanie limitów ruchu.

Koszty:

- część niszowych fingerprintów WhatWeb nie będzie dostępna w MVP;
- potrzebny jest własny parser i normalizacja JSONL;
- własny silnik sygnatur musi dostarczyć evidence, scoring i bezpieczne reguły.
