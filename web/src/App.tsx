import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiFetch, AuthUser, ensureCsrf } from "./auth";
import { AppFooter } from "./AppFooter";
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
    return Array.isArray(parsed) ? parsed : [];
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
}: {
  onAuthenticated: (user: AuthUser) => void;
  highContrast: boolean;
  onToggleContrast: () => void;
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
        setError(data.detail || "Sign-in failed.");
        return;
      }
      if (data.mfa_required) {
        setMfaToken(data.mfa_token);
        return;
      }
      onAuthenticated(data.user as AuthUser);
    } catch {
      setError("Cannot reach authentication API.");
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
        setError(data.detail || "Invalid MFA code.");
        if (data.mfa_token) setMfaToken(data.mfa_token);
        return;
      }
      onAuthenticated(data.user as AuthUser);
    } catch {
      setError("Cannot reach authentication API.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <a className="skip-link" href="#login-form">
        Skip to sign-in form
      </a>
      <main className="login-card panel" id="login-form" aria-labelledby="login-title">
        <div className="panel__header">
          <h2 id="login-title">{mfaToken ? "Multi-factor authentication" : "Sign in"}</h2>
        </div>
        <div className="panel__body">
          <div className="login-brand">
            <Logo />
          </div>
          <p className="field-help" style={{ marginBottom: 16 }} id="login-help">
            {mfaToken
              ? "Enter the 6-digit code from your authenticator app."
              : "Use your console username and password."}
          </p>

          {!mfaToken && (
            <div className="flash flash--error" role="alert">
              <div>
                <strong>Warning: MFA is disabled</strong>
                <p>
                  Multi-factor authentication is currently turned off for this console.
                  Accounts are protected by password only.
                </p>
              </div>
            </div>
          )}

          {error && (
            <div className="flash flash--error" role="alert">
              <div>
                <strong>Authentication error</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          {!mfaToken ? (
            <form onSubmit={submitPassword} aria-describedby="login-help">
              <div className="form-row">
                <label htmlFor="username">Username</label>
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
                <label htmlFor="password">Password</label>
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
                  {busy ? "Signing in…" : "Sign in"}
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={submitMfa} aria-describedby="login-help">
              <div className="form-row">
                <label htmlFor="mfa">MFA code</label>
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
                    TOTP from Google Authenticator, 1Password, or Authy.
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
                  {busy ? "Verifying…" : "Verify"}
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
                  Back
                </button>
              </div>
            </form>
          )}
        </div>
      </main>
      <AppFooter highContrast={highContrast} onToggleContrast={onToggleContrast} />
      <div id="a11y-help" className="sr-only" tabIndex={-1}>
        {APP_NAME} version {APP_VERSION}. Keyboard users can tab through form fields. Screen
        reader users: alerts are announced automatically. Use High contrast for stronger colors.
      </div>
    </div>
  );
}

export function App() {
  const { highContrast, toggleHighContrast } = useHighContrast();
  const [bootstrapping, setBootstrapping] = useState(true);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [nav, setNav] = useState<NavId>("dashboard");
  const [targets, setTargets] = useState<HostTarget[]>(() => loadTargets());
  const [jobs, setJobs] = useState<ProbeJob[]>(() => loadJobs());
  const [draft, setDraft] = useState("");
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
        addedAt: new Date().toISOString(),
      },
      ...prev,
    ]);
    setDraft("");
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

  if (!user) {
    return (
      <LoginScreen
        onAuthenticated={setUser}
        highContrast={highContrast}
        onToggleContrast={toggleHighContrast}
      />
    );
  }

  return (
    <div className="app">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="topnav" role="banner">
        <a className="topnav__brand" href="/" aria-label={`${APP_NAME} home`}>
          <Logo />
        </a>
        <span className="topnav__meta" aria-label="Signed-in account">
          {user.username} · {user.role}
          {user.mfa_enabled ? " · MFA" : ""}
        </span>
        <button
          type="button"
          className="btn btn--normal topnav__contrast"
          aria-pressed={highContrast}
          onClick={toggleHighContrast}
        >
          {highContrast ? "Standard contrast" : "High contrast"}
        </button>
        <button type="button" className="btn btn--normal topnav__signout" onClick={signOut}>
          Sign out
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
              aria-label="Dismiss"
              onClick={() => dismissToast(toast.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>

      <div className="layout">
        <nav className="sidenav" aria-label="Primary">
          <div className="sidenav__section" id="nav-section-label">
            Attack surface
          </div>
          <button
            type="button"
            className={`sidenav__item ${nav === "dashboard" ? "is-active" : ""}`}
            aria-current={nav === "dashboard" ? "page" : undefined}
            onClick={() => setNav("dashboard")}
          >
            Dashboard
          </button>
          <button
            type="button"
            className={`sidenav__item ${nav === "targets" ? "is-active" : ""}`}
            aria-current={nav === "targets" ? "page" : undefined}
            onClick={() => setNav("targets")}
          >
            Targets
          </button>
          <button
            type="button"
            className={`sidenav__item ${nav === "scans" ? "is-active" : ""}`}
            aria-current={nav === "scans" ? "page" : undefined}
            onClick={() => setNav("scans")}
          >
            Scans
          </button>
        </nav>

        <main className="content" id="main-content" tabIndex={-1}>
          {nav === "dashboard" && (
            <>
              <header className="page-header">
                <h1>Dashboard</h1>
                <p>
                  Pick a host and run discovery modules. SurfaceX probes only — no login,
                  brute force, or exploitation.
                </p>
              </header>

              <section className="panel">
                <div className="panel__header">
                  <h2>Target host</h2>
                </div>
                <div className="panel__body">
                  <div className="form-row">
                    <label htmlFor="probe-host">Host / IP</label>
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
                        Type an address or choose from saved targets.
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
              />

              <section className="panel">
                <div className="panel__header">
                  <h2>Recent probe jobs</h2>
                </div>
                <div className="table-wrap">
                  {jobs.length === 0 ? (
                    <div className="empty">
                      <strong>No probe jobs</strong>
                      Select modules and run a discovery probe against a host.
                    </div>
                  ) : (
                    <table className="hosts">
                      <caption className="sr-only">Recent probe jobs</caption>
                      <thead>
                        <tr>
                          <th scope="col">Host</th>
                          <th scope="col">Modules</th>
                          <th scope="col">Status</th>
                          <th scope="col">Queued</th>
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
                <h1>Targets</h1>
                <p>
                  Add IP addresses, CIDR ranges, or hostnames. Select hosts with checkboxes,
                  then queue a scan or remove them from the working set.
                </p>
              </header>

              {flash && (
                <div className="flash flash--ok" role="status">
                  <div>
                    <strong>Success</strong>
                    <p>{flash}</p>
                  </div>
                </div>
              )}

              <section className="panel">
                <div className="panel__header">
                  <h2>Add target</h2>
                </div>
                <form className="panel__body" onSubmit={onAdd}>
                  <div className="form-row">
                    <label htmlFor="host-input">IP / hostname</label>
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
                          One target per submit. CIDR is stored as a range entry.
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="actions">
                    <button type="submit" className="btn btn--primary">
                      Add target
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
                      Scan selected ({selected.size})
                    </button>
                    <button
                      type="button"
                      className="btn btn--danger"
                      disabled={selected.size === 0}
                      onClick={removeSelected}
                    >
                      Remove
                    </button>
                    <button
                      type="button"
                      className="btn btn--normal"
                      disabled={selected.size === 0}
                      onClick={() => setSelected(new Set())}
                    >
                      Clear selection
                    </button>
                  </div>
                  <div className="table-toolbar__count">
                    {selected.size} selected · {targets.length} total
                  </div>
                </div>

                <div className="table-wrap">
                  {targets.length === 0 ? (
                    <div className="empty">
                      <strong>No targets</strong>
                      Add an IP address or hostname to start building the scan set.
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
                          <th scope="col">Host / IP</th>
                          <th scope="col">Type</th>
                          <th scope="col">Added</th>
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
                <h1>Scans</h1>
                <p>Queued discovery jobs from the dashboard and target list.</p>
              </header>
              <div className="panel">
                <div className="table-wrap">
                  {jobs.length === 0 ? (
                    <div className="empty">
                      <strong>No scan runs yet</strong>
                      Use Dashboard modules to probe a host.
                    </div>
                  ) : (
                    <table className="hosts">
                      <caption className="sr-only">Queued discovery scan runs</caption>
                      <thead>
                        <tr>
                          <th scope="col">Host</th>
                          <th scope="col">Modules</th>
                          <th scope="col">Status</th>
                          <th scope="col">Queued</th>
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

      <AppFooter highContrast={highContrast} onToggleContrast={toggleHighContrast} />
      <div id="a11y-help" className="sr-only" tabIndex={-1}>
        Keyboard: Tab moves focus, Enter activates buttons, Escape dismisses toasts when focused.
        Navigation uses aria-current for the active page. Status messages use live regions.
        Enable High contrast from the header or footer for stronger colors and borders.
      </div>
    </div>
  );
}
