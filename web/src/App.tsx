import { FormEvent, useEffect, useMemo, useState } from "react";

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
  if (!v) return false;
  if (v.includes(" ")) return false;
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

export function App() {
  const [nav, setNav] = useState<NavId>("targets");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [targets, setTargets] = useState<HostTarget[]>(() => loadTargets());
  const [draft, setDraft] = useState("");
  const [draftError, setDraftError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health/")
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data: Health) => {
        setHealth(data);
        setHealthError(null);
      })
      .catch((err: Error) => setHealthError(err.message));
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
    const item: HostTarget = {
      id: crypto.randomUUID(),
      value,
      type: detectType(value),
      addedAt: new Date().toISOString(),
    };
    setTargets((prev) => [item, ...prev]);
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
          {healthError
            ? `API unreachable (${healthError})`
            : health
              ? `API ${health.status} · DB ${health.database ? "up" : "down"}`
              : "Checking API…"}
        </span>
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
                              <td>
                                {new Date(target.addedAt).toLocaleString()}
                              </td>
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
