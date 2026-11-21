import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiFetch, AuthUser, ensureCsrf } from "./auth";

type Health = {
  status: string;
  database: boolean;
};

type HostTarget = {
  id: string;
  value: string;
  type: "ip" | "cidr" | "domain";
  addedAt: string;
};

type NavId = "targets" | "scans" | "dashboard";

const STORAGE_KEY = "surfacex.targets.v1";

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

function LoginScreen({
  onAuthenticated,
}: {
  onAuthenticated: (user: AuthUser) => void;
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
      <div className="login-card panel">
        <div className="panel__header">
          <h2>{mfaToken ? "Multi-factor authentication" : "Sign in"}</h2>
        </div>
        <div className="panel__body">
          <div className="login-brand">
            <span className="topnav__mark" aria-hidden="true" />
            <strong>SurfaceX</strong>
          </div>
          <p className="field-help" style={{ marginBottom: 16 }}>
            {mfaToken
              ? "Enter the 6-digit code from your authenticator app."
              : "Use your console username and password."}
          </p>

          {error && (
            <div className="flash flash--error" role="alert">
              <div>
                <strong>Authentication error</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          {!mfaToken ? (
            <form onSubmit={submitPassword}>
              <div className="form-row">
                <label htmlFor="username">Username</label>
                <input
                  id="username"
                  className="input"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  required
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
                />
              </div>
              <div className="actions">
                <button type="submit" className="btn btn--primary" disabled={busy}>
                  {busy ? "Signing in…" : "Sign in"}
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={submitMfa}>
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
                  />
                  <p className="field-help">TOTP from Google Authenticator, 1Password, or Authy.</p>
                </div>
              </div>
              <div className="actions">
                <button type="submit" className="btn btn--primary" disabled={busy || mfaCode.length < 6}>
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
      </div>
    </div>
  );
}

export function App() {
  const [bootstrapping, setBootstrapping] = useState(true);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [nav, setNav] = useState<NavId>("targets");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [targets, setTargets] = useState<HostTarget[]>(() => loadTargets());
  const [draft, setDraft] = useState("");
  const [draftError, setDraftError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch("/api/auth/me/").then(async (r) => r.json()),
      fetch("/api/health/").then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      }),
    ])
      .then(([me, healthData]) => {
        if (me.authenticated) setUser(me.user as AuthUser);
        setHealth(healthData as Health);
        setHealthError(null);
      })
      .catch((err: Error) => setHealthError(err.message))
      .finally(() => setBootstrapping(false));
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(targets));
  }, [targets]);

  const allSelected = targets.length > 0 && selected.size === targets.length;
  const someSelected = selected.size > 0 && selected.size < targets.length;
  const selectedTargets = useMemo(
    () => targets.filter((t) => selected.has(t.id)),
    [targets, selected],
  );

  async function signOut() {
    await apiFetch("/api/auth/logout/", { method: "POST", body: "{}" });
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
  }

  function removeSelected() {
    if (selected.size === 0) return;
    const count = selected.size;
    setTargets((prev) => prev.filter((t) => !selected.has(t.id)));
    setSelected(new Set());
    setFlash(`Removed ${count} target${count === 1 ? "" : "s"}`);
  }

  function queueSelected() {
    if (selectedTargets.length === 0) return;
    setFlash(
      `Queued scan for ${selectedTargets.length} host${selectedTargets.length === 1 ? "" : "s"} (scanner wiring comes next).`,
    );
  }

  if (bootstrapping) {
    return (
      <div className="login-page">
        <p className="field-help">Loading console…</p>
      </div>
    );
  }

  if (!user) {
    return <LoginScreen onAuthenticated={setUser} />;
  }

  return (
    <div className="app">
      <header className="topnav">
        <a className="topnav__brand" href="/">
          <span className="topnav__mark" aria-hidden="true" />
          SurfaceX
        </a>
        <span className="topnav__meta">
          <span
            className={`status-dot ${health?.database ? "is-ok" : healthError ? "is-bad" : ""}`}
            aria-hidden="true"
          />
          {user.username} · {user.role}
          {user.mfa_enabled ? " · MFA on" : ""}
          {" · "}
          {healthError
            ? `API unreachable`
            : health
              ? `API ${health.status}`
              : "Checking API…"}
        </span>
        <button type="button" className="btn btn--normal topnav__signout" onClick={signOut}>
          Sign out
        </button>
      </header>

      <div className="layout">
        <nav className="sidenav" aria-label="Console">
          <div className="sidenav__section">Attack surface</div>
          <button
            type="button"
            className={`sidenav__item ${nav === "targets" ? "is-active" : ""}`}
            onClick={() => setNav("targets")}
          >
            Targets
          </button>
          <button
            type="button"
            className={`sidenav__item ${nav === "scans" ? "is-active" : ""}`}
            onClick={() => setNav("scans")}
          >
            Scans
          </button>
          <button
            type="button"
            className={`sidenav__item ${nav === "dashboard" ? "is-active" : ""}`}
            onClick={() => setNav("dashboard")}
          >
            Dashboard
          </button>
        </nav>

        <main className="content">
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
                      <thead>
                        <tr>
                          <th className="col-check">
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
                          <th>Host / IP</th>
                          <th>Type</th>
                          <th>Added</th>
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
                <p>Scan runs and progress will appear here after scheduler wiring.</p>
              </header>
              <div className="panel">
                <div className="empty">
                  <strong>No scan runs yet</strong>
                  Select targets and use Scan selected to queue work.
                </div>
              </div>
            </>
          )}

          {nav === "dashboard" && (
            <>
              <header className="page-header">
                <h1>Dashboard</h1>
                <p>Change summary across hosts, services, and certificates.</p>
              </header>
              <div className="panel">
                <div className="empty">
                  <strong>Waiting for observations</strong>
                  Dashboard populates after the first completed scan.
                </div>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
