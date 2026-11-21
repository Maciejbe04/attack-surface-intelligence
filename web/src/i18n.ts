import { useEffect, useState } from "react";

export type Language = "en" | "pl";
export type Translate = (text: string) => string;

const STORAGE_KEY = "surfacex.language";

const PL: Record<string, string> = {
  "Skip to sign-in form": "Przejdź do formularza logowania",
  "Multi-factor authentication": "Uwierzytelnianie wieloskładnikowe",
  "Sign in": "Zaloguj się",
  "Enter the 6-digit code from your authenticator app.":
    "Wprowadź 6-cyfrowy kod z aplikacji uwierzytelniającej.",
  "Use your console username and password.": "Użyj nazwy użytkownika i hasła do konsoli.",
  "Warning: MFA is disabled": "Ostrzeżenie: MFA jest wyłączone",
  "Multi-factor authentication is currently turned off for this console. Accounts are protected by password only.":
    "Uwierzytelnianie wieloskładnikowe jest obecnie wyłączone. Konta są chronione wyłącznie hasłem.",
  "Authentication error": "Błąd uwierzytelniania",
  Username: "Nazwa użytkownika",
  Password: "Hasło",
  "Signing in…": "Logowanie…",
  "MFA code": "Kod MFA",
  "TOTP from Google Authenticator, 1Password, or Authy.":
    "Kod TOTP z Google Authenticator, 1Password lub Authy.",
  "Verifying…": "Weryfikacja…",
  Verify: "Zweryfikuj",
  Back: "Wstecz",
  "Sign-in failed.": "Logowanie nie powiodło się.",
  "Invalid MFA code.": "Nieprawidłowy kod MFA.",
  "Cannot reach authentication API.": "Brak połączenia z API uwierzytelniania.",
  "Preparing dashboard…": "Przygotowywanie panelu…",
  "Skip to main content": "Przejdź do głównej treści",
  "Standard contrast": "Standardowy kontrast",
  "High contrast": "Wysoki kontrast",
  "Sign out": "Wyloguj się",
  Dismiss: "Zamknij",
  Primary: "Główna",
  "Attack surface": "Powierzchnia ataku",
  Dashboard: "Panel główny",
  Targets: "Cele",
  Scans: "Skanowania",
  "Pick a host and run discovery modules. SurfaceX probes only — no login, brute force, or exploitation.":
    "Wybierz host i uruchom moduły rozpoznania. SurfaceX wykonuje wyłącznie bezpieczne sondy — bez logowania, brute force i exploitacji.",
  "Add IP addresses, CIDR ranges, or hostnames. Select hosts with checkboxes, then queue a scan or remove them from the working set.":
    "Dodawaj adresy IP, zakresy CIDR i nazwy hostów. Zaznacz hosty, aby uruchomić skan lub usunąć je z zestawu.",
  "Target host": "Host docelowy",
  "Host / IP": "Host / IP",
  "Type an address or choose from saved targets.":
    "Wpisz adres lub wybierz jeden z zapisanych celów.",
  "Recent probe jobs": "Ostatnie zadania rozpoznania",
  "No probe jobs": "Brak zadań rozpoznania",
  "Select modules and run a discovery probe against a host.":
    "Wybierz moduły i uruchom rozpoznanie hosta.",
  Host: "Host",
  Modules: "Moduły",
  Status: "Status",
  Queued: "W kolejce",
  "Add target": "Dodaj cel",
  "Import hosts file": "Import pliku hostów",
  "Host list file": "Plik z listą hostów",
  "TXT: one host per line. CSV/JSON: value/address column. Up to 10 000 hosts. Uses modules selected on the Dashboard.":
    "TXT: jeden host w linii. CSV/JSON: kolumna value/address. Do 10 000 hostów. Używa modułów wybranych na Dashboardzie.",
  "Start scan automatically": "Uruchom skan automatycznie",
  "After import, queue discovery for every loaded host and send results to DefectDojo when finished.":
    "Po imporcie dodaj rozpoznanie dla każdego hosta i po zakończeniu wyślij wyniki do DefectDojo.",
  "Importing…": "Importowanie…",
  "Import and scan": "Importuj i skanuj",
  "Import hosts": "Importuj hosty",
  "Imported targets": "Zaimportowane cele",
  new: "nowe",
  existing: "istniejące",
  "Import finished": "Import zakończony",
  "Hosts loaded and scan queued automatically.":
    "Hosty wczytane i skan dodany do kolejki automatycznie.",
  "Hosts loaded into the target list.": "Hosty wczytane na listę celów.",
  "Some rows were skipped": "Część wierszy pominięto",
  "Import failed": "Import nie powiódł się",
  "Could not import the host file.": "Nie udało się zaimportować pliku hostów.",
  "IP / hostname": "IP / nazwa hosta",
  Comment: "Komentarz",
  "Comment (optional)": "Komentarz (opcjonalny)",
  "One target per submit. CIDR is stored as a range entry.":
    "Jeden cel na zgłoszenie. CIDR jest zapisywany jako zakres.",
  "Optional note describing the host, owner, environment, or purpose.":
    "Opcjonalna notatka opisująca host, właściciela, środowisko lub przeznaczenie.",
  "Scan selected": "Skanuj wybrane",
  Remove: "Usuń",
  "Clear selection": "Wyczyść wybór",
  "No targets": "Brak celów",
  "Add an IP address or hostname to start building the scan set.":
    "Dodaj adres IP lub nazwę hosta, aby utworzyć zestaw skanowania.",
  Type: "Typ",
  Added: "Dodano",
  "No scan runs yet": "Brak uruchomionych skanów",
  "Use Dashboard modules to probe a host.": "Użyj modułów panelu, aby zbadać host.",
  "Queued discovery jobs from the dashboard and target list.":
    "Zadania rozpoznania dodane z panelu i listy celów.",
  "Discovery scan runs": "Uruchomione skany rozpoznania",
  Scan: "Skan",
  Progress: "Postęp",
  Batches: "Partie",
  Actions: "Akcje",
  Running: "W toku",
  "Cancel requested": "Anulowanie",
  Completed: "Zakończony",
  Partial: "Częściowy",
  Failed: "Niepowodzenie",
  Cancelled: "Anulowany",
  Cancel: "Anuluj",
  "Cancelling…": "Anulowanie…",
  "DD sent": "DD wysłano",
  "DD sending": "DD wysyła",
  "DD queued": "DD w kolejce",
  "DD skipped": "DD pominięte",
  "DD failed": "DD błąd",
  "DD idle": "DD bezczynne",
  "Sent to DefectDojo": "Wysłano do DefectDojo",
  "Sending to DefectDojo": "Wysyłanie do DefectDojo",
  "DefectDojo queued": "DefectDojo w kolejce",
  "DefectDojo skipped": "DefectDojo pominięte",
  "DefectDojo failed": "DefectDojo nieudane",
  "DefectDojo idle": "DefectDojo bezczynne",
  Findings: "Znaleziska",
  Test: "Test",
  "Scan progress": "Postęp skanu",
  "Targets unavailable": "Cele niedostępne",
  "Could not load targets.": "Nie udało się pobrać celów.",
  "Scans unavailable": "Skany niedostępne",
  "Could not load scans.": "Nie udało się pobrać skanów.",
  "Enter a valid IPv4, CIDR (e.g. 10.0.0.0/24), or hostname.":
    "Wprowadź poprawny adres IPv4, CIDR (np. 10.0.0.0/24) lub nazwę hosta.",
  "This target is already on the list.": "Ten cel jest już na liście.",
  "Adding…": "Dodawanie…",
  "Could not add target.": "Nie udało się dodać celu.",
  "Target not added": "Nie dodano celu",
  "Removed targets": "Usunięte cele",
  "Removing…": "Usuwanie…",
  "Some targets were not removed": "Niektórych celów nie usunięto",
  "Could not remove selected targets.": "Nie udało się usunąć wybranych celów.",
  "No modules": "Brak modułów",
  "Select at least one discovery module.": "Wybierz co najmniej jeden moduł rozpoznania.",
  "Scan queued": "Skan dodany do kolejki",
  "Scan queued for targets": "Dodano skan dla celów",
  "Scan not queued": "Nie dodano skanu",
  "Could not queue scan.": "Nie udało się dodać skanu do kolejki.",
  "Queueing…": "Dodawanie do kolejki…",
  "Host required": "Wymagany host",
  "Select a saved host / IP to probe.": "Wybierz zapisany host lub adres IP.",
  "Saved target required": "Wymagany zapisany cel",
  "Choose a target saved in Targets.": "Wybierz cel zapisany na liście Celów.",
  "Cancellation requested": "Zażądano anulowania",
  "Cancellation failed": "Anulowanie nie powiodło się",
  "Could not cancel scan.": "Nie udało się anulować skanu.",
  "Read-only access": "Dostęp tylko do odczytu",
  "Your role can view targets and scans but cannot change them.":
    "Twoja rola może wyświetlać cele i skany, ale nie może ich zmieniać.",
  selected: "wybrano",
  total: "łącznie",
  "Select all hosts": "Wybierz wszystkie hosty",
  Select: "Wybierz",
  Success: "Sukces",
  "Discovery modules": "Moduły rozpoznania",
  "Run selected": "Uruchom wybrane",
  Discovery: "Rozpoznanie",
  "Find live hosts and exposed network services.": "Wykrywaj aktywne hosty i usługi sieciowe.",
  "Inspect web endpoints and response metadata.": "Sprawdzaj endpointy WWW i metadane odpowiedzi.",
  "Collect certificate and TLS configuration details.": "Zbieraj dane certyfikatów i konfiguracji TLS.",
  Signatures: "Sygnatury",
  "Match observed services against known fingerprints.":
    "Porównuj wykryte usługi ze znanymi sygnaturami.",
  Pipeline: "Potok",
  "Run a combined discovery workflow.": "Uruchom połączony proces rozpoznania.",
  Enabled: "Włączony",
  Disabled: "Wyłączony",
  Filters: "Filtry",
  "Hide filters": "Ukryj filtry",
  "No filters": "Brak filtrów",
  "Module filters": "Filtry modułu",
  "Configure this module before running discovery.":
    "Skonfiguruj moduł przed uruchomieniem rozpoznania.",
  Active: "Aktywne",
  "Close filters": "Zamknij filtry",
  "Host discovery": "Wykrywanie hostów",
  "ICMP / TCP probes to check if the host responds.": "Sondy ICMP/TCP sprawdzające odpowiedź hosta.",
  "Port scan": "Skan portów",
  "TCP scan with selectable port profile or custom list.":
    "Skan TCP z profilem portów lub własną listą.",
  "Service detection": "Wykrywanie usług",
  "Identify services on open ports (-sV).": "Identyfikacja usług na otwartych portach (-sV).",
  "HTTP fingerprint": "Identyfikacja HTTP",
  "Status, title, headers, tech detect via httpx.":
    "Status, tytuł, nagłówki i technologie wykrywane przez httpx.",
  "TLS certificate": "Certyfikat TLS",
  "Grab certificate CN, issuer, and expiry.": "Pobieranie CN, wystawcy i daty wygaśnięcia certyfikatu.",
  "Custom signatures": "Własne sygnatury",
  "Run declarative SurfaceX signature rules.": "Uruchamianie deklaratywnych reguł sygnatur SurfaceX.",
  "Full discovery pipeline": "Pełny proces rozpoznania",
  "nmap → httpx → signatures → confidence score.":
    "nmap → httpx → sygnatury → ocena pewności.",
  Method: "Metoda",
  "TCP ping ports": "Porty ping TCP",
  "Timeout (s)": "Limit czasu (s)",
  "Port profile": "Profil portów",
  "Custom ports": "Własne porty",
  "Timing template": "Szablon szybkości",
  "Max packets/s": "Maks. pakietów/s",
  "Version intensity": "Intensywność wykrywania wersji",
  "Light probes only": "Tylko lekkie sondy",
  Schemes: "Schematy",
  "HTTP ports": "Porty HTTP",
  "Follow redirects": "Podążaj za przekierowaniami",
  "Max redirects": "Maks. przekierowań",
  "Tech detect": "Wykrywaj technologie",
  "Rate limit (req/s)": "Limit żądań/s",
  "TLS ports": "Porty TLS",
  "Expiry warning (days)": "Ostrzeżenie o wygaśnięciu (dni)",
  "Include chain metadata": "Dołącz metadane łańcucha",
  "Signature pack": "Pakiet sygnatur",
  "Min confidence": "Minimalna pewność",
  "Extra paths": "Dodatkowe ścieżki",
  "Local discovery console": "Lokalna konsola rozpoznania",
  "Accessibility tips": "Wskazówki dostępności",
  "Switch to standard contrast": "Przełącz na standardowy kontrast",
  "Switch to high contrast": "Przełącz na wysoki kontrast",
  Language: "Język",
  "Activity console": "Konsola aktywności",
  "Run a probe or scan selected targets to stream execution logs here.":
    "Uruchom sondę albo skan wybranych celów, aby tu zobaczyć logi wykonania.",
  Live: "Na żywo",
  "Refreshing…": "Odświeżanie…",
  "Clear console": "Wyczyść konsolę",
  "Scan activity log": "Dziennik aktywności skanu",
  "Waiting for the next scan run.": "Oczekiwanie na kolejny przebieg skanu.",
  "No activity events yet for this scan.": "Brak zdarzeń aktywności dla tego skanu.",
  "View log": "Pokaż log",
  "Viewing log": "Podgląd logu",
  "Console unavailable": "Konsola niedostępna",
  "Could not load scan activity.": "Nie udało się wczytać aktywności skanu.",
  System: "System",
  "System & integrations": "System i integracje",
  "Stack composition and active integrations.":
    "Skład stosu i aktywne integracje.",
  "Loading system information…": "Wczytywanie informacji systemowych…",
  "Could not load system information.": "Nie udało się wczytać informacji systemowych.",
  Unavailable: "Niedostępne",
  Integrations: "Integracje",
  "In use": "W użyciu",
  "Not configured": "Nieskonfigurowane",
  Version: "Wersja",
  Endpoint: "Endpoint",
  Export: "Eksport",
  "Automatic after scan completion": "Automatyczny po zakończeniu skanu",
  Product: "Produkt",
  "System information": "Informacje systemowe",
  Platform: "Platforma",
  "Stack components": "Komponenty stosu",
  Component: "Komponent",
  Role: "Rola",
  "Django REST API": "API Django REST",
  Runtime: "Środowisko uruchomieniowe",
  "Web framework": "Framework WWW",
  "Task queue": "Kolejka zadań",
  "Primary database": "Główna baza danych",
  "Broker / cache / sessions": "Broker / cache / sesje",
  "Host / port discovery (worker)": "Wykrywanie hostów / portów (worker)",
  "HTTP fingerprinting (worker)": "Fingerprint HTTP (worker)",
  Frontend: "Frontend",
  "Optional findings platform": "Opcjonalna platforma findings",
  "Automatic findings export after completed scans.":
    "Automatyczny eksport findings po zakończonych skanach.",
  "Optional. Configure URL and credentials to enable export.":
    "Opcjonalne. Skonfiguruj URL i poświadczenia, aby włączyć eksport.",
  "Search failed.":
    "Wyszukiwanie nie powiodło się.",
  "Search saved hosts: IP, CIDR, hostname, or comment":
    "Szukaj zapisanych hostów: IP, CIDR, nazwa lub komentarz",
  "Searching…":
    "Wyszukiwanie…",
  "No saved host matches. Add it on the Targets page first.":
    "Brak pasującego hosta. Najpierw dodaj go na stronie Cele.",
  "Matching hosts":
    "Pasujące hosty",
  "Selected":
    "Wybrano",
  "Start typing to search saved hosts; pick one to scan it on its own.":
    "Zacznij pisać, aby wyszukać zapisany host; wybierz go, aby przeskanować pojedynczo.",
  "Search for a saved host and pick it from the list.":
    "Wyszukaj zapisany host i wybierz go z listy.",
  "Groups":
    "Grupy",
  "Group":
    "Grupa",
  "groups":
    "grup",
  "Not scheduled":
    "Bez harmonogramu",
  "Every":
    "Co",
  "Daily at":
    "Codziennie o",
  "paused":
    "wstrzymany",
  "Monday":
    "Poniedziałek",
  "Tuesday":
    "Wtorek",
  "Wednesday":
    "Środa",
  "Thursday":
    "Czwartek",
  "Friday":
    "Piątek",
  "Saturday":
    "Sobota",
  "Sunday":
    "Niedziela",
  "Group hosts to scan them together, now or on a schedule. A host can belong to several groups.":
    "Grupuj hosty, aby skanować je razem — od razu albo według harmonogramu. Host może należeć do kilku grup.",
  "Create group":
    "Utwórz grupę",
  "Name":
    "Nazwa",
  "Description (optional)":
    "Opis (opcjonalnie)",
  "Creating…":
    "Tworzenie…",
  "Group created":
    "Utworzono grupę",
  "Group not created":
    "Nie utworzono grupy",
  "Could not create the group.":
    "Nie udało się utworzyć grupy.",
  "No groups":
    "Brak grup",
  "Create a group here, add hosts from the Targets page, or assign a group when importing a file.":
    "Utwórz grupę tutaj, dodaj hosty na stronie Cele albo przypisz grupę przy imporcie pliku.",
  "Host groups":
    "Grupy hostów",
  "Hosts":
    "Hosty",
  "Schedule":
    "Harmonogram",
  "Next run":
    "Następne uruchomienie",
  "Last scheduled run":
    "Ostatnie zaplanowane uruchomienie",
  "Show hosts":
    "Pokaż hosty",
  "Scan now":
    "Skanuj teraz",
  "Edit schedule":
    "Edytuj harmonogram",
  "Delete":
    "Usuń",
  "Delete group \"{name}\"? Hosts and past scans are kept.":
    "Usunąć grupę „{name}”? Hosty i dotychczasowe skany zostaną zachowane.",
  "Group deleted":
    "Usunięto grupę",
  "Group not deleted":
    "Nie usunięto grupy",
  "Could not delete the group.":
    "Nie udało się usunąć grupy.",
  "Uncheck to pause without losing the settings.":
    "Odznacz, aby wstrzymać bez utraty ustawień.",
  "Repeat":
    "Powtarzaj",
  "Every N hours":
    "Co N godzin",
  "Daily":
    "Codziennie",
  "Weekly":
    "Co tydzień",
  "Interval (hours)":
    "Odstęp (godziny)",
  "1–168. Counted from the moment the schedule is saved.":
    "1–168. Liczone od momentu zapisania harmonogramu.",
  "Day":
    "Dzień",
  "Time (UTC)":
    "Godzina (UTC)",
  "Scans start within about a minute of this time. Missed runs are not replayed.":
    "Skan startuje mniej więcej w ciągu minuty od tej godziny. Pominięte uruchomienia nie są powtarzane.",
  "Replace with the modules selected on the Dashboard":
    "Zastąp modułami wybranymi na pulpicie",
  "New schedules use the modules selected on the Dashboard.":
    "Nowy harmonogram używa modułów wybranych na pulpicie.",
  "Results of every finished scheduled scan are sent to DefectDojo automatically when it is configured.":
    "Wyniki każdego zakończonego skanu z harmonogramu są automatycznie wysyłane do DefectDojo, jeśli jest skonfigurowane.",
  "Save schedule":
    "Zapisz harmonogram",
  "Remove schedule":
    "Usuń harmonogram",
  "Schedule saved":
    "Zapisano harmonogram",
  "Schedule not saved":
    "Nie zapisano harmonogramu",
  "Could not save the schedule.":
    "Nie udało się zapisać harmonogramu.",
  "Schedule removed":
    "Usunięto harmonogram",
  "Schedule not removed":
    "Nie usunięto harmonogramu",
  "Could not remove the schedule.":
    "Nie udało się usunąć harmonogramu.",
  "scheduled":
    "z harmonogramu",
  "Groups unavailable":
    "Grupy niedostępne",
  "Could not load groups.":
    "Nie udało się wczytać grup.",
  "Added to group":
    "Dodano do grupy",
  "Removed from group":
    "Usunięto z grupy",
  "Group not updated":
    "Nie zaktualizowano grupy",
  "Could not update the group.":
    "Nie udało się zaktualizować grupy.",
  "Group name required":
    "Wymagana nazwa grupy",
  "Type a name for the new group.":
    "Wpisz nazwę nowej grupy.",
  "Add to group":
    "Dodaj do grupy",
  "No group":
    "Bez grupy",
  "New group…":
    "Nowa grupa…",
  "New group name":
    "Nazwa nowej grupy",
  "Every host in the file joins this group. CSV files can also set groups per row in a group column (several names separated by ;).":
    "Każdy host z pliku trafi do tej grupy. W CSV można też podać grupy dla wiersza w kolumnie group (kilka nazw rozdzielonych ;).",
  "Filter":
    "Filtr",
  "Address, comment, or group":
    "Adres, komentarz lub grupa",
  "All hosts":
    "Wszystkie hosty",
  "Add selected to group":
    "Dodaj zaznaczone do grupy",
  "Choose group…":
    "Wybierz grupę…",
  "Add":
    "Dodaj",
  "Remove from this group":
    "Usuń z tej grupy",
  "shown":
    "widocznych",
  "No matching hosts":
    "Brak pasujących hostów",
  "Change the filter or choose another group.":
    "Zmień filtr albo wybierz inną grupę.",
  "Show only this group":
    "Pokaż tylko tę grupę",
};

export function useLanguage() {
  const [language, setLanguage] = useState<Language>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "pl" ? "pl" : "en";
    } catch {
      return "en";
    }
  });

  useEffect(() => {
    document.documentElement.lang = language;
    try {
      localStorage.setItem(STORAGE_KEY, language);
    } catch {
      /* ignore */
    }
  }, [language]);

  const t: Translate = (text) => (language === "pl" ? PL[text] ?? text : text);

  return { language, setLanguage, t };
}
