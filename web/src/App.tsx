import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiFetch, AuthUser, ensureCsrf } from "./auth";
import { AppFooter } from "./AppFooter";
import { Language, Translate, useLanguage } from "./i18n";
import { LanguageSelect } from "./LanguageSelect";
import { Logo } from "./Logo";
import { ModulePanel } from "./ModulePanel";
import {
  createInitialModuleState,
  ModuleRegistryState,
  summarizeFilters,
} from "./modules";
import { useHighContrast } from "./useHighContrast";
import { APP_NAME, APP_VERSION } from "./version";

type HostTarget = {
  id: string;
  value: string;
  type: "ip" | "cidr" | "domain";
  comment: string;
  addedAt: string;
};

type NavId = "dashboard" | "targets" | "scans";

type Toast = {
  id: string;
  kind: "error" | "ok";
  title: string;
  message: string;
};

type ProbeJob = {
  id: string;
  host: string;
  modules: Array<{ id: string; filters: Record<string, string | number | boolean> }>;
  createdAt: string;
  status: "queued";
};

const STORAGE_KEY = "surfacex.targets.v1";
const JOBS_KEY = "surfacex.probeJobs.v1";

function detectType(value: string): HostTarget["type"] {
  if (value.includes("/")) return "cidr";
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(value)) return "ip";
  return "domain";
}

function isValidTarget(value: string): boolean {
  const v = value.trim();
  if (!v || v.includes(" ")) return false;
  if (detectType(v) === "ip") {
    return v.split(".").every((part) => {
      const n = Number(part);
      return Number.isInteger(n) && n >= 0 && n <= 255;
    });
  }
  if (detectType(v) === "cidr") {
    const [ip, prefix] = v.split("/");
    const p = Number(prefix);
    return (
      isValidTarget(ip) &&
      detectType(ip) === "ip" &&
      Number.isInteger(p) &&
      p >= 0 &&
      p <= 32
    );
  }
  return /^[a-z0-9.-]+$/i.test(v) && v.includes(".");
}

function loadTargets(): HostTarget[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as HostTarget[];
    return Array.isArray(parsed)
      ? parsed.map((target) => ({ ...target, comment: target.comment ?? "" }))
      : [];
  } catch {
    return [];
  }
}

