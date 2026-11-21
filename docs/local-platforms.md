# Platformy lokalne

## Oficjalnie wspierane

| Host | Silnik | Obrazy kontenerów | Tryb nmap |
|---|---|---|---|
| Linux `amd64` | Docker Engine + Compose | `linux/amd64` | SYN, jeśli `NET_RAW` działa |
| Linux `arm64` | Docker Engine + Compose | `linux/arm64` | SYN, jeśli `NET_RAW` działa |
| macOS Intel | Docker Desktop | `linux/amd64` | TCP connect |
| macOS Apple Silicon | Docker Desktop | `linux/arm64` | TCP connect |
| Windows 10/11 | Docker Desktop + WSL2 | `linux/amd64` | TCP connect |

Kontenery zawsze są obrazami Linux. Projekt nie używa Windows Containers.

## Windows Docker Desktop

Wymagania:

- Windows 10 lub 11 w wersji wspieranej przez Docker Desktop;
- Docker Desktop z backendem **WSL2**;
- tryb **Linux containers** (domyślny);
- zainstalowana dystrybucja WSL2, np. Ubuntu;
- Git for Windows albo Git wewnątrz WSL;
- co najmniej 8 GB RAM przydzielone Docker Desktop / WSL.

Zalecany sposób pracy:

1. klonować i uruchamiać Compose z poziomu WSL2 (`\\wsl$\...` albo terminal WSL);
2. trzymać repozytorium na systemie plików Linux w WSL, nie na `C:\`, aby uniknąć wolnych bind mountów;
3. używać plików sekretów z uprawnieniami `0600` wewnątrz WSL;
4. nie przełączać Docker Desktop na Windows Containers.

Oczekiwane zachowanie:

- te same komendy `docker compose up --build` co na Linux/macOS;
- worker bez niezawodnego `NET_RAW` → automatyczny TCP connect scan;
- tryb skanu zapisany w metadanych przebiegu;
- smoke test MVP obejmuje Windows Docker Desktop jako platformę akceptacyjną dla `linux/amd64`.

## Ograniczenia wspólne dla Docker Desktop

Dotyczy Windows i macOS:

- sieć nie jest tożsama z natywnym Docker Engine na Linux;
- `network_mode: host` jest zabronione;
- raw sockets / SYN scan zwykle niedostępne;
- wydajność wolumenów zależy od miejsca przechowywania plików projektu.

## Poza zakresem

- natywne Windows Containers (`nanoserver` / `windowsservercore`);
- Docker Toolbox / Hyper-V legacy bez WSL2;
- rootless Docker na Windows poza standardowym Docker Desktop.