function loadJobs(): ProbeJob[] {
  try {
    const raw = localStorage.getItem(JOBS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ProbeJob[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function LoginScreen({
  onAuthenticated,
  highContrast,
  onToggleContrast,
  language,
  onLanguageChange,
  t,
}: {
  onAuthenticated: (user: AuthUser) => void;
  highContrast: boolean;
  onToggleContrast: () => void;
  language: Language;
  onLanguageChange: (language: Language) => void;
  t: Translate;
}) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitPassword(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await ensureCsrf();
      const response = await apiFetch("/api/auth/login/", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.detail || t("Sign-in failed."));
        return;
      }
      if (data.mfa_required) {
        setMfaToken(data.mfa_token);
        return;
      }
      onAuthenticated(data.user as AuthUser);
    } catch {
      setError(t("Cannot reach authentication API."));
    } finally {
      setBusy(false);
    }
  }

  async function submitMfa(event: FormEvent) {
    event.preventDefault();
    if (!mfaToken) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch("/api/auth/mfa/verify/", {
        method: "POST",
        body: JSON.stringify({ mfa_token: mfaToken, code: mfaCode }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.detail || t("Invalid MFA code."));
        if (data.mfa_token) setMfaToken(data.mfa_token);
        return;
      }
      onAuthenticated(data.user as AuthUser);
    } catch {
      setError(t("Cannot reach authentication API."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <a className="skip-link" href="#login-form">
        {t("Skip to sign-in form")}
      </a>
      <div className="login-language">
        <LanguageSelect
          language={language}
          onChange={onLanguageChange}
          label={t("Language")}
        />
      </div>
      <main className="login-card panel" id="login-form" aria-labelledby="login-title">
        <div className="panel__header">
          <h2 id="login-title">
            {mfaToken ? t("Multi-factor authentication") : t("Sign in")}
          </h2>
        </div>
        <div className="panel__body">
          <div className="login-brand">
            <Logo />
          </div>
          <p className="field-help" style={{ marginBottom: 16 }} id="login-help">
            {mfaToken
              ? t("Enter the 6-digit code from your authenticator app.")
              : t("Use your console username and password.")}
          </p>

          {!mfaToken && (
            <div className="flash flash--error" role="alert">
              <div>
                <strong>{t("Warning: MFA is disabled")}</strong>
                <p>
                  {t(
                    "Multi-factor authentication is currently turned off for this console. Accounts are protected by password only.",
                  )}
                </p>
              </div>
            </div>
          )}

          {error && (
            <div className="flash flash--error" role="alert">
              <div>
                <strong>{t("Authentication error")}</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          {!mfaToken ? (
            <form onSubmit={submitPassword} aria-describedby="login-help">
              <div className="form-row">
                <label htmlFor="username">{t("Username")}</label>
                <input
                  id="username"
                  className="input"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  required
                  aria-required="true"
                />
              </div>
              <div className="form-row">
                <label htmlFor="password">{t("Password")}</label>
                <input
                  id="password"
                  type="password"
                  className="input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  aria-required="true"
                />
              </div>
              <div className="actions">
                <button type="submit" className="btn btn--primary" disabled={busy} aria-busy={busy}>
                  {busy ? t("Signing in…") : t("Sign in")}
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={submitMfa} aria-describedby="login-help">
              <div className="form-row">
                <label htmlFor="mfa">{t("MFA code")}</label>
                <div>
                  <input
                    id="mfa"
                    className="input"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={6}
                    value={mfaCode}
                    onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
                    autoComplete="one-time-code"
                    required
                    aria-required="true"
                    aria-describedby="mfa-help"
                  />
                  <p className="field-help" id="mfa-help">
                    {t("TOTP from Google Authenticator, 1Password, or Authy.")}
                  </p>
                </div>
              </div>
              <div className="actions">
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={busy || mfaCode.length < 6}
                  aria-busy={busy}
                >
                  {busy ? t("Verifying…") : t("Verify")}
                </button>
                <button
                  type="button"
                  className="btn btn--normal"
                  disabled={busy}
                  onClick={() => {
                    setMfaToken(null);
                    setMfaCode("");
                    setError(null);
                  }}
                >
                  {t("Back")}
                </button>
              </div>
            </form>
          )}
        </div>
      </main>
      <AppFooter
        highContrast={highContrast}
        onToggleContrast={onToggleContrast}
        language={language}
        onLanguageChange={onLanguageChange}
        t={t}
      />
      <div id="a11y-help" className="sr-only" tabIndex={-1}>
        {APP_NAME} version {APP_VERSION}. Keyboard users can tab through form fields. Screen
        reader users: alerts are announced automatically. Use High contrast for stronger colors.
      </div>
    </div>
  );
}

function DashboardLoader({ t }: { t: Translate }) {
  return (
    <div className="dashboard-loader" role="status" aria-live="polite">
      <div className="dashboard-loader__card">
        <Logo />
        <div className="dashboard-loader__bar" aria-hidden="true">
          <span />
        </div>
        <p>{t("Preparing dashboard…")}</p>
      </div>
    </div>
  );
}

export function App() {
  const { highContrast, toggleHighContrast } = useHighContrast();
  const { language, setLanguage, t } = useLanguage();
  const [bootstrapping, setBootstrapping] = useState(true);
  const [enteringDashboard, setEnteringDashboard] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [nav, setNav] = useState<NavId>("dashboard");
  const [targets, setTargets] = useState<HostTarget[]>(() => loadTargets());
  const [jobs, setJobs] = useState<ProbeJob[]>(() => loadJobs());
  const [draft, setDraft] = useState("");
  const [draftComment, setDraftComment] = useState("");
  const [draftError, setDraftError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [flash, setFlash] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [probeHost, setProbeHost] = useState("");
  const [moduleState, setModuleState] = useState<ModuleRegistryState>(() =>
    createInitialModuleState(),
  );

  function pushToast(kind: Toast["kind"], title: string, message: string) {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, kind, title, message }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 6000);
  }

  function completeAuthentication(authenticatedUser: AuthUser) {
    setEnteringDashboard(true);
    window.setTimeout(() => {
      setUser(authenticatedUser);
      setEnteringDashboard(false);
    }, 300);
  }

  function dismissToast(id: string) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }

  useEffect(() => {
    apiFetch("/api/auth/me/")
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((me) => {
        if (me.authenticated) setUser(me.user as AuthUser);
      })
      .catch(() => {
        pushToast("error", "No connection", "Cannot reach SurfaceX API. Check Docker Compose.");
      })
      .finally(() => setBootstrapping(false));
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(targets));
  }, [targets]);

  useEffect(() => {
    localStorage.setItem(JOBS_KEY, JSON.stringify(jobs));
  }, [jobs]);

  useEffect(() => {
    if (!probeHost && targets.length > 0) {
      setProbeHost(targets[0].value);
    }
  }, [targets, probeHost]);

  const allSelected = targets.length > 0 && selected.size === targets.length;
  const someSelected = selected.size > 0 && selected.size < targets.length;
  const selectedTargets = useMemo(
    () => targets.filter((t) => selected.has(t.id)),
    [targets, selected],
  );

  async function signOut() {
    try {
      await apiFetch("/api/auth/logout/", { method: "POST", body: "{}" });
    } catch {
      pushToast("error", "No connection", "Sign-out request failed.");
    }
    setUser(null);
  }

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(targets.map((t) => t.id)));
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleModuleEnabled(id: string) {
    setModuleState((prev) => {
      const current = prev[id];
      if (!current) return prev;

      if (id === "full-pipeline" && !current.enabled) {
        const next: ModuleRegistryState = {};
        for (const [key, cfg] of Object.entries(prev)) {
          next[key] = {
            ...cfg,
            enabled: key === "full-pipeline",
            expanded: key === "full-pipeline" ? true : cfg.expanded,
          };
        }
        return next;
      }

      const next: ModuleRegistryState = {
        ...prev,
        [id]: {
          ...current,
          enabled: !current.enabled,
        },
      };
      if (id !== "full-pipeline" && next["full-pipeline"]?.enabled) {
        next["full-pipeline"] = { ...next["full-pipeline"], enabled: false };
      }
      return next;
    });
  }

  function toggleModuleExpanded(id: string) {
    setModuleState((prev) => {
      const current = prev[id];
      if (!current) return prev;
      return Object.fromEntries(
        Object.entries(prev).map(([moduleId, config]) => [
          moduleId,
          {
            ...config,
            expanded: moduleId === id ? !current.expanded : false,
          },
        ]),
      );
    });
  }

  function updateModuleFilter(id: string, key: string, value: string | number | boolean) {
    setModuleState((prev) => {
      const current = prev[id];
      if (!current) return prev;
      return {
        ...prev,
        [id]: {
          ...current,
          filters: { ...current.filters, [key]: value },
        },
      };
    });
  }

  function onAdd(event: FormEvent) {
    event.preventDefault();
    const value = draft.trim();
    if (!isValidTarget(value)) {
      setDraftError("Enter a valid IPv4, CIDR (e.g. 10.0.0.0/24), or hostname.");
      return;
    }
    if (targets.some((t) => t.value.toLowerCase() === value.toLowerCase())) {
      setDraftError("This target is already on the list.");
      return;
    }
    setTargets((prev) => [
      {
        id: crypto.randomUUID(),
        value,
        type: detectType(value),
        comment: draftComment.trim(),
        addedAt: new Date().toISOString(),
      },
      ...prev,
    ]);
    setDraft("");
    setDraftComment("");
    setDraftError(null);
    setFlash(`Added ${value}`);
    if (!probeHost) setProbeHost(value);
  }

  function removeSelected() {
    if (selected.size === 0) return;
    const count = selected.size;
    const removed = new Set(selectedTargets.map((t) => t.value));
    setTargets((prev) => prev.filter((t) => !selected.has(t.id)));
    setSelected(new Set());
    if (removed.has(probeHost)) {
      setProbeHost("");
    }
    setFlash(`Removed ${count} target${count === 1 ? "" : "s"}`);
  }

  function queueSelected() {
    if (selectedTargets.length === 0) return;
    setFlash(
      `Queued scan for ${selectedTargets.length} host${selectedTargets.length === 1 ? "" : "s"}.`,
    );
  }

  function runProbe() {
    const host = probeHost.trim();
    if (!host) {
      pushToast("error", "Host required", "Select or enter a host / IP to probe.");
      return;
    }
    const selected = Object.entries(moduleState)
      .filter(([, cfg]) => cfg.enabled)
      .map(([id, cfg]) => ({ id, filters: cfg.filters }));
    if (selected.length === 0) {
      pushToast("error", "No modules", "Select at least one discovery module.");
      return;
    }
    const job: ProbeJob = {
      id: crypto.randomUUID(),
      host,
      modules: selected,
      createdAt: new Date().toISOString(),
      status: "queued",
    };
    setJobs((prev) => [job, ...prev].slice(0, 50));
    pushToast(
      "ok",
      "Probe queued",
      `${host} · ${selected.length} module${selected.length === 1 ? "" : "s"} with filters (worker wiring next).`,
    );
  }

  if (bootstrapping) {
    return (
      <div className="login-page" role="status" aria-live="polite">
        <p className="field-help">Loading {APP_NAME} console…</p>
      </div>
    );
  }

  if (enteringDashboard) {
    return <DashboardLoader t={t} />;
  }

  if (!user) {
    return (
      <LoginScreen
        onAuthenticated={completeAuthentication}
        highContrast={highContrast}
        onToggleContrast={toggleHighContrast}
        language={language}
        onLanguageChange={setLanguage}
        t={t}
      />
    );
  }

  return (
    <div className="app">
      <a className="skip-link" href="#main-content">
        {t("Skip to main content")}
      </a>
      <header className="topnav" role="banner">
        <a className="topnav__brand" href="/" aria-label={`${APP_NAME} home`}>
          <Logo />
        </a>
        <span className="topnav__meta" aria-label={t("Signed-in account")}>
          {user.username} · {user.role}
          {user.mfa_enabled ? " · MFA" : ""}
        </span>
        <button
          type="button"
          className="btn btn--normal topnav__contrast"
          aria-pressed={highContrast}
          onClick={toggleHighContrast}
        >
          {highContrast ? t("Standard contrast") : t("High contrast")}
        </button>
        <LanguageSelect
          language={language}
          onChange={setLanguage}
          label={t("Language")}
          className="language-select--topnav"
        />
        <button type="button" className="btn btn--normal topnav__signout" onClick={signOut}>
          {t("Sign out")}
        </button>
      </header>

      <div className="toast-stack" aria-live="polite" aria-relevant="additions">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast ${toast.kind === "error" ? "toast--error" : "toast--ok"}`}
            role={toast.kind === "error" ? "alert" : "status"}
          >
            <div>
              <strong>{toast.title}</strong>
              <p>{toast.message}</p>
            </div>
            <button
              type="button"
              className="toast__close"
              aria-label={t("Dismiss")}
              onClick={() => dismissToast(toast.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>

      <div className="layout">
        <nav className="sidenav" aria-label={t("Primary")}>
          <div className="sidenav__section" id="nav-section-label">
            {t("Attack surface")}
          </div>
          <button
            type="button"
            className={`sidenav__item ${nav === "dashboard" ? "is-active" : ""}`}
            aria-current={nav === "dashboard" ? "page" : undefined}
            onClick={() => setNav("dashboard")}
          >
            {t("Dashboard")}
          </button>
          <button
            type="button"
            className={`sidenav__item ${nav === "targets" ? "is-active" : ""}`}
            aria-current={nav === "targets" ? "page" : undefined}
            onClick={() => setNav("targets")}
          >
            {t("Targets")}
          </button>
          <button
            type="button"
            className={`sidenav__item ${nav === "scans" ? "is-active" : ""}`}
            aria-current={nav === "scans" ? "page" : undefined}
            onClick={() => setNav("scans")}
          >
            {t("Scans")}
          </button>
        </nav>

        <main className="content content--enter" id="main-content" tabIndex={-1} key={nav}>
          {nav === "dashboard" && (
            <>
              <header className="page-header">
                <h1>{t("Dashboard")}</h1>
                <p>
                  {t(
                    "Pick a host and run discovery modules. SurfaceX probes only — no login, brute force, or exploitation.",
                  )}
                </p>
              </header>

              <section className="panel">
                <div className="panel__header">
                  <h2>{t("Target host")}</h2>
                </div>
                <div className="panel__body">
                  <div className="form-row">
                    <label htmlFor="probe-host">{t("Host / IP")}</label>
                    <div>
                      <input
                        id="probe-host"
                        className="input"
                        list="known-hosts"
                        value={probeHost}
                        onChange={(e) => setProbeHost(e.target.value)}
                        placeholder="10.0.0.15 or app.example.lab"
                        autoComplete="off"
                        spellCheck={false}
                      />
                      <datalist id="known-hosts">
                        {targets.map((t) => (
                          <option key={t.id} value={t.value} />
                        ))}
                      </datalist>
                      <p className="field-help">
                        {t("Type an address or choose from saved targets.")}
                      </p>
                    </div>
                  </div>
                </div>
              </section>

              <ModulePanel
                state={moduleState}
                onToggleEnabled={toggleModuleEnabled}
                onToggleExpanded={toggleModuleExpanded}
                onFilterChange={updateModuleFilter}
                onRun={runProbe}
                t={t}
              />

              <section className="panel">
                <div className="panel__header">
                  <h2>{t("Recent probe jobs")}</h2>
                </div>
                <div className="table-wrap">
                  {jobs.length === 0 ? (
                    <div className="empty">
                      <strong>{t("No probe jobs")}</strong>
                      {t("Select modules and run a discovery probe against a host.")}
                    </div>
                  ) : (
                    <table className="hosts">
                      <caption className="sr-only">Recent probe jobs</caption>
                      <thead>
                        <tr>
                          <th scope="col">{t("Host")}</th>
                          <th scope="col">{t("Modules")}</th>
                          <th scope="col">{t("Status")}</th>
                          <th scope="col">{t("Queued")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {jobs.map((job) => (
                          <tr key={job.id}>
                            <td className="mono">{job.host}</td>
                            <td>
                              {job.modules
                                .map((m) => `${m.id} (${summarizeFilters(m.filters)})`)
                                .join("; ")}
                            </td>
                            <td>{job.status}</td>
                            <td>{new Date(job.createdAt).toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </section>
            </>
          )}

          {nav === "targets" && (
            <>
              <header className="page-header">
                <h1>{t("Targets")}</h1>
                <p>
                  {t(
                    "Add IP addresses, CIDR ranges, or hostnames. Select hosts with checkboxes, then queue a scan or remove them from the working set.",
                  )}
                </p>
              </header>

              {flash && (
                <div className="flash flash--ok" role="status">
                  <div>
                    <strong>{t("Success")}</strong>
                    <p>{flash}</p>
                  </div>
                </div>
              )}

              <section className="panel">
                <div className="panel__header">
                  <h2>{t("Add target")}</h2>
                </div>
                <form className="panel__body" onSubmit={onAdd}>
                  <div className="form-row">
                    <label htmlFor="host-input">{t("IP / hostname")}</label>
                    <div>
                      <input
                        id="host-input"
                        className={`input ${draftError ? "is-invalid" : ""}`}
                        value={draft}
                        onChange={(e) => {
                          setDraft(e.target.value);
                          setDraftError(null);
                          setFlash(null);
                        }}
                        placeholder="10.0.0.15 or app.example.lab or 10.0.0.0/24"
                        autoComplete="off"
                        spellCheck={false}
                      />
                      {draftError ? (
                        <p className="field-error">{draftError}</p>
                      ) : (
                        <p className="field-help">
                          {t("One target per submit. CIDR is stored as a range entry.")}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="form-row">
                    <label htmlFor="target-comment">{t("Comment (optional)")}</label>
                    <div>
                      <textarea
                        id="target-comment"
                        className="input target-comment-input"
                        value={draftComment}
                        onChange={(e) => setDraftComment(e.target.value)}
                        placeholder="e.g. Production API, Warsaw office router, owner: Network Team"
                        maxLength={280}
                        rows={3}
                      />
                      <p className="field-help">
                        {t("Optional note describing the host, owner, environment, or purpose.")}{" "}
                        {draftComment.length}/280
                      </p>
                    </div>
                  </div>
                  <div className="actions">
                    <button type="submit" className="btn btn--primary">
                      {t("Add target")}
                    </button>
                  </div>
                </form>
              </section>

              <section className="panel">
                <div className="table-toolbar">
                  <div className="actions">
                    <button
                      type="button"
                      className="btn btn--primary"
                      disabled={selected.size === 0}
                      onClick={queueSelected}
                    >
                      {t("Scan selected")} ({selected.size})
                    </button>
                    <button
                      type="button"
                      className="btn btn--danger"
                      disabled={selected.size === 0}
                      onClick={removeSelected}
                    >
                      {t("Remove")}
                    </button>
                    <button
                      type="button"
                      className="btn btn--normal"
                      disabled={selected.size === 0}
                      onClick={() => setSelected(new Set())}
                    >
                      {t("Clear selection")}
                    </button>
                  </div>
                  <div className="table-toolbar__count">
                    {selected.size} selected · {targets.length} total
                  </div>
                </div>

                <div className="table-wrap">
                  {targets.length === 0 ? (
                    <div className="empty">
                      <strong>{t("No targets")}</strong>
                      {t("Add an IP address or hostname to start building the scan set.")}
                    </div>
                  ) : (
                    <table className="hosts">
                      <caption className="sr-only">Target hosts for discovery</caption>
                      <thead>
                        <tr>
                          <th className="col-check" scope="col">
                            <input
                              type="checkbox"
                              checked={allSelected}
                              ref={(el) => {
                                if (el) el.indeterminate = someSelected;
                              }}
                              onChange={toggleAll}
                              aria-label="Select all hosts"
                            />
                          </th>
                          <th scope="col">{t("Host / IP")}</th>
                          <th scope="col">{t("Comment")}</th>
                          <th scope="col">{t("Type")}</th>
                          <th scope="col">{t("Added")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {targets.map((target) => {
                          const isSelected = selected.has(target.id);
                          return (
                            <tr
                              key={target.id}
                              className={isSelected ? "is-selected" : undefined}
                            >
                              <td className="col-check">
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() => toggleOne(target.id)}
                                  aria-label={`Select ${target.value}`}
                                />
                              </td>
                              <td className="mono">{target.value}</td>
                              <td className="target-comment">
                                {target.comment || <span className="target-comment--empty">—</span>}
                              </td>
                              <td>{target.type}</td>
                              <td>{new Date(target.addedAt).toLocaleString()}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </section>
            </>
          )}

          {nav === "scans" && (
            <>
              <header className="page-header">
                <h1>{t("Scans")}</h1>
                <p>{t("Queued discovery jobs from the dashboard and target list.")}</p>
              </header>
              <div className="panel">
                <div className="table-wrap">
                  {jobs.length === 0 ? (
                    <div className="empty">
                      <strong>{t("No scan runs yet")}</strong>
                      {t("Use Dashboard modules to probe a host.")}
                    </div>
                  ) : (
                    <table className="hosts">
                      <caption className="sr-only">Queued discovery scan runs</caption>
                      <thead>
                        <tr>
                          <th scope="col">{t("Host")}</th>
                          <th scope="col">{t("Modules")}</th>
                          <th scope="col">{t("Status")}</th>
                          <th scope="col">{t("Queued")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {jobs.map((job) => (
                          <tr key={job.id}>
                            <td className="mono">{job.host}</td>
                            <td>
                              {job.modules
                                .map((m) => `${m.id} (${summarizeFilters(m.filters)})`)
                                .join("; ")}
                            </td>
                            <td>{job.status}</td>
                            <td>{new Date(job.createdAt).toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </>
          )}
        </main>
      </div>

      <AppFooter
        highContrast={highContrast}
        onToggleContrast={toggleHighContrast}
        language={language}
        onLanguageChange={setLanguage}
        t={t}
      />
      <div id="a11y-help" className="sr-only" tabIndex={-1}>
        Keyboard: Tab moves focus, Enter activates buttons, Escape dismisses toasts when focused.
        Navigation uses aria-current for the active page. Status messages use live regions.
        Enable High contrast from the header or footer for stronger colors and borders.
      </div>
    </div>
  );
}
